"""独立升级器。

职责:
1. 等待主程序退出
2. 解压更新包
3. 备份被覆盖文件
4. 覆盖目标目录
5. 失败回滚
6. 重启主程序
"""

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path


class UpdateError(RuntimeError):
    """升级异常。"""


_LOG_FILE_PATH = None


def _set_log_file(log_path):
    global _LOG_FILE_PATH
    _LOG_FILE_PATH = Path(log_path)


def _ensure_parent(path_obj):
    try:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _default_fallback_log_file():
    return Path(tempfile.gettempdir()) / "cgi430_update_tasks" / "updater_fallback.log"


def _log_line(message):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}\n"

    target = _LOG_FILE_PATH or _default_fallback_log_file()
    _ensure_parent(target)
    try:
        with open(target, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
    except Exception:
        pass


def _process_exists(pid):
    try:
        pid = int(pid)
    except Exception:
        return False

    if pid <= 0:
        return False

    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    # Windows 下不使用 os.kill，避免在打包环境触发异常。
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not handle:
        return False

    try:
        status = kernel32.WaitForSingleObject(handle, 0)
        return status == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def wait_for_process_exit(pid, timeout_seconds=120):
    end_at = time.time() + timeout_seconds
    while time.time() < end_at:
        if not _process_exists(pid):
            return True
        time.sleep(0.25)
    return not _process_exists(pid)


def copy_with_retry(src, target, retries=30, interval=0.5):
    last_exc = None
    for _ in range(retries):
        try:
            shutil.copy2(src, target)
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(interval)
    if last_exc is not None:
        raise UpdateError(f"文件被占用，无法覆盖: {target}") from last_exc


def acquire_lock(lock_path):
    lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
    os.write(lock_fd, str(os.getpid()).encode("utf-8"))
    return lock_fd


def release_lock(lock_fd, lock_path):
    try:
        os.close(lock_fd)
    except Exception:
        pass
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _safe_members(zf):
    members = []
    for member in zf.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise UpdateError(f"更新包包含非法路径: {member.filename}")
        members.append(member)
    return members


def _is_mojibake_name(name):
    # 常见乱码字符集中在 box drawing 区间，例如 ╧╚╒ 等。
    return any(0x2500 <= ord(ch) <= 0x259F for ch in name)


def _decode_zip_name(name):
    if not name or not _is_mojibake_name(name):
        return name

    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name

    for enc in ("gbk", "gb18030", "utf-8"):
        try:
            fixed = raw.decode(enc)
            if fixed:
                return fixed
        except UnicodeDecodeError:
            continue
    return name


def _safe_relative_path(path_text):
    path_text = (path_text or "").replace("\\", "/")
    path_obj = Path(path_text)
    if path_obj.is_absolute() or ".." in path_obj.parts:
        raise UpdateError(f"更新包包含非法路径: {path_text}")
    return path_obj


def extract_zip(zip_path, extract_dir):
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in _safe_members(zf):
            raw_name = member.filename
            decoded_name = _decode_zip_name(raw_name)
            rel_path = _safe_relative_path(decoded_name)
            target_path = extract_dir / rel_path

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def iter_files(root_dir):
    for p in root_dir.rglob("*"):
        if p.is_file():
            yield p


def backup_targets(extract_dir, app_dir, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    for src in iter_files(extract_dir):
        rel = src.relative_to(extract_dir)
        target = app_dir / rel
        if target.exists() and target.is_file():
            backup_file = backup_dir / rel
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            copy_with_retry(target, backup_file)


def apply_update(extract_dir, app_dir):
    for src in iter_files(extract_dir):
        rel = src.relative_to(extract_dir)
        target = app_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_with_retry(src, target)


def rollback_from_backup(backup_dir, app_dir):
    if not backup_dir.exists():
        return
    for bak in iter_files(backup_dir):
        rel = bak.relative_to(backup_dir)
        target = app_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_with_retry(bak, target)


def main():
    parser = argparse.ArgumentParser(description="CGI430 updater")
    parser.add_argument("--task-file", required=True, help="升级任务 JSON 文件路径")
    args = parser.parse_args()

    _set_log_file(_default_fallback_log_file())
    _log_line("updater started")

    task_file = Path(args.task_file)
    if not task_file.exists():
        _log_line(f"task file missing: {task_file}")
        raise UpdateError(f"任务文件不存在: {task_file}")

    task = json.loads(task_file.read_text(encoding="utf-8"))
    app_dir = Path(task["app_dir"]).resolve()
    zip_path = Path(task["zip_path"]).resolve()
    pid = int(task["pid"])
    restart_cmd = task.get("restart_cmd") or []
    updater_exec_path = str(task.get("updater_exec_path", "")).strip()

    # run_log_name = f"updater_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.log"
    # _set_log_file(app_dir / "update_logs" / run_log_name)
    _log_line(f"task file: {task_file}")
    _log_line(f"app dir: {app_dir}")
    _log_line(f"zip path: {zip_path}")
    _log_line(f"target pid: {pid}")
    if updater_exec_path:
        _log_line(f"updater exec path: {updater_exec_path}")

    lock_file = app_dir / task.get("lock_file", "update.lock")
    marker_file = app_dir / task.get("unfinished_marker", "unfinished_update.json")
    backup_root = app_dir / task.get("backup_root", "backup")
    cleanup_backup_on_success = bool(task.get("cleanup_backup_on_success", False))

    if not zip_path.exists():
        _log_line("zip package not found")
        raise UpdateError(f"升级包不存在: {zip_path}")

    _log_line("waiting main process exit")
    if not wait_for_process_exit(pid, timeout_seconds=180):
        _log_line("wait main process timeout")
        raise UpdateError(f"等待主程序退出超时，请先关闭主程序后重试。pid={pid}")

    _log_line("acquiring update lock")
    lock_fd = acquire_lock(lock_file)

    backup_dir = backup_root / f"backup_{time.strftime('%Y%m%d_%H%M%S')}"
    work_dir = app_dir / ".update_work"
    extract_dir = work_dir / "extracted"

    try:
        _log_line(f"write unfinished marker: {marker_file}")
        marker_payload = {
            "app_id": task.get("app_id", ""),
            "target_version": task.get("target_version", ""),
            "zip_path": str(zip_path),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        marker_file.write_text(json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        if work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        _log_line(f"work dir ready: {work_dir}")

        _log_line("extract zip")
        extract_zip(zip_path, extract_dir)
        _log_line("backup targets")
        backup_targets(extract_dir, app_dir, backup_dir)
        _log_line("apply update")
        apply_update(extract_dir, app_dir)

        marker_file.unlink(missing_ok=True)
        if cleanup_backup_on_success and backup_root.exists():
            shutil.rmtree(backup_root, ignore_errors=True)
            _log_line(f"cleanup backup root: {backup_root}")
        _log_line("update applied successfully")
    except Exception as exc:
        _log_line(f"update failed, begin rollback: {exc}")
        rollback_from_backup(backup_dir, app_dir)
        _log_line("rollback finished")
        raise
    finally:
        _log_line("cleanup temporary files and lock")
        shutil.rmtree(work_dir, ignore_errors=True)
        release_lock(lock_fd, lock_file)
        _log_line("cleanup zip file if exists")
        if zip_path.exists():
            zip_path.unlink()
            shutil.rmtree(zip_path, ignore_errors=True)

    if restart_cmd:
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        _log_line(f"restart app: {restart_cmd}")
        subprocess.Popen(restart_cmd, cwd=str(app_dir), close_fds=True, creationflags=creation_flags)

    _log_line("updater finished")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 独立升级器默认无 UI，失败信息写到 stderr。
        _log_line(f"fatal error: {exc}")
        _log_line(traceback.format_exc().rstrip())
        print(f"[updater] {exc}", file=sys.stderr)
        sys.exit(1)
