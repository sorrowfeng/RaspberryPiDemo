"""
Program entry for RaspberryPiDemo.
"""

import argparse
import logging
import sys

from active_config import ACTIVE_PRESET
from config import CONFIG_LOAD_ERROR, DEFAULT_COMMUNICATION_MODE
from log import setup_logging
from main_runtime_control import (
    DEFAULT_CONTROL_TIMEOUT,
    DEFAULT_STOP_TIMEOUT,
    install_signal_handlers,
    register_runtime_pid,
    request_existing_main_action,
    stop_existing_main_processes,
    unregister_runtime_pid,
)
from motion_system import MotionController


def main():
    parser = argparse.ArgumentParser(description="LHandPro GPIO 控制程序")
    parser.add_argument(
        "--device-index",
        "-i",
        type=int,
        default=None,
        choices=[0, 1, 2, 3],
        help="设备索引，可选值: 0, 1, 2, 3",
    )
    parser.add_argument(
        "--communication-mode",
        "-m",
        type=str,
        default=None,
        choices=["CANFD", "ECAT", "RS485"],
        help="通信模式，可选值: CANFD, ECAT, RS485；不指定时交互选择",
    )
    parser.add_argument(
        "--rs485-port",
        type=str,
        default=None,
        help="为当前 main.py 实例固定分配 RS485 串口；不指定时沿用配置或自动扫描",
    )
    parser.add_argument(
        "--enable-gpio",
        "-g",
        action="store_true",
        default=True,
        help="启用 GPIO 控制（默认: True）",
    )
    parser.add_argument(
        "--no-enable-gpio",
        action="store_false",
        dest="enable_gpio",
        help="禁用 GPIO 控制",
    )
    parser.add_argument(
        "--stop-existing",
        "--disconnect-existing",
        "--shutdown-existing",
        "--disconnect",
        action="store_true",
        dest="stop_existing",
        help="请求已运行的 main.py 停止运动并断开连接；可配合 -m/-i 过滤目标",
    )
    parser.add_argument(
        "--stop-timeout",
        type=float,
        default=DEFAULT_STOP_TIMEOUT,
        help=f"等待已运行 main.py 优雅退出的超时时间，默认 {DEFAULT_STOP_TIMEOUT}s",
    )
    parser.add_argument(
        "--managed-by-power-cycle",
        "--managed-control",
        action="store_true",
        dest="managed_control",
        help="作为主电源通断测试的长驻子进程运行，等待外部命令控制连接、回零、开始和停止运动",
    )
    parser.add_argument(
        "--start-cycle-existing",
        action="store_true",
        help="请求已运行的长驻 main.py 连接、回零并开始循环运动",
    )
    parser.add_argument(
        "--stop-cycle-existing",
        action="store_true",
        help="请求已运行的长驻 main.py 停止运动并断开连接，但不退出 main.py 进程",
    )
    parser.add_argument(
        "--control-timeout",
        type=float,
        default=DEFAULT_CONTROL_TIMEOUT,
        help=f"等待长驻 main.py 控制命令完成的超时时间，默认 {DEFAULT_CONTROL_TIMEOUT}s",
    )
    args = parser.parse_args()

    if args.start_cycle_existing or args.stop_cycle_existing:
        action = "start_cycle" if args.start_cycle_existing else "stop_cycle"
        communication_mode = args.communication_mode or DEFAULT_COMMUNICATION_MODE
        setup_logging(app_name=f"main_control_{action}_{communication_mode}")
        logging.info(
            "main.py 控制命令: preset=%s, action=%s, communication_mode=%s, "
            "device_index=%s, timeout=%s",
            ACTIVE_PRESET,
            action,
            communication_mode,
            args.device_index,
            args.control_timeout,
        )
        return 0 if request_existing_main_action(
            action,
            communication_mode,
            device_index=args.device_index,
            timeout=args.control_timeout,
        ) else 1

    if args.stop_existing:
        stop_label = args.communication_mode or "all"
        setup_logging(app_name=f"main_stop_existing_{stop_label}")
        logging.info(
            "main.py 停止命令: preset=%s, communication_mode=%s, device_index=%s, timeout=%s",
            ACTIVE_PRESET,
            args.communication_mode,
            args.device_index,
            args.stop_timeout,
        )
        return stop_existing_main_processes(
            communication_mode=args.communication_mode,
            device_index=args.device_index,
            timeout=args.stop_timeout,
        )

    if args.communication_mode is None:
        modes = ["CANFD", "ECAT", "RS485"]
        print("请选择通信模式:")
        for index, mode in enumerate(modes):
            print(f"  [{index}] {mode}")

        while True:
            try:
                choice = input(">>> ").strip()
                if choice == "":
                    args.communication_mode = modes[0]
                    print(f"使用默认模式: {args.communication_mode}")
                    break

                mode_index = int(choice)
                if 0 <= mode_index < len(modes):
                    args.communication_mode = modes[mode_index]
                    break

                print(f"请输入 0 - {len(modes) - 1}")
            except ValueError:
                print("请输入数字")

    device_label = "auto" if args.device_index is None else str(args.device_index)
    setup_logging(app_name=f"main_{args.communication_mode}_device_{device_label}")
    logging.info(
        "main.py 启动参数: preset=%s, communication_mode=%s, device_index=%s, "
        "rs485_port=%s, enable_gpio=%s, managed_control=%s",
        ACTIVE_PRESET,
        args.communication_mode,
        args.device_index,
        args.rs485_port,
        args.enable_gpio,
        args.managed_control,
    )
    if CONFIG_LOAD_ERROR is not None:
        logging.warning("配置加载失败，已回退到默认配置: %s", CONFIG_LOAD_ERROR)
    pid_path = register_runtime_pid(args.communication_mode, args.device_index)
    motion_ctrl = MotionController(
        communication_mode=args.communication_mode,
        device_index=args.device_index,
        enable_gpio=args.enable_gpio,
        rs485_port_name=args.rs485_port,
    )
    install_signal_handlers(motion_ctrl)
    try:
        return motion_ctrl.run(managed_control=args.managed_control)
    finally:
        unregister_runtime_pid(pid_path)


if __name__ == "__main__":
    sys.exit(main())
