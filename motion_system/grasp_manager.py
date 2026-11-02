import logging

from app.config import GRASP_CONFIG


class GraspManager:
    """Handles grasp business logic."""

    def __init__(self, session, runtime_state, cycle_manager):
        self.session = session
        self.runtime_state = runtime_state
        self.cycle_manager = cycle_manager
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
        logging.info("抓握触发: mode=%s", self.mode)
        if not self.cycle_manager.wait_until_stopped():
            logging.error("循环运动线程停止超时，取消本次抓握")
            return
        self.session.stop_and_settle()
        if self.mode == "hold":
            self._run_hold_grasp()
        else:
            self._run_repeat_grasp()

    def _run_hold_grasp(self):
        if not self.session.enable_gpio or not self.session.gpio:
            logging.warning("hold mode requires GPIO support")
            return

        from device.gpio_controller import GPIO_PINS

        is_triggered = self.session.gpio.read_input(GPIO_PINS.START_GRASP)
        logging.info("GPIO START_GRASP state: %s", is_triggered)

        sequence = self.grip_sequence if is_triggered else self.release_sequence
        sequence_name = "grip" if is_triggered else "release"
        self._execute_sequence(sequence, sequence_name)

    def _run_repeat_grasp(self):
        logging.info("start repeat grasp, count=%s", self.repeat_count)

        if not self.runtime_state.start():
            logging.info("motion already running, skip repeat grasp")
            return

        try:
            for cycle in range(self.repeat_count):
                logging.info("repeat grasp cycle %s/%s", cycle + 1, self.repeat_count)
                for index, step in enumerate(self.repeat_sequence["steps"]):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("repeat grasp stopped")
                        return

                    success = self._execute_step(step)
                    if not success:
                        logging.warning("repeat grasp step %s failed", index + 1)

            logging.info("repeat grasp completed")
            self.session.move_to_zero()
        finally:
            self.runtime_state.mark_idle()

    def _execute_step(self, step):
        if "gesture_id" in step:
            success = self.session.controller.play_gesture(
                gesture_id=step["gesture_id"],
                velocity=step["velocity"],
                current=step["current"],
            )
            if success and step["interval"] > 0:
                self.runtime_state.stop_flag.wait(step["interval"])
            return success

        return self.session.controller.move_to_positions_with_params(
            positions=step["positions"],
            velocities=step["velocities"],
            max_currents=step["currents"],
            wait_time=step["interval"],
        )

    def _execute_sequence(self, sequence, name):
        if not self.session.controller.is_connected:
            logging.warning("device not connected, skip grasp sequence: %s", name)
            return

        steps = sequence["steps"]
        for index, step in enumerate(steps):
            if "gesture_id" in step:
                logging.info(
                    "%s step %s/%s: gesture_id=%s",
                    name,
                    index + 1,
                    len(steps),
                    step["gesture_id"],
                )
            else:
                logging.info(
                    "%s step %s/%s: positions=%s",
                    name,
                    index + 1,
                    len(steps),
                    step["positions"],
                )
            success = self._execute_step(step)
            logging.info("%s step %s result: success=%s", name, index + 1, success)
            if not success:
                logging.warning("%s step %s move failed", name, index + 1)
