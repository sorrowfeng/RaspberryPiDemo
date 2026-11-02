"""Configuration preset switcher triggered by GPIO button."""

import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path

import active_config
from app.paths import PROJECT_ROOT
from device.gpio_controller import GPIO_PINS

TIMEOUT_SECONDS = 30
WRITE_TIMEOUT_SECONDS = 5
LONG_PRESS_SECONDS = 1.5
FEEDBACK_DIGIT_HOLD_SECONDS = 1.0
FEEDBACK_DIGIT_GAP_SECONDS = 0.35
FEEDBACK_SEPARATOR_POSITIONS = [5000, 5000, 5000, 5000, 5000, 5000]

FEEDBACK_DIGIT_POSITIONS = {
    0: [9000, 3000, 10000, 10000, 10000, 10000],
    1: [3000, 3000, 0, 10000, 10000, 10000],
    2: [3000, 3000, 0, 0, 10000, 10000],
    3: [3000, 3000, 0, 0, 0, 10000],
    4: [3000, 3000, 0, 0, 0, 0],
    5: [0, 0, 0, 0, 0, 0],
    6: [0, 0, 10000, 10000, 10000, 0],
    7: [0, 0, 0, 10000, 10000, 0],
    8: [0, 0, 0, 10000, 10000, 10000],
    9: [0, 8000, 4000, 10000, 10000, 10000],
}

ACTIVE_CONFIG_FILE = str(PROJECT_ROOT / "active_config.py")
DEFAULT_PRESET_MODULE = "configs.config_runtime_default"


def discover_config_presets(configs_dir=None) -> list:
    """Scan configs/ and build the switchable preset list.

    `config_runtime_default` always stays first (long-press target). Remaining
    `config_*.py` modules are included in sorted order so feedback_id is stable.
    Power-cycle presets are kept: field staff may still want them on the button.
    """
    root = Path(configs_dir or PROJECT_ROOT / "configs")
    modules = [DEFAULT_PRESET_MODULE]
    for path in sorted(root.glob("config_*.py")):
        module = f"configs.{path.stem}"
        if module != DEFAULT_PRESET_MODULE:
            modules.append(module)

    return [
        {"module": module, "feedback_id": index}
        for index, module in enumerate(modules)
    ]


CONFIG_PRESETS = discover_config_presets()


def _find_current_index():
    current = getattr(active_config, "ACTIVE_PRESET", "")
    for i, preset in enumerate(CONFIG_PRESETS):
        if preset["module"] == current:
            return i
    return 0


def write_active_config(preset_module, device_overrides=None):
    """Rewrite active_config.py from a full template (no fragile regex edits)."""
    overrides = device_overrides if device_overrides is not None else {"canfd_node_id": 1}
    content = (
        '"""Selects which preset is active at runtime."""\n'
        '"""Default: config_runtime_default"""\n\n'
        f'ACTIVE_PRESET = "{preset_module}"\n\n'
        "RUNTIME_OVERRIDES = {\n"
        f"    \"device\": {overrides},\n"
        "}\n"
    )
    temp_path = f"{ACTIVE_CONFIG_FILE}.{os.getpid()}.tmp"
    with open(temp_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(content)
    os.replace(temp_path, ACTIVE_CONFIG_FILE)


def feedback_id_to_digits(feedback_id: int):
    if feedback_id < 0:
        raise ValueError(f"feedback_id must be non-negative: {feedback_id}")
    return [int(char) for char in str(feedback_id)]


class ConfigSwitcher:
    def __init__(self, motion_controller):
        self.motion_controller = motion_controller
        self.current_index = _find_current_index()
        self.in_switching_mode = False
        self.timeout_timer = None
        self.write_timer = None
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
        if not self.motion_controller.runtime_state.is_running():
            return

        logging.info("GPIO 触发: 切换配置 - 正在停止当前运动...")
        if not self.motion_controller.cycle_manager.wait_until_stopped():
            logging.error("切换配置时循环运动停止超时")
        self.motion_controller.session.stop_and_settle()
        self.motion_controller.glove_service.stop()

    def _start_timers(self):
        # 调用者必须已持有 self._lock
        if self.timeout_timer is not None:
            self.timeout_timer.cancel()
        self.timeout_timer = threading.Timer(TIMEOUT_SECONDS, self._on_timeout)
        self.timeout_timer.start()

        if self.write_timer is not None:
            self.write_timer.cancel()
        self.write_timer = threading.Timer(
            WRITE_TIMEOUT_SECONDS, self._on_write_timeout
        )
        self.write_timer.start()

    def _execute_short_press(self):
        self._stop_motion_if_running()

        with self._lock:
            is_first_press = not self.in_switching_mode
            if not self.in_switching_mode:
                self.in_switching_mode = True
                logging.info(
                    "进入配置切换模式，%s秒内无操作将自动应用并重启",
                    TIMEOUT_SECONDS,
                )

            self._start_timers()

            if not is_first_press:
                self.current_index = (self.current_index + 1) % len(CONFIG_PRESETS)
            preset = CONFIG_PRESETS[self.current_index]

        action = "当前预设" if is_first_press else "切换到预设"
        logging.info("%s: %s", action, preset["module"])
        self._execute_feedback(preset)

    def _execute_long_press(self):
        self._stop_motion_if_running()

        with self._lock:
            if not self.in_switching_mode:
                self.in_switching_mode = True
                logging.info(
                    "进入配置切换模式，%s秒内无操作将自动应用并重启",
                    TIMEOUT_SECONDS,
                )

            self._start_timers()
            self.current_index = 0
            preset = CONFIG_PRESETS[0]

        logging.info("长按触发，返回第一个预设: %s", preset["module"])
        self._execute_feedback(preset)

    def _execute_feedback(self, preset):
        controller = self.motion_controller.session.controller
        if not controller.is_connected:
            logging.warning("设备未连接，无法执行反馈动作")
            return

        try:
            feedback_id = int(preset["feedback_id"])
            feedback_digits = feedback_id_to_digits(feedback_id)
            for index, digit in enumerate(feedback_digits):
                positions = FEEDBACK_DIGIT_POSITIONS[digit]
                controller.move_to_positions(positions=positions)
                logging.info(
                    "反馈手势: module=%s, feedback_id=%s, digit=%s, positions=%s",
                    preset["module"],
                    feedback_id,
                    digit,
                    positions,
                )
                time.sleep(FEEDBACK_DIGIT_HOLD_SECONDS)

                if index < len(feedback_digits) - 1:
                    controller.move_to_positions(positions=FEEDBACK_SEPARATOR_POSITIONS)
                    time.sleep(FEEDBACK_DIGIT_GAP_SECONDS)

            logging.info(
                "反馈动作执行完成: module=%s, feedback_id=%s",
                preset["module"],
                feedback_id,
            )
        except Exception as e:
            logging.exception("反馈动作执行失败: %s", e)

    def _on_write_timeout(self):
        with self._lock:
            preset_module = CONFIG_PRESETS[self.current_index]["module"]

        logging.info("%s秒超时，正在写入预设: %s", WRITE_TIMEOUT_SECONDS, preset_module)
        try:
            write_active_config(preset_module)
            logging.info("active_config.py 已更新")
        except Exception as e:
            logging.exception("写入 active_config.py 失败: %s", e)

    def _on_timeout(self):
        logging.info("%s秒超时，正在清理资源并重启...", TIMEOUT_SECONDS)

        try:
            self.motion_controller._cleanup()
        except Exception as e:
            logging.exception("清理资源时出错: %s", e)

        logging.info("正在执行系统重启...")
        result = subprocess.run(
            "echo 'leadshine' | sudo -S shutdown -r now",
            shell=True,
            capture_output=True,
            text=True,
        )
        logging.info("shutdown returncode=%s", result.returncode)
        if result.stdout:
            logging.info("shutdown stdout: %s", result.stdout.strip())
        if result.stderr:
            logging.error("shutdown stderr: %s", result.stderr.strip())
