#!/usr/bin/env python3
"""Cycle main power while managing main.py process lifecycle."""

import argparse
import logging
import os
import signal
import time

from active_config import ACTIVE_PRESET
from config import (
    CONFIG_LOAD_ERROR,
    DEFAULT_COMMUNICATION_MODE,
    DEFAULT_LAUNCH_COUNT,
    MAIN_POWER_CYCLE_BAUD_RATE,
    MAIN_POWER_CYCLE_CONNECT_RETRY_INTERVAL,
    MAIN_POWER_CYCLE_CONTROL_TIMEOUT,
    MAIN_POWER_CYCLE_DISCONNECT_LEAD_SECONDS,
    MAIN_POWER_CYCLE_FORCE_OFF_AT_DEADLINE,
    MAIN_POWER_CYCLE_OFF_SECONDS,
    MAIN_POWER_CYCLE_ON_SECONDS,
    MAIN_POWER_CYCLE_PORT,
    MAIN_POWER_CYCLE_RS485_PORTS,
    MAIN_POWER_CYCLE_START_DELAY,
    MAIN_POWER_CYCLE_STOP_TIMEOUT,
)
from gpio_controller import GPIO_AVAILABLE, GPIO_PINS, GPIOController
from log import set_process_logging_context, setup_logging
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
POWER_COMMAND_WRITE_TIMEOUT_SECONDS = 2.0
MAIN_START_COUNT_PULSE_SECONDS = 0.5
MANAGED_START_COMMAND_SPACING_SECONDS = 1.0
logger = logging.getLogger(__name__)


def _raise_keyboard_interrupt(_signum, _frame):
    """Route service termination through the same power-off path as Ctrl+C."""
    raise KeyboardInterrupt


def install_signal_handlers() -> None:
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)


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
        "--rs485-ports",
        nargs="+",
        default=MAIN_POWER_CYCLE_RS485_PORTS,
        help=(
            "Fixed RS485 device ports for managed main.py processes. "
            "When omitted, all non-power serial ports are used if their count matches launch-count."
        ),
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=MAIN_POWER_CYCLE_START_DELAY,
        help="Delay measured from the power-on command before requesting managed motion start.",
    )
    parser.add_argument(
        "--on-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_ON_SECONDS,
        help="Power-on duration measured from the power-on command to the power-off command.",
    )
    parser.add_argument(
        "--disconnect-lead-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_DISCONNECT_LEAD_SECONDS,
        help=(
            "Seconds reserved at the end of the powered-on window for stopping motion "
            "and disconnecting communication before the physical power-off command."
        ),
    )
    parser.add_argument(
        "--force-off-at-deadline",
        dest="force_off_at_deadline",
        action="store_true",
        default=MAIN_POWER_CYCLE_FORCE_OFF_AT_DEADLINE,
        help=(
            "Send the physical power-off command at the configured deadline even "
            "when communication disconnect has not completed."
        ),
    )
    parser.add_argument(
        "--no-force-off-at-deadline",
        dest="force_off_at_deadline",
        action="store_false",
        help="Wait for communication disconnect before sending physical power-off.",
    )
    parser.add_argument(
        "--connect-retry-interval",
        type=float,
        default=MAIN_POWER_CYCLE_CONNECT_RETRY_INTERVAL,
        help=(
            "Seconds between EtherCAT slave discovery attempts within the same "
            "powered-on window. Set to 0 to disable retries."
        ),
    )
    parser.add_argument(
        "--off-seconds",
        type=float,
        default=MAIN_POWER_CYCLE_OFF_SECONDS,
        help="Power-off duration measured from the power-off command to the next power-on command.",
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


def send_command(serial_port: SerialPort, command: bytes, label: str) -> float:
    written = serial_port.write_and_wait(
        command,
        timeout=POWER_COMMAND_WRITE_TIMEOUT_SECONDS,
    )
    if written != len(command):
        raise RuntimeError(f"{label} 指令发送失败")
    queued_at = time.monotonic()
    logger.info("%s 指令已发送: %s", label, command.hex(" ").upper())
    time.sleep(SEND_DRAIN_SECONDS)
    return queued_at


def sleep_until(deadline: float) -> None:
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.5))


def sleep_with_interrupt(seconds: float) -> None:
    sleep_until(time.monotonic() + seconds)


def log_power_cycle_summary(
    *,
    result: str,
    managed_start: str,
    home_started: bool,
    motion_started: bool,
    on_target: float,
    on_actual=None,
    off_target: float,
    off_wait_actual=None,
    next_action: str,
    level=logging.INFO,
) -> None:
    def seconds(value):
        return "-" if value is None else f"{value:.3f}"

    on_drift = None if on_actual is None else on_actual - on_target
    logger.log(
        level,
        "POWER_CYCLE_SUMMARY result=%s managed_start=%s home_started=%s "
        "motion_started=%s on_target_s=%.3f on_actual_s=%s on_drift_s=%s "
        "off_target_s=%.3f off_wait_actual_s=%s next_action=%s",
        result,
        managed_start,
        str(bool(home_started)).lower(),
        str(bool(motion_started)).lower(),
        on_target,
        seconds(on_actual),
        seconds(on_drift),
        off_target,
        seconds(off_wait_actual),
        next_action,
    )


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


def stop_existing_managed_main_processes(args):
    logger.info("清理同通信模式下已存在的 main.py 进程: mode=%s", args.communication_mode)
    stop_result = stop_existing_main_processes(
        communication_mode=args.communication_mode,
        timeout=args.stop_timeout,
    )
    if stop_result != 0:
        raise RuntimeError("同通信模式下已有 main.py 进程未能退出")


def resolve_rs485_device_ports(serial_port: SerialPort, args):
    if args.communication_mode != "RS485":
        return None

    power_port = serial_port.port_name
    if not power_port:
        raise RuntimeError("无法确定主电源控制串口，不能分配 RS485 设备端口")

    available_ports = serial_port.scan_available_ports(excluded_ports=[power_port])
    available_names = {
        serial_port.normalize_port_name(port) for port in available_ports
    }
    configured_ports = list(args.rs485_ports or [])

    if configured_ports:
        selected_ports = []
        selected_names = set()
        power_name = serial_port.normalize_port_name(power_port)
        for port in configured_ports:
            normalized = serial_port.normalize_port_name(port)
            if normalized == power_name:
                raise RuntimeError(f"RS485 设备端口不能与主电源串口相同: {port}")
            if normalized in selected_names:
                raise RuntimeError(f"RS485 设备端口重复: {port}")
            if normalized not in available_names:
                raise RuntimeError(f"配置的 RS485 设备端口当前不可用: {port}")
            selected_names.add(normalized)
            selected_ports.append(port)
    else:
        selected_ports = available_ports

    if len(selected_ports) != args.launch_count:
        raise RuntimeError(
            "RS485 设备串口数量必须与启动数量一致: "
            f"power_port={power_port}, device_ports={selected_ports}, "
            f"launch_count={args.launch_count}；请配置 main_power_cycle_rs485_ports"
        )

    for index, port in enumerate(selected_ports):
        logger.info("RS485 固定端口映射: device_index=%s -> %s", index, port)
    return selected_ports


def start_managed_main_processes(args, serial_port: SerialPort, *, existing_stopped=False):
    if not existing_stopped:
        stop_existing_managed_main_processes(args)

    rs485_port_names = resolve_rs485_device_ports(serial_port, args)
    logger.info("启动长驻 main.py 进程: mode=%s, count=%s", args.communication_mode, args.launch_count)
    processes = start_main_processes(
        args.communication_mode,
        args.launch_count,
        prepare=False,
        new_process_group=True,
        stop_timeout=args.stop_timeout,
        managed_control=True,
        rs485_port_names=rs485_port_names,
    )
    if not wait_for_main_processes(
        args.communication_mode,
        args.launch_count,
        timeout=args.control_timeout,
    ):
        stop_main_processes(processes, args.stop_timeout)
        raise RuntimeError("长驻 main.py 进程未全部就绪")
    return processes


def request_managed_motion_start(
    args,
    cycle_label: str,
    on_progress=None,
    *,
    absolute_deadline=None,
) -> bool:
    connect_retry_interval = max(
        0.0,
        getattr(args, "connect_retry_interval", 0.0),
    )
    retry_enabled = bool(
        args.communication_mode == "ECAT"
        and connect_retry_interval > 0
        and absolute_deadline is not None
    )
    payload = None
    timeout = args.control_timeout
    if retry_enabled:
        payload = {
            "connect_retry_interval_seconds": connect_retry_interval,
            # time.monotonic() uses the same system-wide clock in both processes.
            "connect_deadline_monotonic": absolute_deadline,
        }
        timeout = max(
            timeout,
            max(0.0, absolute_deadline - time.monotonic()) + 0.5,
        )

    logger.info(
        "%s: 请求长驻 main.py 按设备顺序执行连接、回零并开始循环运动；"
        "不同 main.py 间隔 %.3fs，ECAT扫描重试间隔=%.3fs；"
        "未接设备失败将忽略；本轮全部失败时下一轮继续重试",
        cycle_label,
        MANAGED_START_COMMAND_SPACING_SECONDS,
        connect_retry_interval if retry_enabled else 0.0,
    )
    return request_existing_main_action(
        "start_cycle",
        args.communication_mode,
        timeout=timeout,
        payload=payload,
        progress_stage=("home_started", "motion_started"),
        on_progress=on_progress,
        min_successes=1,
        command_spacing_seconds=MANAGED_START_COMMAND_SPACING_SECONDS,
        absolute_deadline=absolute_deadline,
    )


def request_managed_motion_stop(args, cycle_label: str, *, absolute_deadline=None) -> bool:
    logger.info("%s: 请求长驻 main.py 停止软件运动状态并清理通信资源", cycle_label)
    return request_existing_main_action(
        "stop_cycle",
        args.communication_mode,
        timeout=args.control_timeout,
        absolute_deadline=absolute_deadline,
    )


def stop_motion_then_power_off(
    serial_port: SerialPort,
    processes,
    args,
    cycle_label: str,
    *,
    terminate_processes: bool = False,
    planned_power_off_at=None,
):
    cleanup_started_at = time.monotonic()
    logger.info(
        "%s: 开始物理断电前清理，先停止运动并断开通信连接",
        cycle_label,
    )

    force_off_at_deadline = bool(
        getattr(args, "force_off_at_deadline", False)
        and planned_power_off_at is not None
    )

    try:
        command_stopped = request_managed_motion_stop(
            args,
            cycle_label,
            absolute_deadline=(
                planned_power_off_at if force_off_at_deadline else None
            ),
        )
    except Exception as exc:
        logger.exception("%s: 托管停止命令异常: %s", cycle_label, exc)
        command_stopped = False

    force_off_with_incomplete_cleanup = force_off_at_deadline and not command_stopped
    cleanup_succeeded = command_stopped
    communication_released = command_stopped
    processes_stopped = None
    if not command_stopped and not force_off_with_incomplete_cleanup:
        logger.error(
            "%s: 托管停止/断开命令失败，先兜底停止 main.py 进程以释放通信资源",
            cycle_label,
        )
        try:
            processes_stopped = stop_main_processes(processes, args.stop_timeout)
        except Exception as exc:
            processes_stopped = False
            logger.exception("%s: 兜底停止 main.py 进程异常: %s", cycle_label, exc)
        if not processes_stopped:
            logger.error(
                "%s: main.py 进程未能全部停止，将执行紧急物理断电并退出循环",
                cycle_label,
            )
        else:
            communication_released = True
            logger.warning(
                "%s: 已兜底终止 main.py 进程，进程退出已释放通信资源",
                cycle_label,
            )

    # A hard physical power-off deadline takes precedence over waiting for the
    # long-running process to exit.  The caller's finally block will still stop
    # the process after this function has sent the power-off command.
    if terminate_processes and not force_off_at_deadline:
        logger.info("%s: 退出流程需要终止长驻 main.py 进程", cycle_label)
        if processes_stopped is not True:
            try:
                processes_stopped = stop_main_processes(processes, args.stop_timeout)
            except Exception as exc:
                processes_stopped = False
                logger.exception("%s: 终止长驻 main.py 进程异常: %s", cycle_label, exc)
        if not processes_stopped:
            cleanup_succeeded = False
            if communication_released:
                logger.error(
                    "%s: main.py 进程未能全部停止，但通信已断开；物理断电后退出",
                    cycle_label,
                )
            else:
                logger.error(
                    "%s: main.py 进程未能全部停止，将执行紧急物理断电",
                    cycle_label,
                )
        else:
            communication_released = True

    cleanup_finished_at = time.monotonic()
    cleanup_duration = cleanup_finished_at - cleanup_started_at
    if force_off_with_incomplete_cleanup:
        remaining = planned_power_off_at - cleanup_finished_at
        if remaining > 0:
            logger.warning(
                "%s: 通信断开未完成，仍保持上电并等待 %.3fs 到达硬断电时刻",
                cycle_label,
                remaining,
            )
            sleep_until(planned_power_off_at)
        logger.error(
            "%s: 通信断开未在截止时间内完成，按配置立即发送物理断电指令",
            cycle_label,
        )
    elif communication_released:
        if cleanup_succeeded:
            logger.info(
                "%s: 运动停止和通信断开已确认完成，cleanup_duration=%.3fs",
                cycle_label,
                cleanup_duration,
            )
        else:
            logger.warning(
                "%s: 托管清理未完整成功，但已确认通信资源释放，cleanup_duration=%.3fs",
                cycle_label,
                cleanup_duration,
            )
        if planned_power_off_at is not None:
            remaining = planned_power_off_at - cleanup_finished_at
            if remaining > 0:
                logger.debug(
                    "%s: 通信已断开，等待 %.3fs 后按目标时刻物理断电",
                    cycle_label,
                    remaining,
                )
                sleep_until(planned_power_off_at)
            else:
                logger.warning(
                    "%s: 通信清理超过目标物理断电时刻 %.3fs；按要求在断开完成后立即断电",
                    cycle_label,
                    -remaining,
                )
        logger.info("%s: 通信连接已断开，发送物理断电指令", cycle_label)
    else:
        logger.error(
            "%s: 停止命令和进程退出兜底均失败，无法确认通信已断开；"
            "出于电气安全执行紧急物理断电",
            cycle_label,
        )

    try:
        power_off_at = send_command(serial_port, POWER_OFF_COMMAND, "断电")
    except Exception as exc:
        logger.exception("%s: 断电指令发送失败: %s", cycle_label, exc)
        return False, None

    return cleanup_succeeded, power_off_at


def run_power_cycle_loop(
    serial_port: SerialPort,
    args,
    start_counter: MainStartCounter,
    *,
    existing_stopped: bool = False,
) -> int:
    logger.info(
        "开始电源通断托管循环: "
        "preset=%s, mode=%s, count=%s, start_delay=%ss, 物理上电=%ss, "
        "断电前预留清理=%ss, 硬断电截止=%s, ECAT扫描重试=%ss, 物理断电=%ss, "
        "control_timeout=%ss, stop_timeout=%ss",
        ACTIVE_PRESET,
        args.communication_mode,
        args.launch_count,
        args.start_delay,
        args.on_seconds,
        args.disconnect_lead_seconds,
        args.force_off_at_deadline,
        args.connect_retry_interval,
        args.off_seconds,
        args.control_timeout,
        args.stop_timeout,
    )
    disconnect_lead_seconds = max(0.0, min(args.disconnect_lead_seconds, args.on_seconds))
    if disconnect_lead_seconds != args.disconnect_lead_seconds:
        logger.warning(
            "断电前预留清理时间已限制到物理上电窗口内: configured=%.3fs, effective=%.3fs",
            args.disconnect_lead_seconds,
            disconnect_lead_seconds,
        )
    processes = start_managed_main_processes(
        args,
        serial_port,
        existing_stopped=existing_stopped,
    )

    try:
        cycle_index = 1
        previous_power_off_at = None
        while True:
            set_process_logging_context(cycle=cycle_index, command_id=None)
            logger.info("power cycle %s: 上电", cycle_index)
            power_on_at = send_command(serial_port, POWER_ON_COMMAND, "上电")
            if previous_power_off_at is not None:
                actual_off_seconds = power_on_at - previous_power_off_at
                logger.info(
                    "power cycle %s: 断电指令间隔 target=%.3fs, actual=%.3fs, drift=%+.3fs",
                    cycle_index,
                    args.off_seconds,
                    actual_off_seconds,
                    actual_off_seconds - args.off_seconds,
                )
            power_off_deadline = power_on_at + args.on_seconds
            disconnect_start_deadline = power_off_deadline - disconnect_lead_seconds
            start_deadline = min(
                power_on_at + args.start_delay,
                disconnect_start_deadline,
            )
            sleep_until(start_deadline)

            if time.monotonic() >= disconnect_start_deadline:
                logger.error(
                    "power cycle %s: start_delay 已耗尽连接/运动窗口，先清理通信再断电并退出",
                    cycle_index,
                )
                stopped, power_off_at = stop_motion_then_power_off(
                    serial_port,
                    processes,
                    args,
                    f"power cycle {cycle_index} 启动前超时",
                    terminate_processes=True,
                    planned_power_off_at=power_off_deadline,
                )
                log_power_cycle_summary(
                    result="start_delay_timeout",
                    managed_start="not_attempted",
                    home_started=False,
                    motion_started=False,
                    on_target=args.on_seconds,
                    on_actual=(
                        None if power_off_at is None else power_off_at - power_on_at
                    ),
                    off_target=args.off_seconds,
                    next_action="exit",
                    level=logging.ERROR,
                )
                return 1

            motion_started_at = None
            home_started_counted = False

            def handle_start_progress(_data, progress):
                nonlocal home_started_counted, motion_started_at
                stage = progress.get("stage")
                if stage == "home_started" and not home_started_counted:
                    home_started_counted = True
                    start_counter.mark_started(cycle_index)
                elif stage == "motion_started" and motion_started_at is None:
                    motion_started_at = time.monotonic()
                    logger.info(
                        "power cycle %s: 首个设备已开始运动，物理上电剩余 %.3fs",
                        cycle_index,
                        max(0.0, power_off_deadline - motion_started_at),
                    )

            start_succeeded = request_managed_motion_start(
                args,
                f"power cycle {cycle_index}",
                on_progress=handle_start_progress,
                absolute_deadline=disconnect_start_deadline,
            )
            if not start_succeeded:
                logger.warning(
                    "power cycle %s: 本轮设备连接/回零/启动失败；"
                    "仍按计划开始断电前清理，下一轮上电后重新连接",
                    cycle_index,
                )
            elif motion_started_at is None:
                logger.warning(
                    "power cycle %s: 未收到 motion_started 进度；仍按计划开始断电前清理",
                    cycle_index,
                )

            remaining_motion_seconds = disconnect_start_deadline - time.monotonic()
            if remaining_motion_seconds > 0:
                logger.debug(
                    "power cycle %s: 断电前通信清理开始前剩余运动时间 %.3fs",
                    cycle_index,
                    remaining_motion_seconds,
                )
                sleep_until(disconnect_start_deadline)
            else:
                logger.warning(
                    "power cycle %s: start_cycle 完成时断电前预留清理窗口已经开始",
                    cycle_index,
                )

            stopped, power_off_at = stop_motion_then_power_off(
                serial_port,
                processes,
                args,
                f"power cycle {cycle_index}",
                planned_power_off_at=power_off_deadline,
            )
            actual_on_seconds = None
            if power_off_at is not None:
                actual_on_seconds = power_off_at - power_on_at
                logger.info(
                    "power cycle %s: 上电指令间隔 target=%.3fs, actual=%.3fs, drift=%+.3fs",
                    cycle_index,
                    args.on_seconds,
                    actual_on_seconds,
                    actual_on_seconds - args.on_seconds,
                )
            else:
                logger.error(
                    "power cycle %s: 无法确认物理断电指令已发送，退出电源循环",
                    cycle_index,
                )
                log_power_cycle_summary(
                    result="power_off_failed",
                    managed_start="success" if start_succeeded else "failed",
                    home_started=home_started_counted,
                    motion_started=motion_started_at is not None,
                    on_target=args.on_seconds,
                    on_actual=None,
                    off_target=args.off_seconds,
                    next_action="exit",
                    level=logging.ERROR,
                )
                return 1
            forced_power_off = bool(
                not stopped and getattr(args, "force_off_at_deadline", False)
            )
            if not stopped and not forced_power_off:
                logger.error(
                    "power cycle %s: 断电前清理未完整成功；物理断电已执行，退出电源循环",
                    cycle_index,
                )
                log_power_cycle_summary(
                    result="cleanup_failed",
                    managed_start="success" if start_succeeded else "failed",
                    home_started=home_started_counted,
                    motion_started=motion_started_at is not None,
                    on_target=args.on_seconds,
                    on_actual=actual_on_seconds,
                    off_target=args.off_seconds,
                    next_action="exit",
                    level=logging.ERROR,
                )
                return 1
            if forced_power_off:
                logger.warning(
                    "power cycle %s: 通信断开未完成，但已按硬截止时间物理断电；"
                    "保持断电窗口并在下一轮重新尝试连接",
                    cycle_index,
                )

            previous_power_off_at = power_off_at
            sleep_until(power_off_at + args.off_seconds)
            off_wait_actual = time.monotonic() - power_off_at
            log_power_cycle_summary(
                result="forced_power_off" if forced_power_off else "completed",
                managed_start="success" if start_succeeded else "failed",
                home_started=home_started_counted,
                motion_started=motion_started_at is not None,
                on_target=args.on_seconds,
                on_actual=actual_on_seconds,
                off_target=args.off_seconds,
                off_wait_actual=off_wait_actual,
                next_action=(
                    "retry_connect"
                    if forced_power_off or not start_succeeded
                    else "repeat"
                ),
                level=(
                    logging.WARNING
                    if forced_power_off or not start_succeeded
                    else logging.INFO
                ),
            )
            cycle_index += 1
    except KeyboardInterrupt:
        logger.info("收到退出信号，先停止运动并断开通信，再终止进程和物理断电")
        stopped, _power_off_at = stop_motion_then_power_off(
            serial_port,
            processes,
            args,
            "退出流程",
            terminate_processes=True,
        )
        return 0 if stopped else 1
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
    except BaseException as exc:
        logger.error("电源通断托管循环收到非标准退出: %s", exc)
        stop_motion_then_power_off(
            serial_port,
            processes,
            args,
            "非标准退出流程",
            terminate_processes=True,
        )
        raise
    finally:
        try:
            if not stop_main_processes(processes, args.stop_timeout):
                logger.error("电源循环退出时仍有 main.py 进程未停止")
        except Exception as exc:
            logger.exception("电源循环退出时停止 main.py 进程异常: %s", exc)


def main() -> int:
    os.chdir(BASE_DIR)
    args = parse_args()
    setup_logging(
        app_name="main_power_cycle",
        communication_mode=args.communication_mode,
        device_index="all" if args.launch_count > 1 else "auto",
    )
    install_signal_handlers()
    logger.info(
        "main_power_cycle.py 启动参数: preset=%s, communication_mode=%s, "
        "launch_count=%s, port=%s, baud_rate=%s, rs485_ports=%s",
        ACTIVE_PRESET,
        args.communication_mode,
        args.launch_count,
        args.port,
        args.baud_rate,
        args.rs485_ports,
    )
    if CONFIG_LOAD_ERROR is not None:
        logger.warning("配置加载失败，已回退到默认配置: %s", CONFIG_LOAD_ERROR)
    serial_port = None
    start_counter = MainStartCounter()

    try:
        # 必须先释放旧 RS485 设备端口，再统一配置适配器和打开主电源串口。
        stop_existing_managed_main_processes(args)
        start_counter.setup()
        logger.info("准备主电源控制串口，先执行 RS485 模式配置脚本")
        setup_result = setup_rs485_mode()
        if args.communication_mode == "RS485" and setup_result != 0:
            raise RuntimeError(
                f"RS485 模式配置失败，不能启动设备上下电测试: returncode={setup_result}"
            )
        serial_port = open_power_serial(args)
        return run_power_cycle_loop(
            serial_port,
            args,
            start_counter,
            existing_stopped=True,
        )
    except Exception as exc:
        logger.exception("main_power_cycle.py 运行失败: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("main_power_cycle.py 启动/退出阶段收到终止信号")
        if serial_port:
            try:
                send_command(serial_port, POWER_OFF_COMMAND, "断电")
            except Exception as exc:
                logger.exception("终止信号处理期间发送断电指令失败: %s", exc)
        return 0
    finally:
        try:
            if serial_port:
                serial_port.close()
                logger.info("主电源串口已关闭")
        finally:
            start_counter.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
