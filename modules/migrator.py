#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
迁移模块

用于将大文件夹压缩、移动到目标路径并解压
"""

import os
import json
import shutil
import zipfile
import logging
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# 导入资源监控模块
from modules.resource_monitor import ResourceMonitor


class Migrator:
    """文件夹迁移器"""
    
    def __init__(self, scan_result_file, target_path, temp_path, mapping_file, max_threads=4,
                 update_callback=None, progress_callback=None, cpu_limit=0.5, memory_limit=0.5):
        """
        初始化迁移器
        
        Args:
            scan_result_file: 扫描结果文件路径
            target_path: 目标路径
            temp_path: 临时路径（用于存放压缩文件）
            mapping_file: 映射文件路径
            max_threads: 最大线程数
            update_callback: 更新回调函数
            progress_callback: 进度回调函数
            cpu_limit: CPU使用限制，范围0-1，表示可使用的CPU核心数比例
            memory_limit: 内存使用限制，范围0-1，表示可使用的系统内存比例
        """
        self.scan_result_file = scan_result_file
        self.target_path = target_path
        self.temp_path = temp_path
        self.mapping_file = mapping_file
        self.max_threads = max_threads
        self.update_callback = update_callback
        self.progress_callback = progress_callback
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.logger = logging.getLogger('MigrateC.Migrator')
        self.path_mapping = {}  # 路径映射
        self.lock = threading.Lock()  # 线程锁
        self.total_folders = 0  # 总文件夹数
        self.processed_folders = 0  # 已处理文件夹数
        self.is_running = True  # 运行标志
        
        # 创建资源监控器
        self.resource_monitor = ResourceMonitor(
            cpu_limit=self.cpu_limit,
            memory_limit=self.memory_limit,
            check_interval=1.0
        )
    
    def migrate(self):
        """
        执行迁移
        
        Returns:
            bool: 是否成功
        """
        try:
            # 启动资源监控
            self.resource_monitor.start_monitoring()
            self._update(f"资源监控已启动，CPU限制: {self.cpu_limit*100:.0f}%，内存限制: {self.memory_limit*100:.0f}%", "资源监控")
            
            # 确保目录存在
            os.makedirs(self.target_path, exist_ok=True)
            os.makedirs(self.temp_path, exist_ok=True)
            os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
            self._update("已创建必要的目录", "初始化")
            
            # 加载扫描结果
            self._update(f"正在加载扫描结果: {self.scan_result_file}", "初始化")
            scan_result = self._load_scan_result()
            if not scan_result:
                self.resource_monitor.stop_monitoring()
                return False
                
            # 检查目标磁盘空间是否足够
            if not self._check_disk_space(scan_result):
                self.resource_monitor.stop_monitoring()
                return False
            
            # 检查目标磁盘空间是否足够
            if not self._check_disk_space(scan_result):
                self.resource_monitor.stop_monitoring()
                return False
            
            # 获取大文件夹列表
            large_folders = scan_result.get('large_folders', [])
            # 获取大文件列表
            large_files = scan_result.get('large_files', [])
            
            # 计算总迁移项目数
            self.total_folders = len(large_folders) + len(large_files)
            
            if self.total_folders == 0:
                self._update("没有找到需要迁移的大文件夹或大文件", "任务完成")
                self.resource_monitor.stop_monitoring()
                return True
            
            self._update(f"开始迁移 {len(large_folders)} 个大文件夹和 {len(large_files)} 个大文件，总计 {self.total_folders} 项", "任务开始")
            
            # 更新进度
            if self.progress_callback:
                self.progress_callback(0)
            
            # 根据资源监控器获取最大线程数
            max_threads = self.resource_monitor.get_max_threads()
            self._update(f"根据系统资源限制，使用 {max_threads} 个线程进行迁移（最大允许: {self.max_threads}）", "任务配置")
            
            # 使用线程池迁移文件夹和文件
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                # 迁移文件夹
                if large_folders:
                    self._update(f"开始迁移 {len(large_folders)} 个大文件夹", "文件夹迁移")
                    for folder_info in large_folders:
                        if not self.is_running:
                            break
                        
                        # 检查资源使用情况，如果资源紧张则等待
                        while self.is_running and self.resource_monitor.should_throttle():
                            self._update("系统资源使用率较高，暂停提交新任务...", "资源限制")
                            if not self.resource_monitor.wait_for_resources(timeout=5):
                                break
                        
                        folder_path = folder_info['path']
                        executor.submit(self._migrate_folder, folder_path)
                
                # 迁移文件
                if large_files:
                    self._update(f"开始迁移 {len(large_files)} 个大文件", "文件迁移")
                    for file_info in large_files:
                        if not self.is_running:
                            break
                        
                        # 检查资源使用情况，如果资源紧张则等待
                        while self.is_running and self.resource_monitor.should_throttle():
                            self._update("系统资源使用率较高，暂停提交新任务...", "资源限制")
                            if not self.resource_monitor.wait_for_resources(timeout=5):
                                break
                        
                        file_path = file_info['path']
                        executor.submit(self._migrate_file, file_path)
            
            # 保存映射
            if self.is_running:
                self._save_mapping()
                self._update(f"迁移完成，共迁移 {len(self.path_mapping)} 个项目", "任务完成")
                if self.progress_callback:
                    self.progress_callback(100)
                self.resource_monitor.stop_monitoring()
                return True
            else:
                self._update("迁移已取消", "任务中断")
                self.resource_monitor.stop_monitoring()
                return False
                
        except Exception as e:
            self.logger.exception(f"迁移出错: {str(e)}")
            self._update(f"迁移出错: {str(e)}", "任务错误")
            self.resource_monitor.stop_monitoring()
            return False
    
    def _load_scan_result(self):
        """
        加载扫描结果
        
        Returns:
            dict: 扫描结果
        """
        try:
            with open(self.scan_result_file, 'r', encoding='utf-8') as f:
                result = json.load(f)
                self._update(f"扫描结果加载成功", "数据加载")
                return result
        except Exception as e:
            self.logger.exception(f"加载扫描结果出错: {str(e)}")
            self._update(f"加载扫描结果出错: {str(e)}", "数据加载错误")
            return None
    
    def _migrate_file(self, file_path):
        """
        迁移单个文件
        
        Args:
            file_path: 文件路径
        """
        try:
            if not os.path.exists(file_path):
                self._update(f"文件不存在: {file_path}", "文件检查")
                return
            
            # 获取文件名称和大小
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # 构建目标路径，保持原始路径结构
            relative_path = self._get_relative_path(file_path)
            target_file = os.path.join(self.target_path, relative_path)
            
            # 创建目标文件夹
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            
            # 复制文件到目标路径
            self._update(f"开始复制: {file_name} -> {target_file}，大小: {self._format_size(file_size)}", "文件复制")
            
            # 使用分块复制大文件，并显示进度
            if file_size > 10 * 1024 * 1024:  # 大于10MB的文件显示进度
                self._copy_file_with_progress(file_path, target_file, file_size)
            else:
                shutil.copy2(file_path, target_file)
            
            # 添加到映射
            with self.lock:
                self.path_mapping[file_path] = target_file
                self.processed_folders += 1
                progress = int(self.processed_folders / max(1, self.total_folders) * 100)
                if self.progress_callback and progress <= 100:
                    self.progress_callback(progress)
            
            self._update(f"复制完成: {file_name} -> {target_file}", "文件复制")
            
        except Exception as e:
            self.logger.exception(f"迁移文件出错: {file_path}, {str(e)}")
            self._update(f"复制失败: {file_name}, 错误: {str(e)}", "文件复制错误")
            
    def _copy_file_with_progress(self, src_file, dst_file, file_size):
        """
        带进度显示的文件复制
        
        Args:
            src_file: 源文件路径
            dst_file: 目标文件路径
            file_size: 文件大小
        """
        import time
        try:
            # 分块大小：1MB
            chunk_size = 1024 * 1024
            copied_size = 0
            last_progress_time = 0
            start_time = time.time()  # 记录开始时间
            file_name = os.path.basename(src_file)
            
            with open(src_file, 'rb') as src, open(dst_file, 'wb') as dst:
                while True:
                    if not self.is_running:
                        return
                        
                    # 读取数据块
                    chunk = src.read(chunk_size)
                    if not chunk:
                        break
                        
                    # 写入数据块
                    dst.write(chunk)
                    
                    # 更新进度
                    copied_size += len(chunk)
                    
                    # 每秒最多更新一次进度，避免频繁更新
                    current_time = self._get_current_time_ms()
                    if current_time - last_progress_time > 1000 or copied_size == file_size:
                        progress_percent = int(copied_size / file_size * 100)
                        
                        # 计算预估剩余时间
                        elapsed_time = time.time() - start_time
                        if copied_size > 0 and elapsed_time > 0:
                            speed = copied_size / elapsed_time  # 字节/秒
                            remaining_size = file_size - copied_size
                            if speed > 0:
                                remaining_time = remaining_size / speed
                                remaining_str = self._format_time(remaining_time)
                                speed_str = self._format_size(speed) + "/秒"
                                
                                self._update(f"{file_name}: {self._format_size(copied_size)}/{self._format_size(file_size)} ({progress_percent}%)，"
                                           f"速度: {speed_str}，剩余: {remaining_str}", "文件复制进度")
                            else:
                                self._update(f"{file_name}: {self._format_size(copied_size)}/{self._format_size(file_size)} ({progress_percent}%)", "文件复制进度")
                        else:
                            self._update(f"{file_name}: {self._format_size(copied_size)}/{self._format_size(file_size)} ({progress_percent}%)", "文件复制进度")
                            
                        last_progress_time = current_time
            
            # 计算总耗时
            total_time = time.time() - start_time
            time_str = self._format_time(total_time)
            self._update(f"{file_name} 复制完成，大小: {self._format_size(file_size)}，耗时: {time_str}", "文件复制完成")
            
            # 复制文件属性
            shutil.copystat(src_file, dst_file)
            
        except Exception as e:
            self.logger.exception(f"复制文件出错: {src_file}, {str(e)}")
            self._update(f"{file_name} 复制失败: {str(e)}", "文件复制错误")
            raise
    
    def _migrate_folder(self, folder_path):
        """
        迁移文件夹
        
        Args:
            folder_path: 文件夹路径
        """
        try:
            if not os.path.exists(folder_path):
                self._update(f"文件夹不存在: {folder_path}", "文件夹检查")
                return
            
            # 获取文件夹名称
            folder_name = os.path.basename(folder_path)
            
            # 构建目标路径
            # 保持原始路径结构，例如：C:\Program Files\Docker -> D:\C_backup\Program Files\Docker
            relative_path = self._get_relative_path(folder_path)
            target_folder = os.path.join(self.target_path, relative_path)
            
            # 构建临时压缩文件路径
            zip_file = os.path.join(self.temp_path, f"{folder_name}.zip")
            
            # 压缩文件夹
            self._update(f"开始压缩文件夹: {folder_name} ({folder_path})", "文件夹压缩")
            if not self._compress_folder(folder_path, zip_file):
                return
            
            # 创建目标文件夹
            os.makedirs(os.path.dirname(target_folder), exist_ok=True)
            
            # 解压文件到目标路径
            self._update(f"开始解压文件夹: {folder_name} 到 {target_folder}", "文件夹解压")
            if not self._extract_zip(zip_file, os.path.dirname(target_folder)):
                return
            
            # 删除临时压缩文件
            try:
                os.remove(zip_file)
                self._update(f"已删除临时压缩文件: {zip_file}", "清理临时文件")
            except Exception as e:
                self.logger.warning(f"删除临时压缩文件出错: {zip_file}, {str(e)}")
                self._update(f"删除临时文件失败: {zip_file}, {str(e)}", "清理临时文件")
            
            # 添加到映射
            with self.lock:
                self.path_mapping[folder_path] = target_folder
                self.processed_folders += 1
                progress = int(self.processed_folders / max(1, self.total_folders) * 100)
                if self.progress_callback and progress <= 100:
                    self.progress_callback(progress)
            
            self._update(f"文件夹迁移完成: {folder_name} ({folder_path}) -> {target_folder}", "文件夹迁移")
            
        except Exception as e:
            self.logger.exception(f"迁移文件夹出错: {folder_path}, {str(e)}")
            self._update(f"文件夹迁移失败: {folder_name} ({folder_path}), 错误: {str(e)}", "文件夹迁移错误")
    
    def _get_relative_path(self, folder_path):
        """
        获取相对路径
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            str: 相对路径
        """
        # 去除盘符，例如：C:\Program Files\Docker -> Program Files\Docker
        drive, path = os.path.splitdrive(folder_path)
        if path.startswith('\\'):
            path = path[1:]
        return path
    
    def _compress_folder(self, folder_path, zip_file):
        """
        压缩文件夹
        
        Args:
            folder_path: 文件夹路径
            zip_file: 压缩文件路径
            
        Returns:
            bool: 是否成功
        """
        import time
        try:
            # 创建临时目录
            os.makedirs(os.path.dirname(zip_file), exist_ok=True)
            
            # 获取当前资源使用情况和最大线程数
            max_threads = self.resource_monitor.get_max_threads()
            
            # 先统计文件总数和总大小，用于显示进度
            total_files = 0
            total_size = 0
            file_list = []
            scanned_dirs = 0
            last_scan_update_time = 0
            start_time = time.time()  # 记录开始时间
            folder_name = os.path.basename(folder_path)
            
            self._update(f"开始统计: {folder_name} 中的文件数量和大小...", "文件夹扫描")
            for root, dirs, files in os.walk(folder_path):
                if not self.is_running:
                    return False
                
                # 更新扫描进度
                scanned_dirs += 1
                current_time = self._get_current_time_ms()
                if current_time - last_scan_update_time > 300:  # 每300毫秒更新一次扫描进度
                    self._update(f"{folder_name}: 已扫描 {scanned_dirs} 个目录，找到 {total_files} 个文件，总大小 {self._format_size(total_size)}", "文件夹扫描")
                    last_scan_update_time = current_time
                    
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        rel_path = os.path.relpath(root, os.path.dirname(folder_path))
                        arcname = os.path.join(rel_path, file)
                        file_list.append((file_path, arcname, file_size))
                        total_files += 1
                        total_size += file_size
                    except Exception as e:
                        self.logger.warning(f"获取文件信息出错: {file_path}, {str(e)}")
                        self._update(f"获取文件信息失败: {file_path}, {str(e)}", "文件夹扫描错误")
            
            if total_files == 0:
                self._update(f"文件夹 {folder_name} 中没有文件", "文件夹扫描")
                return True
                
            self._update(f"开始压缩: {folder_name}，共 {total_files} 个文件，总大小 {self._format_size(total_size)}", "文件夹压缩")
            
            # 创建压缩文件
            processed_files = 0
            processed_size = 0
            last_progress_time = 0  # 上次更新进度的时间
            last_file_update_time = 0  # 上次更新文件名的时间
            update_interval = 300  # 更新间隔降低到300毫秒
            
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 添加文件到压缩文件
                for file_path, arcname, file_size in file_list:
                    # 如果任务被取消，则立即返回
                    if not self.is_running:
                        return False
                    
                    try:
                        # 显示当前正在处理的文件名和大小
                        current_time = self._get_current_time_ms()
                        if current_time - last_file_update_time > 500:  # 每500毫秒更新一次当前处理的文件
                            file_name = os.path.basename(file_path)
                            formatted_size = self._format_size(file_size)
                            self._update(f"正在压缩: {file_name} ({processed_files+1}/{total_files})，大小: {formatted_size}", "文件压缩")
                            last_file_update_time = current_time
                            
                        # 添加文件到压缩文件
                        zipf.write(file_path, arcname)
                        
                        # 更新进度
                        processed_files += 1
                        processed_size += file_size
                        
                        # 降低更新间隔，提高进度更新频率
                        current_time = self._get_current_time_ms()
                        if current_time - last_progress_time > update_interval or processed_files == total_files:
                            progress_percent = int(processed_size / total_size * 100)
                            
                            # 计算预估剩余时间
                            elapsed_time = time.time() - start_time
                            if processed_size > 0 and elapsed_time > 0:
                                speed = processed_size / elapsed_time  # 字节/秒
                                remaining_size = total_size - processed_size
                                if speed > 0:
                                    remaining_time = remaining_size / speed
                                    remaining_str = self._format_time(remaining_time)
                                    speed_str = self._format_size(speed) + "/秒"
                                    
                                    self._update(f"{folder_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                               f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}，"
                                               f"速度: {speed_str}，剩余: {remaining_str}", "文件夹压缩进度")
                                else:
                                    self._update(f"{folder_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                               f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}", "文件夹压缩进度")
                            else:
                                self._update(f"{folder_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                           f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}", "文件夹压缩进度")
                                
                            last_progress_time = current_time
                            
                            # 更新总体进度条
                            if self.progress_callback:
                                # 压缩过程占总进度的一半
                                sub_progress = int(progress_percent / 2)
                                folder_progress = int(self.processed_folders / max(1, self.total_folders) * 100)
                                self.progress_callback(min(folder_progress + sub_progress, 99))
                    except Exception as e:
                        self.logger.warning(f"添加文件到压缩文件出错: {file_path}, {str(e)}")
                        self._update(f"压缩文件失败: {os.path.basename(file_path)}, {str(e)}", "文件压缩错误")
            
            # 计算总耗时
            total_time = time.time() - start_time
            time_str = self._format_time(total_time)
            self._update(f"{folder_name} 压缩完成: {processed_files}/{total_files} 文件，大小 {self._format_size(processed_size)}，耗时: {time_str}", "文件夹压缩完成")
            return True
        except Exception as e:
            self.logger.exception(f"压缩文件夹出错: {folder_path}, {str(e)}")
            self._update(f"压缩文件夹失败: {os.path.basename(folder_path)}, 错误: {str(e)}", "文件夹压缩错误")
            return False
    
    def _extract_zip(self, zip_file, target_dir):
        """
        解压文件
        
        Args:
            zip_file: 压缩文件路径
            target_dir: 目标目录
            
        Returns:
            bool: 是否成功
        """
        import time
        try:
            # 创建目标目录
            os.makedirs(target_dir, exist_ok=True)
            
            # 获取压缩文件信息
            zip_name = os.path.basename(zip_file)
            with zipfile.ZipFile(zip_file, 'r') as zipf:
                file_list = zipf.infolist()
                total_files = len(file_list)
                total_size = sum(file_info.file_size for file_info in file_list)
                
                if total_files == 0:
                    self._update(f"压缩文件 {zip_name} 中没有文件", "文件解压")
                    return True
                    
                self._update(f"开始解压: {zip_name}，共 {total_files} 个文件，总大小 {self._format_size(total_size)}", "文件解压")
                
                # 解压文件
                processed_files = 0
                processed_size = 0
                last_progress_time = 0
                last_file_update_time = 0  # 上次更新文件名的时间
                update_interval = 300  # 更新间隔降低到300毫秒
                start_time = time.time()  # 记录开始时间
                
                for file_info in file_list:
                    # 如果任务被取消，则立即返回
                    if not self.is_running:
                        return False
                    
                    # 显示当前正在处理的文件名和大小
                    current_time = self._get_current_time_ms()
                    if current_time - last_file_update_time > 500:  # 每500毫秒更新一次当前处理的文件
                        file_name = file_info.filename
                        file_size = file_info.file_size
                        formatted_size = self._format_size(file_size)
                        self._update(f"正在解压: {file_name} ({processed_files+1}/{total_files})，大小: {formatted_size}", "文件解压")
                        last_file_update_time = current_time
                        
                    # 解压单个文件
                    zipf.extract(file_info, target_dir)
                    
                    # 更新进度
                    processed_files += 1
                    processed_size += file_info.file_size
                    
                    # 降低更新间隔，提高进度更新频率
                    current_time = self._get_current_time_ms()
                    if current_time - last_progress_time > update_interval or processed_files == total_files:
                        progress_percent = int(processed_size / total_size * 100)
                        
                        # 计算预估剩余时间
                        elapsed_time = time.time() - start_time
                        if processed_size > 0 and elapsed_time > 0:
                            speed = processed_size / elapsed_time  # 字节/秒
                            remaining_size = total_size - processed_size
                            if speed > 0:
                                remaining_time = remaining_size / speed
                                remaining_str = self._format_time(remaining_time)
                                speed_str = self._format_size(speed) + "/秒"
                                
                                self._update(f"{zip_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                           f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}，"
                                           f"速度: {speed_str}，剩余: {remaining_str}", "文件解压进度")
                            else:
                                self._update(f"{zip_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                           f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}", "文件解压进度")
                        else:
                            self._update(f"{zip_name}: {processed_files}/{total_files} 文件 ({progress_percent}%)，"
                                       f"已处理 {self._format_size(processed_size)}/{self._format_size(total_size)}", "文件解压进度")
                            
                        last_progress_time = current_time
                        
                        # 更新总体进度条
                        if self.progress_callback:
                            # 解压过程占总进度的一半
                            sub_progress = int(progress_percent / 2) + 50  # 解压是第二阶段，从50%开始
                            folder_progress = int(self.processed_folders / max(1, self.total_folders) * 100)
                            self.progress_callback(min(folder_progress + sub_progress, 99))
                
                # 计算总耗时
                total_time = time.time() - start_time
                time_str = self._format_time(total_time)
                self._update(f"{zip_name} 解压完成: {processed_files}/{total_files} 文件，大小 {self._format_size(processed_size)}，耗时: {time_str}", "文件解压完成")
            
            return True
        except Exception as e:
            self.logger.exception(f"解压文件出错: {zip_file}, {str(e)}")
            self._update(f"解压失败: {os.path.basename(zip_file)}, 错误: {str(e)}", "文件解压错误")
            return False
    
    def _save_mapping(self):
        """
        保存映射到文件
        """
        try:
            # 保存为JSON文件
            self._update(f"正在保存路径映射到: {self.mapping_file}", "数据保存")
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'migration_time': self._get_current_time(),
                    'source_path_count': len(self.path_mapping),
                    'path_mapping': self.path_mapping
                }, f, ensure_ascii=False, indent=4)
                
            self._update(f"映射已保存: {len(self.path_mapping)} 个路径映射", "数据保存")
        except Exception as e:
            self.logger.exception(f"保存映射出错: {str(e)}")
            self._update(f"保存映射出错: {str(e)}", "数据保存错误")
    
    def _get_current_time(self):
        """
        获取当前时间字符串
        
        Returns:
            str: 当前时间字符串
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _get_current_time_ms(self):
        """
        获取当前时间的毫秒数
        
        Returns:
            int: 当前时间的毫秒数
        """
        import time
        return int(time.time() * 1000)
    
    def _format_size(self, size_bytes):
        """
        格式化文件大小
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            str: 格式化后的文件大小
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
            
    def _format_time(self, seconds):
        """
        格式化时间
        
        Args:
            seconds: 秒数
            
        Returns:
            str: 格式化后的时间
        """
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}分钟"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}小时"
            
    def _check_disk_space(self, scan_result):
        """
        检查目标磁盘是否有足够的空间
        
        Args:
            scan_result: 扫描结果
            
        Returns:
            bool: 是否有足够的空间
        """
        try:
            # 导入psutil库检查磁盘空间
            import psutil
            
            # 计算需要迁移的文件总大小
            total_size = 0
            
            # 计算大文件夹的总大小
            for folder_info in scan_result.get('large_folders', []):
                total_size += folder_info.get('size', 0)
                
            # 计算大文件的总大小
            for file_info in scan_result.get('large_files', []):
                total_size += file_info.get('size', 0)
                
            # 获取目标磁盘的可用空间
            # 从目标路径中提取盘符
            target_drive = os.path.splitdrive(self.target_path)[0]
            if not target_drive:
                # 如果目标路径没有盘符（例如是相对路径），则使用当前工作目录的盘符
                target_drive = os.path.splitdrive(os.getcwd())[0]
                
            # 获取磁盘使用情况
            disk_usage = psutil.disk_usage(target_drive)
            free_space = disk_usage.free
            
            # 考虑压缩率，假设平均压缩率为0.7（即压缩后大小为原大小的70%）
            # 同时为了安全，额外预留20%的空间
            required_space = total_size * 0.7 * 1.2
            
            # 检查空间是否足够
            if free_space < required_space:
                self._update(f"目标磁盘空间不足！需要至少 {self._format_size(required_space)}，但只有 {self._format_size(free_space)}。", "空间检查")
                self._update(f"请清理目标磁盘 {target_drive} 后重试，或者更改配置中的目标路径。", "空间检查")
                return False
            else:
                self._update(f"目标磁盘空间充足：需要 {self._format_size(required_space)}，可用 {self._format_size(free_space)}。", "空间检查")
                return True
                
        except ImportError:
            self.logger.warning("psutil模块未安装，无法检查磁盘空间")
            self._update("警告：无法检查目标磁盘空间是否足够，请确保目标磁盘有足够空间", "空间检查")
            return True  # 如果无法检查，则假设空间足够
            
        except Exception as e:
            self.logger.exception(f"检查磁盘空间时出错: {str(e)}")
            self._update(f"检查磁盘空间时出错: {str(e)}，请确保目标磁盘有足够空间", "空间检查")
            return True  # 如果检查出错，则假设空间足够
    
    def _update(self, message, operation_type=None):
        """
        更新消息
        
        Args:
            message: 消息内容
            operation_type: 操作类型，用于在日志前添加前缀
        """
        # 添加操作类型前缀
        if operation_type:
            formatted_message = f"[{operation_type}] {message}"
        else:
            formatted_message = message
            
        # 发送消息到回调函数和日志
        if self.update_callback:
            self.update_callback(formatted_message)
        self.logger.info(formatted_message)
    
    def stop(self):
        """
        停止迁移
        """
        self.is_running = False
        self._update("正在停止迁移...", "任务中断")