"""对话框组件"""
import re
from PyQt6.QtCore import QEvent, Qt, pyqtSignal

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QSpinBox,
    QVBoxLayout,
)

from config import LOG_LEVELS
from utils.script_sandbox import build_script_sandbox


class PlainPasteTextEdit(QTextEdit):
    """粘贴时仅保留纯文本，去掉富文本格式。"""

    def insertFromMimeData(self, source):
        self.insertPlainText(source.text())


class FilterDialog(QDialog):
    """筛选对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志筛选")
        self.setMinimumWidth(400)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, True)

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

    def show_usage_help(self):
        """显示筛选表达式用法。"""
        text = (
            "内容筛选支持关键字与逻辑运算:\n"
            "1. 使用 && 表示与，例如: 定位&&成功\n"
            "2. 使用 || 表示或，例如: ERROR||WARN\n"
            "3. 空格会按 || 处理，例如: 定位 成功 等价于 定位||成功\n"
            "4. 双引号内空格不拆分，例如: \"定位 失败\"&&重试\n"
            "5. 支持混合，例如: \"State Change\"&&gnss||北斗"
        )
        QMessageBox.information(self, "筛选说明", text)

    def event(self, event):
        """拦截标题栏帮助按钮触发，直接弹出筛选说明。"""
        if event.type() == QEvent.Type.EnterWhatsThisMode:
            self.show_usage_help()
            return True
        return super().event(event)


class FilterHintDialog(QDialog):
    """筛选入口引导提示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("筛选提示")
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("可以点击“？”获取筛选说明。"))

        self.dont_show_check = QCheckBox("下次不显示该窗口")
        layout.addWidget(self.dont_show_check)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("知道了")
        ok_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def dont_show_again(self):
        return self.dont_show_check.isChecked()


class NotificationSettingsDialog(QDialog):
    """通知设置。"""

    def __init__(self, guide_enabled=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("通知设置")
        self.setMinimumWidth(420)

        layout = QVBoxLayout()
        self.guide_check = QCheckBox("开启引导提示")
        self.guide_check.setChecked(bool(guide_enabled))
        layout.addWidget(self.guide_check)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def get_settings(self):
        return {
            "guide_enabled": self.guide_check.isChecked(),
        }


class InterfaceSettingsDialog(QDialog):
    """界面设置。"""

    def __init__(self, tree_bg_color="#ffffff", parent=None):
        super().__init__(parent)
        self.setWindowTitle("界面设置")
        self.setMinimumWidth(460)
        self.current_color = tree_bg_color or "#ffffff"

        layout = QVBoxLayout()

        row = QHBoxLayout()
        row.addWidget(QLabel("日志背景颜色:"))
        self.color_preview = QLineEdit(self.current_color)
        self.color_preview.setReadOnly(True)
        choose_btn = QPushButton("选择颜色")
        choose_btn.clicked.connect(self.choose_color)
        row.addWidget(self.color_preview)
        row.addWidget(choose_btn)
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def choose_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.current_color = color.name()
            self.color_preview.setText(self.current_color)

    def get_settings(self):
        return {
            "tree_bg_color": self.current_color,
        }


class UpdateSettingsDialog(QDialog):
    """升级设置。"""

    def __init__(
        self,
        server_url,
        channel,
        timeout_seconds,
        auto_check_on_startup,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("升级设置")
        self.setMinimumWidth(520)

        layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("升级服务器地址:"))
        self.server_url_edit = QLineEdit(server_url)
        self.server_url_edit.setPlaceholderText("例如: http://10.10.166.26:10612")
        row1.addWidget(self.server_url_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("发布通道:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setEditable(True)
        self.channel_combo.addItems(["stable", "beta"])
        current_channel = channel.strip() if channel else "stable"
        idx = self.channel_combo.findText(current_channel)
        if idx >= 0:
            self.channel_combo.setCurrentIndex(idx)
        else:
            self.channel_combo.setCurrentText(current_channel)
        row2.addWidget(self.channel_combo)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("请求超时(秒):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(3, 120)
        self.timeout_spin.setValue(int(timeout_seconds))
        row3.addWidget(self.timeout_spin)
        row3.addStretch()
        layout.addLayout(row3)

        self.auto_check_check = QCheckBox("启动时自动检查升级（静默）")
        self.auto_check_check.setChecked(bool(auto_check_on_startup))
        layout.addWidget(self.auto_check_check)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def get_settings(self):
        return {
            "server_url": self.server_url_edit.text().strip(),
            "channel": self.channel_combo.currentText().strip() or "stable",
            "timeout_seconds": int(self.timeout_spin.value()),
            "auto_check_on_startup": self.auto_check_check.isChecked(),
        }


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
        }


class RuleEditorDialog(QDialog):
    """日志解释配置编辑对话框"""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.script_dialog = None
        self.setWindowTitle("日志解释配置")
        self.resize(980, 560)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout()

        tip = QLabel("可直接编辑配置，保存后立即生效。空白行不会保存。")
        layout.addWidget(tip)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["等级", "模块", "函数", "行号", "解释", "脚本代码"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        edit_triggers = QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed
        self.table.setEditTriggers(edit_triggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("新增一行")
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self.delete_selected_rows)
        script_btn = QPushButton("编辑日志解析代码")
        script_btn.clicked.connect(self.edit_script_code)
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.load_rules)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(script_btn)
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
        for rule in rules:
            if len(rule) == 5:
                level, module, func, line_no, remark = rule
                script_code = ""
            else:
                level, module, func, line_no, remark, script_code = rule
            self._append_row(level, module, func, line_no, remark, script_code)

    def _append_row(self, level="", module="", func="", line_no="", remark="", script_code=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [level, module, func, line_no, remark, script_code]
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
        for col in range(6):
            item = self.table.item(row, col)
            values.append(item.text().strip() if item else "")
        return values

    def edit_script_code(self):
        """为选中行打开脚本代码编辑窗口。"""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "编辑脚本", "请先选中一行规则")
            return

        row = selected[0].row()
        current_item = self.table.item(row, 5)
        current_code = current_item.text() if current_item else ""

        if self.script_dialog is not None and self.script_dialog.isVisible():
            self.script_dialog.raise_()
            self.script_dialog.activateWindow()
            return

        self.script_dialog = ScriptCodeDialog(current_code, self)

        def _apply_script(new_code):
            target_item = self.table.item(row, 5)
            if target_item is None:
                target_item = QTableWidgetItem("")
                self.table.setItem(row, 5, target_item)
            target_item.setText(new_code)

        self.script_dialog.scriptSaved.connect(_apply_script)
        self.script_dialog.destroyed.connect(lambda *_: setattr(self, "script_dialog", None))
        self.script_dialog.show()

    def save_rules(self):
        """保存表格配置到数据库。"""
        rules = []
        for row in range(self.table.rowCount()):
            level, module, func, line_no, remark, script_code = self._row_values(row)
            if not any([level, module, func, line_no, remark, script_code]):
                continue
            rules.append((level, module, func, line_no, remark, script_code))

        try:
            self.db.replace_log_rules(rules)
            QMessageBox.information(self, "保存成功", f"已保存 {len(rules)} 条配置")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入数据库失败:\n{str(e)}")


class ScriptCodeDialog(QDialog):
    """日志解析代码编辑对话框。"""

    scriptSaved = pyqtSignal(str)

    def __init__(self, script_code="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志解析代码")
        self.resize(820, 560)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.ai_prompt_dialog = None

        layout = QVBoxLayout()
        tip = QLabel(
            "脚本需定义 explain(context) 函数并返回解释字符串。"
            " context 包含 level/module/function/line_no/content/default_remark。"
        )
        layout.addWidget(tip)

        self.code_edit = PlainPasteTextEdit()
        self.code_edit.setPlaceholderText(
            "def explain(context):\n"
            "    # 示例: 提取状态切换\n"
            "    m = re.search(r'pos type chaged:(\\d+)-->(\\d+)', context['content'])\n"
            "    if m:\n"
            "        return f\"gnss板卡定位状态从{m.group(1)}变为{m.group(2)}\"\n"
            "    return context['default_remark']\n"
        )
        self.code_edit.setPlainText(script_code)
        layout.addWidget(self.code_edit)

        layout.addWidget(QLabel("测试日志内容:"))
        self.test_content_edit = QTextEdit()
        self.test_content_edit.setPlaceholderText(
            "粘贴一条日志内容用于测试，例如:\n"
            "[State_Change] gnss board pos type chaged:16-->17"
        )
        layout.addWidget(self.test_content_edit)

        layout.addWidget(QLabel("默认解释(脚本返回 None 或空串时回退):"))
        self.test_default_remark_edit = QLineEdit("默认解释文本")
        layout.addWidget(self.test_default_remark_edit)

        layout.addWidget(QLabel("测试结果:"))
        self.test_result_edit = QTextEdit()
        self.test_result_edit.setReadOnly(True)
        self.test_result_edit.setPlaceholderText("点击“测试脚本”后在这里显示解析结果")
        layout.addWidget(self.test_result_edit)

        btn_row = QHBoxLayout()
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.code_edit.clear)
        test_btn = QPushButton("测试脚本")
        test_btn.clicked.connect(self.test_script)
        prompt_btn = QPushButton("生成AI Prompt")
        prompt_btn.clicked.connect(self.open_ai_prompt_builder)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save_script)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.close)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(test_btn)
        btn_row.addWidget(prompt_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def get_code(self):
        return self.code_edit.toPlainText().strip()

    def save_script(self):
        self.scriptSaved.emit(self.get_code())
        self.close()

    def test_script(self):
        """执行脚本并展示测试输出。"""
        script_text = self.code_edit.toPlainText().strip()
        if not script_text:
            QMessageBox.warning(self, "测试脚本", "脚本代码为空，请先输入脚本")
            return

        default_remark = self.test_default_remark_edit.text().strip() or "默认解释文本"
        content = self.test_content_edit.toPlainText()

        sandbox = build_script_sandbox({"re": re})

        context = {
            "level": "INFO",
            "module": "",
            "function": "",
            "line_no": "",
            "content": content,
            "default_remark": default_remark,
        }

        try:
            exec(script_text, sandbox, sandbox)
            explain = sandbox.get("explain")
            if not callable(explain):
                self.test_result_edit.setPlainText("[脚本错误] 未找到 explain(context) 函数")
                return

            result = explain(context)
            if result is None:
                result_text = default_remark
            else:
                result_text = str(result).strip() or default_remark
            self.test_result_edit.setPlainText(result_text)
        except Exception as e:
            self.test_result_edit.setPlainText(f"[脚本执行失败] {e}")

    def open_ai_prompt_builder(self):
        """打开 AI Prompt 生成窗口。"""
        if self.ai_prompt_dialog is not None and self.ai_prompt_dialog.isVisible():
            self.ai_prompt_dialog.raise_()
            self.ai_prompt_dialog.activateWindow()
            return

        self.ai_prompt_dialog = AIPromptBuilderDialog(self)
        self.ai_prompt_dialog.destroyed.connect(lambda *_: setattr(self, "ai_prompt_dialog", None))
        self.ai_prompt_dialog.show()


class AIPromptBuilderDialog(QDialog):
    """AI Prompt 生成对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Prompt 生成器")
        self.resize(900, 700)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout()

        tip = QLabel(
            "填写需求后点击“一键生成AI Prompt”。将生成结果复制给 AI，可直接产出 explain(context) 脚本。"
        )
        layout.addWidget(tip)

        layout.addWidget(QLabel("日志样例内容:"))
        self.logs_edit = PlainPasteTextEdit()
        self.logs_edit.setPlaceholderText("粘贴 1~5 条典型日志样例")
        layout.addWidget(self.logs_edit)

        layout.addWidget(QLabel("想要提取的信息:"))
        self.extract_edit = PlainPasteTextEdit()
        self.extract_edit.setPlaceholderText("例如: 提取状态码 old/new、故障码、模块名、时间差等")
        layout.addWidget(self.extract_edit)

        layout.addWidget(QLabel("解析规则或约束:"))
        self.rule_edit = PlainPasteTextEdit()
        self.rule_edit.setPlaceholderText("例如: 优先正则匹配; 匹配失败回退默认解释; 不抛异常")
        layout.addWidget(self.rule_edit)

        layout.addWidget(QLabel("期望解释输出格式:"))
        self.format_edit = PlainPasteTextEdit()
        self.format_edit.setPlaceholderText("例如: gnss板卡定位状态从{old}变为{new}")
        layout.addWidget(self.format_edit)

        action_row = QHBoxLayout()
        gen_btn = QPushButton("一键生成AI Prompt")
        gen_btn.clicked.connect(self.generate_prompt)
        copy_btn = QPushButton("复制Prompt")
        copy_btn.clicked.connect(self.copy_prompt)
        action_row.addWidget(gen_btn)
        action_row.addWidget(copy_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        layout.addWidget(QLabel("生成的AI Prompt(可继续手工修改):"))
        self.prompt_output = PlainPasteTextEdit()
        self.prompt_output.setPlaceholderText("点击上方按钮生成")
        layout.addWidget(self.prompt_output)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.setLayout(layout)

    def generate_prompt(self):
        logs = self.logs_edit.toPlainText().strip() or "(未提供日志样例)"
        extract = self.extract_edit.toPlainText().strip() or "(未提供)"
        rules = self.rule_edit.toPlainText().strip() or "(未提供)"
        out_fmt = self.format_edit.toPlainText().strip() or "(未提供)"

        prompt = (
            "请基于以下需求，生成可直接运行的 Python 脚本代码。\n\n"
            "【目标】\n"
            "- 生成一个函数: explain(context)\n"
            "- 该函数用于日志解释，返回字符串\n"
            "- 函数要能在本地脚本测试窗口直接运行\n\n"
            "【运行环境与约束】\n"
            "- 输入只有一个参数: context (dict)\n"
            "- context 字段固定为: level, module, function, line_no, content, default_remark\n"
            "- 必须使用 context 作为入参，不要设计其它入参\n"
            "- 可使用 re 模块，但是无需import re\n"
            "- 不要依赖外部第三方库，不要使用import函数\n"
            "- 代码必须包含 def explain(context):\n"
            "- 匹配失败时返回 context['default_remark']\n"
            "- 发生异常时不要抛出，返回 context['default_remark']\n"
            "- 输出只要 Python 代码，不要解释说明，输出为markdown格式\n\n"
            "- 可以使用的 Python 内置函数有: str, int, float, bool, len, min, max, abs, round, list, tuple, set, dict, sum, sorted, enumerate, zip, any, all, range, map, filter, next\n\n"
            "- 其他函数或模块都不可用\n\n"
            "【日志样例】\n"
            f"{logs}\n\n"
            "【需要提取的信息】\n"
            f"{extract}\n\n"
            "【解析规则/约束】\n"
            f"{rules}\n\n"
            "【期望输出格式】\n"
            f"{out_fmt}\n\n"
            "请严格按上述要求给出最终代码。"
        )
        self.prompt_output.setPlainText(prompt)

    def copy_prompt(self):
        text = self.prompt_output.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "复制Prompt", "请先生成 Prompt")
            return
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "复制Prompt", "已复制到剪贴板")


class QuickAddRuleDialog(QDialog):
    """右键快速新增日志解释对话框。"""

    ruleSaved = pyqtSignal(dict)

    def __init__(self, default_rule, parent=None):
        super().__init__(parent)
        self.rule_id = default_rule.get("rule_id")
        self.is_edit_mode = bool(default_rule.get("is_edit_mode", False))
        self.setWindowTitle("修改日志解释" if self.is_edit_mode else "新增日志解释")
        self.resize(700, 420)
        self.script_code = default_rule.get("script_code", "")
        self.script_dialog = None
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        layout = QVBoxLayout()

        self.level_edit = QLineEdit(default_rule.get("level", ""))
        self.module_edit = QLineEdit(default_rule.get("module", ""))
        self.function_edit = QLineEdit(default_rule.get("function", ""))
        self.line_no_edit = QLineEdit(default_rule.get("line_no", ""))

        for widget in [self.level_edit, self.module_edit, self.function_edit, self.line_no_edit]:
            widget.setReadOnly(True)

        for label, widget in [
            ("等级", self.level_edit),
            ("模块", self.module_edit),
            ("函数", self.function_edit),
            ("行号", self.line_no_edit),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}:"))
            row.addWidget(widget)
            layout.addLayout(row)

        layout.addWidget(QLabel("解释信息:"))
        self.remark_edit = QTextEdit()
        self.remark_edit.setPlaceholderText("请输入日志解释...")
        self.remark_edit.setPlainText(default_rule.get("remark", ""))
        layout.addWidget(self.remark_edit)

        self.test_content = default_rule.get("content", "")
        script_row = QHBoxLayout()
        self.script_status = QLabel("日志解析代码: 已设置" if self.script_code else "日志解析代码: 未设置")
        edit_script_btn = QPushButton("编辑日志解析代码")
        edit_script_btn.clicked.connect(self.edit_script_code)
        script_row.addWidget(self.script_status)
        script_row.addStretch()
        script_row.addWidget(edit_script_btn)
        layout.addLayout(script_row)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("修改" if self.is_edit_mode else "保存")
        save_btn.clicked.connect(self.save_rule)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def edit_script_code(self):
        """打开脚本代码编辑窗口。"""
        if self.script_dialog is not None and self.script_dialog.isVisible():
            self.script_dialog.raise_()
            self.script_dialog.activateWindow()
            return

        self.script_dialog = ScriptCodeDialog(self.script_code, self)
        if self.test_content:
            self.script_dialog.test_content_edit.setPlainText(self.test_content)
        if self.remark_edit.toPlainText().strip():
            self.script_dialog.test_default_remark_edit.setText(self.remark_edit.toPlainText().strip())

        self.script_dialog.scriptSaved.connect(self._apply_script_code)
        self.script_dialog.destroyed.connect(lambda *_: setattr(self, "script_dialog", None))
        self.script_dialog.show()

    def _apply_script_code(self, code):
        self.script_code = code
        self.script_status.setText("脚本代码: 已设置" if self.script_code else "脚本代码: 未设置")

    def save_rule(self):
        self.ruleSaved.emit(self.get_rule_data())
        self.close()

    def get_rule_data(self):
        """获取输入的配置数据。"""
        return {
            "rule_id": self.rule_id,
            "level": self.level_edit.text().strip(),
            "module": self.module_edit.text().strip(),
            "function": self.function_edit.text().strip(),
            "line_no": self.line_no_edit.text().strip(),
            "remark": self.remark_edit.toPlainText().strip(),
            "script_code": self.script_code,
        }
