import logging
import sys
from datetime import datetime
import os
import threading


class _TeeStream:
    def __init__(self, original_stream, file_stream):
        self.original_stream = original_stream
        self.file_stream = file_stream
        self.encoding = getattr(original_stream, "encoding", "utf-8")

    def write(self, data):
        self.original_stream.write(data)
        try:
            self.file_stream.write(data)
        except Exception:
            pass

    def flush(self):
        self.original_stream.flush()
        try:
            self.file_stream.flush()
        except Exception:
            pass

    def isatty(self):
        return self.original_stream.isatty()


def cleanup_old_logs(log_dir="logs", max_files=100):
    """清理旧日志文件，保留最新的max_files个文件"""
    if not os.path.exists(log_dir):
        return

    # 获取所有日志文件
    log_files = []
    for filename in os.listdir(log_dir):
        if filename.endswith(".log"):
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

def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def _install_exception_hooks(logger):
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "未捕获异常",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception

    if hasattr(threading, "excepthook"):
        def handle_thread_exception(args):
            if args.exc_type is KeyboardInterrupt:
                return
            logger.critical(
                f"线程未捕获异常: {args.thread.name}",
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = handle_thread_exception


def setup_logging(app_name="app", log_dir="logs", max_files=100, tee_std_streams=True):
    """配置日志系统"""

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    # 确保logs目录存在
    os.makedirs(log_dir, exist_ok=True)

    # 清理旧日志文件
    cleanup_old_logs(log_dir=log_dir, max_files=max_files)

    # 创建 logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 设置最低日志级别

    # 清除已有的 handler（避免重复）
    logger.handlers.clear()

    # 1. 文件 handler - 输出到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_app_name = _safe_name(app_name)
    log_path = os.path.join(log_dir, f"{safe_app_name}_{timestamp}_pid{os.getpid()}.log")
    file_handler = logging.FileHandler(
        filename=log_path,
        mode="a",  # 追加模式
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    # 2. 控制台 handler - 输出到终端
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上

    # 设置日志格式
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d - %(levelname)s - "
        "pid=%(process)d - %(threadName)s - %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加 handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logging.captureWarnings(True)
    _install_exception_hooks(logger)
    if tee_std_streams:
        sys.stdout = _TeeStream(sys.__stdout__, file_handler.stream)
        sys.stderr = _TeeStream(sys.__stderr__, file_handler.stream)

    logger.info(f"日志已初始化: app={app_name}, file={log_path}")

    return logger
