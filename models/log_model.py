"""日志表格模型"""
from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from config import LOG_COLORS, TABLE_HEADERS


class LogTableModel(QAbstractTableModel):
    """日志表格数据模型"""
    
    def __init__(self, logs):
        super().__init__()
        self.logs = logs
        self.headers = TABLE_HEADERS

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

        if role == Qt.ItemDataRole.BackgroundRole:
            level = log[1]
            return LOG_COLORS.get(level, None)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None


class LogFilterProxyModel(QSortFilterProxyModel):
    """日志筛选代理模型"""
    
    def __init__(self):
        super().__init__()
        self.filter_level = ""
        self.filter_module = ""
        self.filter_function = ""
        self.filter_content = ""
    
    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        
        # 获取该行数据
        level = model.data(model.index(source_row, 1), Qt.ItemDataRole.DisplayRole)
        module = model.data(model.index(source_row, 2), Qt.ItemDataRole.DisplayRole)
        function = model.data(model.index(source_row, 3), Qt.ItemDataRole.DisplayRole)
        content = model.data(model.index(source_row, 5), Qt.ItemDataRole.DisplayRole)
        
        # 应用筛选条件
        if self.filter_level and level != self.filter_level:
            return False
        if self.filter_module and self.filter_module.lower() not in module.lower():
            return False
        if self.filter_function and self.filter_function.lower() not in function.lower():
            return False
        if self.filter_content and self.filter_content.lower() not in content.lower():
            return False
        
        return True
    
    def set_filters(self, level="", module="", function="", content=""):
        """设置筛选条件"""
        self.filter_level = level
        self.filter_module = module
        self.filter_function = function
        self.filter_content = content
        self.invalidateFilter()
