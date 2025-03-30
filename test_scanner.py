#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
扫描器测试脚本

用于测试扫描器的层级限制功能
"""

import os
import sys
import yaml
import logging
from modules.scanner import Scanner
from modules.utils import setup_logger

# 设置日志
logger = setup_logger(log_file="./logs/test.log", log_level="INFO")

# 加载配置
def load_config():
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
        
        return config
    except Exception as e:
        print(f"加载配置文件失败: {str(e)}")
        sys.exit(1)

# 主函数
def main():
    # 加载配置
    config = load_config()
    
    # 创建必要的目录
    os.makedirs(os.path.dirname(config['scan']['output_file']), exist_ok=True)
    
    # 打印配置信息
    print("扫描配置:")
    for path_info in config['scan']['scan_paths']:
        print(f"  路径: {path_info['path']}, 最大深度: {path_info.get('max_depth', '不限')}")
    print(f"  大小阈值: {config['scan']['size_threshold']} 字节")
    print(f"  输出文件: {config['scan']['output_file']}")
    
    # 创建扫描器
    scanner = Scanner(
        scan_paths=config['scan']['scan_paths'],
        size_threshold=config['scan']['size_threshold'],
        output_file=config['scan']['output_file'],
        max_threads=4,
        update_callback=lambda msg: print(msg),
        progress_callback=lambda progress: print(f"进度: {progress}%"),
        exclude_folders=config['scan'].get('exclude_folders', [])
    )
    
    # 执行扫描
    print("开始扫描...")
    success = scanner.scan()
    
    if success:
        print(f"扫描完成，结果已保存到 {config['scan']['output_file']}")
    else:
        print("扫描失败")

if __name__ == "__main__":
    main()