import logging

from config import DEFAULT_HOME_TIME, RS485_PORT_NAME
from gpio_controller import GPIO_AVAILABLE, GPIO_PINS, GPIOController
from lhandpro_controller import LHandProController


class DeviceSession:
    """Owns device connection, GPIO access, and indicator outputs."""

    def __init__(self, communication_mode: str, device_index: int = None, enable_gpio: bool = True):
        self.controller = LHandProController(communication_mode=communication_mode)
        self.device_index = device_index
        self.gpio = None
        self.enable_gpio = self._initialize_gpio(enable_gpio)
        self.cycle_complete_pin = self._select_cycle_complete_pin(device_index)

    def _initialize_gpio(self, enable_gpio: bool) -> bool:
        if enable_gpio and not GPIO_AVAILABLE:
            logging.warning("RPi.GPIO 未安装，GPIO 功能已自动禁用")
            return False

        if not enable_gpio:
            return False

        try:
            self.gpio = GPIOController()
            return True
        except RuntimeError as exc:
            logging.warning(f"GPIO 初始化失败，GPIO 功能已自动禁用: {exc}")
            return False

    @staticmethod
    def _select_cycle_complete_pin(device_index: int):
        if device_index in [0, None]:
            return GPIO_PINS.CYCLE_COMPLETE[0]
        return GPIO_PINS.CYCLE_COMPLETE[device_index]

    def connect(self) -> bool:
        return self.controller.connect(
            enable_motors=True,
            home_motors=True,
            home_wait_time=DEFAULT_HOME_TIME,
            device_index=self.device_index,
            auto_select=self.device_index is None,
            rs485_port_name=RS485_PORT_NAME,
        )

    def disconnect(self):
        self.controller.disconnect()

    def move_to_zero(self):
        logging.info("正在移动到零位置...")
        self.controller.move_to_zero(velocity=20000, max_current=1000, wait_time=2.0)
        logging.info("已回到零位置")

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
            logging.info(f"输出循环完成信号: GPIO {self.cycle_complete_pin}")
            self.gpio.output_pulse(self.cycle_complete_pin, duration=0.5)

    def cleanup_gpio(self):
        if self.enable_gpio and self.gpio:
            self.gpio.cleanup()
