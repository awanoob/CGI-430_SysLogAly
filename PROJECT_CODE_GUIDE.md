# CGI-430_SysLogAly 工程说明文档

## 文档范围
- 本文档基于当前工程目录生成，覆盖源码与关键工程文件。
- 对 Python 文件给出：文件职责、类、函数、关键实例字段（self.xxx 及模块级关键对象）。
- 构建产物目录 build、dist、__pycache__ 不做代码级展开，仅在文件总览说明。

## 1. 文件总览

### 1.1 根目录关键文件
- .gitattributes：Git 属性配置。
- .gitignore：Git 忽略规则。
- config.py：全局配置（颜色、表头、数据库路径、筛选项数量）。
- main.py：程序入口。
- main.spec：PyInstaller 打包配置。
- CGI-430系统日志分析.exe.spec：可执行文件打包配置。
- log_config.db：日志解释规则数据库。
- run.log / run1.log / sys.log / test_sys.log / test_empty_line_sys.log：日志样例/运行日志。

### 1.2 源码目录
- models/
  - __init__.py
  - database.py
  - log_model.py
- utils/
  - __init__.py
  - log_parser.py
  - script_sandbox.py
- views/
  - __init__.py
  - dialogs.py
  - main_window.py
- functional_tests/
  - test_dock.py
  - test_statusbar.py

### 1.3 其他目录
- build/：打包中间产物。
- dist/：打包输出目录。
- __pycache__/：Python 缓存文件。

## 2. 各文件详细说明

## 2.1 main.py
### 文件职责
- 创建 QApplication。
- 创建并显示主窗口 LogViewer。
- 启动事件循环。

### 顶层函数
- main()：应用主流程入口。

### 关键实例
- app：QApplication 实例。
- viewer：LogViewer 主窗口实例。

## 2.2 config.py
### 文件职责
- 提供 UI 与业务公共配置常量。

### 常量
- LOG_COLORS：日志等级到背景色映射。
- DB_PATH：数据库文件路径（log_config.db）。
- TABLE_HEADERS：表头定义。
- LOG_LEVELS：等级筛选选项。
- MAX_FILTER_ITEMS_TIME：时间列筛选最大项。
- MAX_FILTER_ITEMS_OTHER：其他列筛选最大项。

## 2.3 models/__init__.py
### 文件职责
- 统一导出模型层对象。

### 导出对象
- LogTableModel
- LogFilterProxyModel
- LogDatabase

## 2.4 models/log_model.py
### 文件职责
- 提供表格数据模型与筛选代理模型（历史实现，当前主界面已主要使用 QTreeWidget）。

### 类
- LogTableModel(QAbstractTableModel)
  - __init__(logs)：保存 logs 与表头。
  - rowCount(parent)：返回行数。
  - columnCount(parent)：返回列数。
  - data(index, role)：返回单元格显示值与背景色。
  - headerData(section, orientation, role)：返回列头文本。
  - 关键实例字段：
    - self.logs
    - self.headers

- LogFilterProxyModel(QSortFilterProxyModel)
  - __init__()：初始化筛选条件。
  - filterAcceptsRow(source_row, source_parent)：按条件决定是否显示。
  - set_filters(level, module, function, content)：更新筛选条件。
  - 关键实例字段：
    - self.filter_level
    - self.filter_module
    - self.filter_function
    - self.filter_content

## 2.5 models/database.py
### 文件职责
- 管理日志解释规则数据库（SQLite）。
- 支持静态解释与脚本解释。
- 支持规则新增、更新、按优先级查询。

### 类
- LogDatabase
  - __init__(db_path=DB_PATH)：设置数据库路径。
  - connect()：建立数据库连接。
  - close()：关闭连接。
  - initialize()：建表、补字段、初始化默认规则。
  - _run_rule_script(script_code, level, module, func, line_no, content, default_remark)：执行脚本并兜底。
  - _query_rule_with_id(level, module, func, line_no="")：按优先级查询规则（含 id）。
  - _query_rule(level, module, func, line_no="")：按优先级查询 remark/script。
  - get_log_rule(level, module, func, line_no="")：返回完整规则 dict。
  - get_log_remark(level, module, func, line_no="", content="")：获取最终解释文本。
  - list_log_rules()：读取全部规则。
  - replace_log_rules(rules)：全量替换规则。
  - upsert_log_rule(level, module, func, line_no, remark, script_code="")：按键值新增/更新。
  - save_log_rule(rule_id, level, module, func, line_no, remark, script_code="")：按主键优先更新。
  - 关键实例字段：
    - self.db_path
    - self.conn

## 2.6 utils/__init__.py
### 文件职责
- 对外导出日志解析工具函数。

### 导出函数
- parse_log_line
- split_boot_sessions
- extract_version_info

## 2.7 utils/log_parser.py
### 文件职责
- 日志行解析。
- 上电分段。
- 版本信息提取。

### 顶层函数
- parse_log_line(line)：解析标准/非标准日志行。
- extract_year(datetime_str)：提取年份。
- is_boot_marker(parsed_log)：识别上电标记日志。
- split_boot_sessions(parsed_logs)：按上电周期分组。
- extract_version_info(parsed_logs)：提取 SN/PN/firmware/gnss board version。

## 2.8 utils/script_sandbox.py
### 文件职责
- 提供脚本执行白名单环境（测试与正式解析共用）。

### 顶层函数
- _safe_builtins()：返回允许的内建函数集合（如 map、range、sum、zip 等）。
- build_script_sandbox(extra_globals=None)：构造 exec/eval 沙箱字典。

## 2.9 views/__init__.py
### 文件职责
- 统一导出视图层对象。

### 导出对象
- LogViewer
- FilterDialog
- FindDialog

## 2.10 views/dialogs.py
### 文件职责
- 管理所有对话框：筛选、查找、规则编辑、脚本编辑、AI Prompt 生成、通知/界面设置等。

### 类与函数
- PlainPasteTextEdit(QTextEdit)
  - insertFromMimeData(source)：粘贴时强制纯文本。

- FilterDialog(QDialog)
  - __init__(parent=None)：构建筛选 UI。
  - get_filters()：返回筛选条件。
  - reset_filters()：重置筛选。
  - show_usage_help()：弹出筛选表达式说明。
  - event(event)：处理标题栏 ? 帮助按钮。
  - 关键实例：self.level_combo/self.module_edit/self.func_edit/self.content_edit

- FilterHintDialog(QDialog)
  - __init__(parent=None)：引导提示弹窗。
  - dont_show_again()：是否不再提示。
  - 关键实例：self.dont_show_check

- NotificationSettingsDialog(QDialog)
  - __init__(guide_enabled=True, parent=None)
  - get_settings()：返回通知设置。
  - 关键实例：self.guide_check

- InterfaceSettingsDialog(QDialog)
  - __init__(tree_bg_color="#ffffff", parent=None)
  - choose_color()：颜色选择。
  - get_settings()：返回界面设置。
  - 关键实例：self.current_color / self.color_preview

- FindDialog(QDialog)
  - __init__(parent=None)
  - get_search_params()
  - 关键实例：self.find_edit / self.case_sensitive

- RuleEditorDialog(QDialog)
  - __init__(db, parent=None)
  - load_rules()
  - _append_row(level, module, func, line_no, remark, script_code)
  - add_row()
  - delete_selected_rows()
  - _row_values(row)
  - edit_script_code()
  - save_rules()
  - 内部函数：_apply_script(new_code)（定义于 edit_script_code）
  - 关键实例：self.db / self.script_dialog / self.table

- ScriptCodeDialog(QDialog)
  - __init__(script_code="", parent=None)
  - get_code()
  - save_script()
  - test_script()
  - open_ai_prompt_builder()
  - 关键实例：self.code_edit / self.test_content_edit / self.test_default_remark_edit / self.test_result_edit / self.ai_prompt_dialog

- AIPromptBuilderDialog(QDialog)
  - __init__(parent=None)
  - generate_prompt()
  - copy_prompt()
  - 关键实例：self.logs_edit / self.extract_edit / self.rule_edit / self.format_edit / self.prompt_output

- QuickAddRuleDialog(QDialog)
  - __init__(default_rule, parent=None)
  - edit_script_code()
  - _apply_script_code(code)
  - save_rule()
  - get_rule_data()
  - 关键实例：
    - self.rule_id / self.is_edit_mode
    - self.script_code / self.script_dialog
    - self.level_edit / self.module_edit / self.function_edit / self.line_no_edit
    - self.remark_edit / self.script_status / self.test_content

## 2.11 views/main_window.py
### 文件职责
- 主界面与主交互逻辑。
- 日志加载、解析、分组渲染、筛选/查找、右键规则编辑、帮助页面、设置、最近文件管理等。

### 类
- LogTreeItemDelegate(QStyledItemDelegate)
  - paint(painter, option, index)
  - sizeHint(option, index)
  - createEditor(parent, option, index)
  - setEditorData(editor, index)
  - setModelData(editor, model, index)

- LogViewer(QMainWindow)
  - 初始化与界面：
    - __init__()
    - init_ui()
    - create_menu()
    - _build_tree_stylesheet(bg_color)
    - apply_tree_background_color(color_hex, persist=True)
    - create_dock_widgets()
    - on_detail_dock_visibility_changed(visible)
    - create_toolbar()
    - create_status_bar()
  - 帮助与菜单动作：
    - show_about_info()
    - check_upgrade()
    - build_help_html()
    - open_help_page()
  - 状态与设置：
    - is_rule_editor_open()
    - is_quick_add_open()
    - update_action_states()
    - show_notification_settings()
    - show_interface_settings()
  - 最近文件与路径：
    - update_recent_files_menu()
    - add_recent_file(file_path)
    - open_recent_file(index)
    - open_current_file_folder()
  - 文件与拖拽加载：
    - open_file()
    - _load_file_path(file_path)
    - dragEnterEvent(event)
    - dropEvent(event)
  - 日志处理：
    - load_logs(lines)
    - update_device_info(info)
    - render_sessions()
    - auto_resize_columns()
    - show_log_detail(item, _column)
  - 筛选相关：
    - show_filter_dialog()
    - visible_log_count()
    - apply_filters_to_tree()
    - match_row(row)
    - _tokenize_filter_expression(expression)
    - match_content_expression(expression, content)
    - clear_filters()
    - header_context_menu(pos)
    - apply_column_filter(column_index, value)
  - 查找与定位：
    - show_find_dialog()
    - find_next(params)
    - collect_visible_log_items()
    - jump_to_date()
    - set_date_expanded(expanded)
  - 分组展开与 sticky：
    - expand_all_sessions()
    - collapse_all_sessions()
    - _get_top_visible_item()
    - update_sticky_session_label()
    - sync_sticky_columns()
    - jump_to_sticky_session(*_args)
  - 右键与规则编辑：
    - show_rule_editor()
    - on_rule_editor_closed(*_args)
    - show_context_menu(pos)
    - toggle_log_detail_dock(checked)
    - copy_selected_row()
    - quick_add_log_rule(item)
    - on_quick_add_closed(*_args)
    - save_quick_add_rule(payload, item)
  - 生命周期：
    - closeEvent(event)

  - 关键实例字段（部分）
    - 基础对象：self.settings / self.db / self.tree / self.sticky_tree / self.log_detail / self.detail_dock
    - 业务状态：self.sessions / self.current_filters / self.last_search_pos
    - sticky 状态：self.current_sticky_session_item / self.current_sticky_text / self.suspend_sticky_updates
    - 对话框互斥：self.rule_editor_dialog / self.quick_add_dialog
    - 文件与最近记录：self.current_file_path / self.recent_files / self.recent_menu / self.recent_file_actions
    - 设置项：self.guide_prompts_enabled / self.filter_hint_suppressed / self.tree_bg_color
    - 菜单动作：self.edit_rules_action / self.open_folder_action / self.toggle_detail_action

## 2.12 functional_tests/test_dock.py
### 文件职责
- PyQt Dock 主从关系与 tab 切换统计的功能示例/测试脚本。

### 类
- FileDock(QDockWidget)
  - __init__(filename, content)
  - 信号：activated
  - 实例：self.editor

- InfoDock(QDockWidget)
  - __init__()
  - update_info(text)
  - 实例：self.label

- MainWindow(QMainWindow)
  - __init__()
  - add_file_dock(filename, content)
  - _install_tab_changed_handler()
  - _on_tab_changed(index)
  - on_file_activated(dock)
  - 实例：self.infoDock / self.fileDocks

## 2.13 functional_tests/test_statusbar.py
### 文件职责
- 状态栏组件示例/测试脚本。

### 类
- Main(QMainWindow)
  - __init__()：创建状态栏、左侧状态标签、右侧永久控件与进度条。

## 3. 维护建议
- 对高复杂模块（views/main_window.py、views/dialogs.py）建议持续补充方法 docstring。
- 若后续继续扩大功能，建议把设置管理、最近文件管理、筛选表达式解析拆分到独立模块。
- 可在 CI 中加入文档自动生成步骤，避免说明与代码脱节。
