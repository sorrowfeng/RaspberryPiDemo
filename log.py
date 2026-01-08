import logging
import sys
from datetime import datetime
import os

def cleanup_old_logs(max_files=100):
    """清理旧日志文件，保留最新的max_files个文件"""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        return
    
    # 获取所有日志文件
    log_files = []
    for filename in os.listdir(log_dir):
        if filename.startswith('app_') and filename.endswith('.log'):
            file_path = os.path.join(log_dir, filename)
            if os.path.isfile(file_path):
                # 获取文件创建时间
                create_time = os.path.getctime(file_path)
                log_files.append((create_time, file_path))
    
    # 按创建时间排序
    log_files.sort()
    
    # 删除超出数量的最旧文件
    while len(log_files) > max_files:
        _, file_path = log_files.pop(0)  # 弹出最旧的文件
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"删除旧日志文件失败: {e}")

def setup_logging():
    """配置日志系统"""
    
    # 确保logs目录存在
    os.makedirs('logs', exist_ok=True)
    
    # 清理旧日志文件
    cleanup_old_logs()
    
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