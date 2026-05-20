"""数据库操作"""
import sqlite3

from config import DB_PATH


class LogDatabase:
    """日志数据库管理类"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """连接数据库"""
        self.conn = sqlite3.connect(self.db_path)
        return self.conn

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()

    def initialize(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS log_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                module TEXT NOT NULL,
                function TEXT NOT NULL,
                line_no TEXT NOT NULL DEFAULT '',
                remark TEXT
            )
            """
        )
        self.conn.commit()

        cursor.execute("PRAGMA table_info(log_info)")
        columns = [row[1] for row in cursor.fetchall()]
        if "line_no" not in columns:
            cursor.execute("ALTER TABLE log_info ADD COLUMN line_no TEXT NOT NULL DEFAULT ''")
            self.conn.commit()

        cursor.execute("SELECT COUNT(*) FROM log_info")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO log_info (level, module, function, line_no, remark) VALUES (?, ?, ?, ?, ?)",
                [
                    ("INFO", "misc", "print_3g_signal_intensity", "30", "打印 3G 信号强度，用于监控网络质量"),
                    ("WARN", "gps", "parse_data", "", "GPS 信号弱，可能由于遮挡或天线问题"),
                    ("ERROR", "comm", "send_packet", "", "通信模块发送失败，可能链路中断或硬件故障"),
                    ("ERROR", "", "", "", "错误级别日志,需要立即关注"),
                    ("WARN", "", "", "", "警告级别日志,建议检查"),
                    ("INFO", "", "", "", "信息级别日志,正常运行状态"),
                ],
            )
            self.conn.commit()

    def get_log_remark(self, level, module, func, line_no=""):
        """查询日志解释。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT remark FROM log_info WHERE level=? AND module=? AND function=? AND line_no=?",
            (level, module, func, str(line_no)),
        )
        result = cursor.fetchone()
        if result:
            return result[0]

        cursor.execute(
            "SELECT remark FROM log_info WHERE level=? AND module=? AND function=? AND line_no=''",
            (level, module, func),
        )
        result = cursor.fetchone()
        if result:
            return result[0]

        cursor.execute(
            "SELECT remark FROM log_info WHERE level=? AND module='' AND function='' AND line_no=''",
            (level,),
        )
        result = cursor.fetchone()
        if result:
            return result[0]

        return (
            "⚠ 数据库中没有找到对应解释\n"
            f"建议添加配置: level={level}, module={module}, function={func}, line_no={line_no}"
        )

    def list_log_rules(self):
        """获取全部日志解释配置。"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT level, module, function, line_no, remark
            FROM log_info
            ORDER BY id ASC
            """
        )
        return cursor.fetchall()

    def replace_log_rules(self, rules):
        """用传入配置整体替换 log_info 内容。"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM log_info")
        cursor.executemany(
            "INSERT INTO log_info (level, module, function, line_no, remark) VALUES (?, ?, ?, ?, ?)",
            rules,
        )
        self.conn.commit()
