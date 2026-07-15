#!/usr/bin/env python3
"""Shared helpers for launching and stopping main.py controller processes."""

import logging
import os
import signal
import subprocess
import sys
import time


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
DEFAULT_STOP_TIMEOUT = 5.0
logger = logging.getLogger(__name__)


def build_python_cmd():
    if sys.platform.startswith("win32"):
        return ["python3"] if sys.executable.endswith("python3") else ["python"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return ["python3"]
    preserved_log_env = [
        f"{name}={os.environ[name]}"
        for name in ("RPD_LOG_RUN_ID", "RPD_LOG_SESSION_DIR")
        if os.environ.get(name)
    ]
    if preserved_log_env:
        return ["sudo", "env", *preserved_log_env, "python3"]
    return ["sudo", "python3"]


def setup_rs485_mode() -> int:
    cmd = [sys.executable, os.path.join(TOOLS_DIR, "setup_rs485_mode.py")]
    logger.info("执行 USB-to-RS485 模式配置脚本: %s", cmd)
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
    )
    for line in (result.stdout or "").splitlines():
        logger.info("RS485_SETUP stdout: %s", line)
    for line in (result.stderr or "").splitlines():
        logger.warning("RS485_SETUP stderr: %s", line)
    if result.returncode == 0:
        logger.info("USB-to-RS485 模式配置完成: returncode=%s", result.returncode)
    else:
        logger.warning("USB-to-RS485 模式配置脚本返回非零: returncode=%s", result.returncode)
    return result.returncode


def prepare_bus(communication_mode: str) -> None:
    if communication_mode != "RS485":
        return

    setup_rs485_mode()


def start_process(cmd, new_process_group: bool = False):
    if not new_process_group:
        return subprocess.Popen(cmd)

    if sys.platform.startswith("win32"):
        process = subprocess.Popen(
            cmd,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        process._managed_new_process_group = True
        return process

    process = subprocess.Popen(cmd, start_new_session=True)
    process._managed_new_process_group = True
    process._managed_pgid = process.pid
    return process


def build_main_command(
    python_cmd,
    communication_mode: str,
    launch_count: int,
    index: int,
    managed_control: bool = False,
    rs485_port_names=None,
):
    cmd = python_cmd + [
        "main.py",
        f"--communication-mode={communication_mode}",
    ]
    if launch_count > 1:
        cmd.append(f"--device-index={index}")
    if communication_mode == "RS485" and rs485_port_names:
        cmd.append(f"--rs485-port={rs485_port_names[index]}")
    if managed_control:
        cmd.append("--managed-by-power-cycle")
    return cmd


def request_existing_main_stop(
    communication_mode: str,
    python_cmd=None,
    *,
    timeout: float = DEFAULT_STOP_TIMEOUT,
) -> int:
    python_cmd = python_cmd or build_python_cmd()
    cmd = python_cmd + [
        "main.py",
        "--stop-existing",
        f"--communication-mode={communication_mode}",
        f"--stop-timeout={timeout}",
    ]
    logger.info("请求已运行 main.py 优雅退出: %s", cmd)
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        logger.info("main.py --stop-existing 已完成: returncode=%s", result.returncode)
    else:
        logger.warning("main.py --stop-existing 返回非零: returncode=%s", result.returncode)
    return result.returncode


def start_main_processes(
    communication_mode: str,
    launch_count: int,
    python_cmd=None,
    *,
    prepare: bool = True,
    start_interval: float = 1.0,
    new_process_group: bool = False,
    continue_on_error: bool = False,
    stop_timeout: float = DEFAULT_STOP_TIMEOUT,
    startup_check_delay: float = 0.2,
    managed_control: bool = False,
    rs485_port_names=None,
):
    if (
        communication_mode == "RS485"
        and rs485_port_names is not None
        and len(rs485_port_names) != launch_count
    ):
        raise ValueError(
            "RS485 端口数量与启动数量不一致: "
            f"ports={len(rs485_port_names)}, launch_count={launch_count}"
        )

    if prepare:
        prepare_bus(communication_mode)

    python_cmd = python_cmd or build_python_cmd()
    processes = []

    for index in range(launch_count):
        try:
            cmd = build_main_command(
                python_cmd,
                communication_mode,
                launch_count,
                index,
                managed_control=managed_control,
                rs485_port_names=rs485_port_names,
            )
            logger.debug("启动 main.py 命令: %s", cmd)
            process = start_process(cmd, new_process_group=new_process_group)
            processes.append(process)
            label = f"device {index}" if launch_count > 1 else "device"
            logger.info("%s started, pid=%s", label, process.pid)

            if startup_check_delay > 0:
                time.sleep(startup_check_delay)
                returncode = process.poll()
                if returncode is not None:
                    raise RuntimeError(
                        f"{label} exited immediately with returncode={returncode}"
                    )

            time.sleep(start_interval)
        except Exception as exc:
            label = str(index) if launch_count > 1 else ""
            logger.exception("启动设备进程失败: device=%s, error=%s", label, exc)
            if continue_on_error:
                continue
            stop_main_processes(processes, stop_timeout)
            raise

    running_count = sum(1 for process in processes if is_process_active(process))
    logger.info(
        "main.py 启动请求完成: requested=%s, running=%s",
        launch_count,
        running_count,
    )
    return processes


def process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_process_active(process) -> bool:
    if process.poll() is None:
        return True

    pgid = getattr(process, "_managed_pgid", None)
    if pgid is not None and not sys.platform.startswith("win32"):
        return process_group_exists(pgid)

    return False


def terminate_process(process):
    pgid = getattr(process, "_managed_pgid", None)
    if pgid is not None and not sys.platform.startswith("win32"):
        try:
            os.killpg(pgid, signal.SIGTERM)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass

    if process.poll() is not None:
        return

    if sys.platform.startswith("win32"):
        ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
        if ctrl_break is not None:
            process.send_signal(ctrl_break)
            return
        process.terminate()
        return

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.terminate()
    except Exception:
        process.terminate()


def kill_process(process):
    pgid = getattr(process, "_managed_pgid", None)
    if pgid is not None and not sys.platform.startswith("win32"):
        try:
            os.killpg(pgid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except Exception:
            pass

    if process.poll() is not None:
        return

    if sys.platform.startswith("win32"):
        process.kill()
        return

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        process.kill()
    except Exception:
        process.kill()


def stop_main_processes(processes, timeout: float = DEFAULT_STOP_TIMEOUT) -> bool:
    running = [process for process in processes if is_process_active(process)]
    if not running:
        logger.debug("没有需要停止的 main.py 进程")
        return True

    logger.info("正在停止 %s 个 main.py 进程", len(running))
    for process in running:
        logger.debug("发送停止信号: pid=%s", process.pid)
        terminate_process(process)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(is_process_active(process) for process in running):
            break

        for process in running:
            if process.poll() is None:
                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass

        time.sleep(0.1)

    still_running = [process for process in running if is_process_active(process)]
    if still_running:
        logger.warning("有 %s 个 main.py 进程未按时退出，准备强制结束", len(still_running))
        for process in still_running:
            logger.debug("发送强制结束信号: pid=%s", process.pid)
            kill_process(process)
        for process in still_running:
            try:
                if process.poll() is None:
                    process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                logger.error("进程强制结束后仍未退出: pid=%s", process.pid)

    for process in running:
        logger.info(
            "main.py 进程停止状态: pid=%s, returncode=%s",
            process.pid,
            process.poll(),
        )

    final_running = [process for process in running if is_process_active(process)]
    return len(final_running) == 0
