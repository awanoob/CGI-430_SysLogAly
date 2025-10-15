"""应用配置文件"""
from PyQt6.QtGui import QColor

# 日志颜色规则
LOG_COLORS = {
    "INFO": QColor(220, 255, 220),
    "WARN": QColor(255, 255, 200),
    "ERROR": QColor(255, 200, 200),
    "DEBUG": QColor(200, 200, 255),
    "TRACE": QColor(240, 240, 240),
}

# 数据库配置
DB_PATH = "log_config.db"

# 表头配置
TABLE_HEADERS = ["时间", "等级", "模块", "函数", "行号", "内容"]

# 日志等级列表
LOG_LEVELS = ["全部", "INFO", "WARN", "ERROR", "DEBUG", "TRACE"]

# 筛选配置
MAX_FILTER_ITEMS_TIME = 20  # 时间列最大显示项
MAX_FILTER_ITEMS_OTHER = 50  # 其他列最大显示项
