import logging
import threading
import time

import keyboard

from config import AUTO_CONNECT, AUTO_CYCLE_RUNNING
from gpio_controller import GPIO_PINS
from main_runtime_control import (
    complete_control_command,
    emit_control_progress,
    read_control_command,
)
from log import logging_context, set_process_logging_context

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from config_switcher import ConfigSwitcher
from .cycle_motion_manager import CycleMotionManager
from .device_session import DeviceSession
from .glove_listener_service import GloveListenerService
from .grasp_manager import GraspManager
from .runtime_state import MotionRuntimeState


class MotionController:
    """Top-level coordinator that wires all runtime components together."""

    def __init__(
        self,
        communication_mode: str,
        device_index: int = None,
        enable_gpio: bool = True,
        rs485_port_name: str = None,
    ):
        self.session = DeviceSession(
            communication_mode=communication_mode,
            device_index=device_index,
            enable_gpio=enable_gpio,
            rs485_port_name=rs485_port_name,
        )
        self.runtime_state = MotionRuntimeState()
        self.cycle_manager = CycleMotionManager(self.session, self.runtime_state)
        self.grasp_manager = GraspManager(self.session, self.runtime_state)
        self.glove_service = GloveListenerService(self.session)
        self.config_switcher = ConfigSwitcher(self)
        self.shutdown_requested = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleaned_up = False

    def request_shutdown(self, reason: str = ""):
        if reason:
            logging.info("收到退出请求: %s", reason)
        else:
            logging.info("收到退出请求")
        self.shutdown_requested.set()
        self.runtime_state.stop()

    def start_managed_cycle(self, command=None):
        logging.info("托管命令: 连接设备、回零并开始循环运动")
        if not self.cycle_manager.wait_until_stopped():
            logging.error("托管命令: 上一轮循环运动线程停止超时")
            return False, "上一轮循环运动线程停止超时"
        self.glove_service.stop()

        if self.session.controller.is_connected:
            logging.info("设备已连接，先停止并断开后重新初始化")
            self.session.controller.stop_motors()
            time.sleep(0.1)
            self.session.disconnect()
            self.session.set_disconnected_status()

        def on_home_start():
            if command is None:
                return
            emit_control_progress(
                self.session.controller.communication_mode,
                self.session.device_index,
                command,
                "home_started",
                "回零指令已发送",
            )

        payload = (command or {}).get("payload") or {}
        if not self.session.connect(
            on_home_start=on_home_start,
            connect_retry_interval_seconds=payload.get(
                "connect_retry_interval_seconds",
                0.0,
            ),
            connect_deadline_monotonic=payload.get(
                "connect_deadline_monotonic",
            ),
        ):
            logging.error("托管命令: 设备连接/回零失败")
            self.session.set_disconnected_status()
            return False, "设备连接/回零失败"

        self.session.set_connected_status()
        if not self.on_start_motion():
            logging.error("托管命令: 循环运动线程启动失败，断开设备")
            self.session.disconnect()
            self.session.set_disconnected_status()
            return False, "循环运动线程启动失败"
        if command is not None:
            emit_control_progress(
                self.session.controller.communication_mode,
                self.session.device_index,
                command,
                "motion_started",
                "循环运动已开始",
            )
        return True, "循环运动已启动"

    def stop_managed_cycle(self):
        logging.info("托管命令: 停止循环运动并断开连接")
        if not self.cycle_manager.wait_until_stopped():
            logging.error("托管命令: 循环运动线程停止超时，拒绝在其仍运行时断开设备")
            return False, "循环运动线程停止超时，设备尚未断开"
        self.glove_service.stop()

        if self.session.controller.is_connected:
            self.session.controller.stop_motors()
            time.sleep(0.1)

        # disconnect() 可重复调用，也会清理“连接标志尚未置位”时残留的部分初始化资源。
        self.session.disconnect()

        self.session.set_disconnected_status()
        return True, "循环运动已停止，设备已断开"

    def _handle_control_command(self, command):
        action = command.get("action")
        if action == "start_cycle":
            return self.start_managed_cycle(command)
        if action == "stop_cycle":
            return self.stop_managed_cycle()
        if action == "shutdown":
            self.request_shutdown("control command")
            return True, "已请求 main.py 退出"

        return False, f"未知控制命令: {action}"

    def _poll_control_command(self):
        command = read_control_command(
            self.session.controller.communication_mode,
            self.session.device_index,
        )
        if not command:
            return

        command_log_context = command.get("log_context") or {}
        set_process_logging_context(
            cycle=command_log_context.get("cycle"),
            command_id=command.get("id"),
        )
        with logging_context(
            cycle=command_log_context.get("cycle"),
            command_id=command.get("id"),
        ):
            logging.info(
                "收到 main.py 控制命令: action=%s, id=%s",
                command.get("action"),
                command.get("id"),
            )
            try:
                ok, message = self._handle_control_command(command)
            except Exception as exc:
                logging.exception("执行 main.py 控制命令异常: %s", exc)
                ok = False
                message = str(exc)

            complete_control_command(
                self.session.controller.communication_mode,
                self.session.device_index,
                command,
                ok,
                message,
            )

    def _setup_gpio_inputs(self):
        self.session.gpio.setup_input(GPIO_PINS.START_MOTION, callback=self.on_start_motion, pull_up_down=GPIO.PUD_DOWN)
        self.session.gpio.setup_input(GPIO_PINS.STOP_MOTION, callback=self.on_stop_motion, pull_up_down=GPIO.PUD_DOWN)
        self.session.gpio.setup_input(GPIO_PINS.CONNECT, callback=self.on_connect_device, pull_up_down=GPIO.PUD_DOWN)
        self.session.gpio.setup_input(GPIO_PINS.DISCONNECT, callback=self.on_disconnect_device, pull_up_down=GPIO.PUD_DOWN)
        self.session.gpio.setup_input(
            GPIO_PINS.START_GLOVE_LISTEN,
            callback=self.on_start_glove_listen,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.session.gpio.setup_input(
            GPIO_PINS.SWITCH_CONFIG,
            callback=self.config_switcher.on_button_press,
            pull_up_down=GPIO.PUD_DOWN,
            edge=GPIO.BOTH,
        )

        edge_name = self.grasp_manager.get_gpio_edge_name()
        logging.info(f"[DEBUG] 抓握模式: {self.grasp_manager.mode}, GPIO 边沿设置: {edge_name}")
        self.session.gpio.setup_input(
            GPIO_PINS.START_GRASP,
            callback=self.on_start_grasp,
            pull_up_down=GPIO.PUD_DOWN,
            edge=self.grasp_manager.resolve_gpio_edge(GPIO),
        )

    def setup_gpio(self, *, enable_inputs: bool = True):
        if not self.session.enable_gpio or not self.session.gpio or GPIO is None:
            return

        if enable_inputs:
            self._setup_gpio_inputs()
        else:
            logging.info("主电源托管模式已禁用 GPIO 业务输入，避免断开期间重新触发通信")

        self.session.gpio.setup_output(self.session.cycle_complete_pin, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.STATUS_LED, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.READY_STATUS, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.RUNNING_STATUS, initial=False)
        logging.info("GPIO 设置完成")

    def on_start_motion(self):
        logging.info("GPIO 触发: 开始循环运动")
        return self.cycle_manager.start()

    def on_stop_motion(self):
        logging.info("GPIO 触发: 停止运动并回零")
        stopped = self.cycle_manager.stop()
        self.glove_service.stop()
        return stopped

    def on_connect_device(self):
        logging.info("GPIO 触发: 连接设备")
        if not self.cycle_manager.wait_until_stopped():
            logging.error("循环运动线程停止超时，取消本次设备连接")
            return
        if self.session.connect():
            logging.info("设备自动连接成功")
            self.session.set_connected_status()
        else:
            logging.error("设备连接失败")
            self.session.set_disconnected_status()

    def on_disconnect_device(self):
        logging.info("GPIO 触发: 断开设备")
        if not self.cycle_manager.wait_until_stopped():
            logging.error("循环运动线程停止超时，取消本次设备断开")
            return
        self.glove_service.stop()
        if self.session.controller.is_connected:
            self.session.controller.stop_motors()
            time.sleep(0.1)
        self.session.disconnect()
        self.session.set_disconnected_status()
        logging.info("设备已断开")

    def on_start_glove_listen(self):
        self.glove_service.start()

    def on_start_grasp(self):
        self.grasp_manager.on_start_grasp()

    def _log_gpio_summary(self, *, managed_control: bool = False):
        logging.info("\nGPIO 功能说明:")
        if managed_control:
            logging.info("  主电源托管模式：GPIO 业务输入已禁用")
        else:
            logging.info(f"  GPIO {GPIO_PINS.START_MOTION}: 开始循环运动")
            logging.info(f"  GPIO {GPIO_PINS.STOP_MOTION}: 停止运动并回零")
            logging.info(f"  GPIO {GPIO_PINS.CONNECT}: 连接设备")
            logging.info(f"  GPIO {GPIO_PINS.DISCONNECT}: 断开设备")
            logging.info(f"  GPIO {GPIO_PINS.START_GLOVE_LISTEN}: 开始手套监听")
            logging.info(f"  GPIO {GPIO_PINS.SWITCH_CONFIG}: 切换配置预设（短按切换下一个，长按1.5秒返回第一个，60秒无操作自动应用并重启）")
        logging.info(f"  GPIO {self.session.cycle_complete_pin}: 循环完成信号输出")
        logging.info(f"  GPIO {GPIO_PINS.STATUS_LED}: 状态 LED 输出")
        logging.info("\n按 Esc 键退出程序\n")

    def _setup_runtime(self, *, managed_control: bool = False):
        try:
            self.setup_gpio(enable_inputs=not managed_control)
        except Exception as exc:
            logging.warning(f"GPIO 设置失败，GPIO 功能已禁用: {exc}")
            self.session.enable_gpio = False
        self._log_gpio_summary(managed_control=managed_control)

    def _handle_auto_connect(self) -> int:
        if not AUTO_CONNECT:
            logging.info("自动连接已禁用，等待手动连接")
            if self.session.enable_gpio:
                self.session.set_disconnected_status()
                return 0
            logging.error("自动连接已禁用且 GPIO 未启用，程序退出")
            return -1

        logging.info("正在尝试自动连接设备...")
        if not self.session.connect():
            logging.error("设备自动连接失败")
            self.session.set_disconnected_status()
            return 0 if self.session.enable_gpio else -1

        logging.info("设备自动连接成功")
        self.session.set_connected_status()
        if AUTO_CYCLE_RUNNING:
            logging.info("自动开始执行循环运动")
            self.on_start_motion()
        return 0

    def _cleanup(self):
        with self._cleanup_lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True

        logging.info("正在清理资源...")
        cycle_stopped = self.cycle_manager.wait_until_stopped()
        if not cycle_stopped:
            logging.error("退出清理时循环运动线程仍未停止")
        self.glove_service.stop()
        if self.session.controller.is_connected:
            logging.info("正在停止运动...")
            self.session.controller.stop_motors()
            time.sleep(0.1)
        self.session.disconnect()
        self.session.set_disconnected_status()
        self.session.cleanup_gpio()
        logging.info("资源清理完成")

    def run(self, managed_control: bool = False):
        logging.info("=" * 50)
        logging.info("LHandPro GPIO 控制程序")
        logging.info("=" * 50)

        self._setup_runtime(managed_control=managed_control)
        if managed_control:
            logging.info("main.py 进入电源通断托管模式，等待外部控制命令")
            if self.session.enable_gpio:
                self.session.set_disconnected_status()
        else:
            result = self._handle_auto_connect()
            if result != 0:
                return result

        try:
            while True:
                if self.shutdown_requested.is_set():
                    logging.info("检测到退出请求，准备退出主循环")
                    break
                if managed_control:
                    self._poll_control_command()
                if keyboard.is_pressed("esc"):
                    logging.info("Esc 键按下，正在退出...")
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            logging.info("程序被用户中断")
        finally:
            self._cleanup()

        return 0
