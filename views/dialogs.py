"""对话框组件"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox
)
from config import LOG_LEVELS


class FilterDialog(QDialog):
    """筛选对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日志筛选")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # 等级筛选
        level_layout = QHBoxLayout()
        level_layout.addWidget(QLabel("等级:"))
        self.level_combo = QComboBox()
        self.level_combo.addItems(LOG_LEVELS)
        level_layout.addWidget(self.level_combo)
        layout.addLayout(level_layout)
        
        # 模块筛选
        module_layout = QHBoxLayout()
        module_layout.addWidget(QLabel("模块:"))
        self.module_edit = QLineEdit()
        self.module_edit.setPlaceholderText("输入模块名(支持部分匹配)")
        module_layout.addWidget(self.module_edit)
        layout.addLayout(module_layout)
        
        # 函数筛选
        func_layout = QHBoxLayout()
        func_layout.addWidget(QLabel("函数:"))
        self.func_edit = QLineEdit()
        self.func_edit.setPlaceholderText("输入函数名(支持部分匹配)")
        func_layout.addWidget(self.func_edit)
        layout.addLayout(func_layout)
        
        # 内容筛选
        content_layout = QHBoxLayout()
        content_layout.addWidget(QLabel("内容:"))
        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText("输入关键字(支持部分匹配)")
        content_layout.addWidget(self.content_edit)
        layout.addLayout(content_layout)
        
        # 按钮
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
            'level': "" if self.level_combo.currentText() == "全部" else self.level_combo.currentText(),
            'module': self.module_edit.text(),
            'function': self.func_edit.text(),
            'content': self.content_edit.text()
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
        
        # 查找输入
        find_layout = QHBoxLayout()
        find_layout.addWidget(QLabel("查找:"))
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("输入查找内容")
        find_layout.addWidget(self.find_edit)
        layout.addLayout(find_layout)
        
        # 查找选项
        self.case_sensitive = QCheckBox("区分大小写")
        layout.addWidget(self.case_sensitive)
        
        self.in_errors_only = QCheckBox("仅在错误日志中查找")
        layout.addWidget(self.in_errors_only)
        
        # 按钮
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
            'text': self.find_edit.text(),
            'case_sensitive': self.case_sensitive.isChecked(),
            'errors_only': self.in_errors_only.isChecked()
        }
