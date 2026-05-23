"""数据库操作"""
import re
import sqlite3

from config import DB_PATH
from utils.script_sandbox import build_script_sandbox


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
                remark TEXT,
                script_code TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.conn.commit()

        cursor.execute("PRAGMA table_info(log_info)")
        columns = [row[1] for row in cursor.fetchall()]
        if "line_no" not in columns:
            cursor.execute("ALTER TABLE log_info ADD COLUMN line_no TEXT NOT NULL DEFAULT ''")
            self.conn.commit()
        if "script_code" not in columns:
            cursor.execute("ALTER TABLE log_info ADD COLUMN script_code TEXT NOT NULL DEFAULT ''")
            self.conn.commit()

        cursor.execute("SELECT COUNT(*) FROM log_info")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO log_info (level, module, function, line_no, remark, script_code) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("ERROR", "", "", "", "错误级别日志,需要立即关注", ""),
                    ("DEBUG", "", "", "", "Debug级别日志,正常运行状态", ""),
                    ("INFO", "", "", "", "信息级别日志,正常运行状态", ""),
                ],
            )
            self.conn.commit()

    def _run_rule_script(self, script_code, level, module, func, line_no, content, default_remark):
        """执行规则脚本，执行失败时返回默认解释+错误提示。"""
        script_text = (script_code or "").strip()
        if not script_text:
            return default_remark

        sandbox = build_script_sandbox({"re": re})

        try:
            exec(script_text, sandbox, sandbox)
            explain = sandbox.get("explain")
            if not callable(explain):
                return f"{default_remark}\n\n[脚本错误] 未找到 explain(context) 函数"

            context = {
                "level": level,
                "module": module,
                "function": func,
                "line_no": str(line_no),
                "content": content,
                "default_remark": default_remark,
            }
            result = explain(context)
            if result is None:
                return default_remark
            result_text = str(result).strip()
            return result_text if result_text else default_remark
        except Exception as e:
            return f"{default_remark}\n\n[脚本执行失败] {e}"

    def _query_rule_with_id(self, level, module, func, line_no=""):
        """按优先级查询匹配规则，返回 (id, level, module, function, line_no, remark, script_code) 或 None。"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, level, module, function, line_no, remark, script_code FROM log_info WHERE level=? AND module=? AND function=? AND line_no=?",
            (level, module, func, str(line_no)),
        )
        result = cursor.fetchone()
        if result:
            return result

        cursor.execute(
            "SELECT id, level, module, function, line_no, remark, script_code FROM log_info WHERE level=? AND module=? AND function=? AND line_no=''",
            (level, module, func),
        )
        result = cursor.fetchone()
        if result:
            return result

        cursor.execute(
            "SELECT id, level, module, function, line_no, remark, script_code FROM log_info WHERE level=? AND module='' AND function='' AND line_no=''",
            (level,),
        )
        result = cursor.fetchone()
        if result:
            return result

        return None

    def _query_rule(self, level, module, func, line_no=""):
        """按优先级查询匹配规则，返回 (remark, script_code) 或 None。"""
        row = self._query_rule_with_id(level, module, func, line_no)
        if not row:
            return None
        return row[5], row[6]

    def get_log_rule(self, level, module, func, line_no=""):
        """获取匹配到的完整规则信息。"""
        row = self._query_rule_with_id(level, module, func, line_no)
        if not row:
            return None
        return {
            "id": row[0],
            "level": row[1],
            "module": row[2],
            "function": row[3],
            "line_no": row[4],
            "remark": row[5] or "",
            "script_code": row[6] or "",
        }

    def get_log_remark(self, level, module, func, line_no="", content=""):
        """查询日志解释。"""
        matched = self._query_rule(level, module, func, line_no)
        if matched:
            remark, script_code = matched
            return self._run_rule_script(script_code, level, module, func, line_no, content, remark)

        return (
            "⚠ 数据库中没有找到对应解释\n"
            f"建议添加配置: level={level}, module={module}, function={func}, line_no={line_no}"
        )

    def list_log_rules(self):
        """获取全部日志解释配置。"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT level, module, function, line_no, remark, script_code
            FROM log_info
            ORDER BY id ASC
            """
        )
        return cursor.fetchall()

    def replace_log_rules(self, rules):
        """用传入配置整体替换 log_info 内容。"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM log_info")
        normalized_rules = []
        for rule in rules:
            if len(rule) == 5:
                level, module, func, line_no, remark = rule
                script_code = ""
            else:
                level, module, func, line_no, remark, script_code = rule
            normalized_rules.append((level, module, func, line_no, remark, script_code))

        cursor.executemany(
            "INSERT INTO log_info (level, module, function, line_no, remark, script_code) VALUES (?, ?, ?, ?, ?, ?)",
            normalized_rules,
        )
        self.conn.commit()

    def upsert_log_rule(self, level, module, func, line_no, remark, script_code=""):
        """新增或更新单条解释规则。"""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id FROM log_info
            WHERE level=? AND module=? AND function=? AND line_no=?
            LIMIT 1
            """,
            (level, module, func, str(line_no)),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE log_info SET remark=?, script_code=? WHERE id=?",
                (remark, script_code, row[0]),
            )
            self.conn.commit()
            return "updated"

        cursor.execute(
            "INSERT INTO log_info (level, module, function, line_no, remark, script_code) VALUES (?, ?, ?, ?, ?, ?)",
            (level, module, func, str(line_no), remark, script_code),
        )
        self.conn.commit()
        return "inserted"

    def save_log_rule(self, rule_id, level, module, func, line_no, remark, script_code=""):
        """按主键更新规则；若主键不存在则新增。"""
        cursor = self.conn.cursor()
        if rule_id is not None:
            cursor.execute(
                "SELECT id FROM log_info WHERE id=? LIMIT 1",
                (rule_id,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    """
                    UPDATE log_info
                    SET level=?, module=?, function=?, line_no=?, remark=?, script_code=?
                    WHERE id=?
                    """,
                    (level, module, func, str(line_no), remark, script_code, rule_id),
                )
                self.conn.commit()
                return "updated"

        cursor.execute(
            "INSERT INTO log_info (level, module, function, line_no, remark, script_code) VALUES (?, ?, ?, ?, ?, ?)",
            (level, module, func, str(line_no), remark, script_code),
        )
        self.conn.commit()
        return "inserted"
