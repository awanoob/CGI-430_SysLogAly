"""主窗口"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

from PyQt6.QtCore import QPoint, QSettings, QTimer, QUrl, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QDesktopServices, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QLineEdit,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QStyledItemDelegate,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_ID,
    APP_VERSION,
    LOG_COLORS,
    MAX_FILTER_ITEMS_OTHER,
    MAX_FILTER_ITEMS_TIME,
    TABLE_HEADERS,
    UPDATE_AUTO_CHECK_ON_STARTUP,
    UPDATE_CHANNEL,
    UPDATE_REQUEST_TIMEOUT,
    UPDATE_SERVER_BASE_URL,
    UPDATER_EXE_NAME,
)
from models import LogDatabase
from utils import extract_version_info, parse_log_line, split_boot_sessions
from views.dialogs import (
    FilterDialog,
    FilterHintDialog,
    FindDialog,
    InterfaceSettingsDialog,
    NotificationSettingsDialog,
    QuickAddRuleDialog,
    RuleEditorDialog,
    UpdateSettingsDialog,
)


class LogTreeItemDelegate(QStyledItemDelegate):
    """为树表格绘制列边框，并增加行高。"""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        painter.save()
        right_pen = QPen(QColor("#e0e0e0"))
        bottom_pen = QPen(QColor("#f0f0f0"))

        painter.setPen(right_pen)
        painter.drawLine(option.rect.topRight(), option.rect.bottomRight())

        painter.setPen(bottom_pen)
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())
        painter.restore()

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(size.height() + 8)
        return size

    def createEditor(self, parent, option, index):
        """创建只读文本编辑器，用于左键拖选文本并 Ctrl+C 复制。"""
        editor = QLineEdit(parent)
        editor.setReadOnly(True)
        editor.setFrame(False)
        editor.setCursorPosition(0)
        return editor

    def setEditorData(self, editor, index):
        editor.setText(index.data(Qt.ItemDataRole.DisplayRole) or "")

    def setModelData(self, editor, model, index):
        # 只读编辑器，不回写，避免修改数据
        return


class LogViewer(QMainWindow):
    """日志查看器主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("系统日志分析工具")
        self.settings = QSettings("CGI430", "SysLogAly")

        self.db = LogDatabase()
        self.db.connect()
        self.db.initialize()

        self.last_search_pos = -1
        self.current_filters = {
            "time": "",
            "level": "",
            "module": "",
            "function": "",
            "content": "",
        }
        self.sessions = []
        self.current_sticky_session_item = None
        self.current_sticky_text = ""
        self.suspend_sticky_updates = False
        self.rule_editor_dialog = None
        self.quick_add_dialog = None
        self.current_file_path = ""

        self.guide_prompts_enabled = self.settings.value("guide_prompts_enabled", True, type=bool)
        self.filter_hint_suppressed = self.settings.value("filter_hint_suppressed", False, type=bool)
        self.tree_bg_color = self.settings.value("tree_bg_color", "#ffffff", type=str)
        self.update_server_url = self.settings.value(
            "update_server_url",
            UPDATE_SERVER_BASE_URL,
            type=str,
        )
        self.update_channel = self.settings.value("update_channel", UPDATE_CHANNEL, type=str)
        self.update_timeout_seconds = self.settings.value(
            "update_timeout_seconds",
            UPDATE_REQUEST_TIMEOUT,
            type=int,
        )
        self.update_auto_check_on_startup = self.settings.value(
            "update_auto_check_on_startup",
            UPDATE_AUTO_CHECK_ON_STARTUP,
            type=bool,
        )
        recent = self.settings.value("recent_files", [])
        if isinstance(recent, str):
            self.recent_files = [recent] if recent else []
        else:
            self.recent_files = list(recent) if recent else []
        self.recent_files = [p for p in self.recent_files if p][:5]

        self.setAcceptDrops(True)
        self.init_ui()
        self.check_unfinished_update_marker()

    def init_ui(self):
        self.create_menu()

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(TABLE_HEADERS))
        self.tree.setHeaderLabels(TABLE_HEADERS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked | QAbstractItemView.EditTrigger.DoubleClicked)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.tree.setWordWrap(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setItemDelegate(LogTreeItemDelegate(self.tree))
        self.apply_tree_background_color(self.tree_bg_color, persist=False)
        self.tree.itemClicked.connect(self.show_log_detail)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        self.tree.header().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.header().customContextMenuRequested.connect(self.header_context_menu)
        self.sticky_tree = QTreeWidget()
        self.sticky_tree.setColumnCount(len(TABLE_HEADERS))
        self.sticky_tree.setHeaderHidden(True)
        self.sticky_tree.setRootIsDecorated(False)
        self.sticky_tree.setIndentation(0)
        self.sticky_tree.setItemDelegate(LogTreeItemDelegate(self.sticky_tree))
        self.sticky_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sticky_tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sticky_tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sticky_tree.setStyleSheet(
            "QTreeWidget { border-left: 1px solid #bdbdbd; border-right: 1px solid #bdbdbd; border-top: 1px solid #bdbdbd; }"
        )
        self.sticky_tree.itemClicked.connect(self.jump_to_sticky_session)
        self.sticky_tree.hide()

        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        center_layout.addWidget(self.sticky_tree)
        center_layout.addWidget(self.tree)
        self.setCentralWidget(center_widget)

        self.tree.verticalScrollBar().valueChanged.connect(self.update_sticky_session_label)
        self.tree.itemExpanded.connect(lambda _item: self.update_sticky_session_label())
        self.tree.itemCollapsed.connect(lambda _item: self.update_sticky_session_label())
        self.tree.header().sectionResized.connect(self.sync_sticky_columns)

        self.create_dock_widgets()
        self.create_toolbar()
        self.create_status_bar()

        if self.update_auto_check_on_startup:
            QTimer.singleShot(1200, self.check_upgrade_silent)

    def create_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        open_action = QAction("打开文件", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        self.open_folder_action = QAction("打开文件所在文件夹", self)
        self.open_folder_action.triggered.connect(self.open_current_file_folder)
        self.open_folder_action.setEnabled(False)
        file_menu.addAction(self.open_folder_action)

        self.recent_menu = file_menu.addMenu("最近文件")
        self.recent_file_actions = []
        for idx in range(5):
            action = QAction("", self)
            action.setVisible(False)
            action.triggered.connect(lambda _checked=False, i=idx: self.open_recent_file(i))
            self.recent_menu.addAction(action)
            self.recent_file_actions.append(action)
        self.update_recent_files_menu()

        search_menu = menubar.addMenu("搜索")
        find_action = QAction("查找", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.show_find_dialog)
        search_menu.addAction(find_action)

        copy_action = QAction("复制选中内容", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_selected_row)
        search_menu.addAction(copy_action)

        filter_action = QAction("筛选", self)
        filter_action.setShortcut("Ctrl+Shift+F")
        filter_action.triggered.connect(self.show_filter_dialog)
        search_menu.addAction(filter_action)

        jump_date_action = QAction("按日期跳转", self)
        jump_date_action.setShortcut("Ctrl+J")
        jump_date_action.triggered.connect(self.jump_to_date)
        search_menu.addAction(jump_date_action)

        advanced_menu = menubar.addMenu("高级")
        self.edit_rules_action = QAction("日志解释配置", self)
        self.edit_rules_action.triggered.connect(self.show_rule_editor)
        advanced_menu.addAction(self.edit_rules_action)

        settings_menu = menubar.addMenu("设置")
        notification_action = QAction("通知设置", self)
        notification_action.triggered.connect(self.show_notification_settings)
        settings_menu.addAction(notification_action)

        interface_action = QAction("界面设置", self)
        interface_action.triggered.connect(self.show_interface_settings)
        settings_menu.addAction(interface_action)

        update_settings_action = QAction("升级设置", self)
        update_settings_action.triggered.connect(self.show_update_settings)
        settings_menu.addAction(update_settings_action)

        view_menu = menubar.addMenu("视图")
        expand_all_action = QAction("展开全部上电日志", self)
        expand_all_action.triggered.connect(self.expand_all_sessions)
        view_menu.addAction(expand_all_action)

        collapse_all_action = QAction("折叠全部上电日志", self)
        collapse_all_action.triggered.connect(self.collapse_all_sessions)
        view_menu.addAction(collapse_all_action)

        expand_by_date_action = QAction("按日期展开", self)
        expand_by_date_action.triggered.connect(lambda: self.set_date_expanded(True))
        view_menu.addAction(expand_by_date_action)

        collapse_by_date_action = QAction("按日期折叠", self)
        collapse_by_date_action.triggered.connect(lambda: self.set_date_expanded(False))
        view_menu.addAction(collapse_by_date_action)

        self.toggle_detail_action = QAction("显示日志详情窗口", self)
        self.toggle_detail_action.setCheckable(True)
        self.toggle_detail_action.setChecked(True)
        self.toggle_detail_action.toggled.connect(self.toggle_log_detail_dock)
        view_menu.addAction(self.toggle_detail_action)

        help_menu = menubar.addMenu("？")

        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about_info)
        help_menu.addAction(about_action)

        check_upgrade_action = QAction("检查升级", self)
        check_upgrade_action.triggered.connect(self.check_upgrade)
        help_menu.addAction(check_upgrade_action)

        help_action = QAction("帮助", self)
        help_action.triggered.connect(self.open_help_page)
        help_menu.addAction(help_action)

        self.update_action_states()

    def _build_tree_stylesheet(self, bg_color):
        return (
            f"QTreeWidget {{ background-color: {bg_color}; }}"
            "QHeaderView::section {"
            " border-right: 1px solid #bdbdbd;"
            " border-bottom: 1px solid #bdbdbd;"
            " padding: 4px 6px;"
            "}"
        )

    def apply_tree_background_color(self, color_hex, persist=True):
        """应用日志背景颜色。"""
        if not color_hex:
            color_hex = "#ffffff"
        self.tree_bg_color = color_hex
        if hasattr(self, "tree"):
            self.tree.setStyleSheet(self._build_tree_stylesheet(self.tree_bg_color))
        if persist:
            self.settings.setValue("tree_bg_color", self.tree_bg_color)

    def check_unfinished_update_marker(self):
        """检测未完成升级标记，提示用户进行排障。"""
        marker = self._runtime_base_dir() / "unfinished_update.json"
        lock_file = self._runtime_base_dir() / "update.lock"
        if not marker.exists():
            return

        marker_text = ""
        try:
            marker_text = marker.read_text(encoding="utf-8").strip()
        except Exception:
            marker_text = "(无法读取标记详情)"

        lock_tip = "检测到 update.lock 仍存在。" if lock_file.exists() else "未检测到 update.lock。"
        QMessageBox.warning(
            self,
            "升级恢复提示",
            "检测到上次升级可能未完成。\n"
            f"标记文件: {marker}\n"
            f"{lock_tip}\n\n"
            "如程序运行异常，请回滚 backup 目录后重试升级。\n\n"
            f"标记内容:\n{marker_text}",
        )

    def show_about_info(self):
        """关于信息入口。"""
        QMessageBox.information(
            self,
            "关于",
            f"系统日志分析工具\n\n应用标识: {APP_ID}\n当前版本: {APP_VERSION}",
        )

    @staticmethod
    def _normalize_version(version):
        nums = []
        for token in re.split(r"[^0-9]+", str(version or "")):
            if token:
                nums.append(int(token))
        return tuple(nums) if nums else (0,)

    def _is_newer_version(self, remote_version):
        return self._normalize_version(remote_version) > self._normalize_version(APP_VERSION)

    @staticmethod
    def _parse_sha256_text(raw_text):
        match = re.search(r"([a-fA-F0-9]{64})", raw_text or "")
        return match.group(1).lower() if match else ""

    def _fetch_json(self, url):
        with urlopen(url, timeout=max(3, int(self.update_timeout_seconds))) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    def _fetch_text(self, url):
        with urlopen(url, timeout=max(3, int(self.update_timeout_seconds))) as response:
            return response.read().decode("utf-8", errors="replace")

    def _default_manifest_url(self):
        base = (self.update_server_url or UPDATE_SERVER_BASE_URL).rstrip("/") + "/"
        channel = (self.update_channel or UPDATE_CHANNEL).strip() or UPDATE_CHANNEL
        return urljoin(base, f"{APP_ID}/{channel}/latest.json")

    @staticmethod
    def _runtime_base_dir():
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def _project_root_dir():
        return Path(__file__).resolve().parents[1]

    def _build_restart_command(self):
        if getattr(sys, "frozen", False):
            return [sys.executable]
        return [sys.executable, str(self._project_root_dir() / "main.py")]

    def _resolve_updater_command(self):
        runtime_dir = self._runtime_base_dir()
        updater_exe = runtime_dir / UPDATER_EXE_NAME
        if updater_exe.exists():
            return [str(updater_exe)], str(updater_exe)

        updater_script = self._project_root_dir() / "updater.py"
        if updater_script.exists():
            return [sys.executable, str(updater_script)], str(updater_script)

        return None, ""

    def _prepare_temp_updater_command(self, cmd_prefix):
        """将升级器复制到临时目录后再运行，避免占用应用目录文件。"""
        runtime_dir = Path(tempfile.gettempdir()) / "cgi430_updater_runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        stamp = f"{os.getpid()}_{int(time.time())}"

        if len(cmd_prefix) == 1:
            source = Path(cmd_prefix[0])
            target = runtime_dir / f"{source.stem}_{stamp}{source.suffix or '.exe'}"
            shutil.copy2(source, target)
            return [str(target)], str(target)

        if len(cmd_prefix) == 2:
            source = Path(cmd_prefix[1])
            target = runtime_dir / f"{source.stem}_{stamp}{source.suffix or '.py'}"
            shutil.copy2(source, target)
            return [cmd_prefix[0], str(target)], str(target)

        raise RuntimeError("升级器命令格式不支持")

    def _launch_external_updater(self, zip_path, remote_version):
        cmd_prefix, updater_path = self._resolve_updater_command()
        if not cmd_prefix:
            raise RuntimeError("未找到独立升级器，请确认同目录存在 updater.exe 或工程根目录存在 updater.py")

        try:
            launch_prefix, runtime_updater_path = self._prepare_temp_updater_command(cmd_prefix)
        except Exception as e:
            raise RuntimeError(f"复制临时升级器失败:\n{str(e)}") from e

        task_dir = Path(tempfile.gettempdir()) / "cgi430_update_tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / f"update_task_{os.getpid()}_{int(time.time())}.json"

        payload = {
            "app_id": APP_ID,
            "pid": os.getpid(),
            "target_version": remote_version,
            "app_dir": str(self._runtime_base_dir()),
            "zip_path": str(Path(zip_path).resolve()),
            "restart_cmd": self._build_restart_command(),
            "lock_file": "update.lock",
            "unfinished_marker": "unfinished_update.json",
            "backup_root": "back_up",
            "cleanup_backup_on_success": True,
            "updater_exec_path": runtime_updater_path,
        }
        task_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        launch_cmd = launch_prefix + ["--task-file", str(task_file)]
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(launch_cmd, close_fds=True, creationflags=creation_flags)
        except Exception as e:
            try:
                task_file.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(
                "启动临时升级器失败，请检查杀软拦截或目录权限。\n"
                f"原升级器: {updater_path}\n"
                f"临时升级器: {runtime_updater_path}\n"
                f"错误: {str(e)}"
            ) from e

        return runtime_updater_path

    def _download_with_progress(self, src_url, dst_path):
        with urlopen(src_url, timeout=max(3, int(self.update_timeout_seconds))) as response:
            total = int(response.headers.get("Content-Length", "0") or "0")
            progress = QProgressDialog("正在下载升级包...", "取消", 0, 100, self)
            progress.setWindowTitle("升级下载")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.show()

            received = 0
            cancelled = False
            try:
                with open(dst_path, "wb") as out:
                    while True:
                        chunk = response.read(1024 * 128)
                        if not chunk:
                            break
                        out.write(chunk)
                        received += len(chunk)
                        if total > 0:
                            percent = min(100, int(received * 100 / total))
                            progress.setValue(percent)
                            progress.setLabelText(f"正在下载升级包... {percent}%")
                        else:
                            progress.setLabelText(f"正在下载升级包... 已接收 {received} 字节")
                        QApplication.processEvents()
                        if progress.wasCanceled():
                            cancelled = True
                            break
                if total > 0:
                    progress.setValue(100)
                QApplication.processEvents()
            finally:
                progress.close()

        if cancelled:
            try:
                Path(dst_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError("用户取消下载")

    @staticmethod
    def _sha256_file(file_path):
        digest = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    def check_upgrade_silent(self):
        """启动时静默检查升级（仅在发现新版本时提示）。"""
        self.check_upgrade(interactive=False)

    def check_upgrade(self, interactive=True):
        """检查升级并支持下载升级包。"""
        manifest_url = self._default_manifest_url()

        try:
            manifest = self._fetch_json(manifest_url)
        except URLError as e:
            if interactive:
                QMessageBox.warning(self, "检查升级", f"无法连接升级服务器:\n{str(e)}")
            return
        except json.JSONDecodeError as e:
            if interactive:
                QMessageBox.warning(self, "检查升级", f"升级清单格式错误:\n{str(e)}")
            return
        except Exception as e:
            if interactive:
                QMessageBox.warning(self, "检查升级", f"读取升级清单失败:\n{str(e)}")
            return

        remote_version = str(manifest.get("version", "")).strip()
        if not remote_version:
            if interactive:
                QMessageBox.warning(self, "检查升级", "升级清单缺少 version 字段")
            return

        force_upgrade = bool(manifest.get("force", False))
        is_newer = self._is_newer_version(remote_version)
        if not is_newer and not force_upgrade:
            if interactive:
                QMessageBox.information(
                    self,
                    "检查升级",
                    f"当前已是最新版本\n\n当前版本: {APP_VERSION}\n服务器版本: {remote_version}",
                )
            return

        package_url = str(manifest.get("url", "")).strip()
        if not package_url:
            if interactive:
                QMessageBox.warning(self, "检查升级", "升级清单缺少 url 字段")
            return

        base_url = package_url.rsplit("/", 1)[0] + "/"
        changelog_url = str(manifest.get("changelog_url", "")).strip() or urljoin(base_url, "changelog.txt")

        expected_sha256 = str(manifest.get("sha256", "")).strip().lower()
        sha256_text_url = str(manifest.get("sha256_url", "")).strip() or urljoin(base_url, "SHA256.txt")
        if not expected_sha256:
            try:
                expected_sha256 = self._parse_sha256_text(self._fetch_text(sha256_text_url))
            except Exception:
                expected_sha256 = ""

        changelog_text = ""
        try:
            changelog_text = self._fetch_text(changelog_url).strip()
        except Exception:
            changelog_text = "(未获取到 changelog.txt，可继续下载升级包)"

        detail_lines = [
            f"当前版本: {APP_VERSION}",
            f"服务器版本: {remote_version}",
            f"下载地址: {package_url}",
        ]
        if expected_sha256:
            detail_lines.append(f"SHA256: {expected_sha256}")
        if force_upgrade:
            detail_lines.append("提示: 该版本为强制升级")
        detail_lines.append("\n更新日志:\n" + changelog_text)

        ask_text = "检测到可用更新，是否下载升级包？"
        if not interactive:
            ask_text = f"检测到新版本 {remote_version}，是否立即下载升级包？"

        reply = QMessageBox.question(
            self,
            "检查升级",
            ask_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            if interactive:
                QMessageBox.information(self, "检查升级", "已取消下载\n\n" + "\n".join(detail_lines))
            return

        save_path = str(self._runtime_base_dir() / "app.zip")

        try:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).unlink(missing_ok=True)
            self._download_with_progress(package_url, save_path)
            if expected_sha256:
                actual_sha256 = self._sha256_file(save_path)
                if actual_sha256 != expected_sha256:
                    Path(save_path).unlink(missing_ok=True)
                    QMessageBox.critical(
                        self,
                        "检查升级",
                        "升级包校验失败，文件已删除。\n"
                        f"期望: {expected_sha256}\n实际: {actual_sha256}",
                    )
                    return

            verify_text = "SHA256 校验通过。\n" if expected_sha256 else "未获取 SHA256，已跳过校验。\n"
            done_message = (
                "升级包下载完成。\n\n"
                f"保存路径: {save_path}\n"
                f"{verify_text}"
                "\n是否立即开始升级？（将启动独立升级器并关闭当前程序）"
            )
            do_upgrade = QMessageBox.question(
                self,
                "检查升级",
                done_message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if do_upgrade == QMessageBox.StandardButton.Yes:
                updater_path = self._launch_external_updater(save_path, remote_version)
                QMessageBox.information(
                    self,
                    "开始升级",
                    "已启动独立升级器，将退出当前程序。\n\n"
                    f"升级器: {updater_path}\n"
                    "关闭后将自动执行文件替换并重启主程序。",
                )
                self.close()
                return

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(save_path).parent)))
        except Exception as e:
            QMessageBox.critical(self, "检查升级", f"升级流程失败:\n{str(e)}")

    def build_help_html(self):
        """构建帮助文档 HTML 内容。"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>系统日志分析工具 - 使用说明</title>
    <style>
        body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 24px auto; max-width: 980px; line-height: 1.7; color: #1f2937; padding: 0 16px; }
        h1, h2 { color: #0f172a; }
        .card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; margin: 12px 0; }
        code { background: #eef2ff; padding: 2px 6px; border-radius: 6px; }
        ul { margin-top: 6px; }
    </style>
</head>
<body>
    <h1>系统日志分析工具 使用说明</h1>

    <div class="card">
        <h2>1. 快速开始</h2>
        <ul>
            <li>点击菜单 <code>文件 -> 打开文件</code>，或直接拖拽日志文件到主窗口。</li>
            <li>日志加载后按“上电分组”显示，可展开查看详细日志。</li>
            <li>点击任一日志行，右侧“日志详情”会展示字段和解释信息。</li>
        </ul>
    </div>

    <div class="card">
        <h2>2. 搜索相关功能</h2>
        <ul>
            <li><code>搜索 -> 查找</code>：按关键字在可见日志中逐条向后查找。</li>
            <li><code>搜索 -> 筛选</code>：按等级/模块/函数/内容过滤日志。</li>
            <li><code>搜索 -> 按日期跳转</code>：输入日期快速定位日志。</li>
            <li><code>搜索 -> 复制选中内容</code>：复制当前选中的日志行。</li>
        </ul>
    </div>

    <div class="card">
        <h2>3. 日志解释配置</h2>
        <ul>
            <li>通过 <code>高级 -> 日志解释配置</code> 管理解释规则。</li>
            <li>支持静态解释文本与“日志解析代码”两种方式。</li>
            <li>右键日志行可打开“新增/修改日志解释”，并支持脚本测试。</li>
        </ul>
    </div>

    <div class="card">
        <h2>4. 日志解析代码脚本规范</h2>
        <ul>
            <li>脚本必须定义函数：<code>explain(context)</code>。</li>
            <li><code>context</code> 包含字段：<code>level/module/function/line_no/content/default_remark</code>。</li>
            <li>脚本应返回字符串；匹配失败建议返回 <code>context['default_remark']</code>。</li>
            <li>可使用 <code>re</code> 模块与已开放的安全内建函数（如 <code>map/range/list/sum</code> 等）。</li>
        </ul>
    </div>

    <div class="card">
        <h2>5. 其他说明</h2>
        <ul>
            <li>“检查升级”会读取内网升级清单、下载并校验更新包，然后启动独立升级器执行替换与重启。</li>
            <li>可通过 <code>设置 -> 升级设置</code> 配置服务器地址、通道、超时和启动静默检查。</li>
            <li>帮助页由程序运行时生成临时 HTML 文件并在浏览器打开。</li>
        </ul>
    </div>
</body>
</html>
"""

    def open_help_page(self):
        """生成临时 HTML 帮助文档并在浏览器打开。"""
        try:
            html = self.build_help_html()
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix="_cgi430_help.html",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(html)
                temp_path = f.name

            webbrowser.open(Path(temp_path).as_uri())
        except Exception as e:
            QMessageBox.critical(self, "帮助", f"打开帮助文档失败:\n{str(e)}")

    def is_rule_editor_open(self):
        return self.rule_editor_dialog is not None and self.rule_editor_dialog.isVisible()

    def is_quick_add_open(self):
        return self.quick_add_dialog is not None and self.quick_add_dialog.isVisible()

    def update_action_states(self):
        if hasattr(self, "edit_rules_action"):
            self.edit_rules_action.setEnabled(not self.is_quick_add_open())

    def update_recent_files_menu(self):
        """刷新最近文件菜单。"""
        for idx, action in enumerate(self.recent_file_actions):
            if idx < len(self.recent_files):
                path = self.recent_files[idx]
                action.setText(f"{idx + 1}. {path}")
                action.setVisible(True)
            else:
                action.setVisible(False)

    def add_recent_file(self, file_path):
        """记录最近文件。"""
        if not file_path:
            return
        path = str(Path(file_path))
        self.recent_files = [p for p in self.recent_files if p != path]
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:5]
        self.settings.setValue("recent_files", self.recent_files)
        self.update_recent_files_menu()

    def open_recent_file(self, index):
        """打开最近文件。"""
        if index >= len(self.recent_files):
            return
        path = self.recent_files[index]
        if not Path(path).exists():
            QMessageBox.warning(self, "最近文件", f"文件不存在:\n{path}")
            self.recent_files.pop(index)
            self.settings.setValue("recent_files", self.recent_files)
            self.update_recent_files_menu()
            return
        self._load_file_path(path)

    def open_current_file_folder(self):
        """打开当前日志文件所在目录。"""
        if not self.current_file_path:
            QMessageBox.information(self, "打开目录", "当前没有已打开的日志文件")
            return
        folder = str(Path(self.current_file_path).parent)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def show_notification_settings(self):
        """打开通知设置。"""
        dialog = NotificationSettingsDialog(self.guide_prompts_enabled, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()
        self.guide_prompts_enabled = settings["guide_enabled"]
        self.settings.setValue("guide_prompts_enabled", self.guide_prompts_enabled)

    def show_interface_settings(self):
        """打开界面设置。"""
        dialog = InterfaceSettingsDialog(self.tree_bg_color, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.get_settings()
        self.apply_tree_background_color(settings["tree_bg_color"], persist=True)

    def show_update_settings(self):
        """打开升级设置。"""
        dialog = UpdateSettingsDialog(
            server_url=self.update_server_url,
            channel=self.update_channel,
            timeout_seconds=self.update_timeout_seconds,
            auto_check_on_startup=self.update_auto_check_on_startup,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        settings = dialog.get_settings()
        if not settings["server_url"]:
            QMessageBox.warning(self, "升级设置", "升级服务器地址不能为空")
            return

        self.update_server_url = settings["server_url"].rstrip("/")
        self.update_channel = settings["channel"]
        self.update_timeout_seconds = settings["timeout_seconds"]
        self.update_auto_check_on_startup = settings["auto_check_on_startup"]

        self.settings.setValue("update_server_url", self.update_server_url)
        self.settings.setValue("update_channel", self.update_channel)
        self.settings.setValue("update_timeout_seconds", self.update_timeout_seconds)
        self.settings.setValue("update_auto_check_on_startup", self.update_auto_check_on_startup)

        QMessageBox.information(
            self,
            "升级设置",
            "升级设置已保存。\n"
            f"服务器: {self.update_server_url}\n"
            f"通道: {self.update_channel}\n"
            f"超时: {self.update_timeout_seconds}s\n"
            f"启动自动检查: {'开启' if self.update_auto_check_on_startup else '关闭'}",
        )

    def create_dock_widgets(self):
        self.log_detail = QTextEdit()
        self.log_detail.setReadOnly(True)
        self.detail_dock = QDockWidget("日志详情")
        self.detail_dock.setWidget(self.log_detail)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.detail_dock)
        self.detail_dock.visibilityChanged.connect(self.on_detail_dock_visibility_changed)

    def on_detail_dock_visibility_changed(self, visible):
        if hasattr(self, "toggle_detail_action"):
            self.toggle_detail_action.blockSignals(True)
            self.toggle_detail_action.setChecked(bool(visible))
            self.toggle_detail_action.blockSignals(False)

    def create_toolbar(self):
        toolbar = QToolBar("主工具栏", self)
        self.addToolBar(toolbar)

        expand_action = QAction("展开全部", self)
        expand_action.triggered.connect(self.expand_all_sessions)
        toolbar.addAction(expand_action)

        collapse_action = QAction("折叠全部", self)
        collapse_action.triggered.connect(self.collapse_all_sessions)
        toolbar.addAction(collapse_action)

        jump_date_action = QAction("按日期跳转", self)
        jump_date_action.triggered.connect(self.jump_to_date)
        toolbar.addAction(jump_date_action)

    def create_status_bar(self):
        self.status_label = QLabel(
            "SN: - | PN: - | 固件版本: - | 板卡固件版本: -"
        )
        self.status_label.setObjectName("deviceStatusLabel")
        self.status_label.setStyleSheet("QLabel#deviceStatusLabel { padding: 0 8px; }")
        self.statusBar().addPermanentWidget(self.status_label)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择日志文件",
            "",
            "日志文件 (*.log *.txt);;所有文件 (*.*)",
        )
        if file_path:
            self._load_file_path(file_path)

    def _load_file_path(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件:\n{str(e)}")
            return

        self.load_logs(lines)
        self.current_file_path = file_path
        self.add_recent_file(file_path)
        self.open_folder_action.setEnabled(True)
        QMessageBox.information(self, "成功", f"成功加载 {len(lines)} 行日志")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path:
                self._load_file_path(file_path)

    def load_logs(self, lines):
        parsed_logs = []
        current_log = None
        total_lines = len(lines)

        progress_dialog = QProgressDialog("正在解析日志...", None, 0, 100, self)
        progress_dialog.setWindowTitle("解析进度")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.setCancelButton(None)
        progress_dialog.setValue(0)
        progress_dialog.show()

        last_percent = -1

        try:
            for idx, line in enumerate(lines):
                clean_line = line.lstrip("\x00").rstrip("\r\n")
                if not clean_line.strip():
                    if current_log:
                        current_log[5] += "\n"
                else:
                    parsed = parse_log_line(clean_line.strip())
                    if parsed:
                        if current_log:
                            current_log[5] = current_log[5].rstrip()
                            parsed_logs.append(tuple(current_log))
                        current_log = list(parsed)
                    elif current_log:
                        current_log[5] += f"\n{clean_line}"

                if total_lines > 0:
                    # 解析阶段占到 95%，预留后处理与渲染阶段进度，避免弹窗提前消失造成割裂感
                    percent = int((idx + 1) * 95 / total_lines)
                    if percent != last_percent:
                        progress_dialog.setLabelText(f"正在解析日志... {percent}%")
                        progress_dialog.setValue(percent)
                        QApplication.processEvents()
                        last_percent = percent

            if current_log:
                parsed_logs.append(tuple(current_log))

            progress_dialog.setLabelText("正在整理开机分组... 96%")
            progress_dialog.setValue(96)
            QApplication.processEvents()
            self.sessions = split_boot_sessions(parsed_logs)

            progress_dialog.setLabelText("正在提取版本信息... 98%")
            progress_dialog.setValue(98)
            QApplication.processEvents()
            version_info = extract_version_info(parsed_logs)

            progress_dialog.setLabelText("正在加载界面... 99%")
            progress_dialog.setValue(99)
            QApplication.processEvents()
            self.update_device_info(version_info)
            self.render_sessions()

            progress_dialog.setLabelText("完成 100%")
            progress_dialog.setValue(100)
            QApplication.processEvents()
        finally:
            progress_dialog.close()

    def update_device_info(self, info):
        self.status_label.setText(
            f"SN: {info['sn']} | PN: {info['pn']} | "
            f"固件版本: {info['firmware_version']} | 板卡固件版本: {info['gnss_board_version']}"
        )

    def render_sessions(self):
        self.tree.clear()

        for session in self.sessions:
            actual_time = session["actual_time"]
            title = f"开机#{session['id']}"
            if actual_time:
                title += f" | 日志时间: {actual_time}"

            parent = QTreeWidgetItem([title, "", "", "", "", ""])
            parent.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {"kind": "session", "session_id": session["id"]},
            )
            self.tree.addTopLevelItem(parent)

            for idx, log in enumerate(session["logs"]):
                child = QTreeWidgetItem(
                    [
                        str(log[0]),
                        str(log[1]),
                        str(log[2]),
                        str(log[3]),
                        str(log[4]),
                        str(log[5]),
                    ]
                )
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"kind": "log", "session_id": session["id"], "row": idx},
                )
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)

                # 按日志等级恢复行背景色
                level_color = LOG_COLORS.get(str(log[1]))
                if level_color is not None:
                    brush = QBrush(level_color)
                    for col in range(self.tree.columnCount()):
                        child.setBackground(col, brush)

                parent.addChild(child)

        self.collapse_all_sessions()
        self.apply_filters_to_tree()
        self.auto_resize_columns()
        self.update_sticky_session_label()

    def auto_resize_columns(self):
        header = self.tree.header()
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for i in range(5):
            self.tree.resizeColumnToContents(i)
        self.sync_sticky_columns()

    def show_log_detail(self, item, _column):
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("kind") != "log":
            return

        log = [item.text(c) for c in range(6)]
        level, module, func, line_no = log[1], log[2], log[3], log[4]
        remark = self.db.get_log_remark(level, module, func, line_no, content=log[5])
        detail = "\n".join(f"{TABLE_HEADERS[i]}: {log[i]}" for i in range(len(log)))
        self.log_detail.setText(detail + "\n\n解释:\n" + remark)

    def show_filter_dialog(self):
        if self.guide_prompts_enabled and not self.filter_hint_suppressed:
            hint = FilterHintDialog(self)
            hint.exec()
            if hint.dont_show_again():
                self.filter_hint_suppressed = True
                self.settings.setValue("filter_hint_suppressed", True)

        dialog = FilterDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        filters = dialog.get_filters()
        self.current_filters["level"] = filters["level"]
        self.current_filters["module"] = filters["module"]
        self.current_filters["function"] = filters["function"]
        self.current_filters["content"] = filters["content"]
        self.apply_filters_to_tree()

        count = self.visible_log_count()
        QMessageBox.information(self, "筛选", f"已应用筛选，显示 {count} 条日志")

    def visible_log_count(self):
        count = 0
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                if not parent.child(j).isHidden():
                    count += 1
        return count

    def apply_filters_to_tree(self):
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            visible_children = 0
            for j in range(parent.childCount()):
                child = parent.child(j)

                row = {
                    "time": child.text(0),
                    "level": child.text(1),
                    "module": child.text(2),
                    "function": child.text(3),
                    "content": child.text(5),
                }
                show = self.match_row(row)
                child.setHidden(not show)
                if show:
                    visible_children += 1

            parent.setHidden(visible_children == 0)

        self.update_sticky_session_label()

    def match_row(self, row):
        if self.current_filters["time"] and self.current_filters["time"] not in row["time"]:
            return False
        if self.current_filters["level"] and self.current_filters["level"] != row["level"]:
            return False
        if self.current_filters["module"] and self.current_filters["module"].lower() not in row["module"].lower():
            return False
        if self.current_filters["function"] and self.current_filters["function"].lower() not in row["function"].lower():
            return False
        if self.current_filters["content"] and not self.match_content_expression(
            self.current_filters["content"], row["content"]
        ):
            return False
        return True

    def _tokenize_filter_expression(self, expression):
        tokens = []
        buf = []
        in_quote = False
        i = 0
        while i < len(expression):
            ch = expression[i]
            if ch == '"':
                in_quote = not in_quote
                i += 1
                continue
            if not in_quote and i + 1 < len(expression) and expression[i:i + 2] in ("&&", "||"):
                token = "".join(buf).strip()
                if token:
                    tokens.append(token)
                tokens.append(expression[i:i + 2])
                buf = []
                i += 2
                continue
            if not in_quote and ch.isspace():
                token = "".join(buf).strip()
                if token:
                    tokens.append(token)
                buf = []
                i += 1
                continue
            buf.append(ch)
            i += 1

        token = "".join(buf).strip()
        if token:
            tokens.append(token)
        return tokens

    def match_content_expression(self, expression, content):
        tokens = self._tokenize_filter_expression(expression)
        if not tokens:
            return True

        normalized = []
        prev_is_term = False
        for tok in tokens:
            is_op = tok in ("&&", "||")
            if not is_op and prev_is_term:
                normalized.append("||")
            normalized.append(tok)
            prev_is_term = not is_op

        if normalized[0] in ("&&", "||") or normalized[-1] in ("&&", "||"):
            return expression.lower() in content.lower()

        groups = [[]]
        for tok in normalized:
            if tok == "||":
                groups.append([])
            elif tok == "&&":
                continue
            else:
                groups[-1].append(tok.lower())

        target = content.lower()
        for group in groups:
            if group and all(term in target for term in group):
                return True
        return False

    def show_find_dialog(self):
        dialog = FindDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.find_next(dialog.get_search_params())

    def show_rule_editor(self):
        """打开日志解释配置编辑器。"""
        if self.is_quick_add_open():
            QMessageBox.information(self, "日志解释配置", "新增日志解释窗口已打开，请先关闭后再打开日志解释配置")
            return

        if self.rule_editor_dialog is not None and self.rule_editor_dialog.isVisible():
            self.rule_editor_dialog.raise_()
            self.rule_editor_dialog.activateWindow()
            return

        self.rule_editor_dialog = RuleEditorDialog(self.db, self)
        self.rule_editor_dialog.destroyed.connect(self.on_rule_editor_closed)
        self.rule_editor_dialog.show()
        self.update_action_states()

    def on_rule_editor_closed(self, *_args):
        self.rule_editor_dialog = None
        self.update_action_states()

    def find_next(self, params):
        search_text = params["text"]
        if not search_text:
            QMessageBox.warning(self, "查找", "请输入查找内容")
            return

        case_sensitive = params["case_sensitive"]

        all_items = self.collect_visible_log_items()
        start = self.last_search_pos + 1
        for i in range(start, len(all_items)):
            item = all_items[i]
            content = item.text(5)
            found = search_text in content if case_sensitive else search_text.lower() in content.lower()
            if found:
                parent = item.parent()
                if parent is not None:
                    parent.setExpanded(True)
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                self.show_log_detail(item, 0)
                self.last_search_pos = i
                return

        self.last_search_pos = -1
        QMessageBox.information(self, "查找", "未找到更多匹配项")

    def collect_visible_log_items(self):
        items = []
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            if parent.isHidden():
                continue
            for j in range(parent.childCount()):
                child = parent.child(j)
                if not child.isHidden():
                    items.append(child)
        return items

    def jump_to_date(self):
        date, ok = QInputDialog.getText(self, "按日期跳转", "请输入日期(如 2023-01-01):")
        if not ok or not date.strip():
            return

        target_date = date.strip()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.text(0).startswith(target_date):
                    parent.setExpanded(True)
                    self.tree.setCurrentItem(child)
                    self.tree.scrollToItem(child)
                    self.show_log_detail(child, 0)
                    return

        QMessageBox.information(self, "跳转", f"未找到日期 {target_date} 对应日志")

    def expand_all_sessions(self):
        self.suspend_sticky_updates = True
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.tree.setUpdatesEnabled(True)
        self.suspend_sticky_updates = False
        self.update_sticky_session_label()

    def collapse_all_sessions(self):
        self.suspend_sticky_updates = True
        self.tree.setUpdatesEnabled(False)
        self.tree.blockSignals(True)
        self.tree.collapseAll()
        self.tree.blockSignals(False)
        self.tree.setUpdatesEnabled(True)
        self.suspend_sticky_updates = False
        self.update_sticky_session_label()

    def set_date_expanded(self, expanded):
        date, ok = QInputDialog.getText(self, "按日期操作", "请输入日期(如 2023-01-01):")
        if not ok or not date.strip():
            return

        target_date = date.strip()
        affected = 0
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            matched = False
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.text(0).startswith(target_date):
                    matched = True
                    break
            if matched:
                parent.setExpanded(expanded)
                affected += 1

        action_text = "展开" if expanded else "折叠"
        QMessageBox.information(self, "按日期操作", f"已{action_text} {affected} 个上电分组")

    def show_context_menu(self, pos: QPoint):
        clicked_item = self.tree.itemAt(pos)
        menu = QMenu(self)

        find_action = QAction("查找 (Ctrl+F)", self)
        find_action.triggered.connect(self.show_find_dialog)
        menu.addAction(find_action)

        filter_action = QAction("筛选 (Ctrl+Shift+F)", self)
        filter_action.triggered.connect(self.show_filter_dialog)
        menu.addAction(filter_action)

        jump_date_action = QAction("按日期跳转 (Ctrl+J)", self)
        jump_date_action.triggered.connect(self.jump_to_date)
        menu.addAction(jump_date_action)

        menu.addSeparator()

        copy_action = QAction("复制选中内容", self)
        copy_action.triggered.connect(self.copy_selected_row)
        menu.addAction(copy_action)

        if clicked_item is not None:
            meta = clicked_item.data(0, Qt.ItemDataRole.UserRole) or {}
            if meta.get("kind") == "log":
                menu.addSeparator()
                add_rule_action = QAction("新增日志解释", self)
                add_rule_action.setEnabled(not self.is_rule_editor_open())
                add_rule_action.triggered.connect(lambda: self.quick_add_log_rule(clicked_item))
                menu.addAction(add_rule_action)

        menu.addSeparator()

        clear_filter_action = QAction("清除所有筛选", self)
        clear_filter_action.triggered.connect(self.clear_filters)
        menu.addAction(clear_filter_action)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def toggle_log_detail_dock(self, checked):
        if hasattr(self, "detail_dock"):
            self.detail_dock.setVisible(bool(checked))

    def copy_selected_row(self):
        from PyQt6.QtWidgets import QApplication

        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit) and focus_widget.hasSelectedText():
            QApplication.clipboard().setText(focus_widget.selectedText())
            return

        items = self.tree.selectedItems()
        if not items:
            QMessageBox.warning(self, "复制", "请先选择要复制的行")
            return

        text_lines = []
        for item in items:
            meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if meta.get("kind") != "log":
                continue
            text_lines.append("\t".join(item.text(c) for c in range(6)))

        if not text_lines:
            QMessageBox.warning(self, "复制", "请选择具体日志行，而不是分组标题")
            return

        QApplication.clipboard().setText("\n".join(text_lines))
        QMessageBox.information(self, "复制", f"已复制 {len(text_lines)} 行到剪贴板")

    def quick_add_log_rule(self, item):
        """基于右键日志行快速新增解释配置。"""
        if item is None:
            return

        if self.is_rule_editor_open():
            QMessageBox.information(self, "新增日志解释", "日志解释配置窗口已打开，请先关闭后再新增日志解释")
            return

        if self.is_quick_add_open():
            self.quick_add_dialog.raise_()
            self.quick_add_dialog.activateWindow()
            return

        level = item.text(1).strip()
        module = item.text(2).strip()
        func = item.text(3).strip()
        line_no = item.text(4).strip()

        if not any([level, module, func, line_no]):
            QMessageBox.warning(self, "新增日志解释", "当前行缺少可用的日志关键字段")
            return

        existed_rule = self.db.get_log_rule(level, module, func, line_no)
        dialog_payload = {
            "level": level,
            "module": module,
            "function": func,
            "line_no": line_no,
            "remark": "",
            "script_code": "",
            "rule_id": None,
            "is_edit_mode": False,
            "content": item.text(5),
        }
        if existed_rule is not None:
            dialog_payload.update(
                {
                    "level": existed_rule["level"],
                    "module": existed_rule["module"],
                    "function": existed_rule["function"],
                    "line_no": str(existed_rule["line_no"]),
                    "remark": existed_rule["remark"],
                    "script_code": existed_rule["script_code"],
                    "rule_id": existed_rule["id"],
                    "is_edit_mode": True,
                }
            )

        dialog = QuickAddRuleDialog(
            dialog_payload,
            self,
        )
        self.quick_add_dialog = dialog
        dialog.ruleSaved.connect(lambda payload, clicked=item: self.save_quick_add_rule(payload, clicked))
        dialog.destroyed.connect(self.on_quick_add_closed)
        dialog.show()
        self.update_action_states()

    def on_quick_add_closed(self, *_args):
        self.quick_add_dialog = None
        self.update_action_states()

    def save_quick_add_rule(self, payload, item):
        """保存右键新增的解释规则。"""
        if item is None:
            return

        if not payload["remark"] and not payload["script_code"]:
            QMessageBox.warning(self, "新增日志解释", "解释信息和脚本代码至少填写一个")
            return

        try:
            status = self.db.save_log_rule(
                payload.get("rule_id"),
                payload["level"],
                payload["module"],
                payload["function"],
                payload["line_no"],
                payload["remark"],
                payload["script_code"],
            )
            action_text = "已更新" if status == "updated" else "已新增"
            QMessageBox.information(
                self,
                "新增日志解释",
                f"{action_text}配置: level={payload['level']}, module={payload['module']}, "
                f"function={payload['function']}, line_no={payload['line_no']}",
            )
            self.show_log_detail(item, 0)
        except Exception as e:
            QMessageBox.critical(self, "新增日志解释", f"保存失败:\n{str(e)}")

    def clear_filters(self):
        self.current_filters = {
            "time": "",
            "level": "",
            "module": "",
            "function": "",
            "content": "",
        }
        self.apply_filters_to_tree()
        QMessageBox.information(self, "筛选", "已清除所有筛选条件")

    def header_context_menu(self, pos: QPoint):
        header = self.tree.header()
        logical_index = header.logicalIndexAt(pos)

        if logical_index not in [0, 1, 2, 3]:
            return

        column_name = TABLE_HEADERS[logical_index]
        unique_values = set()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                value = parent.child(j).text(logical_index)
                if value:
                    unique_values.add(value)

        menu = QMenu(self)
        menu.setTitle(f"筛选 {column_name}")

        all_action = QAction("显示全部", self)
        all_action.triggered.connect(lambda: self.apply_column_filter(logical_index, ""))
        menu.addAction(all_action)
        menu.addSeparator()

        max_items = MAX_FILTER_ITEMS_TIME if logical_index == 0 else MAX_FILTER_ITEMS_OTHER
        sorted_values = sorted(unique_values)[:max_items]

        for value in sorted_values:
            action = QAction(str(value), self)
            action.triggered.connect(
                lambda checked, v=value, idx=logical_index: self.apply_column_filter(idx, v)
            )
            menu.addAction(action)

        if len(unique_values) > max_items:
            menu.addSeparator()
            more_action = QAction(f"...还有 {len(unique_values) - max_items} 个值", self)
            more_action.setEnabled(False)
            menu.addAction(more_action)

        menu.exec(header.mapToGlobal(pos))

    def apply_column_filter(self, column_index, value):
        if column_index == 0:
            self.current_filters["time"] = value
        elif column_index == 1:
            self.current_filters["level"] = value
        elif column_index == 2:
            self.current_filters["module"] = value
        elif column_index == 3:
            self.current_filters["function"] = value

        self.apply_filters_to_tree()

        if value:
            QMessageBox.information(
                self,
                "筛选",
                f"已筛选 {TABLE_HEADERS[column_index]}: {value}\n显示 {self.visible_log_count()} 条日志",
            )

    def closeEvent(self, event):
        self.db.close()
        event.accept()

    def _get_top_visible_item(self):
        """获取当前视口顶部可见项。"""
        if self.tree.topLevelItemCount() == 0:
            return None

        viewport = self.tree.viewport()
        for y in range(1, min(viewport.height(), 120), 4):
            item = self.tree.itemAt(8, y)
            if item is not None and not item.isHidden():
                return item
        return None

    def update_sticky_session_label(self):
        """更新顶部冻结显示的开机分组标题。"""
        if self.suspend_sticky_updates:
            return

        top_item = self._get_top_visible_item()
        if top_item is None:
            self.current_sticky_session_item = None
            self.current_sticky_text = ""
            self.sticky_tree.hide()
            return

        session_item = top_item if top_item.parent() is None else top_item.parent()
        if session_item.isHidden():
            self.current_sticky_session_item = None
            self.current_sticky_text = ""
            self.sticky_tree.hide()
            return

        text = session_item.text(0)
        if not text:
            self.current_sticky_session_item = None
            self.current_sticky_text = ""
            self.sticky_tree.hide()
            return

        self.current_sticky_session_item = session_item
        if text == self.current_sticky_text and self.sticky_tree.topLevelItemCount() > 0:
            if not self.sticky_tree.isVisible():
                self.sticky_tree.show()
            return

        self.current_sticky_text = text
        self.sticky_tree.clear()
        sticky_item = QTreeWidgetItem([text, "", "", "", "", ""])
        sticky_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "sticky_session"})
        self.sticky_tree.addTopLevelItem(sticky_item)
        self.sticky_tree.setFixedHeight(max(30, self.sticky_tree.sizeHintForRow(0) + 2))
        self.sync_sticky_columns()
        self.sticky_tree.show()

    def sync_sticky_columns(self):
        """同步固定行与主表列宽，保证视觉对齐。"""
        for i in range(self.tree.columnCount()):
            self.sticky_tree.setColumnWidth(i, self.tree.columnWidth(i))

    def jump_to_sticky_session(self, *_args):
        """点击冻结条时跳转到当前分组起始位置。"""
        session_item = self.current_sticky_session_item
        if session_item is None:
            return

        session_item.setExpanded(True)
        self.tree.setCurrentItem(session_item)
        self.tree.scrollToItem(session_item, QTreeWidget.ScrollHint.PositionAtTop)
