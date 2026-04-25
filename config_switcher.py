"""Configuration preset switcher triggered by GPIO button."""

import logging
import os
import subprocess
import threading
import time

import active_config
from gpio_controller import GPIO_PINS

TIMEOUT_SECONDS = 60
LONG_PRESS_SECONDS = 1.5

CONFIG_PRESETS = [
    {
        "module": "configs.config_DH116S_CANFD_aging",
        "feedback_positions": [3000, 3000, 0, 10000, 10000, 10000],
    },
    {
        "module": "configs.config_DH116S_CANFD_grasp_aging",
        "feedback_positions": [3000, 3000, 0, 0, 10000, 10000],
    },
    {
        "module": "configs.config_DH116S_CANFD_gesture_aging",
        "feedback_positions": [3000, 3000, 0, 0, 0, 10000],
    },
    {
        "module": "configs.config_DH116_CANFD_aging",
        "feedback_positions": [3000, 3000, 0, 0, 0, 0],
    },
    {
        "module": "configs.config_DH116_CANFD_grasp_aging",
        "feedback_positions": [0, 0, 0, 0, 0, 0],
    },
    {
        "module": "configs.config_DH116_ECAT_aging",
        "feedback_positions": [0, 0, 10000, 10000, 10000, 0],
    },
    {
        "module": "configs.config_DH116_ECAT_grasp_aging",
        "feedback_positions": [0, 0, 0, 10000, 10000, 0],
    },
]

ACTIVE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "active_config.py")


def _find_current_index():
    current = getattr(active_config, "ACTIVE_PRESET", "")
    for i, preset in enumerate(CONFIG_PRESETS):
        if preset["module"] == current:
            return i
    return 0


def write_active_config(preset_module):
    file_content = (
        '"""Selects which preset is active at runtime."""\n\n'
        f'ACTIVE_PRESET = "{preset_module}"\n\n'
        "RUNTIME_OVERRIDES = {\n"
        '    "device": {},\n'
        "}\n"
    )
    with open(ACTIVE_CONFIG_FILE, "w", encoding="utf-8") as file_obj:
        file_obj.write(file_content)


class ConfigSwitcher:
    def __init__(self, motion_controller):
        self.motion_controller = motion_controller
        self.current_index = _find_current_index()
        self.in_switching_mode = False
        self.timeout_timer = None
        self._lock = threading.Lock()
        self.press_start_time = None
        self.long_press_handled = False
        self._long_press_timer = None

    def on_button_press(self):
        gpio = self.motion_controller.session.gpio
        if gpio is None:
            return
        is_pressed = gpio.read_input(GPIO_PINS.SWITCH_CONFIG)

        if is_pressed:
            with self._lock:
                self.press_start_time = time.time()
                self.long_press_handled = False
                if self._long_press_timer is not None:
                    self._long_press_timer.cancel()
                self._long_press_timer = threading.Timer(
                    LONG_PRESS_SECONDS, self._on_long_press
                )
                self._long_press_timer.start()
        else:
            with self._lock:
                if self._long_press_timer is not None:
                    self._long_press_timer.cancel()
                    self._long_press_timer = None

                if self.long_press_handled:
                    self.long_press_handled = False
                    self.press_start_time = None
                    return

                if self.press_start_time is None:
                    return

                duration = time.time() - self.press_start_time
                self.press_start_time = None
                is_long_press = duration >= LONG_PRESS_SECONDS

            if is_long_press:
                self._execute_long_press()
            else:
                self._execute_short_press()

    def _on_long_press(self):
        with self._lock:
            gpio = self.motion_controller.session.gpio
            if gpio is None or not gpio.read_input(GPIO_PINS.SWITCH_CONFIG):
                return
            self.long_press_handled = True
        self._execute_long_press()

    def _stop_motion_if_running(self):
        if self.motion_controller.runtime_state.running:
            logging.info("GPIO 触发: 切换配置 - 正在停止当前运动...")
            self.motion_controller.cycle_manager.stop()
            self.motion_controller.glove_service.stop()

    def _reset_timeout_and_enter_mode(self):
        with self._lock:
            if not self.in_switching_mode:
                self.in_switching_mode = True
                logging.info("进入配置切换模式，60秒内无操作将自动应用并重启")

            if self.timeout_timer is not None:
                self.timeout_timer.cancel()
            self.timeout_timer = threading.Timer(TIMEOUT_SECONDS, self._on_timeout)
            self.timeout_timer.start()

    def _execute_short_press(self):
        self._stop_motion_if_running()
        self._reset_timeout_and_enter_mode()

        with self._lock:
            self.current_index = (self.current_index + 1) % len(CONFIG_PRESETS)
            preset = CONFIG_PRESETS[self.current_index]

        logging.info(f"切换到预设: {preset['module']}")
        self._execute_feedback(preset)

    def _execute_long_press(self):
        self._stop_motion_if_running()
        self._reset_timeout_and_enter_mode()

        with self._lock:
            self.current_index = 0
            preset = CONFIG_PRESETS[0]

        logging.info(f"长按触发，返回第一个预设: {preset['module']}")
        self._execute_feedback(preset)

    def _execute_feedback(self, preset):
        controller = self.motion_controller.session.controller
        if not controller.is_connected:
            logging.warning("设备未连接，无法执行反馈动作")
            return

        try:
            controller.move_to_positions(
                positions=preset["feedback_positions"],
            )
            logging.info(f"反馈动作执行完成: positions={preset['feedback_positions']}")
        except Exception as e:
            logging.error(f"反馈动作执行失败: {e}")

    def _on_timeout(self):
        with self._lock:
            preset_module = CONFIG_PRESETS[self.current_index]["module"]

        logging.info(f"配置切换超时，正在应用预设: {preset_module}")

        try:
            write_active_config(preset_module)
            logging.info("active_config.py 已更新")
        except Exception as e:
            logging.error(f"写入 active_config.py 失败: {e}")
            return

        try:
            self.motion_controller._cleanup()
        except Exception as e:
            logging.error(f"清理资源时出错: {e}")

        time.sleep(0.5)
        logging.info("正在执行系统重启...")
        subprocess.run(
            "echo 'leadshine' | sudo -S reboot",
            shell=True,
            check=False,
        )
