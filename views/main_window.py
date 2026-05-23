"""主窗口"""
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QPen
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

from config import LOG_COLORS, MAX_FILTER_ITEMS_OTHER, MAX_FILTER_ITEMS_TIME, TABLE_HEADERS
from models import LogDatabase
from utils import extract_version_info, parse_log_line, split_boot_sessions
from views.dialogs import FilterDialog, FindDialog, RuleEditorDialog, QuickAddRuleDialog


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

        self.setAcceptDrops(True)
        self.init_ui()

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
        self.tree.setStyleSheet(
            "QHeaderView::section {"
            " border-right: 1px solid #bdbdbd;"
            " border-bottom: 1px solid #bdbdbd;"
            " padding: 4px 6px;"
            "}"
        )
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

    def create_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        open_action = QAction("打开文件", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        edit_menu = menubar.addMenu("编辑")
        find_action = QAction("查找", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.show_find_dialog)
        edit_menu.addAction(find_action)

        copy_action = QAction("复制选中内容", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(self.copy_selected_row)
        edit_menu.addAction(copy_action)

        filter_action = QAction("筛选", self)
        filter_action.setShortcut("Ctrl+Shift+F")
        filter_action.triggered.connect(self.show_filter_dialog)
        edit_menu.addAction(filter_action)

        self.edit_rules_action = QAction("日志解释配置", self)
        self.edit_rules_action.triggered.connect(self.show_rule_editor)
        edit_menu.addAction(self.edit_rules_action)

        jump_date_action = QAction("按日期跳转", self)
        jump_date_action.setShortcut("Ctrl+J")
        jump_date_action.triggered.connect(self.jump_to_date)
        edit_menu.addAction(jump_date_action)

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

        self.update_action_states()

    def is_rule_editor_open(self):
        return self.rule_editor_dialog is not None and self.rule_editor_dialog.isVisible()

    def is_quick_add_open(self):
        return self.quick_add_dialog is not None and self.quick_add_dialog.isVisible()

    def update_action_states(self):
        if hasattr(self, "edit_rules_action"):
            self.edit_rules_action.setEnabled(not self.is_quick_add_open())

    def create_dock_widgets(self):
        self.log_detail = QTextEdit()
        self.log_detail.setReadOnly(True)
        self.detail_dock = QDockWidget("日志详情")
        self.detail_dock.setWidget(self.log_detail)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.detail_dock)

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
        if self.current_filters["content"] and self.current_filters["content"].lower() not in row["content"].lower():
            return False
        return True

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
