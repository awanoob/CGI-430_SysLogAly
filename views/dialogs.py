"""对话框组件"""
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from config import LOG_LEVELS


class FilterDialog(QDialog):
    """筛选对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志筛选")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("等级:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(LOG_LEVELS)
        level_layout.addWidget(self.level_combo)
        layout.addLayout(level_layout)

        module_layout = QHBoxLayout()
        module_layout.addWidget(QLabel("模块:"))
        self.module_edit = QLineEdit()
        self.module_edit.setPlaceholderText("输入模块名(支持部分匹配)")
        module_layout.addWidget(self.module_edit)
        layout.addLayout(module_layout)

        func_layout = QHBoxLayout()
        func_layout.addWidget(QLabel("函数:"))
        self.func_edit = QLineEdit()
        self.func_edit.setPlaceholderText("输入函数名(支持部分匹配)")
        func_layout.addWidget(self.func_edit)
        layout.addLayout(func_layout)

        content_layout = QHBoxLayout()
        content_layout.addWidget(QLabel("内容:"))
        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText("输入关键字(支持部分匹配)")
        content_layout.addWidget(self.content_edit)
        layout.addLayout(content_layout)

        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("应用筛选")
        apply_btn.clicked.connect(self.accept)
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self.reset_filters)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(apply_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_filters(self):
        """获取筛选条件"""
        return {
            "level": "" if self.level_combo.currentText() == "全部" else self.level_combo.currentText(),
            "module": self.module_edit.text(),
            "function": self.func_edit.text(),
            "content": self.content_edit.text(),
        }

    def reset_filters(self):
        """重置筛选条件"""
        self.level_combo.setCurrentIndex(0)
        self.module_edit.clear()
        self.func_edit.clear()
        self.content_edit.clear()


class FindDialog(QDialog):
    """查找对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查找")
        self.setMinimumWidth(400)

        layout = QVBoxLayout()

        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("查找:"))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("输入查找内容")
        find_layout.addWidget(self.find_edit)
        layout.addLayout(find_layout)

        self.case_sensitive = QCheckBox("区分大小写")
        layout.addWidget(self.case_sensitive)

        self.in_errors_only = QCheckBox("仅在错误日志中查找")
        layout.addWidget(self.in_errors_only)

        btn_layout = QHBoxLayout()
        find_btn = QPushButton("查找下一个")
        find_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(find_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def get_search_params(self):
        """获取查找参数"""
        return {
            "text": self.find_edit.text(),
            "case_sensitive": self.case_sensitive.isChecked(),
            "errors_only": self.in_errors_only.isChecked(),
        }


class RuleEditorDialog(QDialog):
    """日志解释配置编辑对话框"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("日志解释配置")
        self.resize(980, 560)

        layout = QVBoxLayout()

        tip = QLabel("可直接编辑配置，保存后立即生效。空白行不会保存。")
        layout.addWidget(tip)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["等级", "模块", "函数", "行号", "解释"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        edit_triggers = QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed
        self.table.setEditTriggers(edit_triggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增一行")
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self.delete_selected_rows)
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.load_rules)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        action_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_rules)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        action_row.addStretch()
        action_row.addWidget(save_btn)
        action_row.addWidget(close_btn)
        layout.addLayout(action_row)

        self.setLayout(layout)
        self.load_rules()

    def load_rules(self):
        """从数据库读取规则并填充到表格。"""
        rules = self.db.list_log_rules()
        self.table.setRowCount(0)
        for level, module, func, line_no, remark in rules:
            self._append_row(level, module, func, line_no, remark)

    def _append_row(self, level="", module="", func="", line_no="", remark=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [level, module, func, line_no, remark]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value) if value is not None else "")
            self.table.setItem(row, col, item)

    def add_row(self):
        """新增空白配置行。"""
        self._append_row()

    def delete_selected_rows(self):
        """删除选中的配置行。"""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        for index in sorted(selected, key=lambda x: x.row(), reverse=True):
            self.table.removeRow(index.row())

    def _row_values(self, row):
        values = []
        for col in range(5):
            item = self.table.item(row, col)
            values.append(item.text().strip() if item else "")
        return values

    def save_rules(self):
        """保存表格配置到数据库。"""
        rules = []
        for row in range(self.table.rowCount()):
            level, module, func, line_no, remark = self._row_values(row)
            if not any([level, module, func, line_no, remark]):
                continue
            rules.append((level, module, func, line_no, remark))

        try:
            self.db.replace_log_rules(rules)
            QMessageBox.information(self, "保存成功", f"已保存 {len(rules)} 条配置")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入数据库失败:\n{str(e)}")
