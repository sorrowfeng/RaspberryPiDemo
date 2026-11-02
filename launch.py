#!/usr/bin/env python3
"""Launch one or more controller processes based on the selected bus mode."""

import argparse
import logging
import os
import subprocess
import time

from active_config import ACTIVE_PRESET
from app.config import (
    COMMUNICATION_CONFIG,
    CONFIG_LOAD_ERROR,
    FEATURE_FLAGS,
    LOG_RETENTION_CONFIG,
)
from app.log import setup_logging
from app.lifecycle import (
    build_python_cmd,
    is_process_active,
    start_main_processes,
    stop_main_processes,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_POWER_CYCLE_SCRIPT = os.path.join(BASE_DIR, "power_cycle", "main.py")
logger = logging.getLogger(__name__)


def _run_main_power_cycle(python_cmd, communication_mode, launch_count) -> int:
    if not os.path.exists(MAIN_POWER_CYCLE_SCRIPT):
        raise FileNotFoundError(f"主电源控制脚本不存在: {MAIN_POWER_CYCLE_SCRIPT}")

    cmd = python_cmd + [
        MAIN_POWER_CYCLE_SCRIPT,
        f"--communication-mode={communication_mode}",
        f"--launch-count={launch_count}",
    ]
    logger.info("电源通断模式已启用，交由 power_cycle/main.py 管理生命周期")
    logger.debug("main_power_cycle command: %s", cmd)
    return subprocess.run(cmd).returncode


def supervise_main_processes(
    processes,
    *,
    communication_mode: str,
    launch_count: int,
    python_cmd,
    check_interval: float = 1.0,
    restart_backoff_seconds: float = 2.0,
) -> int:
    """监督 main.py：异常退出后按当前 preset 重拉，保证开机自启目标。

    开机 service 场景下没有人在场点确认，子进程死掉必须自动恢复。
    """
    import time as _time

    from app.lifecycle import build_main_command

    alive = list(processes)
    logger.info("子进程监督启动: count=%s", len(alive))

    try:
        while True:
            dead_indexes = [
                index for index, proc in enumerate(alive) if not is_process_active(proc)
            ]
            if not dead_indexes:
                _time.sleep(check_interval)
                continue

            for index in dead_indexes:
                proc = alive[index]
                returncode = getattr(proc, "returncode", None)
                logger.warning(
                    "检测到 main.py 退出，准备重拉: index=%s, pid=%s, returncode=%s",
                    index,
                    getattr(proc, "pid", None),
                    returncode,
                )
                _time.sleep(restart_backoff_seconds)

                cmd = build_main_command(
                    python_cmd,
                    communication_mode,
                    launch_count,
                    index,
                )
                logger.info("重拉 main.py: index=%s, cmd=%s", index, cmd)
                try:
                    from app.lifecycle import start_process

                    alive[index] = start_process(cmd)
                    logger.info("main.py 已重拉: index=%s, pid=%s", index, alive[index].pid)
                except Exception as exc:
                    logger.exception("重拉 main.py 失败: index=%s, error=%s", index, exc)

            _time.sleep(check_interval)
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止子进程并退出 launch.py")
        stop_main_processes(alive, timeout=5.0)
        return 0



def main() -> int:
    os.chdir(BASE_DIR)

    parser = argparse.ArgumentParser(description="Launch LHandPro devices")
    parser.add_argument(
        "--communication-mode",
        "-m",
        type=str,
        choices=["CANFD", "ECAT", "RS485"],
        help="Communication mode. Overrides DEFAULT_COMMUNICATION_MODE in config.py.",
    )
    parser.add_argument(
        "--launch-count",
        "-n",
        type=int,
        help="Number of processes to launch. Overrides DEFAULT_LAUNCH_COUNT in config.py.",
    )
    args = parser.parse_args()

    communication_mode = args.communication_mode or COMMUNICATION_CONFIG["default_mode"]
    launch_count = (
        args.launch_count
        if args.launch_count is not None
        else COMMUNICATION_CONFIG["default_launch_count"]
    )

    setup_logging(
        app_name="launch",
        communication_mode=communication_mode,
        device_index="all",
        **LOG_RETENTION_CONFIG,
    )
    logger.info(
        "launch.py 启动参数: preset=%s, communication_mode=%s, launch_count=%s, "
        "enable_main_power_cycle=%s",
        ACTIVE_PRESET,
        communication_mode,
        launch_count,
        FEATURE_FLAGS.get("enable_main_power_cycle", False),
    )
    if CONFIG_LOAD_ERROR is not None:
        logger.warning("配置加载失败，已回退到默认配置: %s", CONFIG_LOAD_ERROR)

    python_cmd = build_python_cmd()
    logger.debug("python command: %s", python_cmd)

    if FEATURE_FLAGS.get("enable_main_power_cycle", False):
        try:
            return _run_main_power_cycle(python_cmd, communication_mode, launch_count)
        except Exception as exc:
            logger.exception("启动 power_cycle/main.py 失败: %s", exc)
            return 1

    processes = start_main_processes(
        communication_mode,
        launch_count,
        python_cmd=python_cmd,
        continue_on_error=True,
    )

    logger.info(
        "所有启动请求已提交，进入子进程监督循环（Ctrl+C 退出）: alive=%s",
        len(processes),
    )

    return supervise_main_processes(
        processes,
        communication_mode=communication_mode,
        launch_count=launch_count,
        python_cmd=python_cmd,
    )


if __name__ == "__main__":
    raise SystemExit(main())
