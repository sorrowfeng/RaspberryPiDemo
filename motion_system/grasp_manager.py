import logging
import time

from config import (
    GRASP_GRIP_CURRENTS,
    GRASP_GRIP_POSITIONS,
    GRASP_GRIP_VELOCITIES,
    GRASP_MODE,
    GRASP_RELEASE_CURRENTS,
    GRASP_RELEASE_POSITIONS,
    GRASP_RELEASE_VELOCITIES,
    GRASP_REPEAT_COUNT,
    GRASP_REPEAT_CURRENTS,
    GRASP_REPEAT_POSITIONS,
    GRASP_REPEAT_VELOCITIES,
)


class GraspManager:
    """Handles grasp business logic."""

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        self.mode = GRASP_MODE
        self.repeat_positions = GRASP_REPEAT_POSITIONS
        self.repeat_velocities = GRASP_REPEAT_VELOCITIES
        self.repeat_currents = GRASP_REPEAT_CURRENTS
        self.repeat_count = GRASP_REPEAT_COUNT
        self.grip_positions = GRASP_GRIP_POSITIONS
        self.grip_velocities = GRASP_GRIP_VELOCITIES
        self.grip_currents = GRASP_GRIP_CURRENTS
        self.release_positions = GRASP_RELEASE_POSITIONS
        self.release_velocities = GRASP_RELEASE_VELOCITIES
        self.release_currents = GRASP_RELEASE_CURRENTS

    def get_gpio_edge_name(self):
        return "BOTH" if self.mode == "hold" else "RISING"

    def resolve_gpio_edge(self, gpio_module):
        return gpio_module.BOTH if self.mode == "hold" else gpio_module.RISING

    def on_start_grasp(self):
        logging.info(f"[DEBUG] on_start_grasp called, mode={self.mode}")
        if self.mode == "hold":
            self._run_hold_grasp()
        else:
            self._run_repeat_grasp()

    def _run_hold_grasp(self):
        if not self.session.enable_gpio or not self.session.gpio:
            logging.warning("hold 模式需要 GPIO 支持")
            return

        from gpio_controller import GPIO_PINS

        is_triggered = self.session.gpio.read_input(GPIO_PINS.START_GRASP)
        logging.info(f"[DEBUG] GPIO START_GRASP state: {is_triggered}")

        if is_triggered:
            self._execute_sequence(
                positions=self.grip_positions,
                velocities=self.grip_velocities,
                currents=self.grip_currents,
                name="grip",
            )
        else:
            self._execute_sequence(
                positions=self.release_positions,
                velocities=self.release_velocities,
                currents=self.release_currents,
                name="release",
            )

    def _run_repeat_grasp(self):
        logging.info(f"开始 repeat 抓握，共 {self.repeat_count} 次")

        with self.runtime_state.lock:
            if self.runtime_state.running:
                logging.info("检测到循环运动正在运行，先停止循环运动")
                self.runtime_state.stop_flag.set()
                time.sleep(0.5)
            self.runtime_state.stop_flag.clear()
            self.runtime_state.running = True

        try:
            for cycle in range(self.repeat_count):
                logging.info(f"[DEBUG] repeat grasp cycle {cycle + 1}/{self.repeat_count}")
                for index, pos_list in enumerate(self.repeat_positions):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("抓握运动被停止")
                        return

                    success = self.session.controller.move_to_positions_with_params(
                        positions=pos_list,
                        velocities=self.repeat_velocities,
                        max_currents=self.repeat_currents,
                        wait_time=2,
                    )
                    if not success:
                        logging.warning(f"repeat 抓握步骤 {index + 1} 执行失败")

            logging.info("repeat 抓握执行完成")
            self.session.move_to_zero()
        finally:
            self.runtime_state.mark_idle()

    def _execute_sequence(self, positions, velocities, currents, name):
        if not self.session.controller.is_connected:
            logging.warning(f"设备未连接，跳过抓握序列: {name}")
            return

        for index, pos_list in enumerate(positions):
            logging.info(f"[DEBUG] {name} step {index + 1}/{len(positions)}: positions={pos_list}")
            success = self.session.controller.move_to_positions_with_params(
                positions=pos_list,
                velocities=velocities,
                max_currents=currents,
                wait_time=1,
            )
            logging.info(f"[DEBUG] {name} step {index + 1} result: success={success}")
            if not success:
                logging.warning(f"{name} step {index + 1} move failed")
