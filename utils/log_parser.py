"""日志解析工具"""
from __future__ import annotations

import re
from typing import Optional


def parse_log_line(line: str):
    """
    解析一行日志:
    [2025-09-13 07:24:45:007443][ INFO ] misc print_3g_signal_intensity 30 : 3G signal dbm change to -81

    Args:
        line: 日志行字符串

    Returns:
        tuple: (时间, 等级, 模块, 函数, 行号, 内容) 或 None
    """
    # 标准日志严格匹配: [time][ LEVEL ] module func line_no : content
    standard_pattern = re.compile(
        r"^\[(?P<time>[^\]]+)\]\[\s*(?P<level>INFO|WARN|ERROR|DEBUG|TRACE)\s*\]\s+"
        r"(?P<module>\S+)\s+(?P<func>\S+)\s+(?P<line_no>\S+)\s*:\s*(?P<content>.*)$"
    )
    matched_standard = standard_pattern.match(line)
    if matched_standard:
        return (
            matched_standard.group("time"),
            matched_standard.group("level"),
            matched_standard.group("module"),
            matched_standard.group("func"),
            matched_standard.group("line_no"),
            matched_standard.group("content"),
        )

    try:
        # 兜底处理: [时间] + 其余任意内容，只提取时间，剩余全部放到内容列
        matched = re.match(r"^\[([^\]]+)\](.*)$", line)
        if not matched:
            return None

        date_time = matched.group(1).strip()
        rest_content = matched.group(2).strip()
        return date_time, "", "", "", "", rest_content
    except Exception:
        return None


def extract_year(datetime_str: str) -> Optional[int]:
    """从日志时间字符串提取年份。"""
    try:
        return int(datetime_str[:4])
    except Exception:
        return None


def is_boot_marker(parsed_log: tuple) -> bool:
    """识别上电标记日志。"""
    if not parsed_log or len(parsed_log) < 6:
        return False

    _, level, module, func, _, content = parsed_log
    if level != "INFO" or module != "mng" or func != "mng_init__buzzer_control":
        return False

    return "mng initializing" in content and "buzzer" in content


def split_boot_sessions(parsed_logs: list[tuple]) -> list[dict]:
    """
    按上电周期分隔日志，保持原始顺序。

    分段策略:
    1. 第一个分段从文件第一条日志开始。
    2. 以 buzzer 上电标记作为强特征。
    3. 对每个标记向前回溯到连续 2023-01-01 块开头作为新分段起点。
    4. 仅当该起点在当前分段内部时才切分，避免误切。
    """
    if not parsed_logs:
        return []

    starts = [0]

    for marker_idx, log in enumerate(parsed_logs):
        if not is_boot_marker(log):
            continue

        back = marker_idx
        while back - 1 >= 0 and parsed_logs[back - 1][0].startswith("2023-01-01"):
            back -= 1

        if back > starts[-1]:
            starts.append(back)

    sessions = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(parsed_logs)
        session_logs = parsed_logs[start:end]

        actual_time = ""
        for item in session_logs:
            year = extract_year(item[0])
            if year is not None and year not in (1980, 2023):
                actual_time = item[0]
                break

        sessions.append(
            {
                "id": i + 1,
                "start": start,
                "end": end,
                "actual_time": actual_time,
                "logs": session_logs,
            }
        )

    return sessions


def extract_version_info(parsed_logs: list[tuple]) -> dict:
    """提取最后一次打印的 show_version 关键信息。"""
    result = {
        "sn": "-",
        "pn": "-",
        "firmware_version": "-",
        "gnss_board_version": "-",
    }

    key_patterns = {
        "sn": re.compile(r"sn\s*:\s*(.+)$", re.IGNORECASE),
        "pn": re.compile(r"pn\s*:\s*(.+)$", re.IGNORECASE),
        "firmware_version": re.compile(r"firmware_version\s*:\s*(.+)$", re.IGNORECASE),
        "gnss_board_version": re.compile(r"gnss_board_version\s*:\s*(.+)$", re.IGNORECASE),
    }

    for item in parsed_logs:
        if len(item) < 6:
            continue

        _, _, module, func, _, content = item
        if module != "mng" or func != "show_version":
            continue

        normalized = content.strip()
        for key, pattern in key_patterns.items():
            matched = pattern.search(normalized)
            if matched:
                value = matched.group(1).strip()
                if value:
                    result[key] = value

    return result
