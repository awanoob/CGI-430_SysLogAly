"""系统日志分析工具 - 主程序入口"""
import sys
from PyQt6.QtWidgets import QApplication
from views import LogViewer


def main():
    """主函数"""
    app = QApplication(sys.argv)
    viewer = LogViewer()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
