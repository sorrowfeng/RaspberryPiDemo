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
    MAIN_POWER_CYCLE_CONTROL_TIMEOUT,
    MAIN_POWER_CYCLE_OFF_SECONDS,
    MAIN_POWER_CYCLE_ON_SECONDS,
    MAIN_POWER_CYCLE_PORT,
    MAIN_POWER_CYCLE_START_DELAY,
    MAIN_POWER_CYCLE_STOP_TIMEOUT,
)
from gpio_controller import GPIO_AVAILABLE, GPIO_PINS, GPIOController
from log import setup_logging
from main_lifecycle import (
    setup_rs485_mode,
    start_main_processes,
    stop_main_processes,
)
from main_runtime_control import (
    request_existing_main_action,
    stop_existing_main_processes,
    wait_for_main_processes,
)
from serial_port import SerialPort


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POWER_ON_COMMAND = bytes.fromhex("01 06 00 00 00 00 89 CA")
POWER_OFF_COMMAND = bytes.fromhex("01 06 00 00 00 01 48 0A")
SEND_DRAIN_SECONDS = 0.1
MAIN_START_COUNT_PULSE_SECONDS = 0.5
MANAGED_START_COMMAND_SPACING_SECONDS = 1.0
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
        help="Number of long-running managed main.py processes to launch.",
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
        help="Delay after power-on before requesting managed main.py motion start.",
    )
    parser.add_argument(
        "--on-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_ON_SECONDS,
        help="Motion window seconds after the first managed main.py starts motion.",
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
    parser.add_argument(
        "--control-timeout",
        type=float,
        default=MAIN_POWER_CYCLE_CONTROL_TIMEOUT,
        help=(
            "Seconds to wait for long-running main.py control commands "
            "such as connect/home/start and stop/disconnect."
        ),
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


class MainStartCounter:
    """Outputs one GPIO pulse when a power-cycle round starts homing."""

    def __init__(
        self,
        pin: int = GPIO_PINS.POWER_CYCLE_MAIN_START_COUNT,
        pulse_seconds: float = MAIN_START_COUNT_PULSE_SECONDS,
    ):
        self.pin = pin
        self.pulse_seconds = pulse_seconds
        self.total_count = 0
        self.gpio = None

    def setup(self) -> None:
        if not GPIO_AVAILABLE:
            logger.warning("RPi.GPIO 未安装，GPIO%s 回零启动计数脉冲已禁用", self.pin)
            return

        try:
            self.gpio = GPIOController()
            self.gpio.setup_output(self.pin, initial=False)
            logger.info(
                "主电源通断回零启动计数 GPIO 已启用: GPIO%s, pulse=%ss",
                self.pin,
                self.pulse_seconds,
            )
        except Exception as exc:
            self.gpio = None
            logger.warning("GPIO%s 回零启动计数初始化失败，计数脉冲已禁用: %s", self.pin, exc)

    def mark_started(self, cycle_index: int) -> None:
        self.total_count += 1
        if self.gpio is None:
            logger.info(
                "power cycle %s: 回零启动计数 +1, total=%s, GPIO%s 脉冲未启用",
                cycle_index,
                self.total_count,
                self.pin,
            )
            return

        logger.info(
            "power cycle %s: 回零启动计数 +1, total=%s, 输出 GPIO%s 脉冲",
            cycle_index,
            self.total_count,
            self.pin,
        )
        self.gpio.output_pulse(self.pin, duration=self.pulse_seconds)

    def cleanup(self) -> None:
        if self.gpio is None:
            return

        try:
            self.gpio.cleanup()
            logger.info("GPIO%s 回零启动计数资源已清理", self.pin)
        except Exception as exc:
            logger.exception("GPIO%s 回零启动计数资源清理失败: %s", self.pin, exc)


def open_power_serial(args):
    serial_port = SerialPort()
    port_name = args.port or select_port(serial_port)

    if not serial_port.open(port_name, baud_rate=args.baud_rate):
        raise RuntimeError(f"串口连接失败: {port_name}")

    logger.info("主电源串口已连接: port=%s, baudrate=%s", port_name, args.baud_rate)
    return serial_port


def start_managed_main_processes(args):
    logger.info("清理同通信模式下已存在的 main.py 进程: mode=%s", args.communication_mode)
    stop_result = stop_existing_main_processes(
        communication_mode=args.communication_mode,
        timeout=args.stop_timeout,
    )
    if stop_result != 0:
        raise RuntimeError("同通信模式下已有 main.py 进程未能退出")

    logger.info("启动长驻 main.py 进程: mode=%s, count=%s", args.communication_mode, args.launch_count)
    processes = start_main_processes(
        args.communication_mode,
        args.launch_count,
        new_process_group=True,
        stop_timeout=args.stop_timeout,
        managed_control=True,
    )
    if not wait_for_main_processes(
        args.communication_mode,
        args.launch_count,
        timeout=args.control_timeout,
    ):
        stop_main_processes(processes, args.stop_timeout)
        raise RuntimeError("长驻 main.py 进程未全部就绪")
    return processes


def request_managed_motion_start(args, cycle_label: str, on_progress=None) -> bool:
    logger.info(
        "%s: 请求长驻 main.py 按设备顺序执行连接、回零并开始循环运动；"
        "不同 main.py 间隔 %.3fs，未接设备失败将忽略，至少需要 1 个设备开始运动",
        cycle_label,
        MANAGED_START_COMMAND_SPACING_SECONDS,
    )
    return request_existing_main_action(
        "start_cycle",
        args.communication_mode,
        timeout=args.control_timeout,
        progress_stage=("home_started", "motion_started"),
        on_progress=on_progress,
        min_successes=1,
        command_spacing_seconds=MANAGED_START_COMMAND_SPACING_SECONDS,
    )


def request_managed_motion_stop(args, cycle_label: str) -> bool:
    logger.info("%s: 请求长驻 main.py 停止运动并断开连接", cycle_label)
    return request_existing_main_action(
        "stop_cycle",
        args.communication_mode,
        timeout=args.control_timeout,
    )


def stop_motion_then_power_off(
    serial_port: SerialPort,
    processes,
    args,
    cycle_label: str,
    *,
    terminate_processes: bool = False,
) -> bool:
    command_stopped = request_managed_motion_stop(args, cycle_label)
    if not command_stopped:
        logger.error("%s: 托管停止命令失败，兜底停止 main.py 进程", cycle_label)
        processes_stopped = stop_main_processes(processes, args.stop_timeout)
        if not processes_stopped:
            logger.error("%s: main.py 进程未能全部停止，跳过断电指令", cycle_label)
            return False

        logger.info("%s: 已兜底终止 main.py 进程，发送断电指令后退出循环", cycle_label)
        send_command(serial_port, POWER_OFF_COMMAND, "断电")
        return False

    if terminate_processes:
        logger.info("%s: 退出流程需要终止长驻 main.py 进程", cycle_label)
        if not stop_main_processes(processes, args.stop_timeout):
            logger.error("%s: main.py 进程未能全部停止，跳过断电指令", cycle_label)
            return False

    logger.info("%s: 运动/进程停止流程已完成，发送断电指令", cycle_label)
    send_command(serial_port, POWER_OFF_COMMAND, "断电")
    return True


def run_power_cycle_loop(serial_port: SerialPort, args, start_counter: MainStartCounter) -> int:
    logger.info(
        "开始电源通断托管循环: "
        "preset=%s, mode=%s, count=%s, start_delay=%ss, 运动窗口=%ss, 断电等待=%ss, "
        "control_timeout=%ss, stop_timeout=%ss",
        ACTIVE_PRESET,
        args.communication_mode,
        args.launch_count,
        args.start_delay,
        args.on_seconds,
        args.off_seconds,
        args.control_timeout,
        args.stop_timeout,
    )
    processes = start_managed_main_processes(args)

    try:
        cycle_index = 1
        while True:
            logger.info("power cycle %s: 上电", cycle_index)
            send_command(serial_port, POWER_ON_COMMAND, "上电")
            sleep_with_interrupt(args.start_delay)

            motion_window_started_at = None
            home_started_counted = False

            def handle_start_progress(_data, progress):
                nonlocal home_started_counted, motion_window_started_at
                stage = progress.get("stage")
                if stage == "home_started" and not home_started_counted:
                    home_started_counted = True
                    start_counter.mark_started(cycle_index)
                elif stage == "motion_started" and motion_window_started_at is None:
                    motion_window_started_at = time.monotonic()
                    logger.info(
                        "power cycle %s: 首个设备已开始运动，开始 %.3fs 运动窗口计时",
                        cycle_index,
                        args.on_seconds,
                    )

            if not request_managed_motion_start(
                args,
                f"power cycle {cycle_index}",
                on_progress=handle_start_progress,
            ):
                logger.error("power cycle %s: 没有设备成功开始运动，准备停止进程并断电后退出", cycle_index)
                stop_motion_then_power_off(
                    serial_port,
                    processes,
                    args,
                    f"power cycle {cycle_index} 启动失败",
                    terminate_processes=True,
                )
                return 1

            if motion_window_started_at is None:
                motion_window_started_at = time.monotonic()
                logger.warning(
                    "power cycle %s: 未收到 motion_started 进度，使用 start_cycle 完成时间作为运动窗口起点",
                    cycle_index,
                )

            remaining_on_seconds = args.on_seconds - (time.monotonic() - motion_window_started_at)
            if remaining_on_seconds > 0:
                logger.debug("power cycle %s: 剩余上电等待 %.3fs", cycle_index, remaining_on_seconds)
                sleep_with_interrupt(remaining_on_seconds)
            else:
                logger.warning(
                    "power cycle %s: start_cycle 完成时运动窗口 %.3fs 已结束",
                    cycle_index,
                    args.on_seconds,
                )

            logger.info("power cycle %s: 停止运动并断开连接，完成后断电", cycle_index)
            stopped = stop_motion_then_power_off(
                serial_port,
                processes,
                args,
                f"power cycle {cycle_index}",
            )
            if not stopped:
                logger.error("power cycle %s: 停止流程未完成，退出电源循环", cycle_index)
                return 1

            sleep_with_interrupt(args.off_seconds)
            cycle_index += 1
    except KeyboardInterrupt:
        logger.info("收到退出信号，先停止运动和长驻 main.py 进程，完成后发送断电指令")
        return 0 if stop_motion_then_power_off(
            serial_port,
            processes,
            args,
            "退出流程",
            terminate_processes=True,
        ) else 1
    except Exception as exc:
        logger.exception("电源通断托管循环运行失败: %s", exc)
        stop_motion_then_power_off(
            serial_port,
            processes,
            args,
            "异常流程",
            terminate_processes=True,
        )
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
    start_counter = MainStartCounter()
    start_counter.setup()

    try:
        logger.info("准备主电源控制串口，先执行 RS485 模式配置脚本")
        setup_rs485_mode()
        serial_port = open_power_serial(args)
        return run_power_cycle_loop(serial_port, args, start_counter)
    except Exception as exc:
        logger.exception("main_power_cycle.py 运行失败: %s", exc)
        return 1
    finally:
        if serial_port:
            serial_port.close()
            logger.info("主电源串口已关闭")
        start_counter.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
