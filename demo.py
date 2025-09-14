import sys
import sqlite3
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTableView, QDockWidget,
    QListWidget, QTextEdit, QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex


# 日志颜色规则
LOG_COLORS = {
    "INFO": QColor(220, 255, 220),
    "WARN": QColor(255, 255, 200),
    "ERROR": QColor(255, 200, 200),
}


def parse_log_line(line: str):
    """
    解析一行日志:
    [2025-09-13 07:24:45:007443][ INFO ] misc print_3g_signal_intensity 30 : 3G signal dbm change to -81
    """
    try:
        date_time = line.split("]")[0].strip("[")
        level = line.split("]")[1].strip("[ ]")
        rest = line.split("]")[2].strip()
        parts = rest.split(" ")
        module = parts[0]
        func = parts[1]
        line_no = parts[2]
        content = " ".join(parts[4:])
        return date_time, level, module, func, line_no, content
    except Exception:
        return None


class LogTableModel(QAbstractTableModel):
    def __init__(self, logs):
        super().__init__()
        self.logs = logs
        self.headers = ["时间", "等级", "模块", "函数", "行号", "内容"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.logs)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        log = self.logs[row]

        if role == Qt.ItemDataRole.DisplayRole:
            return log[col]

        if role == Qt.ItemDataRole.BackgroundRole:  # 按日志等级给整行染色
            level = log[1]
            return LOG_COLORS.get(level, None)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None


class LogViewer(QMainWindow):
    def __init__(self, db_path="log_config.db"):
        super().__init__()
        self.setWindowTitle("系统日志分析工具 (QTableView + SQLite)")

        # 连接配置数据库
        self.conn = sqlite3.connect(db_path)

        # 中心日志表格
        self.table = QTableView()
        self.setCentralWidget(self.table)
        self.table.clicked.connect(self.show_log_detail)

        # 下侧设备信息栏
        self.device_info = QLabel("设备信息:\n版本: v1.0\nIMEI: 123456789")
        info_dock = QDockWidget("设备信息")
        info_widget = QWidget()
        vbox = QVBoxLayout()
        vbox.addWidget(self.device_info)
        info_widget.setLayout(vbox)
        info_dock.setWidget(info_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, info_dock)

        # 右侧日志详情栏
        self.log_detail = QTextEdit()
        self.log_detail.setReadOnly(True)
        detail_dock = QDockWidget("日志详情")
        detail_dock.setWidget(self.log_detail)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, detail_dock)

        # 左侧错误导航栏
        self.error_nav = QListWidget()
        self.error_nav.itemClicked.connect(self.jump_to_error)
        error_dock = QDockWidget("错误导航")
        error_dock.setWidget(self.error_nav)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, error_dock)

        # 加载示例日志
        self.load_logs([
            "[2025-09-13 07:24:45:007443][ INFO ] misc print_3g_signal_intensity 30 : 3G signal dbm change to -81",
            "[2025-09-13 07:24:46:008123][ ERROR ] comm send_packet 120 : failed to send packet",
            "[2025-09-13 07:24:47:002211][ WARN ] gps parse_data 88 : gps weak signal",
        ])

    def load_logs(self, lines):
        parsed_logs = []
        for line in lines:
            parsed = parse_log_line(line)
            if parsed:
                parsed_logs.append(parsed)
                if parsed[1] == "ERROR":
                    self.error_nav.addItem(f"Row {len(parsed_logs)-1}: {parsed[-1]}")
        self.model = LogTableModel(parsed_logs)
        self.table.setModel(self.model)

    def show_log_detail(self, index: QModelIndex):
        row = index.row()
        log = [self.model.data(self.model.index(row, c), Qt.ItemDataRole.DisplayRole)
               for c in range(self.model.columnCount())]
        level, module, func = log[1], log[2], log[3]

        # 查询数据库解释
        cursor = self.conn.cursor()
        cursor.execute("SELECT remark FROM log_info WHERE level=? AND module=? AND function=?",
                       (level, module, func))
        row_data = cursor.fetchone()
        remark = row_data[0] if row_data else "⚠ 数据库中没有找到对应解释"

        detail = "\n".join(f"{self.model.headers[i]}: {log[i]}" for i in range(len(log)))
        self.log_detail.setText(detail + "\n\n解释:\n" + remark)

    def jump_to_error(self, item):
        row = int(item.text().split()[1].strip(":"))
        self.table.selectRow(row)


if __name__ == "__main__":
    # 初始化配置数据库
    conn = sqlite3.connect("log_config.db")
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS log_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT NOT NULL,
        module TEXT NOT NULL,
        function TEXT NOT NULL,
        remark TEXT
    )
    """)
    conn.commit()

    # 如果表是空的，插入一些示例配置
    c.execute("SELECT COUNT(*) FROM log_info")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO log_info (level, module, function, remark) VALUES (?, ?, ?, ?)",
            [
                ("INFO", "misc", "print_3g_signal_intensity", "打印 3G 信号强度，用于监控网络质量"),
                ("WARN", "gps", "parse_data", "GPS 信号弱，可能由于遮挡或天线问题"),
                ("ERROR", "comm", "send_packet", "通信模块发送失败，可能链路中断或硬件故障"),
            ]
        )
        conn.commit()

    conn.close()

    # 启动应用
    app = QApplication(sys.argv)
    viewer = LogViewer()
    viewer.show()
    sys.exit(app.exec())
