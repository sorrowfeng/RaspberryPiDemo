import contextlib
import contextvars
import atexit
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import sys
import threading
from datetime import datetime


LOG_RUN_ID_ENV = "RPD_LOG_RUN_ID"
LOG_SESSION_DIR_ENV = "RPD_LOG_SESSION_DIR"
LOG_FILE_ENV = "RPD_LOG_FILE"

DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5
DEFAULT_MAX_SESSIONS = 30

_CONTEXT_FIELDS = ("run_id", "mode", "device", "cycle", "command_id")
_base_context = {field: "-" for field in _CONTEXT_FIELDS}
_base_context_lock = threading.RLock()
_dynamic_context = contextvars.ContextVar("rpd_log_context", default={})


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))


def _context_value(value):
    if value is None or value == "":
        return "-"
    return str(value)


def get_logging_context() -> dict:
    with _base_context_lock:
        context = dict(_base_context)
    context.update(_dynamic_context.get())
    return context


def set_process_logging_context(**fields) -> None:
    """Bind context visible to background threads in the current process."""
    with _base_context_lock:
        for key, value in fields.items():
            if key not in _CONTEXT_FIELDS or key == "run_id":
                continue
            _base_context[key] = _context_value(value)


def set_logging_context(**fields) -> None:
    """Update context fields for subsequent records in the current context."""
    context = dict(_dynamic_context.get())
    for key, value in fields.items():
        if key not in _CONTEXT_FIELDS or key == "run_id":
            continue
        if value is None:
            context.pop(key, None)
        else:
            context[key] = _context_value(value)
    _dynamic_context.set(context)


@contextlib.contextmanager
def logging_context(**fields):
    """Temporarily bind mode/device/cycle/command context to log records."""
    context = dict(_dynamic_context.get())
    for key, value in fields.items():
        if key not in _CONTEXT_FIELDS or key == "run_id":
            continue
        if value is None:
            context.pop(key, None)
        else:
            context[key] = _context_value(value)
    token = _dynamic_context.set(context)
    try:
        yield
    finally:
        _dynamic_context.reset(token)


class _ContextFilter(logging.Filter):
    def filter(self, record):
        context = get_logging_context()
        for field in _CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, _context_value(context.get(field)))
        return True


class _TeeStream:
    """Mirror stdio to the console and a rotating, formatted file handler."""

    def __init__(self, original_stream, file_handler, stream_name: str, level: int):
        self.original_stream = original_stream
        self.file_handler = file_handler
        self.stream_name = stream_name
        self.level = level
        self.encoding = getattr(original_stream, "encoding", "utf-8")
        self.errors = getattr(original_stream, "errors", "replace")
        self._lock = threading.RLock()
        self._buffers = {}

    def _emit_line(self, line: str) -> None:
        if not line:
            return
        record = logging.LogRecord(
            name=f"stdio.{self.stream_name}",
            level=self.level,
            pathname=f"<{self.stream_name}>",
            lineno=0,
            msg=line,
            args=(),
            exc_info=None,
        )
        try:
            self.file_handler.handle(record)
        except Exception:
            # Logging must never break device control because a log sink failed.
            pass

    def write(self, data):
        if not data:
            return 0

        try:
            self.original_stream.write(data)
        except Exception:
            pass

        thread_id = threading.get_ident()
        with self._lock:
            buffered = self._buffers.get(thread_id, "") + str(data)
            lines = buffered.split("\n")
            self._buffers[thread_id] = lines.pop()
            for line in lines:
                self._emit_line(line.rstrip("\r"))
        return len(data)

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass

        thread_id = threading.get_ident()
        with self._lock:
            buffered = self._buffers.pop(thread_id, "")
            if buffered:
                self._emit_line(buffered.rstrip("\r"))
            try:
                self.file_handler.flush()
            except Exception:
                pass

    def isatty(self):
        return bool(getattr(self.original_stream, "isatty", lambda: False)())

    def fileno(self):
        return self.original_stream.fileno()

    def writable(self):
        return True


def cleanup_old_logs(log_dir="logs", max_files=100):
    """Clean legacy flat log files; session directories are handled separately."""
    if not os.path.exists(log_dir):
        return

    log_files = []
    for filename in os.listdir(log_dir):
        if filename.endswith(".log"):
            file_path = os.path.join(log_dir, filename)
            if os.path.isfile(file_path):
                log_files.append((os.path.getctime(file_path), file_path))

    log_files.sort()
    while len(log_files) > max_files:
        _, file_path = log_files.pop(0)
        try:
            os.remove(file_path)
        except Exception as exc:
            print(f"删除旧日志文件失败: {exc}", file=sys.__stderr__)


def _is_pid_running(pid: int) -> bool:
    if sys.platform.startswith("win32"):
        try:
            import ctypes
            from ctypes import wintypes

            process_query_limited_information = 0x1000
            synchronize = 0x00100000
            wait_timeout = 0x00000102
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(
                process_query_limited_information | synchronize,
                False,
                int(pid),
            )
            if not handle:
                return ctypes.get_last_error() == 5
            try:
                return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return True

    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _session_has_active_process(session_dir: str) -> bool:
    active = False
    try:
        names = os.listdir(session_dir)
    except OSError:
        return True

    for name in names:
        if not name.startswith(".active_pid"):
            continue
        marker_path = os.path.join(session_dir, name)
        try:
            pid = int(name[len(".active_pid"):])
        except ValueError:
            continue
        if _is_pid_running(pid):
            active = True
            continue
        try:
            os.remove(marker_path)
        except OSError:
            pass
    return active


def _register_active_process(session_dir: str) -> None:
    marker_path = os.path.join(session_dir, f".active_pid{os.getpid()}")
    try:
        with open(marker_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(f"{datetime.now().astimezone().isoformat()}\n")
    except OSError:
        return

    def remove_marker():
        # Close rotating handlers before declaring the session process inactive.
        logging.shutdown()
        try:
            os.remove(marker_path)
        except OSError:
            pass

    atexit.register(remove_marker)


def cleanup_old_log_sessions(log_root: str, current_session: str, max_sessions: int) -> None:
    """Keep a bounded number of complete launch sessions."""
    if max_sessions <= 0 or not os.path.isdir(log_root):
        return

    current_session = os.path.abspath(current_session)
    sessions = []
    for name in os.listdir(log_root):
        path = os.path.abspath(os.path.join(log_root, name))
        if path == current_session or not os.path.isdir(path):
            continue
        if not os.path.isfile(os.path.join(path, "session.json")):
            continue
        if _session_has_active_process(path):
            continue
        try:
            sessions.append((os.path.getmtime(path), path))
        except OSError:
            continue

    sessions.sort()
    # Include the current session in the retention count.
    while len(sessions) + 1 > max_sessions:
        _, path = sessions.pop(0)
        try:
            shutil.rmtree(path)
        except Exception as exc:
            print(f"删除旧日志批次失败: path={path}, error={exc}", file=sys.__stderr__)


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
                "线程未捕获异常: %s",
                args.thread.name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

        threading.excepthook = handle_thread_exception


def _resolve_log_session(log_dir: str):
    inherited_run_id = os.environ.get(LOG_RUN_ID_ENV)
    inherited_session_dir = os.environ.get(LOG_SESSION_DIR_ENV)
    if inherited_run_id and inherited_session_dir:
        return inherited_run_id, os.path.abspath(inherited_session_dir), False

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_pid{os.getpid()}"
    log_root = os.path.abspath(log_dir)
    session_dir = os.path.join(log_root, _safe_name(run_id))
    os.environ[LOG_RUN_ID_ENV] = run_id
    os.environ[LOG_SESSION_DIR_ENV] = session_dir
    return run_id, session_dir, True


def _write_session_metadata(
    session_dir: str,
    run_id: str,
    app_name: str,
    communication_mode,
) -> None:
    metadata_path = os.path.join(session_dir, "session.json")
    if os.path.exists(metadata_path):
        return
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "source_pid": os.getpid(),
        "entry_app": app_name,
        "communication_mode": communication_mode,
    }
    try:
        with open(metadata_path, "x", encoding="utf-8") as file_obj:
            json.dump(metadata, file_obj, ensure_ascii=False, indent=2)
            file_obj.write("\n")
    except FileExistsError:
        pass


def _write_latest_pointer(log_root: str, session_dir: str) -> None:
    pointer_path = os.path.join(log_root, "latest.txt")
    temp_path = f"{pointer_path}.{os.getpid()}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as file_obj:
            file_obj.write(f"{os.path.abspath(session_dir)}\n")
        os.replace(temp_path, pointer_path)
    except OSError:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _close_root_handlers(logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def setup_logging(
    app_name="app",
    log_dir="logs",
    max_files=100,
    tee_std_streams=True,
    *,
    communication_mode=None,
    device_index=None,
    max_bytes=DEFAULT_MAX_BYTES,
    backup_count=DEFAULT_BACKUP_COUNT,
    max_sessions=DEFAULT_MAX_SESSIONS,
):
    """Configure per-process rotating logs within one shared launch session."""
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    run_id, session_dir, created_session = _resolve_log_session(log_dir)
    log_root = os.path.abspath(log_dir)
    os.makedirs(session_dir, exist_ok=True)
    _write_session_metadata(
        session_dir,
        run_id,
        app_name,
        communication_mode,
    )
    _register_active_process(session_dir)
    if created_session:
        _write_latest_pointer(log_root, session_dir)
        cleanup_old_logs(log_dir=log_root, max_files=max_files)
        cleanup_old_log_sessions(log_root, session_dir, max_sessions=max_sessions)

    with _base_context_lock:
        _base_context.update(
            {
                "run_id": _context_value(run_id),
                "mode": _context_value(communication_mode),
                "device": _context_value(device_index),
                "cycle": "-",
                "command_id": "-",
            }
        )
    _dynamic_context.set({})

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    _close_root_handlers(logger)

    safe_app_name = _safe_name(app_name)
    log_path = os.path.abspath(
        os.path.join(session_dir, f"{safe_app_name}_pid{os.getpid()}.log")
    )
    file_handler = RotatingFileHandler(
        filename=log_path,
        mode="a",
        maxBytes=max(0, int(max_bytes)),
        backupCount=max(0, int(backup_count)),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d - %(levelname)s - "
        "run=%(run_id)s mode=%(mode)s device=%(device)s cycle=%(cycle)s "
        "command=%(command_id)s pid=%(process)d thread=%(threadName)s - "
        "%(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    context_filter = _ContextFilter()
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        handler.addFilter(context_filter)
        logger.addHandler(handler)

    logging.captureWarnings(True)
    _install_exception_hooks(logger)
    if tee_std_streams:
        sys.stdout = _TeeStream(sys.__stdout__, file_handler, "stdout", logging.INFO)
        sys.stderr = _TeeStream(sys.__stderr__, file_handler, "stderr", logging.ERROR)

    os.environ[LOG_FILE_ENV] = log_path
    logger.log_path = log_path
    logger.log_session_dir = session_dir
    logger.run_id = run_id
    logger.info(
        "日志已初始化: app=%s, file=%s, rotate_max_bytes=%s, backups=%s",
        app_name,
        log_path,
        max_bytes,
        backup_count,
    )
    return logger
