import logging
import time

import keyboard

from config import AUTO_CONNECT, AUTO_CYCLE_RUNNING
from gpio_controller import GPIO_PINS

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

    def __init__(self, communication_mode: str, device_index: int = None, enable_gpio: bool = True):
        self.session = DeviceSession(
            communication_mode=communication_mode,
            device_index=device_index,
            enable_gpio=enable_gpio,
        )
        self.runtime_state = MotionRuntimeState()
        self.cycle_manager = CycleMotionManager(self.session, self.runtime_state)
        self.grasp_manager = GraspManager(self.session, self.runtime_state)
        self.glove_service = GloveListenerService(self.session)
        self.config_switcher = ConfigSwitcher(self)

    def setup_gpio(self):
        if not self.session.enable_gpio or not self.session.gpio or GPIO is None:
            return

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

        self.session.gpio.setup_output(self.session.cycle_complete_pin, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.STATUS_LED, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.READY_STATUS, initial=False)
        self.session.gpio.setup_output(GPIO_PINS.RUNNING_STATUS, initial=False)
        logging.info("GPIO 设置完成")

    def on_start_motion(self):
        logging.info("GPIO 触发: 开始循环运动")
        self.cycle_manager.start()

    def on_stop_motion(self):
        logging.info("GPIO 触发: 停止运动并回零")
        self.cycle_manager.stop()
        self.glove_service.stop()

    def on_connect_device(self):
        logging.info("GPIO 触发: 连接设备")
        self.runtime_state.stop()
        if self.session.connect():
            logging.info("设备自动连接成功")
            self.session.set_connected_status()
        else:
            logging.error("设备连接失败")
            self.session.set_disconnected_status()

    def on_disconnect_device(self):
        logging.info("GPIO 触发: 断开设备")
        self.runtime_state.stop()
        self.glove_service.stop()
        self.session.disconnect()
        self.session.set_disconnected_status()
        logging.info("设备已断开")

    def on_start_glove_listen(self):
        self.glove_service.start()

    def on_start_grasp(self):
        self.grasp_manager.on_start_grasp()

    def _log_gpio_summary(self):
        logging.info("\nGPIO 功能说明:")
        logging.info(f"  GPIO {GPIO_PINS.START_MOTION}: 开始循环运动")
        logging.info(f"  GPIO {GPIO_PINS.STOP_MOTION}: 停止运动并回零")
        logging.info(f"  GPIO {GPIO_PINS.CONNECT}: 连接设备")
        logging.info(f"  GPIO {GPIO_PINS.DISCONNECT}: 断开设备")
        logging.info(f"  GPIO {GPIO_PINS.START_GLOVE_LISTEN}: 开始手套监听")
        logging.info(f"  GPIO {GPIO_PINS.SWITCH_CONFIG}: 切换配置预设（短按切换下一个，长按1.5秒返回第一个，60秒无操作自动应用并重启）")
        logging.info(f"  GPIO {self.session.cycle_complete_pin}: 循环完成信号输出")
        logging.info(f"  GPIO {GPIO_PINS.STATUS_LED}: 状态 LED 输出")
        logging.info("\n按 Esc 键退出程序\n")

    def _setup_runtime(self):
        try:
            self.setup_gpio()
        except Exception as exc:
            logging.warning(f"GPIO 设置失败，GPIO 功能已禁用: {exc}")
            self.session.enable_gpio = False
        self._log_gpio_summary()

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
        logging.info("正在清理资源...")
        self.runtime_state.stop()
        self.glove_service.stop()
        if self.session.controller.is_connected:
            self.session.disconnect()
        self.session.cleanup_gpio()
        logging.info("资源清理完成")

    def run(self):
        logging.info("=" * 50)
        logging.info("LHandPro GPIO 控制程序")
        logging.info("=" * 50)

        self._setup_runtime()
        result = self._handle_auto_connect()
        if result != 0:
            return result

        try:
            while True:
                if keyboard.is_pressed("esc"):
                    logging.info("Esc 键按下，正在退出...")
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            logging.info("程序被用户中断")
        finally:
            self._cleanup()

        return 0
