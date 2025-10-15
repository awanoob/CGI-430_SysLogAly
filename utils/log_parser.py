"""日志解析工具"""

def parse_log_line(line: str):
    """
    解析一行日志:
    [2025-09-13 07:24:45:007443][ INFO ] misc print_3g_signal_intensity 30 : 3G signal dbm change to -81
    
    Args:
        line: 日志行字符串
        
    Returns:
        tuple: (时间, 等级, 模块, 函数, 行号, 内容) 或 None
    """
    try:
        log_list = line.split("]")
        date_time = line.split("]")[0].strip("[")
        level = line.split("]")[1].strip("[ ]")
        rest = "]".join(log_list[2:]).strip()
        parts = rest.split(":")[0].strip().split()
        module = parts[0]
        func = parts[1]
        line_no = parts[2]
        content = rest.split(':')
        log_content = ":".join(content[1:]).strip()
        return date_time, level, module, func, line_no, log_content
    except Exception:
        return None
