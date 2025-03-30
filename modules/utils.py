#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
工具模块

提供一些通用功能，如检查管理员权限、设置日志等
"""

import os
import sys
import logging
import ctypes
import multiprocessing
from pathlib import Path


def is_admin():
    """
    检查当前程序是否以管理员身份运行
    
    Returns:
        bool: 是否以管理员身份运行
    """
    try:
        # Windows系统下检查管理员权限
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def setup_logger(log_file, log_level='INFO'):
    """
    设置日志记录器
    
    Args:
        log_file: 日志文件路径
        log_level: 日志级别
        
    Returns:
        logging.Logger: 日志记录器
    """
    # 创建日志目录
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 创建日志记录器
    logger = logging.getLogger('MigrateC')
    
    # 设置日志级别
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # 防止日志重复
    if not logger.handlers:
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # 创建格式化器
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger


def get_optimal_thread_count():
    """
    获取最优线程数
    
    Returns:
        int: 线程数
    """
    # 获取CPU核心数
    cpu_count = multiprocessing.cpu_count()
    
    # 设置最优线程数
    # 一般设置为CPU核心数的1-2倍
    # 对于IO密集型任务，可以设置为CPU核心数的2倍
    # 对于CPU密集型任务，可以设置为CPU核心数
    return max(4, cpu_count * 2)  # 至少4个线程