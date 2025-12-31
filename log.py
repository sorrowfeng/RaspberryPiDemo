import logging
import sys
from datetime import datetime

def setup_logging():
    """配置日志系统"""
    
    # 确保logs目录存在
    import os
    os.makedirs('logs', exist_ok=True)
    
    # 创建 logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 设置最低日志级别
    
    # 清除已有的 handler（避免重复）
    logger.handlers.clear()
    
    # 1. 文件 handler - 输出到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        filename=f"logs/app_{timestamp}.log",
        mode='a',  # 追加模式
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # 2. 控制台 handler - 输出到终端
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加 handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 使用示例
logger = setup_logging()