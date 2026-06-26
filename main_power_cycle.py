#!/usr/bin/env python3
"""Cycle main power while managing main.py process lifecycle."""

import argparse
import logging
import os
import time

from active_config import ACTIVE_PRESET
from config import (
    CONFIG_LOAD_ERROR,
    DEFAULT_COMMUNICATION_MODE,
    DEFAULT_LAUNCH_COUNT,
    MAIN_POWER_CYCLE_BAUD_RATE,
    MAIN_POWER_CYCLE_OFF_SECONDS,
    MAIN_POWER_CYCLE_ON_SECONDS,
    MAIN_POWER_CYCLE_PORT,
    MAIN_POWER_CYCLE_START_DELAY,
    MAIN_POWER_CYCLE_STOP_TIMEOUT,
)
from log import setup_logging
from main_lifecycle import setup_rs485_mode, start_main_processes, stop_main_processes
from serial_port import SerialPort


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POWER_ON_COMMAND = bytes.fromhex("01 06 00 00 00 00 89 CA")
POWER_OFF_COMMAND = bytes.fromhex("01 06 00 00 00 01 48 0A")
SEND_DRAIN_SECONDS = 0.1
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Main power cycle controller")
    parser.add_argument(
        "--communication-mode",
        "-m",
        type=str,
        default=DEFAULT_COMMUNICATION_MODE,
        choices=["CANFD", "ECAT", "RS485"],
        help="Communication mode for managed main.py processes.",
    )
    parser.add_argument(
        "--launch-count",
        "-n",
        type=int,
        default=DEFAULT_LAUNCH_COUNT,
        help="Number of managed main.py processes to launch per power-on cycle.",
    )
    parser.add_argument(
        "--port",
        "-p",
        default=MAIN_POWER_CYCLE_PORT,
        help="Serial port name. If omitted, the script scans and selects a port.",
    )
    parser.add_argument(
        "--baud-rate",
        "-b",
        type=int,
        default=MAIN_POWER_CYCLE_BAUD_RATE,
        help=f"Serial baud rate. Default: {MAIN_POWER_CYCLE_BAUD_RATE}",
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=MAIN_POWER_CYCLE_START_DELAY,
        help="Delay after power-on before starting managed main.py processes.",
    )
    parser.add_argument(
        "--on-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_ON_SECONDS,
        help="Power-on duration for each cycle.",
    )
    parser.add_argument(
        "--off-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_OFF_SECONDS,
        help="Power-off duration for each cycle.",
    )
    parser.add_argument(
        "--stop-timeout",
        type=float,
        default=MAIN_POWER_CYCLE_STOP_TIMEOUT,
        help="Seconds to wait for managed main.py processes to stop before killing them.",
    )
    return parser.parse_args()


def select_port(serial_port: SerialPort) -> str:
    ports = serial_port.scan_available_ports()
    if not ports:
        raise RuntimeError("未找到可用串口")

    if len(ports) == 1:
        logger.info("检测到唯一串口，自动连接: %s", ports[0])
        return ports[0]

    logger.info("检测到多个串口，需要选择主电源控制串口")
    for index, port in enumerate(ports):
        logger.info("  [%s] %s", index, port)

    while True:
        choice = input(f"请选择串口编号 [0-{len(ports) - 1}]: ").strip()
        try:
            port_index = int(choice)
        except ValueError:
            logger.warning("串口选择输入无效: %s", choice)
            continue

        if 0 <= port_index < len(ports):
            logger.info("已选择主电源控制串口: %s", ports[port_index])
            return ports[port_index]

        logger.warning("串口编号超出范围: %s", choice)


def send_command(serial_port: SerialPort, command: bytes, label: str) -> None:
    written = serial_port.write(command)
    if written != len(command):
        raise RuntimeError(f"{label} 指令发送失败")
    logger.info("%s 指令已发送: %s", label, command.hex(" ").upper())
    time.sleep(SEND_DRAIN_SECONDS)


def sleep_with_interrupt(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.5))


def open_power_serial(args):
    serial_port = SerialPort()
    port_name = args.port or select_port(serial_port)

    if not serial_port.open(port_name, baud_rate=args.baud_rate):
        raise RuntimeError(f"串口连接失败: {port_name}")

    logger.info("主电源串口已连接: port=%s, baudrate=%s", port_name, args.baud_rate)
    return serial_port


def run_power_cycle_loop(serial_port: SerialPort, args) -> int:
    logger.info(
        "开始电源通断托管循环: "
        "preset=%s, mode=%s, count=%s, start_delay=%ss, 上电=%ss, 断电=%ss, "
        "stop_timeout=%ss",
        ACTIVE_PRESET,
        args.communication_mode,
        args.launch_count,
        args.start_delay,
        args.on_seconds,
        args.off_seconds,
        args.stop_timeout,
    )
    processes = []

    try:
        cycle_index = 1
        while True:
            logger.info("power cycle %s: 上电", cycle_index)
            power_on_at = time.monotonic()
            send_command(serial_port, POWER_ON_COMMAND, "上电")
            sleep_with_interrupt(args.start_delay)

            logger.info("power cycle %s: 启动 main.py 进程", cycle_index)
            processes = start_main_processes(
                args.communication_mode,
                args.launch_count,
                new_process_group=True,
                stop_timeout=args.stop_timeout,
            )

            remaining_on_seconds = args.on_seconds - (time.monotonic() - power_on_at)
            if remaining_on_seconds > 0:
                logger.debug("power cycle %s: 剩余上电等待 %.3fs", cycle_index, remaining_on_seconds)
                sleep_with_interrupt(remaining_on_seconds)
            else:
                logger.warning(
                    "power cycle %s: main.py 启动耗时已超过上电窗口 %.3fs",
                    cycle_index,
                    args.on_seconds,
                )

            logger.info("power cycle %s: 断电并停止 main.py 进程", cycle_index)
            send_command(serial_port, POWER_OFF_COMMAND, "断电")
            stopped = stop_main_processes(processes, args.stop_timeout)
            processes = []
            if not stopped:
                logger.error("power cycle %s: main.py 进程未能全部停止，退出电源循环", cycle_index)
                return 1

            sleep_with_interrupt(args.off_seconds)
            cycle_index += 1
    except KeyboardInterrupt:
        logger.info("收到退出信号，停止 main.py 进程并发送断电指令")
        stop_main_processes(processes, args.stop_timeout)
        try:
            send_command(serial_port, POWER_OFF_COMMAND, "断电")
        except Exception as exc:
            logger.exception("退出前断电失败: %s", exc)
        return 0
    except Exception as exc:
        logger.exception("电源通断托管循环运行失败: %s", exc)
        stop_main_processes(processes, args.stop_timeout)
        try:
            send_command(serial_port, POWER_OFF_COMMAND, "断电")
        except Exception as power_exc:
            logger.exception("异常后断电失败: %s", power_exc)
        return 1


def main() -> int:
    os.chdir(BASE_DIR)
    args = parse_args()
    setup_logging(app_name="main_power_cycle")
    logger.info(
        "main_power_cycle.py 启动参数: preset=%s, communication_mode=%s, "
        "launch_count=%s, port=%s, baud_rate=%s",
        ACTIVE_PRESET,
        args.communication_mode,
        args.launch_count,
        args.port,
        args.baud_rate,
    )
    if CONFIG_LOAD_ERROR is not None:
        logger.warning("配置加载失败，已回退到默认配置: %s", CONFIG_LOAD_ERROR)
    serial_port = None

    try:
        logger.info("准备主电源控制串口，先执行 RS485 模式配置脚本")
        setup_rs485_mode()
        serial_port = open_power_serial(args)
        return run_power_cycle_loop(serial_port, args)
    except Exception as exc:
        logger.exception("main_power_cycle.py 运行失败: %s", exc)
        return 1
    finally:
        if serial_port:
            serial_port.close()
            logger.info("主电源串口已关闭")


if __name__ == "__main__":
    raise SystemExit(main())
