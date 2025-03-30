#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
扫描模块

用于扫描指定目录下超过指定大小的文件夹
"""

import os
import json
import logging
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from queue import Queue


class Scanner:
    """文件夹和文件扫描器"""
    
    def __init__(self, scan_paths, size_threshold, output_file, max_threads=4,
                 update_callback=None, progress_callback=None, exclude_folders=None):
        """
        初始化扫描器
        
        Args:
            scan_paths: 需要扫描的路径列表，每个元素包含路径、最大扫描深度和特定排除文件夹
                        格式：[{'path': '路径', 'max_depth': 深度, 'exclude_folders': [文件夹列表]}, ...]
            size_threshold: 文件夹大小阈值（字节）
            output_file: 扫描结果输出文件路径
            max_threads: 最大线程数
            update_callback: 更新回调函数
            progress_callback: 进度回调函数
            exclude_folders: 全局需要排除的文件夹名称列表，这些文件夹将在所有路径下被跳过不进行迁移
        """
        self.scan_paths = scan_paths
        self.size_threshold = size_threshold
        self.output_file = output_file
        self.max_threads = max_threads
        self.update_callback = update_callback
        self.progress_callback = progress_callback
        self.global_exclude_folders = exclude_folders or []  # 全局需要排除的文件夹名称列表
        self.logger = logging.getLogger('MigrateC.Scanner')
        self.large_folders = []  # 存储大文件夹信息
        self.large_files = []  # 存储大文件信息
        self.lock = threading.Lock()  # 线程锁
        self.total_folders = 0  # 总文件夹数
        self.processed_folders = 0  # 已处理文件夹数
        self.is_running = True  # 运行标志
    
    def scan(self):
        """
        执行扫描
        
        Returns:
            bool: 是否成功
        """
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            
            # 首先计算总文件夹数
            self._count_total_folders()
            
            # 更新进度
            if self.progress_callback:
                self.progress_callback(0)
            
            # 使用线程池扫描文件夹
            with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                for path_info in self.scan_paths:
                    if not self.is_running:
                        break
                    
                    # 获取路径、最大深度和特定排除文件夹
                    path = path_info['path']
                    max_depth = path_info.get('max_depth', None)
                    path_exclude_folders = path_info.get('exclude_folders', [])
                    
                    if not os.path.exists(path):
                        self._update(f"路径不存在: {path}")
                        continue
                    
                    # self._update(f"开始扫描: {path}，最大深度: {max_depth if max_depth is not None else '不限'}，特定排除文件夹: {path_exclude_folders}，全局排除文件夹: {self.global_exclude_folders}")
                    executor.submit(self._scan_directory, path, max_depth, path_exclude_folders)
            
            # 保存结果
            if self.is_running:
                self._save_results()
                self._update(f"扫描完成，共找到 {len(self.large_folders)} 个大文件夹")
                if self.progress_callback:
                    self.progress_callback(100)
                return True
            else:
                self._update("扫描已取消")
                return False
                
        except Exception as e:
            self.logger.exception(f"扫描出错: {str(e)}")
            self._update(f"扫描出错: {str(e)}")
            return False
    
    def _count_total_folders(self):
        """
        计算总文件夹数
        """
        self._update("正在计算总文件夹数...")
        self.total_folders = 0
        
        for path_info in self.scan_paths:
            path = path_info['path']
            max_depth = path_info.get('max_depth', None)
            
            if not os.path.exists(path):
                continue
            
            # 考虑层级限制计算文件夹数
            for root, dirs, _ in os.walk(path, topdown=True):
                # 如果设置了最大深度，计算当前深度
                if max_depth is not None:
                    rel_path = os.path.relpath(root, path)
                    current_depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                    
                    # 如果已经达到最大深度，则不再递归
                    if current_depth >= max_depth:
                        self.total_folders += len(dirs)  # 添加当前层的文件夹数
                        dirs.clear()  # 清空dirs列表，阻止os.walk继续递归
                        continue
                
                self.total_folders += len(dirs)
        
        self._update(f"总文件夹数: {self.total_folders}")
    
    def _scan_directory(self, directory, max_depth=None, path_exclude_folders=None):
        """
        扫描目录
        
        Args:
            directory: 要扫描的目录
            max_depth: 最大扫描深度，None表示不限制
            path_exclude_folders: 该路径特定的排除文件夹列表
        """
        try:
            # 合并全局排除和路径特定排除文件夹列表
            exclude_folders = list(self.global_exclude_folders)
            if path_exclude_folders:
                exclude_folders.extend(path_exclude_folders)
            
            # 记录详细的扫描配置信息
            self._update(f"扫描目录: {directory}，最大深度: {max_depth if max_depth is not None else '不限'}，"  
                       f"应用的排除规则 - 全局: {self.global_exclude_folders}，路径特定: {path_exclude_folders or []}，"  
                       f"合并后的排除列表: {exclude_folders}")
            
            # 使用os.walk的topdown参数，以便我们可以控制递归深度
            for root, dirs, files in os.walk(directory, topdown=True):
                if not self.is_running:
                    return
                
                # 计算当前深度
                current_depth = 0
                if max_depth is not None:
                    # 计算相对于起始目录的深度
                    rel_path = os.path.relpath(root, directory)
                    current_depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                    
                    # 如果已经达到最大深度，则不再递归
                    if current_depth >= max_depth:
                        dirs.clear()  # 清空dirs列表，阻止os.walk继续递归
                        continue  # 跳过当前层级，不处理这一层的目录
                
                # 过滤掉需要排除的文件夹
                dirs_to_process = [d for d in dirs if d not in exclude_folders]
                
                # 扫描当前目录下的文件
                for file_name in files:
                    if not self.is_running:
                        return
                    
                    file_path = os.path.join(root, file_name)
                    
                    try:
                        # 获取文件大小
                        file_size = os.path.getsize(file_path)
                        
                        # 如果文件大小超过阈值，则添加到结果列表
                        if file_size >= self.size_threshold:
                            # 计算文件相对于起始目录的深度
                            file_rel_path = os.path.relpath(file_path, directory)
                            file_depth = 0 if file_rel_path == '.' else file_rel_path.count(os.sep)
                            
                            with self.lock:
                                self.large_files.append({
                                    'path': file_path,
                                    'size': file_size,
                                    'size_human': self._format_size(file_size),
                                    'depth': file_depth,  # 添加深度信息，方便后续过滤
                                    'type': 'file'  # 标记为文件
                                })
                                self._update(f"找到大文件: {file_path} ({self._format_size(file_size)})")
                    except Exception as e:
                        self.logger.warning(f"获取文件大小出错: {file_path}, {str(e)}")
                
                for dir_name in dirs_to_process:
                    if not self.is_running:
                        return
                    
                    dir_path = os.path.join(root, dir_name)
                    
                    # 如果文件夹名称在排除列表中，跳过该文件夹
                    if dir_name in exclude_folders:
                        self._update(f"跳过排除的文件夹: {dir_path}，排除原因: 文件夹名称在排除列表中 {exclude_folders}")
                        continue
                    
                    # 更新已处理文件夹数
                    with self.lock:
                        self.processed_folders += 1
                        progress = int(self.processed_folders / max(1, self.total_folders) * 100)
                        if self.progress_callback and progress <= 100:
                            self.progress_callback(progress)
                    
                    # 计算当前目录的深度
                    dir_rel_path = os.path.relpath(dir_path, directory)
                    dir_depth = 0 if dir_rel_path == '.' else dir_rel_path.count(os.sep) + 1
                    
                    # 只有当深度符合要求时才处理该目录
                    # 如果max_depth为2，则只处理深度为0（根目录）和深度为2的目录
                    # 跳过深度为1的目录（中间层级）
                    if max_depth is not None and dir_depth == 1 and max_depth == 2:
                        self.logger.debug(f"跳过中间层级目录: {dir_path} (深度: {dir_depth}, 最大深度: {max_depth})")
                        continue
                    
                    # 计算文件夹大小
                    try:
                        size = self._get_folder_size(dir_path)
                        
                        # 如果文件夹大小超过阈值，则添加到结果列表
                        if size >= self.size_threshold:
                            with self.lock:
                                self.large_folders.append({
                                    'path': dir_path,
                                    'size': size,
                                    'size_human': self._format_size(size),
                                    'depth': dir_depth,  # 添加深度信息，方便后续过滤
                                    'type': 'folder'  # 标记为文件夹
                                })
                                self._update(f"找到大文件夹: {dir_path} ({self._format_size(size)})")
                    except Exception as e:
                        self.logger.warning(f"计算文件夹大小出错: {dir_path}, {str(e)}")
        except Exception as e:
            self.logger.warning(f"扫描目录出错: {directory}, {str(e)}")
    
    def _get_folder_size(self, folder_path):
        """
        获取文件夹大小
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            int: 文件夹大小（字节）
        """
        total_size = 0
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                try:
                    file_path = os.path.join(root, file)
                    total_size += os.path.getsize(file_path)
                except Exception as e:
                    self.logger.debug(f"获取文件大小出错: {file_path}, {str(e)}")
        return total_size
    
    def _format_size(self, size):
        """
        格式化文件大小
        
        Args:
            size: 文件大小（字节）
            
        Returns:
            str: 格式化后的文件大小
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    def _save_results(self):
        """
        保存扫描结果
        过滤掉中间层级的目录：
        - 如果配置了扫描3层目录，那么第2层的结果会被过滤掉
        - 如果配置了扫描2层目录，那么第1层的结果会被过滤掉
        """
        try:
            # 过滤掉中间层级的目录
            filtered_folders = self._filter_intermediate_folders()
            
            # 过滤掉中间层级的文件
            filtered_files = self._filter_intermediate_files()
            
            # 合并文件夹和文件结果
            all_results = {
                'large_folders': filtered_folders,
                'large_files': filtered_files,
                'scan_time': self._get_current_time()
            }
            
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, ensure_ascii=False, indent=4)
            
            total_items = len(filtered_folders) + len(filtered_files)
            self.logger.info(f"扫描结果已保存到: {self.output_file}，大文件夹数量: {len(filtered_folders)}，大文件数量: {len(filtered_files)}，总数量: {total_items}")
            self._update(f"扫描完成，共找到 {len(filtered_folders)} 个大文件夹和 {len(filtered_files)} 个大文件")
        except Exception as e:
            self.logger.exception(f"保存扫描结果出错: {str(e)}")
    
    def _update(self, message):
        """
        更新消息
        
        Args:
            message: 消息内容
        """
        # 确保消息中包含完整的配置信息
        if self.update_callback:
            self.update_callback(message)
        self.logger.info(message)
    
    def _filter_intermediate_files(self):
        """
        过滤中间层级的文件
        
        根据用户需求：
        1. 如果配置了扫描3层目录，那么第2层的结果应该被过滤掉
        2. 如果配置了扫描2层目录，那么第1层的结果应该被过滤掉
        
        Returns:
            list: 过滤后的大文件列表
        """
        # 如果没有配置扫描路径或者最大深度，则不过滤
        if not self.scan_paths:
            return self.large_files
        
        # 创建一个字典，按扫描路径分组存储文件
        path_groups = {}
        for path_info in self.scan_paths:
            base_path = path_info['path']
            max_depth = path_info.get('max_depth', None)
            if max_depth and max_depth > 1:  # 只有当最大深度大于1时才需要过滤
                path_groups[base_path] = {
                    'max_depth': max_depth,
                    'files': []
                }
        
        # 如果没有需要过滤的路径，则直接返回原始结果
        if not path_groups:
            return self.large_files
        
        # 将文件按扫描路径分组
        filtered_files = []
        for file in self.large_files:
            file_path = file['path']
            added = False
            
            for base_path, group_info in path_groups.items():
                # 检查文件是否在当前扫描路径下
                if file_path.startswith(base_path):
                    # 计算相对于基础路径的深度
                    rel_path = os.path.relpath(file_path, base_path)
                    depth = 0 if rel_path == '.' else rel_path.count(os.sep)
                    
                    # 将文件添加到对应的组
                    group_info['files'].append({
                        'file': file,
                        'depth': depth
                    })
                    added = True
                    break
            
            # 如果文件不在任何需要过滤的路径下，直接添加到结果中
            if not added:
                filtered_files.append(file)
        
        # 对每个组进行过滤
        for base_path, group_info in path_groups.items():
            max_depth = group_info['max_depth']
            files = group_info['files']
            
            # 按照用户需求过滤中间层级：
            # 1. 保留最深层级的文件（depth == max_depth）
            # 2. 保留超过最深层级的文件（depth > max_depth）
            # 3. 根据max_depth决定是否保留第1层（depth == 1）：
            #    - 如果max_depth > 2，则保留第1层
            #    - 如果max_depth <= 2，则过滤掉第1层
            for file_info in files:
                depth = file_info['depth']
                
                # 保留的条件：
                # 1. 最深层级的文件
                # 2. 超过最深层级的文件
                # 3. 根目录（depth == 0）
                # 4. 第1层文件，但仅当max_depth > 2时
                if depth == max_depth or depth > max_depth or depth == 0 or (depth == 1 and max_depth > 2):
                    filtered_files.append(file_info['file'])
                    
                # 记录过滤情况
                if 0 < depth < max_depth and not (depth == 1 and max_depth > 2):
                    self.logger.debug(f"过滤掉中间层级文件: {file_info['file']['path']} (深度: {depth}, 最大深度: {max_depth})")
        
        return filtered_files
        
    def _filter_intermediate_folders(self):
        """
        过滤中间层级的目录
        
        根据用户需求：
        1. 如果配置了扫描3层目录，那么第2层的结果应该被过滤掉
        2. 如果配置了扫描2层目录，那么第1层的结果应该被过滤掉
        
        Returns:
            list: 过滤后的大文件夹列表
        """
        # 如果没有配置扫描路径或者最大深度，则不过滤
        if not self.scan_paths:
            return self.large_folders
        
        # 创建一个字典，按扫描路径分组存储文件夹
        path_groups = {}
        for path_info in self.scan_paths:
            base_path = path_info['path']
            max_depth = path_info.get('max_depth', None)
            if max_depth and max_depth > 1:  # 只有当最大深度大于1时才需要过滤
                path_groups[base_path] = {
                    'max_depth': max_depth,
                    'folders': []
                }
        
        # 如果没有需要过滤的路径，则直接返回原始结果
        if not path_groups:
            return self.large_folders
        
        # 将文件夹按扫描路径分组
        filtered_folders = []
        for folder in self.large_folders:
            folder_path = folder['path']
            added = False
            
            for base_path, group_info in path_groups.items():
                # 检查文件夹是否在当前扫描路径下
                if folder_path.startswith(base_path):
                    # 计算相对于基础路径的深度
                    rel_path = os.path.relpath(folder_path, base_path)
                    depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                    
                    # 将文件夹添加到对应的组
                    group_info['folders'].append({
                        'folder': folder,
                        'depth': depth
                    })
                    added = True
                    break
            
            # 如果文件夹不在任何需要过滤的路径下，直接添加到结果中
            if not added:
                filtered_folders.append(folder)
        
        # 对每个组进行过滤
        for base_path, group_info in path_groups.items():
            max_depth = group_info['max_depth']
            folders = group_info['folders']
            
            # 按照用户需求过滤中间层级：
            # 1. 保留最深层级的文件夹（depth == max_depth）
            # 2. 保留超过最深层级的文件夹（depth > max_depth）
            # 3. 根据max_depth决定是否保留第1层（depth == 1）：
            #    - 如果max_depth > 2，则保留第1层
            #    - 如果max_depth <= 2，则过滤掉第1层
            for folder_info in folders:
                depth = folder_info['depth']
                
                # 保留的条件：
                # 1. 最深层级的文件夹
                # 2. 超过最深层级的文件夹
                # 3. 根目录（depth == 0）
                # 4. 第1层文件夹，但仅当max_depth > 2时
                if depth == max_depth or depth > max_depth or depth == 0 or (depth == 1 and max_depth > 2):
                    filtered_folders.append(folder_info['folder'])
                    
                # 记录过滤情况
                if 0 < depth < max_depth and not (depth == 1 and max_depth > 2):
                    self.logger.debug(f"过滤掉中间层级目录: {folder_info['folder']['path']} (深度: {depth}, 最大深度: {max_depth})")
        
        return filtered_folders
    
    def _get_current_time(self):
        """
        获取当前时间字符串
        
        Returns:
            str: 当前时间字符串
        """
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def stop(self):
        """
        停止扫描
        """
        self.is_running = False
        self.logger.info("扫描已停止")