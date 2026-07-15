"""Runtime control helpers for main.py processes."""

import json
import logging
import os
import signal
import sys
import time
import uuid

from log import LOG_FILE_ENV, LOG_RUN_ID_ENV, get_logging_context


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
DEFAULT_STOP_TIMEOUT = 5.0
DEFAULT_CONTROL_TIMEOUT = 15.0


def device_label(device_index):
    return "auto" if device_index is None else str(device_index)


def target_sort_key(data):
    device_index = data.get("device_index")
    try:
        device_order = int(device_index)
    except (TypeError, ValueError):
        device_order = 9999
    return (
        device_order,
        str(data.get("device_label") or ""),
        int(data.get("pid") or 0),
    )


def runtime_pid_path(communication_mode, device_index):
    return os.path.join(
        RUNTIME_DIR,
        f"main_{communication_mode}_device_{device_label(device_index)}.pid",
    )


def runtime_command_path(communication_mode, device_index):
    return os.path.join(
        RUNTIME_DIR,
        f"main_{communication_mode}_device_{device_label(device_index)}.command.json",
    )


def runtime_response_path(communication_mode, device_index):
    return os.path.join(
        RUNTIME_DIR,
        f"main_{communication_mode}_device_{device_label(device_index)}.response.json",
    )


def runtime_progress_path(communication_mode, device_index):
    return os.path.join(
        RUNTIME_DIR,
        f"main_{communication_mode}_device_{device_label(device_index)}.progress.json",
    )


def atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file_obj:
        json.dump(data, file_obj, ensure_ascii=False, indent=2)
        file_obj.write("\n")
    os.replace(temp_path, path)


def read_json_file(path, *, warn: bool = True):
    try:
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except FileNotFoundError:
        return None
    except Exception as exc:
        if warn:
            logging.warning("读取 JSON 文件失败: path=%s, error=%s", path, exc)
        return None


def is_windows_pid_running(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    wait_timeout = 0x00000102
    error_access_denied = 5

    handle = kernel32.OpenProcess(
        process_query_limited_information | synchronize,
        False,
        int(pid),
    )
    if not handle:
        return ctypes.get_last_error() == error_access_denied

    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def is_pid_running(pid: int) -> bool:
    if sys.platform.startswith("win32"):
        return is_windows_pid_running(pid)

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def pid_cmdline_matches_main_py(pid: int) -> bool:
    if not sys.platform.startswith("linux"):
        return True

    cmdline_path = f"/proc/{pid}/cmdline"
    try:
        with open(cmdline_path, "rb") as file_obj:
            raw_parts = file_obj.read().split(b"\0")
    except FileNotFoundError:
        return False
    except PermissionError:
        return True
    except Exception as exc:
        logging.warning("读取进程命令行失败，保守视为有效: pid=%s, error=%s", pid, exc)
        return True

    parts = [part.decode(errors="ignore") for part in raw_parts if part]
    return any(os.path.basename(part) == "main.py" for part in parts)


def is_runtime_main_process_running(data) -> bool:
    pid = data["pid"]
    if not is_pid_running(pid):
        return False

    if pid_cmdline_matches_main_py(pid):
        return True

    logging.warning(
        "main.py PID 文件对应的进程不是 main.py，按失效处理: pid=%s, path=%s",
        pid,
        data.get("path"),
    )
    return False


def read_pid_file(path):
    data = read_json_file(path)
    if data is None:
        logging.warning("读取 main.py PID 文件失败，忽略: path=%s", path)
        return None

    try:
        data["pid"] = int(data["pid"])
    except (KeyError, TypeError, ValueError):
        logging.warning("main.py PID 文件内容无效，忽略: path=%s", path)
        return None

    data["path"] = path
    return data


def read_control_command(communication_mode, device_index):
    path = runtime_command_path(communication_mode, device_index)
    data = read_json_file(path, warn=False)
    if data is None:
        return None

    if not data.get("id") or not data.get("action"):
        logging.warning("main.py 控制命令无效，忽略: path=%s", path)
        return None

    data["path"] = path
    return data


def complete_control_command(communication_mode, device_index, command, ok: bool, message: str):
    response = {
        "id": command.get("id"),
        "action": command.get("action"),
        "ok": bool(ok),
        "message": message,
        "pid": os.getpid(),
        "completed_at": time.time(),
        "log_context": command.get("log_context") or {},
        "log_file": os.environ.get(LOG_FILE_ENV),
    }
    atomic_write_json(runtime_response_path(communication_mode, device_index), response)

    command_path = runtime_command_path(communication_mode, device_index)
    current_command = read_json_file(command_path, warn=False)
    if current_command and current_command.get("id") == command.get("id"):
        try:
            os.remove(command_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logging.warning("删除 main.py 控制命令失败: path=%s, error=%s", command_path, exc)


def emit_control_progress(communication_mode, device_index, command, stage: str, message: str):
    progress = {
        "id": command.get("id"),
        "action": command.get("action"),
        "stage": stage,
        "message": message,
        "pid": os.getpid(),
        "updated_at": time.time(),
        "log_context": command.get("log_context") or {},
        "log_file": os.environ.get(LOG_FILE_ENV),
    }
    atomic_write_json(runtime_progress_path(communication_mode, device_index), progress)


def wait_for_main_processes(communication_mode, expected_count: int, timeout: float = DEFAULT_CONTROL_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        running = [
            data
            for data in iter_runtime_pid_files(communication_mode)
            if is_runtime_main_process_running(data)
        ]
        if len(running) >= expected_count:
            logging.info(
                "main.py 长驻进程已就绪: mode=%s, expected=%s, running=%s",
                communication_mode,
                expected_count,
                len(running),
            )
            return True
        time.sleep(0.1)

    running = [
        data
        for data in iter_runtime_pid_files(communication_mode)
        if is_runtime_main_process_running(data)
    ]
    logging.error(
        "等待 main.py 长驻进程就绪超时: mode=%s, expected=%s, running=%s",
        communication_mode,
        expected_count,
        len(running),
    )
    return False


def iter_runtime_pid_files(communication_mode=None, device_index=None):
    if not os.path.isdir(RUNTIME_DIR):
        return

    expected_label = None if device_index is None else device_label(device_index)
    for filename in os.listdir(RUNTIME_DIR):
        if not filename.startswith("main_") or not filename.endswith(".pid"):
            continue

        path = os.path.join(RUNTIME_DIR, filename)
        data = read_pid_file(path)
        if data is None:
            continue

        if communication_mode is not None and data.get("communication_mode") != communication_mode:
            continue
        if expected_label is not None and str(data.get("device_label")) != expected_label:
            continue

        yield data


def remove_stale_pid_file(path):
    try:
        os.remove(path)
        logging.info("已删除失效 main.py PID 文件: %s", path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logging.warning("删除失效 main.py PID 文件失败: path=%s, error=%s", path, exc)


def register_runtime_pid(communication_mode, device_index):
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    path = runtime_pid_path(communication_mode, device_index)
    data = {
        "pid": os.getpid(),
        "communication_mode": communication_mode,
        "device_index": device_index,
        "device_label": device_label(device_index),
        "started_at": time.time(),
        "log_run_id": os.environ.get(LOG_RUN_ID_ENV),
        "log_file": os.environ.get(LOG_FILE_ENV),
    }
    atomic_write_json(path, data)
    logging.info("已写入 main.py PID 文件: %s", path)
    return path


def unregister_runtime_pid(path):
    if not path:
        return

    data = read_pid_file(path)
    if data is not None and data.get("pid") != os.getpid():
        logging.warning(
            "main.py PID 文件已指向其他进程，不删除: path=%s, pid=%s",
            path,
            data.get("pid"),
        )
        return

    try:
        os.remove(path)
        logging.info("已删除 main.py PID 文件: %s", path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logging.warning("删除 main.py PID 文件失败: path=%s, error=%s", path, exc)

    if data is not None:
        for extra_path in (
            runtime_command_path(data.get("communication_mode"), data.get("device_index")),
            runtime_response_path(data.get("communication_mode"), data.get("device_index")),
            runtime_progress_path(data.get("communication_mode"), data.get("device_index")),
        ):
            try:
                os.remove(extra_path)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logging.warning("删除 main.py 控制文件失败: path=%s, error=%s", extra_path, exc)


def signal_name(signum):
    try:
        return signal.Signals(signum).name
    except Exception:
        return str(signum)


def install_signal_handlers(motion_ctrl):
    def handle_signal(signum, _frame):
        motion_ctrl.request_shutdown(signal_name(signum))

    for signal_value in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if signal_value is None:
            continue
        try:
            signal.signal(signal_value, handle_signal)
            logging.debug("已安装退出信号处理: %s", signal_name(signal_value))
        except Exception as exc:
            logging.warning("安装退出信号处理失败: signal=%s, error=%s", signal_value, exc)


def stop_existing_main_processes(communication_mode=None, device_index=None, timeout=DEFAULT_STOP_TIMEOUT):
    targets = []
    for data in iter_runtime_pid_files(communication_mode, device_index):
        pid = data["pid"]
        path = data["path"]
        if pid == os.getpid():
            continue

        if not is_runtime_main_process_running(data):
            remove_stale_pid_file(path)
            continue

        targets.append(data)

    if not targets:
        logging.info(
            "没有找到需要停止的 main.py 进程: communication_mode=%s, device_index=%s",
            communication_mode,
            device_index,
        )
        return 0

    for data in targets:
        try:
            os.kill(data["pid"], signal.SIGTERM)
            logging.info(
                "已请求 main.py 优雅退出: pid=%s, mode=%s, device=%s",
                data["pid"],
                data.get("communication_mode"),
                data.get("device_label"),
            )
        except ProcessLookupError:
            remove_stale_pid_file(data["path"])
        except Exception as exc:
            logging.error("请求 main.py 退出失败: pid=%s, error=%s", data["pid"], exc)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pending = []
        for data in targets:
            if os.path.exists(data["path"]) and is_runtime_main_process_running(data):
                pending.append(data)

        if not pending:
            logging.info("匹配的 main.py 进程已全部退出")
            return 0

        time.sleep(0.1)

    for data in targets:
        if os.path.exists(data["path"]) and is_runtime_main_process_running(data):
            logging.error(
                "main.py 进程未在超时时间内退出: pid=%s, mode=%s, device=%s",
                data["pid"],
                data.get("communication_mode"),
                data.get("device_label"),
            )
    return 1


def request_existing_main_action(
    action: str,
    communication_mode: str,
    device_index=None,
    timeout: float = DEFAULT_CONTROL_TIMEOUT,
    payload=None,
    progress_stage=None,
    on_progress=None,
    min_successes=None,
    command_spacing_seconds: float = 0.0,
    absolute_deadline=None,
) -> bool:
    targets = []
    for data in iter_runtime_pid_files(communication_mode, device_index):
        if not is_runtime_main_process_running(data):
            remove_stale_pid_file(data["path"])
            continue
        targets.append(data)
    targets.sort(key=target_sort_key)

    if not targets:
        logging.error(
            "没有找到可接收控制命令的 main.py 进程: action=%s, mode=%s, device_index=%s",
            action,
            communication_mode,
            device_index,
        )
        return False

    effective_deadline = None
    if absolute_deadline is not None:
        effective_deadline = min(
            absolute_deadline,
            time.monotonic() + timeout,
        )

    command_ids = {}
    pending = {}
    failed = {}
    if isinstance(progress_stage, str):
        progress_stages = {progress_stage}
    else:
        progress_stages = set(progress_stage or [])
    progressed = set()
    succeeded = set()

    def poll_pending_once():
        for pid, data in list(pending.items()):
            if not is_runtime_main_process_running(data):
                failed[pid] = "进程已退出"
                pending.pop(pid, None)
                continue

            if progress_stages:
                progress = read_json_file(
                    runtime_progress_path(data.get("communication_mode"), data.get("device_index")),
                    warn=False,
                )
                if (
                    progress
                    and progress.get("id") == command_ids[pid]
                    and progress.get("stage") in progress_stages
                    and (pid, progress.get("stage")) not in progressed
                ):
                    progressed.add((pid, progress.get("stage")))
                    logging.info(
                        "main.py 控制命令进度: action=%s, command_id=%s, stage=%s, "
                        "pid=%s, device=%s, message=%s, log_file=%s",
                        action,
                        command_ids[pid],
                        progress.get("stage"),
                        pid,
                        data.get("device_label"),
                        progress.get("message"),
                        data.get("log_file"),
                    )
                    if on_progress:
                        try:
                            on_progress(data, progress)
                        except Exception as exc:
                            logging.warning(
                                "main.py 控制进度回调失败: action=%s, stage=%s, pid=%s, error=%s",
                                action,
                                progress.get("stage"),
                                pid,
                                exc,
                            )

            response = read_json_file(
                runtime_response_path(data.get("communication_mode"), data.get("device_index")),
                warn=False,
            )
            if not response or response.get("id") != command_ids[pid]:
                continue

            if response.get("ok"):
                succeeded.add(pid)
                logging.info(
                    "main.py 控制命令完成: action=%s, command_id=%s, pid=%s, "
                    "device=%s, message=%s, log_file=%s",
                    action,
                    command_ids[pid],
                    pid,
                    data.get("device_label"),
                    response.get("message"),
                    data.get("log_file"),
                )
            else:
                failed[pid] = response.get("message") or "命令执行失败"
                logging.error(
                    "main.py 控制命令失败: action=%s, command_id=%s, pid=%s, "
                    "device=%s, message=%s, log_file=%s",
                    action,
                    command_ids[pid],
                    pid,
                    data.get("device_label"),
                    failed[pid],
                    data.get("log_file"),
                )
            pending.pop(pid, None)

    def poll_pending_until(deadline):
        while time.monotonic() < deadline:
            if pending:
                poll_pending_once()
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))

    dispatch_stopped_at = None
    for index, data in enumerate(targets):
        if effective_deadline is not None and time.monotonic() >= effective_deadline:
            dispatch_stopped_at = index
            break

        command_id = f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        command_ids[data["pid"]] = command_id
        response_path = runtime_response_path(data.get("communication_mode"), data.get("device_index"))
        try:
            os.remove(response_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logging.warning("删除旧 main.py 控制响应失败: path=%s, error=%s", response_path, exc)

        progress_path = runtime_progress_path(data.get("communication_mode"), data.get("device_index"))
        try:
            os.remove(progress_path)
        except FileNotFoundError:
            pass
        except Exception as exc:
            logging.warning("删除旧 main.py 控制进度失败: path=%s, error=%s", progress_path, exc)

        command = {
            "id": command_id,
            "action": action,
            "payload": payload or {},
            "log_context": {
                key: value
                for key, value in get_logging_context().items()
                if key in ("cycle",) and value not in (None, "", "-")
            },
            "created_at": time.time(),
            "source_pid": os.getpid(),
        }
        command_path = runtime_command_path(data.get("communication_mode"), data.get("device_index"))
        atomic_write_json(command_path, command)
        pending[data["pid"]] = data
        logging.info(
            "已发送 main.py 控制命令: action=%s, command_id=%s, pid=%s, "
            "mode=%s, device=%s, log_file=%s",
            action,
            command_id,
            data["pid"],
            data.get("communication_mode"),
            data.get("device_label"),
            data.get("log_file"),
        )

        if command_spacing_seconds > 0 and index < len(targets) - 1:
            spacing_deadline = time.monotonic() + command_spacing_seconds
            if effective_deadline is not None:
                spacing_deadline = min(spacing_deadline, effective_deadline)
            logging.debug(
                "等待下一个 main.py 控制命令间隔: action=%s, current_device=%s, spacing=%ss",
                action,
                data.get("device_label"),
                command_spacing_seconds,
            )
            poll_pending_until(spacing_deadline)

    if dispatch_stopped_at is not None:
        for data in targets[dispatch_stopped_at:]:
            failed[data["pid"]] = "控制截止时间前未能发送控制命令"
            logging.error(
                "控制截止时间前未能发送 main.py 控制命令: "
                "action=%s, pid=%s, mode=%s, device=%s",
                action,
                data["pid"],
                data.get("communication_mode"),
                data.get("device_label"),
            )

    deadline = (
        effective_deadline
        if effective_deadline is not None
        else time.monotonic() + timeout
    )
    while time.monotonic() < deadline and pending:
        poll_pending_once()
        if pending:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))

    for pid, data in pending.items():
        failed[pid] = "等待控制命令响应超时"
        logging.error(
            "main.py 控制命令超时: action=%s, command_id=%s, pid=%s, "
            "mode=%s, device=%s, log_file=%s",
            action,
            command_ids[pid],
            pid,
            data.get("communication_mode"),
            data.get("device_label"),
            data.get("log_file"),
        )

    if min_successes is not None:
        if len(succeeded) >= min_successes:
            if failed:
                logging.warning(
                    "main.py 控制命令部分成功: action=%s, succeeded=%s, required=%s, failed=%s",
                    action,
                    len(succeeded),
                    min_successes,
                    len(failed),
                )
            return True

        logging.error(
            "main.py 控制命令成功数量不足: action=%s, succeeded=%s, required=%s, failed=%s",
            action,
            len(succeeded),
            min_successes,
            len(failed),
        )
        return False

    return not failed
