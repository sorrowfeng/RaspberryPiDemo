#!/usr/bin/env python3
"""Launch one or more controller processes based on the selected bus mode."""

import argparse
import logging
import os
import subprocess
import time

from active_config import ACTIVE_PRESET
from config import (
    CONFIG_LOAD_ERROR,
    DEFAULT_COMMUNICATION_MODE,
    DEFAULT_LAUNCH_COUNT,
    ENABLE_MAIN_POWER_CYCLE_SCRIPT,
)
from log import setup_logging
from main_lifecycle import build_python_cmd, start_main_processes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_POWER_CYCLE_SCRIPT = os.path.join(BASE_DIR, "main_power_cycle.py")
logger = logging.getLogger(__name__)


def _run_main_power_cycle(python_cmd, communication_mode, launch_count) -> int:
    if not os.path.exists(MAIN_POWER_CYCLE_SCRIPT):
        raise FileNotFoundError(f"主电源控制脚本不存在: {MAIN_POWER_CYCLE_SCRIPT}")

    cmd = python_cmd + [
        MAIN_POWER_CYCLE_SCRIPT,
        f"--communication-mode={communication_mode}",
        f"--launch-count={launch_count}",
    ]
    logger.info("电源通断模式已启用，交由 main_power_cycle.py 管理生命周期")
    logger.debug("main_power_cycle command: %s", cmd)
    return subprocess.run(cmd).returncode


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

    communication_mode = args.communication_mode or DEFAULT_COMMUNICATION_MODE
    launch_count = args.launch_count if args.launch_count is not None else DEFAULT_LAUNCH_COUNT

    setup_logging(app_name="launch")
    logger.info(
        "launch.py 启动参数: preset=%s, communication_mode=%s, launch_count=%s, "
        "enable_main_power_cycle=%s",
        ACTIVE_PRESET,
        communication_mode,
        launch_count,
        ENABLE_MAIN_POWER_CYCLE_SCRIPT,
    )
    if CONFIG_LOAD_ERROR is not None:
        logger.warning("配置加载失败，已回退到默认配置: %s", CONFIG_LOAD_ERROR)

    python_cmd = build_python_cmd()
    logger.debug("python command: %s", python_cmd)

    if ENABLE_MAIN_POWER_CYCLE_SCRIPT:
        try:
            return _run_main_power_cycle(python_cmd, communication_mode, launch_count)
        except Exception as exc:
            logger.exception("启动 main_power_cycle.py 失败: %s", exc)
            return 1

    start_main_processes(
        communication_mode,
        launch_count,
        python_cmd=python_cmd,
        continue_on_error=True,
    )

    logger.info("所有启动请求已提交，按 Ctrl+C 退出 launch.py")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，launch.py 退出")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
