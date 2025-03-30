#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
链接模块

用于创建软链接并检查链接是否生效
"""

import os
import json
import time
import logging
import subprocess
from pathlib import Path


class Linker:
    """软链接创建器"""
    
    def __init__(self, mapping_file, check_timeout=10,
                 update_callback=None, progress_callback=None):
        """
        初始化链接器
        
        Args:
            mapping_file: 映射文件路径
            check_timeout: 链接检查超时时间（秒）
            update_callback: 更新回调函数
            progress_callback: 进度回调函数
        """
        self.mapping_file = mapping_file
        self.check_timeout = check_timeout
        self.update_callback = update_callback
        self.progress_callback = progress_callback
        self.logger = logging.getLogger('MigrateC.Linker')
        self.path_mapping = {}  # 路径映射
        self.total_links = 0  # 总链接数
        self.processed_links = 0  # 已处理链接数
        self.is_running = True  # 运行标志
        self.failed_links = []  # 创建失败的链接
    
    def create_links(self):
        """
        创建软链接
        
        Returns:
            bool: 是否成功
        """
        try:
            # 检查管理员权限
            if not self._is_admin():
                self._update("创建软链接需要管理员权限，请以管理员身份运行程序")
                return False
            
            # 加载映射
            if not self._load_mapping():
                return False
            
            self.total_links = len(self.path_mapping)
            
            if self.total_links == 0:
                self._update("没有找到需要创建链接的路径")
                return True
            
            self._update(f"开始创建 {self.total_links} 个软链接")
            
            # 更新进度
            if self.progress_callback:
                self.progress_callback(0)
            
            # 创建软链接
            for source_path, target_path in self.path_mapping.items():
                if not self.is_running:
                    break
                
                self._create_link(source_path, target_path)
                
                # 更新进度
                self.processed_links += 1
                progress = int(self.processed_links / max(1, self.total_links) * 100)
                if self.progress_callback and progress <= 100:
                    self.progress_callback(progress)
            
            # 输出结果
            if self.is_running:
                if len(self.failed_links) == 0:
                    self._update(f"链接创建完成，所有链接已成功创建")
                    if self.progress_callback:
                        self.progress_callback(100)
                    return True
                else:
                    self._update(f"链接创建部分完成，{len(self.failed_links)} 个链接创建失败")
                    for link in self.failed_links:
                        self._update(f"创建失败: {link}")
                    return False
            else:
                self._update("链接创建已取消")
                return False
                
        except Exception as e:
            self.logger.exception(f"创建链接出错: {str(e)}")
            self._update(f"创建链接出错: {str(e)}")
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
    
    def _create_link(self, source_path, target_path):
        """
        创建软链接
        
        Args:
            source_path: 源路径（C盘路径）
            target_path: 目标路径（D盘路径）
        """
        try:
            # 检查源路径是否存在
            if os.path.exists(source_path):
                self._update(f"源路径已存在，跳过: {source_path}")
                return
            
            # 检查目标路径是否存在
            if not os.path.exists(target_path):
                self._update(f"目标路径不存在，跳过: {target_path}")
                self.failed_links.append(source_path)
                return
            
            self._update(f"正在创建软链接: {source_path} -> {target_path}")
            
            # 创建软链接
            success = self._create_symlink(source_path, target_path)
            
            if success:
                # 检查链接是否生效
                if self._check_link(source_path, target_path):
                    self._update(f"软链接创建成功: {source_path} -> {target_path}")
                else:
                    self._update(f"软链接创建失败，链接检查未通过: {source_path}")
                    self.failed_links.append(source_path)
            else:
                self._update(f"软链接创建失败: {source_path}")
                self.failed_links.append(source_path)
                
        except Exception as e:
            self.logger.exception(f"创建软链接出错: {source_path}, {str(e)}")
            self._update(f"创建软链接出错: {source_path}, {str(e)}")
            self.failed_links.append(source_path)
    
    def _create_symlink(self, source_path, target_path):
        """
        创建符号链接
        
        Args:
            source_path: 源路径（C盘路径）
            target_path: 目标路径（D盘路径）
            
        Returns:
            bool: 是否成功
        """
        try:
            # 使用mklink命令创建目录符号链接
            cmd = f'cmd /c mklink /D "{source_path}" "{target_path}"'
            
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            
            if result.returncode == 0:
                return True
            else:
                self.logger.warning(f"创建符号链接失败: {result.stderr}")
                return False
        except Exception as e:
            self.logger.warning(f"创建符号链接出错: {str(e)}")
            return False
    
    def _check_link(self, source_path, target_path):
        """
        检查链接是否生效
        
        Args:
            source_path: 源路径（C盘路径）
            target_path: 目标路径（D盘路径）
            
        Returns:
            bool: 是否生效
        """
        try:
            # 等待链接生效
            start_time = time.time()
            while time.time() - start_time < self.check_timeout:
                if os.path.exists(source_path) and os.path.isdir(source_path):
                    # 使用dir命令检查是否为符号链接
                    cmd = f'cmd /c dir "{source_path}" | findstr "<SYMLINKD>"'
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
                    
                    if result.returncode == 0 and "<SYMLINKD>" in result.stdout:
                        return True
                
                time.sleep(0.5)
            
            return False
        except Exception as e:
            self.logger.warning(f"检查链接出错: {str(e)}")
            return False
    
    def _is_admin(self):
        """
        检查是否具有管理员权限
        
        Returns:
            bool: 是否具有管理员权限
        """