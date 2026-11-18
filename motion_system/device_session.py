import logging
import time

from app.config import DEVICE_CONFIG, MOTION_CONFIG
from device.gpio_controller import GPIO_AVAILABLE, GPIO_PINS, GPIOController
from device.lhandpro_controller import LHandProController


class DeviceSession:
    """Owns device connection, GPIO access, and indicator outputs."""

    def __init__(
        self,
        communication_mode: str,
        device_index: int = None,
        enable_gpio: bool = True,
        rs485_port_name: str = None,
        *,
        ec_master=None,
        ecat_slave_id=None,
        gpio=None,
        owns_gpio: bool = True,
        cycle_complete_index: int = None,
    ):
        self.controller = LHandProController(
            communication_mode=communication_mode,
            ec_master=ec_master,
            ecat_slave_id=ecat_slave_id,
        )
        self.device_index = device_index
        self.rs485_port_name = (
            rs485_port_name
            if rs485_port_name is not None
            else DEVICE_CONFIG["rs485_port_name"]
        )
        self.gpio = gpio
        self._owns_gpio = owns_gpio
        self.enable_gpio = self._initialize_gpio(enable_gpio)
        pin_index = (
            cycle_complete_index
            if cycle_complete_index is not None
            else device_index
        )
        self.cycle_complete_pin = self._select_cycle_complete_pin(pin_index)

    def _initialize_gpio(self, enable_gpio: bool) -> bool:
        if self.gpio is not None:
            return True

        if enable_gpio and not GPIO_AVAILABLE:
            logging.warning("RPi.GPIO 未安装，GPIO 功能已自动禁用")
            return False

        if not enable_gpio:
            return False

        try:
            self.gpio = GPIOController()
            return True
        except RuntimeError as exc:
            logging.warning("GPIO 初始化失败，GPIO 功能已自动禁用: %s", exc)
            return False

    @staticmethod
    def _select_cycle_complete_pin(device_index: int):
        pins = GPIO_PINS.CYCLE_COMPLETE
        if device_index is None:
            return pins[0]
        if 0 <= int(device_index) < len(pins):
            return pins[int(device_index)]
        logging.warning(
            "循环完成 GPIO 索引超出范围: index=%s, pins=%s，复用最后一个引脚",
            device_index,
            pins,
        )
        return pins[-1]

    def connect(
        self,
        on_home_start=None,
        connect_retry_interval_seconds: float = 0.0,
        connect_deadline_monotonic=None,
    ) -> bool:
        home_time = MOTION_CONFIG["default_home_time"]
        logging.info(
            "准备连接设备: mode=%s, device_index=%s, rs485_port=%s, home_wait_time=%s",
            self.controller.communication_mode,
            self.device_index,
            self.rs485_port_name,
            home_time,
        )
        return self.controller.connect(
            enable_motors=True,
            home_motors=True,
            home_wait_time=home_time,
            device_index=self.device_index,
            auto_select=self.device_index is None,
            rs485_port_name=self.rs485_port_name,
            on_home_start=on_home_start,
            ecat_connect_retry_interval_seconds=connect_retry_interval_seconds,
            ecat_connect_deadline_monotonic=connect_deadline_monotonic,
            non_interactive=True,
        )

    def disconnect(self):
        self.controller.disconnect()

    def move_to_zero(self):
        logging.info("正在移动到零位置...")
        self.controller.move_to_zero(velocity=20000, max_current=1000, wait_time=2.0)
        logging.info("已回到零位置")

    def stop_and_settle(self):
        """停止电机并给总线一点时间落地，避免紧接着断开导致指令被截断。"""
        if not self.controller.is_connected:
            return
        self.controller.stop_motors()
        time.sleep(0.1)

    def set_ready_status(self):
        if self.enable_gpio and self.gpio:
            self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_high(GPIO_PINS.READY_STATUS)

    def set_running_status(self):
        if self.enable_gpio and self.gpio:
            self.gpio.output_high(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_low(GPIO_PINS.READY_STATUS)

    def set_connected_status(self):
        if self.enable_gpio and self.gpio:
            self.gpio.output_high(GPIO_PINS.STATUS_LED)
            self.set_ready_status()

    def set_disconnected_status(self):
        if self.enable_gpio and self.gpio:
            self.gpio.output_low(GPIO_PINS.STATUS_LED)
            self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_low(GPIO_PINS.READY_STATUS)

    def pulse_cycle_complete(self):
        if self.enable_gpio and self.gpio:
            logging.info("输出循环完成信号: GPIO %s", self.cycle_complete_pin)
            self.gpio.output_pulse(self.cycle_complete_pin, duration=0.5)

    def cleanup_gpio(self):
        if self._owns_gpio and self.enable_gpio and self.gpio:
            self.gpio.cleanup()
