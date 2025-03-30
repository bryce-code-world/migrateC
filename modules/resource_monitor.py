#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
资源监控模块

用于监控和限制程序的CPU和内存使用，确保不会占用过多系统资源
"""

import os
import time
import logging
import threading
import multiprocessing

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class ResourceMonitor:
    """资源监控器，用于监控和限制程序的资源使用"""
    
    def __init__(self, cpu_limit=0.5, memory_limit=0.5, check_interval=1.0):
        """
        初始化资源监控器
        
        Args:
            cpu_limit: CPU使用限制，范围0-1，表示可使用的CPU核心数比例
            memory_limit: 内存使用限制，范围0-1，表示可使用的系统内存比例
            check_interval: 检查间隔时间（秒）
        """
        self.cpu_limit = max(0.1, min(1.0, cpu_limit))  # 确保在0.1-1.0之间
        self.memory_limit = max(0.1, min(1.0, memory_limit))  # 确保在0.1-1.0之间
        self.check_interval = check_interval
        self.logger = logging.getLogger('MigrateC.ResourceMonitor')
        self.monitor_thread = None
        self.is_running = False
        self.current_cpu_usage = 0
        self.current_memory_usage = 0
        self.system_memory_total = 0
        self.system_memory_available = 0
        self.cpu_count = multiprocessing.cpu_count()
        self.max_threads = max(1, int(self.cpu_count * self.cpu_limit))
        self.lock = threading.Lock()
        
        # 检查psutil是否可用
        if not PSUTIL_AVAILABLE:
            self.logger.warning("psutil模块未安装，资源监控功能将受限。建议安装psutil以获得更准确的资源监控：pip install psutil")
    
    def start_monitoring(self):
        """
        开始资源监控
        """
        if self.is_running:
            return
            
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        self.monitor_thread.start()
        self.logger.info(f"资源监控已启动，CPU限制: {self.cpu_limit*100:.0f}%，内存限制: {self.memory_limit*100:.0f}%")
    
    def stop_monitoring(self):
        """
        停止资源监控
        """
        self.is_running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        self.logger.info("资源监控已停止")
    
    def _monitor_resources(self):
        """
        监控资源使用情况
        """
        while self.is_running:
            try:
                self._update_resource_usage()
                time.sleep(self.check_interval)
            except Exception as e:
                self.logger.error(f"监控资源时出错: {str(e)}")
                time.sleep(self.check_interval * 2)  # 出错时增加等待时间
    
    def _update_resource_usage(self):
        """
        更新资源使用情况
        """
        if PSUTIL_AVAILABLE:
            # 使用psutil获取更准确的资源使用情况
            try:
                # 获取CPU使用率
                self.current_cpu_usage = psutil.cpu_percent(interval=None) / 100.0
                
                # 获取内存使用情况
                memory = psutil.virtual_memory()
                self.system_memory_total = memory.total
                self.system_memory_available = memory.available
                self.current_memory_usage = (memory.total - memory.available) / memory.total
                
                # 获取当前进程的资源使用情况
                process = psutil.Process(os.getpid())
                process_cpu = process.cpu_percent(interval=None) / 100.0
                process_memory = process.memory_info().rss
                
                # 更新最大线程数
                with self.lock:
                    # 根据当前CPU使用情况动态调整最大线程数
                    available_cpu = max(0.1, self.cpu_limit - (self.current_cpu_usage - process_cpu))
                    self.max_threads = max(1, int(self.cpu_count * available_cpu))
                
                # 记录资源使用情况（仅在使用率较高时记录，避免日志过多）
                if self.current_cpu_usage > 0.7 or self.current_memory_usage > 0.7:
                    self.logger.info(f"系统资源使用情况 - CPU: {self.current_cpu_usage*100:.1f}%，"  
                                    f"内存: {self.current_memory_usage*100:.1f}%，"  
                                    f"进程CPU: {process_cpu*100:.1f}%，"  
                                    f"进程内存: {self._format_size(process_memory)}，"  
                                    f"最大线程数: {self.max_threads}")
            except Exception as e:
                self.logger.error(f"使用psutil获取资源使用情况时出错: {str(e)}")
        else:
            # 如果psutil不可用，使用简单的方法估计资源使用情况
            # 这种方法不太准确，但可以提供基本的资源限制
            self.max_threads = max(1, int(self.cpu_count * self.cpu_limit))
    
    def should_throttle(self):
        """
        检查是否应该限制资源使用
        
        Returns:
            bool: 是否应该限制资源使用
        """
        if not PSUTIL_AVAILABLE:
            return False
            
        # 如果内存使用超过限制，则应该限制
        return self.current_memory_usage > self.memory_limit
    
    def get_max_threads(self):
        """
        获取当前建议的最大线程数
        
        Returns:
            int: 最大线程数
        """
        with self.lock:
            return self.max_threads
    
    def wait_for_resources(self, timeout=None):
        """
        等待资源可用
        
        Args:
            timeout: 超时时间（秒），None表示无限等待
            
        Returns:
            bool: 是否在超时前资源变为可用
        """
        if not PSUTIL_AVAILABLE:
            return True
            
        start_time = time.time()
        while self.is_running:
            # 如果资源使用低于限制，则可以继续
            if self.current_memory_usage < self.memory_limit:
                return True
                
            # 检查是否超时
            if timeout is not None and time.time() - start_time > timeout:
                return False
                
            # 等待一段时间再检查
            time.sleep(self.check_interval)
        
        return False
    
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


def get_optimal_thread_count(cpu_limit=0.5):
    """
    获取最优线程数，考虑CPU限制
    
    Args:
        cpu_limit: CPU使用限制，范围0-1
        
    Returns:
        int: 线程数
    """
    # 获取CPU核心数
    cpu_count = multiprocessing.cpu_count()
    
    # 根据CPU限制计算可用的CPU核心数
    available_cores = max(1, int(cpu_count * cpu_limit))
    
    # 设置最优线程数
    # 对于IO密集型任务，可以设置为可用CPU核心数的2倍
    # 对于CPU密集型任务，可以设置为可用CPU核心数
    return max(2, available_cores * 2)  # 至少2个线程