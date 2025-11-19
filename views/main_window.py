"""主窗口"""
from PyQt6.QtWidgets import (
    QMainWindow, QTableView, QDockWidget, QListWidget,
    QTextEdit, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QMessageBox, QMenu, QHeaderView, QDialog
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QPoint

from models import LogTableModel, LogFilterProxyModel, LogDatabase
from utils import parse_log_line
from views.dialogs import FilterDialog, FindDialog
from config import TABLE_HEADERS, MAX_FILTER_ITEMS_TIME, MAX_FILTER_ITEMS_OTHER


class LogViewer(QMainWindow):
    """日志查看器主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("系统日志分析工具")
        
        # 初始化数据库
        self.db = LogDatabase()
        self.db.connect()
        self.db.initialize()
        
        # 查找相关
        self.last_search_pos = -1
        
        # 初始化UI
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        # 创建菜单栏
        self.create_menu()
        
        # 中心日志表格
        self.table = QTableView()
        self.proxy_model = LogFilterProxyModel()
        self.setCentralWidget(self.table)
        self.table.clicked.connect(self.show_log_detail)
        
        # 启用右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # 启用表头右键菜单
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.header_context_menu)
        
        # 创建停靠窗口
        self.create_dock_widgets()
        
        # 新增：创建状态栏，显示PN/SN/版本
        self.create_status_bar()
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        open_action = QAction("打开文件", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu("编辑")
        find_action = QAction("查找", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.show_find_dialog)
        edit_menu.addAction(find_action)
        
        filter_action = QAction("筛选", self)
        filter_action.setShortcut("Ctrl+Shift+F")
        filter_action.triggered.connect(self.show_filter_dialog)
        edit_menu.addAction(filter_action)
    
    def create_dock_widgets(self):
        """创建停靠窗口"""
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
    
    def create_status_bar(self):
        """创建状态栏，显示设备PN、SN和版本"""
        status_label = QLabel("PN: 11064738700BA | SN: 4205653 | 版本: 2.5.1")
        status_label.setObjectName("deviceStatusLabel")
        status_label.setStyleSheet("QLabel#deviceStatusLabel { padding: 0 8px; }")
        self.statusBar().addPermanentWidget(status_label)
    
    def open_file(self):
        """打开文件并解析日志"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择日志文件", "",
            "日志文件 (*.log *.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                self.error_nav.clear()
                self.load_logs(lines)
                QMessageBox.information(self, "成功", f"成功加载 {len(lines)} 条日志")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开文件:\n{str(e)}")
    
    def load_logs(self, lines):
        """加载日志"""
        parsed_logs = []
        for line in lines:
            parsed = parse_log_line(line)
            if parsed:
                parsed_logs.append(parsed)
                if parsed[1] == "ERROR":
                    self.error_nav.addItem(f"Row {len(parsed_logs)-1}: {parsed[-1]}")
        
        self.model = LogTableModel(parsed_logs)
        self.proxy_model.setSourceModel(self.model)
        self.table.setModel(self.proxy_model)
        self.auto_resize_columns()
    
    def auto_resize_columns(self):
        """自动调整表格列宽"""
        header = self.table.horizontalHeader()
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(5, 400)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
    
    def show_log_detail(self, index):
        """显示日志详情"""
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()
        log = [self.model.data(self.model.index(row, c), Qt.ItemDataRole.DisplayRole)
               for c in range(self.model.columnCount())]
        level, module, func = log[1], log[2], log[3]
        
        remark = self.db.get_log_remark(level, module, func)
        detail = "\n".join(f"{TABLE_HEADERS[i]}: {log[i]}" for i in range(len(log)))
        self.log_detail.setText(detail + "\n\n解释:\n" + remark)
    
    def jump_to_error(self, item):
        """跳转到错误行"""
        row = int(item.text().split()[1].strip(":"))
        for proxy_row in range(self.proxy_model.rowCount()):
            source_index = self.proxy_model.mapToSource(self.proxy_model.index(proxy_row, 0))
            if source_index.row() == row:
                self.table.selectRow(proxy_row)
                break
    
    def show_filter_dialog(self):
        """显示筛选对话框"""
        dialog = FilterDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            filters = dialog.get_filters()
            self.proxy_model.set_filters(**filters)
            QMessageBox.information(self, "筛选", 
                f"已应用筛选,显示 {self.proxy_model.rowCount()} 条日志")
    
    def show_find_dialog(self):
        """显示查找对话框"""
        dialog = FindDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.find_next(dialog.get_search_params())
    
    def find_next(self, params):
        """查找下一个匹配项"""
        search_text = params['text']
        if not search_text:
            QMessageBox.warning(self, "查找", "请输入查找内容")
            return
        
        case_sensitive = params['case_sensitive']
        errors_only = params['errors_only']
        start = self.last_search_pos + 1
        
        if errors_only:
            for i in range(start, self.error_nav.count()):
                item_text = self.error_nav.item(i).text()
                found = search_text in item_text if case_sensitive else \
                        search_text.lower() in item_text.lower()
                if found:
                    self.error_nav.setCurrentRow(i)
                    self.last_search_pos = i
                    self.jump_to_error(self.error_nav.item(i))
                    return
            self.last_search_pos = -1
            QMessageBox.information(self, "查找", "未找到更多匹配项")
        else:
            for proxy_row in range(start, self.proxy_model.rowCount()):
                content = self.proxy_model.data(
                    self.proxy_model.index(proxy_row, 5), 
                    Qt.ItemDataRole.DisplayRole
                )
                found = search_text in content if case_sensitive else \
                        search_text.lower() in content.lower()
                if found:
                    self.table.selectRow(proxy_row)
                    self.table.scrollTo(self.proxy_model.index(proxy_row, 0))
                    self.last_search_pos = proxy_row
                    return
            self.last_search_pos = -1
            QMessageBox.information(self, "查找", "未找到更多匹配项")
    
    def show_context_menu(self, pos: QPoint):
        """显示右键菜单"""
        menu = QMenu(self)
        
        find_action = QAction("查找 (Ctrl+F)", self)
        find_action.triggered.connect(self.show_find_dialog)
        menu.addAction(find_action)
        
        filter_action = QAction("筛选 (Ctrl+Shift+F)", self)
        filter_action.triggered.connect(self.show_filter_dialog)
        menu.addAction(filter_action)
        
        menu.addSeparator()
        
        copy_action = QAction("复制选中内容", self)
        copy_action.triggered.connect(self.copy_selected_row)
        menu.addAction(copy_action)
        
        menu.addSeparator()
        
        clear_filter_action = QAction("清除所有筛选", self)
        clear_filter_action.triggered.connect(self.clear_filters)
        menu.addAction(clear_filter_action)
        
        menu.exec(self.table.viewport().mapToGlobal(pos))
    
    def copy_selected_row(self):
        """复制选中行到剪贴板"""
        from PyQt6.QtWidgets import QApplication
        
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.warning(self, "复制", "请先选择要复制的行")
            return
        
        text_lines = []
        for index in indexes:
            row_data = []
            for col in range(self.proxy_model.columnCount()):
                data = self.proxy_model.data(
                    self.proxy_model.index(index.row(), col),
                    Qt.ItemDataRole.DisplayRole
                )
                row_data.append(str(data))
            text_lines.append("\t".join(row_data))
        
        QApplication.clipboard().setText("\n".join(text_lines))
        QMessageBox.information(self, "复制", f"已复制 {len(indexes)} 行到剪贴板")
    
    def clear_filters(self):
        """清除所有筛选条件"""
        self.proxy_model.set_filters("", "", "", "")
        QMessageBox.information(self, "筛选", "已清除所有筛选条件")
    
    def header_context_menu(self, pos: QPoint):
        """表头右键菜单"""
        header = self.table.horizontalHeader()
        logical_index = header.logicalIndexAt(pos)
        
        if logical_index not in [0, 1, 2, 3]:
            return
        
        column_name = TABLE_HEADERS[logical_index]
        unique_values = set()
        for row in range(self.model.rowCount()):
            value = self.model.data(
                self.model.index(row, logical_index),
                Qt.ItemDataRole.DisplayRole
            )
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
                lambda checked, v=value, idx=logical_index: 
                self.apply_column_filter(idx, v)
            )
            menu.addAction(action)
        
        if len(unique_values) > max_items:
            menu.addSeparator()
            more_action = QAction(f"...还有 {len(unique_values) - max_items} 个值", self)
            more_action.setEnabled(False)
            menu.addAction(more_action)
        
        menu.exec(header.mapToGlobal(pos))
    
    def apply_column_filter(self, column_index, value):
        """应用列筛选"""
        current_filters = {
            'level': self.proxy_model.filter_level,
            'module': self.proxy_model.filter_module,
            'function': self.proxy_model.filter_function,
            'content': self.proxy_model.filter_content
        }
        
        if column_index == 0:
            current_filters['content'] = value
        elif column_index == 1:
            current_filters['level'] = value
        elif column_index == 2:
            current_filters['module'] = value
        elif column_index == 3:
            current_filters['function'] = value
        
        self.proxy_model.set_filters(**current_filters)
        
        if value:
            QMessageBox.information(self, "筛选",
                f"已筛选 {TABLE_HEADERS[column_index]}: {value}\n"
                f"显示 {self.proxy_model.rowCount()} 条日志")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.db.close()
        event.accept()
