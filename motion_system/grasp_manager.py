import logging
import time

from config import GRASP_CONFIG


class GraspManager:
    """Handles grasp business logic."""

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        self.mode = GRASP_CONFIG["mode"]
        self.repeat_count = GRASP_CONFIG["repeat_count"]
        self.repeat_sequence = GRASP_CONFIG["repeat"]
        self.grip_sequence = GRASP_CONFIG["hold"]["grip"]
        self.release_sequence = GRASP_CONFIG["hold"]["release"]

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
            logging.warning("hold mode requires GPIO support")
            return

        from gpio_controller import GPIO_PINS

        is_triggered = self.session.gpio.read_input(GPIO_PINS.START_GRASP)
        logging.info(f"[DEBUG] GPIO START_GRASP state: {is_triggered}")

        sequence = self.grip_sequence if is_triggered else self.release_sequence
        sequence_name = "grip" if is_triggered else "release"
        self._execute_sequence(sequence, sequence_name)

    def _run_repeat_grasp(self):
        logging.info(f"start repeat grasp, count={self.repeat_count}")

        with self.runtime_state.lock:
            if self.runtime_state.running:
                logging.info("cycle motion is running, stopping it before repeat grasp")
                self.runtime_state.stop_flag.set()
                time.sleep(0.5)
            self.runtime_state.stop_flag.clear()
            self.runtime_state.running = True

        try:
            for cycle in range(self.repeat_count):
                logging.info(f"[DEBUG] repeat grasp cycle {cycle + 1}/{self.repeat_count}")
                for index, step in enumerate(self.repeat_sequence["steps"]):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("repeat grasp stopped")
                        return

                    success = self.session.controller.move_to_positions_with_params(
                        positions=step["positions"],
                        velocities=step["velocities"],
                        max_currents=step["currents"],
                        wait_time=step["interval"],
                    )
                    if not success:
                        logging.warning(f"repeat grasp step {index + 1} failed")

            logging.info("repeat grasp completed")
            self.session.move_to_zero()
        finally:
            self.runtime_state.mark_idle()

    def _execute_sequence(self, sequence, name):
        if not self.session.controller.is_connected:
            logging.warning(f"device not connected, skip grasp sequence: {name}")
            return

        steps = sequence["steps"]
        for index, step in enumerate(steps):
            logging.info(
                f"[DEBUG] {name} step {index + 1}/{len(steps)}: positions={step['positions']}"
            )
            success = self.session.controller.move_to_positions_with_params(
                positions=step["positions"],
                velocities=step["velocities"],
                max_currents=step["currents"],
                wait_time=step["interval"],
            )
            logging.info(f"[DEBUG] {name} step {index + 1} result: success={success}")
            if not success:
                logging.warning(f"{name} step {index + 1} move failed")
