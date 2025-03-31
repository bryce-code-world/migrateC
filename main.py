#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
C盘大文件迁移工具

该工具用于迁移C盘下的大文件夹到目标路径，并创建软链接，从而释放C盘空间。
"""

import sys
import os
import logging
import yaml
import json
import threading
import multiprocessing
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, \
    QPushButton, QTextEdit, QLabel, QProgressBar, QMessageBox, QFileDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QTextCursor

# 导入自定义模块
from modules.scanner import Scanner
from modules.migrator import Migrator
from modules.cleaner import Cleaner
from modules.linker import Linker
from modules.utils import is_admin, setup_logger, get_optimal_thread_count


class WorkerThread(QThread):
    """工作线程，用于执行耗时操作"""
    update_signal = pyqtSignal(str)  # 更新信号，用于向UI发送消息
    progress_signal = pyqtSignal(int)  # 进度信号，用于更新进度条
    finished_signal = pyqtSignal(bool, str)  # 完成信号，参数为是否成功和消息

    def __init__(self, task_type, config, parent=None):
        """
        初始化工作线程
        
        Args:
            task_type: 任务类型（'scan', 'migrate', 'clean', 'link', 'all'）
            config: 配置信息
            parent: 父对象
        """
        super().__init__(parent)
        self.task_type = task_type
        self.config = config
        self.logger = logging.getLogger('MigrateC')
        self.is_running = True

    def run(self):
        """运行线程"""
        try:
            if self.task_type == 'scan':
                self._run_scan()
            elif self.task_type == 'migrate':
                self._run_migrate()
            elif self.task_type == 'clean':
                self._run_clean()
            elif self.task_type == 'link':
                self._run_link()
            elif self.task_type == 'all':
                self._run_all()
            else:
                self.update_signal.emit(f"未知任务类型: {self.task_type}")
                self.finished_signal.emit(False, f"未知任务类型: {self.task_type}")
        except Exception as e:
            self.logger.exception(f"任务执行出错: {str(e)}")
            self.update_signal.emit(f"任务执行出错: {str(e)}")
            self.finished_signal.emit(False, f"任务执行出错: {str(e)}")

    def _run_scan(self):
        """运行扫描任务"""
        self.update_signal.emit("开始扫描大文件夹...")
        
        # 创建扫描器
        scanner = Scanner(
            scan_paths=self.config['scan']['scan_paths'],
            size_threshold=self.config['scan']['size_threshold'],
            output_file=self.config['scan']['output_file'],
            max_threads=self.config['performance']['max_threads'],
            update_callback=lambda msg: self.update_signal.emit(msg),
            progress_callback=lambda progress: self.progress_signal.emit(progress),
            exclude_folders=self.config['scan'].get('exclude_folders', [])
        )
        
        # 执行扫描
        success = scanner.scan()
        
        if success:
            self.update_signal.emit(f"扫描完成，结果已保存到 {self.config['scan']['output_file']}")
            self.finished_signal.emit(True, "扫描完成")
        else:
            self.update_signal.emit("扫描失败")
            self.finished_signal.emit(False, "扫描失败")

    def _run_migrate(self):
        """运行迁移任务"""
        self.update_signal.emit("开始迁移文件夹...")
        
        # 检查扫描结果文件是否存在
        if not os.path.exists(self.config['scan']['output_file']):
            self.update_signal.emit(f"扫描结果文件不存在: {self.config['scan']['output_file']}")
            self.finished_signal.emit(False, "扫描结果文件不存在")
            return
        
        # 创建迁移器
        migrator = Migrator(
            scan_result_file=self.config['scan']['output_file'],
            target_path=self.config['migration']['target_path'],
            temp_path=self.config['migration']['temp_path'],
            mapping_file=self.config['migration']['mapping_file'],
            max_threads=self.config['performance']['max_threads'],
            update_callback=lambda msg: self.update_signal.emit(msg),
            progress_callback=lambda progress: self.progress_signal.emit(progress)
        )
        
        # 执行迁移
        success = migrator.migrate()
        
        if success:
            self.update_signal.emit(f"迁移完成，映射已保存到 {self.config['migration']['mapping_file']}")
            self.finished_signal.emit(True, "迁移完成")
        else:
            self.update_signal.emit("迁移失败")
            self.finished_signal.emit(False, "迁移失败")

    def _run_clean(self):
        """运行清理任务"""
        self.update_signal.emit("开始清理原文件夹...")
        
        # 检查映射文件是否存在
        if not os.path.exists(self.config['migration']['mapping_file']):
            self.update_signal.emit(f"映射文件不存在: {self.config['migration']['mapping_file']}")
            self.finished_signal.emit(False, "映射文件不存在")
            return
        
        # 创建清理器
        cleaner = Cleaner(
            mapping_file=self.config['migration']['mapping_file'],
            retry_count=self.config['cleanup']['retry_count'],
            retry_interval=self.config['cleanup']['retry_interval'],
            update_callback=lambda msg: self.update_signal.emit(msg),
            progress_callback=lambda progress: self.progress_signal.emit(progress)
        )
        
        # 执行清理
        success = cleaner.clean()
        
        if success:
            self.update_signal.emit("清理完成")
            self.finished_signal.emit(True, "清理完成")
        else:
            self.update_signal.emit("清理失败，请查看日志获取详细信息")
            self.finished_signal.emit(False, "清理失败")

    def _run_link(self):
        """运行链接任务"""
        self.update_signal.emit("开始创建软链接...")
        
        # 检查映射文件是否存在
        if not os.path.exists(self.config['migration']['mapping_file']):
            self.update_signal.emit(f"映射文件不存在: {self.config['migration']['mapping_file']}")
            self.finished_signal.emit(False, "映射文件不存在")
            return
        
        # 检查是否有管理员权限
        if not is_admin():
            self.update_signal.emit("创建软链接需要管理员权限，请以管理员身份运行程序")
            self.finished_signal.emit(False, "需要管理员权限")
            return
        
        # 创建链接器
        linker = Linker(
            mapping_file=self.config['migration']['mapping_file'],
            check_timeout=self.config['link']['check_timeout'],
            update_callback=lambda msg: self.update_signal.emit(msg),
            progress_callback=lambda progress: self.progress_signal.emit(progress)
        )
        
        # 执行链接
        success = linker.create_links()
        
        if success:
            self.update_signal.emit("软链接创建完成")
            self.finished_signal.emit(True, "软链接创建完成")
        else:
            self.update_signal.emit("软链接创建失败，请查看日志获取详细信息")
            self.finished_signal.emit(False, "软链接创建失败")

    def _run_all(self):
        """运行所有任务"""
        # 扫描
        self.update_signal.emit("===== 步骤1: 扫描大文件夹 =====")
        self._run_scan()
        
        # 迁移
        self.update_signal.emit("\n===== 步骤2: 迁移文件夹 =====")
        self._run_migrate()
        
        # 清理
        self.update_signal.emit("\n===== 步骤3: 清理原文件夹 =====")
        self._run_clean()
        
        # 链接
        self.update_signal.emit("\n===== 步骤4: 创建软链接 =====")
        self._run_link()
        
        self.update_signal.emit("\n所有任务执行完成！")
        self.finished_signal.emit(True, "所有任务执行完成")

    def stop(self):
        """停止线程"""
        self.is_running = False


class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        
        # 加载配置
        self.config = self._load_config()
        
        # 设置日志
        self.logger = setup_logger(
            log_file=self.config['logging']['log_file'],
            log_level=self.config['logging']['log_level']
        )
        
        # 创建必要的目录
        self._create_directories()
        
        # 初始化UI
        self._init_ui()
        
        # 工作线程
        self.worker_thread = None
        
        # 检查管理员权限
        if not is_admin():
            self.log_message("警告: 程序未以管理员身份运行，某些功能可能无法正常工作")

    def _load_config(self):
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # 处理用户名变量
            for i, path_info in enumerate(config['scan']['scan_paths']):
                if isinstance(path_info, dict) and 'path' in path_info:
                    config['scan']['scan_paths'][i]['path'] = path_info['path'].replace('%USERNAME%', os.environ['USERNAME'])
                elif isinstance(path_info, str):
                    # 兼容旧格式
                    config['scan']['scan_paths'][i] = {
                        'path': path_info.replace('%USERNAME%', os.environ['USERNAME']),
                        'max_depth': 3  # 默认深度
                    }
                
            # 处理相对路径
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for section in ['scan', 'migration', 'logging']:
                for key in config[section]:
                    if isinstance(config[section][key], str) and config[section][key].startswith('./'):
                        config[section][key] = os.path.normpath(os.path.join(base_dir, config[section][key]))
            
            # 设置最大线程数
            if config['performance']['max_threads'] == 0:
                config['performance']['max_threads'] = get_optimal_thread_count()
                
            return config
        except Exception as e:
            print(f"加载配置文件失败: {str(e)}")
            sys.exit(1)

    def _create_directories(self):
        """创建必要的目录"""
        directories = [
            os.path.dirname(self.config['logging']['log_file']),
            os.path.dirname(self.config['scan']['output_file']),
            os.path.dirname(self.config['migration']['mapping_file']),
            self.config['migration']['temp_path']
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("C盘大文件迁移工具")
        self.setMinimumSize(800, 600)
        
        # 主布局
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        
        # 左侧控制面板
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setMaximumWidth(200)
        
        # 添加按钮
        self.scan_btn = QPushButton("1.扫描大文件")
        self.migrate_btn = QPushButton("2.迁移大文件")
        self.clean_btn = QPushButton("3.清理原文件")
        self.link_btn = QPushButton("4.创建软链接")
        self.all_btn = QPushButton("执行所有步骤")
        self.stop_btn = QPushButton("停止当前任务")
        self.config_btn = QPushButton("修改配置")
        
        # 设置按钮点击事件
        self.scan_btn.clicked.connect(lambda: self._start_task('scan'))
        self.migrate_btn.clicked.connect(lambda: self._start_task('migrate'))
        self.clean_btn.clicked.connect(lambda: self._start_task('clean'))
        self.link_btn.clicked.connect(lambda: self._start_task('link'))
        self.all_btn.clicked.connect(lambda: self._start_task('all'))
        self.stop_btn.clicked.connect(self._stop_task)
        self.config_btn.clicked.connect(self._open_config)
        
        # 初始状态下停止按钮不可用
        self.stop_btn.setEnabled(False)
        
        # 添加按钮到控制面板
        control_layout.addWidget(QLabel("操作："))
        control_layout.addWidget(self.scan_btn)
        control_layout.addWidget(self.migrate_btn)
        control_layout.addWidget(self.clean_btn)
        control_layout.addWidget(self.link_btn)
        control_layout.addWidget(self.all_btn)
        control_layout.addSpacing(20)
        control_layout.addWidget(self.stop_btn)
        control_layout.addSpacing(20)
        control_layout.addWidget(self.config_btn)
        control_layout.addStretch()
        
        # 右侧信息面板
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        
        # 日志显示区域
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        
        # 进度条
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("进度："))
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        # 添加控件到信息面板
        info_layout.addWidget(QLabel("日志信息："))
        info_layout.addWidget(self.log_area)
        info_layout.addLayout(progress_layout)
        
        # 添加面板到主布局
        main_layout.addWidget(control_panel)
        main_layout.addWidget(info_panel)
        
        # 设置中央窗口部件
        self.setCentralWidget(main_widget)
        
        # 显示初始信息
        self.log_message("C盘大文件迁移工具已启动")
        self.log_message(f"配置已加载，最大线程数: {self.config['performance']['max_threads']}")
        if not is_admin():
            self.log_message("警告: 程序未以管理员身份运行，创建软链接功能将无法使用")

    def log_message(self, message):
        """记录消息到日志区域"""
        self.log_area.append(message)
        # 滚动到底部
        self.log_area.moveCursor(QTextCursor.End)
        # 同时记录到日志文件
        self.logger.info(message)

    def _start_task(self, task_type):
        """启动任务"""
        # 如果已有任务在运行，则不启动新任务
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.warning(self, "警告", "有任务正在运行，请等待当前任务完成或停止当前任务")
            return
        
        # 创建并启动工作线程
        self.worker_thread = WorkerThread(task_type, self.config, self)
        self.worker_thread.update_signal.connect(self.log_message)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self._on_task_finished)
        
        # 更新UI状态
        self._set_buttons_enabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # 启动线程
        self.worker_thread.start()

    def _stop_task(self):
        """停止当前任务"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(self, "确认", "确定要停止当前任务吗？", 
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.log_message("正在停止任务...")
                self.worker_thread.stop()
                self.worker_thread.wait(3000)  # 等待最多3秒
                if self.worker_thread.isRunning():
                    self.worker_thread.terminate()  # 强制终止
                self._set_buttons_enabled(True)
                self.stop_btn.setEnabled(False)
                self.log_message("任务已停止")

    def _on_task_finished(self, success, message):
        """任务完成回调"""
        self._set_buttons_enabled(True)
        self.stop_btn.setEnabled(False)
        
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.critical(self, "错误", message)

    def _set_buttons_enabled(self, enabled):
        """设置按钮启用状态"""
        self.scan_btn.setEnabled(enabled)
        self.migrate_btn.setEnabled(enabled)
        self.clean_btn.setEnabled(enabled)
        self.link_btn.setEnabled(enabled)
        self.all_btn.setEnabled(enabled)
        self.config_btn.setEnabled(enabled)

    def _open_config(self):
        """打开配置文件"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        os.startfile(config_path)


if __name__ == "__main__":
    # 创建应用
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    sys.exit(app.exec_())