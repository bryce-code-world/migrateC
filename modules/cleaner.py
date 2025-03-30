#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
清理模块

用于删除C盘原路径下的文件和文件夹，并处理文件占用问题
"""

import os
import json
import time
import shutil
import logging
import subprocess
from pathlib import Path


class Cleaner:
    """文件和文件夹清理器"""
    
    def __init__(self, mapping_file, retry_count=3, retry_interval=5,
                 update_callback=None, progress_callback=None):
        """
        初始化清理器
        
        Args:
            mapping_file: 映射文件路径
            retry_count: 重试次数
            retry_interval: 重试间隔时间（秒）
            update_callback: 更新回调函数
            progress_callback: 进度回调函数
        """
        self.mapping_file = mapping_file
        self.retry_count = retry_count
        self.retry_interval = retry_interval
        self.update_callback = update_callback
        self.progress_callback = progress_callback
        self.logger = logging.getLogger('MigrateC.Cleaner')
        self.path_mapping = {}  # 路径映射
        self.total_items = 0  # 总项目数（文件和文件夹）
        self.processed_items = 0  # 已处理项目数
        self.is_running = True  # 运行标志
        self.failed_items = []  # 删除失败的项目
    
    def clean(self):
        """
        执行清理
        
        Returns:
            bool: 是否成功
        """
        try:
            # 加载映射
            if not self._load_mapping():
                return False
            
            self.total_items = len(self.path_mapping)
            
            if self.total_items == 0:
                self._update("没有找到需要清理的文件或文件夹")
                return True
            
            self._update(f"开始清理 {self.total_items} 个项目")
            
            # 更新进度
            if self.progress_callback:
                self.progress_callback(0)
            
            # 清理文件和文件夹
            for source_path, target_path in self.path_mapping.items():
                if not self.is_running:
                    break
                
                # 判断是文件还是文件夹
                if os.path.isfile(source_path):
                    self._clean_file(source_path, target_path)
                else:
                    self._clean_folder(source_path, target_path)
                
                # 更新进度
                self.processed_items += 1
                progress = int(self.processed_items / max(1, self.total_items) * 100)
                if self.progress_callback and progress <= 100:
                    self.progress_callback(progress)
            
            # 输出结果
            if self.is_running:
                if len(self.failed_items) == 0:
                    self._update(f"清理完成，所有文件和文件夹已成功删除")
                    if self.progress_callback:
                        self.progress_callback(100)
                    return True
                else:
                    self._update(f"清理部分完成，{len(self.failed_items)} 个项目删除失败")
                    for item in self.failed_items:
                        self._update(f"删除失败: {item}")
                    return False
            else:
                self._update("清理已取消")
                return False
                
        except Exception as e:
            self.logger.exception(f"清理出错: {str(e)}")
            self._update(f"清理出错: {str(e)}")
            return False
    
    def _load_mapping(self):
        """
        加载映射
        
        Returns:
            bool: 是否成功
        """
        try:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                mapping_data = json.load(f)
                self.path_mapping = mapping_data.get('path_mapping', {})
            return True
        except Exception as e:
            self.logger.exception(f"加载映射出错: {str(e)}")
            self._update(f"加载映射出错: {str(e)}")
            return False
    
    def _clean_file(self, source_path, target_path):
        """
        清理文件
        
        Args:
            source_path: 源路径（C盘路径）
            target_path: 目标路径（D盘路径）
        """
        try:
            # 检查源路径是否存在
            if not os.path.exists(source_path):
                self._update(f"源文件不存在，跳过: {source_path}")
                return
            
            # 检查目标路径是否存在
            if not os.path.exists(target_path):
                self._update(f"目标文件不存在，跳过: {source_path}")
                self.failed_items.append(source_path)
                return
            
            self._update(f"正在删除文件: {source_path}")
            
            # 尝试删除文件
            success = self._remove_file_with_retry(source_path)
            
            if success:
                self._update(f"文件删除成功: {source_path}")
            else:
                self._update(f"文件删除失败: {source_path}")
                self.failed_items.append(source_path)
                
        except Exception as e:
            self.logger.exception(f"删除文件出错: {source_path}, {str(e)}")
            self._update(f"删除文件出错: {source_path}, {str(e)}")
            self.failed_items.append(source_path)
    
    def _clean_folder(self, source_path, target_path):
        """
        清理文件夹
        
        Args:
            source_path: 源路径（C盘路径）
            target_path: 目标路径（D盘路径）
        """
        try:
            # 检查源路径是否存在
            if not os.path.exists(source_path):
                self._update(f"源路径不存在，跳过: {source_path}")
                return
            
            # 检查目标路径是否存在
            if not os.path.exists(target_path):
                self._update(f"目标路径不存在，跳过: {source_path}")
                self.failed_items.append(source_path)
                return
            
            self._update(f"正在删除文件夹: {source_path}")
            
            # 尝试删除文件夹
            success = self._remove_folder_with_retry(source_path)
            
            if success:
                self._update(f"文件夹删除成功: {source_path}")
            else:
                self._update(f"文件夹删除失败: {source_path}")
                self.failed_items.append(source_path)
                
        except Exception as e:
            self.logger.exception(f"删除文件夹出错: {source_path}, {str(e)}")
            self._update(f"删除文件夹出错: {source_path}, {str(e)}")
            self.failed_items.append(source_path)
    
    def _remove_file_with_retry(self, file_path):
        """
        尝试删除文件，如果失败则重试
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功
        """
        for attempt in range(self.retry_count):
            try:
                # 尝试删除文件
                os.remove(file_path)
                return True
            except PermissionError:
                # 如果是权限错误，可能是文件被占用
                self._update(f"文件被占用，尝试结束占用进程: {file_path}")
                
                # 尝试结束占用进程
                if self._kill_processes_using_file(file_path):
                    # 再次尝试删除
                    try:
                        os.remove(file_path)
                        return True
                    except Exception as e:
                        self.logger.warning(f"结束进程后删除文件仍然失败: {file_path}, {str(e)}")
                
                # 如果不是最后一次尝试，则等待一段时间后重试
                if attempt < self.retry_count - 1:
                    self._update(f"等待 {self.retry_interval} 秒后重试...")
                    time.sleep(self.retry_interval)
            except Exception as e:
                self.logger.warning(f"删除文件出错: {file_path}, {str(e)}")
                
                # 如果不是最后一次尝试，则等待一段时间后重试
                if attempt < self.retry_count - 1:
                    self._update(f"等待 {self.retry_interval} 秒后重试...")
                    time.sleep(self.retry_interval)
        
        return False
        
    def _remove_folder_with_retry(self, folder_path):
        """
        尝试删除文件夹，如果失败则重试
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            bool: 是否成功
        """
        for attempt in range(self.retry_count):
            try:
                # 尝试删除文件夹
                shutil.rmtree(folder_path)
                return True
            except PermissionError:
                # 如果是权限错误，可能是文件被占用
                self._update(f"文件夹被占用，尝试结束占用进程: {folder_path}")
                
                # 尝试结束占用进程
                if self._kill_processes_using_folder(folder_path):
                    # 再次尝试删除
                    try:
                        shutil.rmtree(folder_path)
                        return True
                    except Exception as e:
                        self.logger.warning(f"结束进程后删除文件夹仍然失败: {folder_path}, {str(e)}")
                
                # 如果不是最后一次尝试，则等待一段时间后重试
                if attempt < self.retry_count - 1:
                    self._update(f"等待 {self.retry_interval} 秒后重试...")
                    time.sleep(self.retry_interval)
            except Exception as e:
                self.logger.warning(f"删除文件夹出错: {folder_path}, {str(e)}")
                
                # 如果不是最后一次尝试，则等待一段时间后重试
                if attempt < self.retry_count - 1:
                    self._update(f"等待 {self.retry_interval} 秒后重试...")
                    time.sleep(self.retry_interval)
        
        return False
    
    def _kill_processes_using_file(self, file_path):
        """
        结束占用文件的进程
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用PowerShell命令查找占用文件的进程
            cmd = f'powershell "Get-Process | Where-Object {{$_.Modules.FileName -eq \"{file_path}\"}} | Select-Object Id, ProcessName | ConvertTo-Csv -NoTypeInformation"'
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                processes = []
                
                if len(lines) > 1:  # 第一行是标题行
                    for line in lines[1:]:  # 跳过标题行
                        if '"' in line:
                            parts = line.strip('"').split('","')
                            if len(parts) >= 2:
                                pid = parts[0]
                                name = parts[1]
                                processes.append((pid, name))
                
                if not processes:
                    self._update(f"未找到占用文件的进程: {file_path}")
                    return False
                
                # 结束进程
                for pid, name in processes:
                    self._update(f"正在结束进程: {name} (PID: {pid})")
                    try:
                        # 使用taskkill命令结束进程
                        subprocess.run(f'taskkill /F /PID {pid}', shell=True, check=True)
                    except subprocess.CalledProcessError as e:
                        self.logger.warning(f"结束进程失败: {name} (PID: {pid}), {str(e)}")
                
                # 等待一段时间，让系统释放文件句柄
                time.sleep(1)
                
                return True
        except Exception as e:
            self.logger.warning(f"结束占用进程出错: {str(e)}")
            return False
    
    def _kill_processes_using_folder(self, folder_path):
        """
        结束占用文件夹的进程
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用handle命令查找占用文件夹的进程
            # 需要安装SysInternals的Handle工具
            # 如果没有安装，可以使用其他方法，如tasklist和findstr
            
            # 使用tasklist和findstr查找占用进程
            # 这种方法不太精确，但不需要额外的工具
            processes = self._find_processes_using_folder(folder_path)
            
            if not processes:
                self._update(f"未找到占用文件夹的进程: {folder_path}")
                return False
            
            # 结束进程
            for pid, name in processes:
                self._update(f"正在结束进程: {name} (PID: {pid})")
                try:
                    # 使用taskkill命令结束进程
                    subprocess.run(f'taskkill /F /PID {pid}', shell=True, check=True)
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"结束进程失败: {name} (PID: {pid}), {str(e)}")
            
            # 等待一段时间，让系统释放文件句柄
            time.sleep(1)
            
            return True
        except Exception as e:
            self.logger.warning(f"结束占用进程出错: {str(e)}")
            return False
    
    def _find_processes_using_folder(self, folder_path):
        """
        查找占用文件夹的进程
        
        Args:
            folder_path: 文件夹路径
            
        Returns:
            list: 进程列表，每个元素为 (pid, name)
        """
        processes = []
        
        try:
            # 使用PowerShell命令查找占用文件夹的进程
            # 这种方法比较精确，但需要PowerShell支持
            cmd = f'powershell "Get-Process | Where-Object {{$_.Modules.FileName -like \"{folder_path}*\"}} | Select-Object Id, ProcessName | ConvertTo-Csv -NoTypeInformation"'
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:  # 第一行是标题行
                    for line in lines[1:]:  # 跳过标题行
                        if '"' in line:
                            parts = line.strip('"').split('","')
                            if len(parts) >= 2:
                                pid = parts[0]
                                name = parts[1]
                                processes.append((pid, name))
        except Exception as e:
            self.logger.warning(f"查找占用进程出错: {str(e)}")
        
        return processes
    
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
    
    def stop(self):
        """
        停止清理
        """
        self.is_running = False
        self._update("正在停止清理...")