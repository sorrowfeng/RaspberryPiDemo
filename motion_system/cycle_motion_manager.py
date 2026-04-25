import logging

from config import (
    CYCLE_FINISH_POSITION,
    DEFAULT_CYCLE_COUNT,
    ENABLE_ALARM_CHECK,
    MOTION_CONFIG,
)


class CycleMotionManager:
    """Handles cyclic motion execution."""

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        self.cycle_steps = self._normalize_cycle_move_positions(MOTION_CONFIG["cycle_move_positions"])
        self.cycle_run_plan = MOTION_CONFIG["cycle_run_plan"]

    @staticmethod
    def _normalize_cycle_move_positions(cycle_move_positions):
        normalized_positions = []
        for index, step in enumerate(cycle_move_positions):
            if isinstance(step, dict):
                if "gesture_id" in step:
                    normalized_positions.append({
                        "gesture_id": int(step["gesture_id"]),
                        "velocity": step.get("velocity", MOTION_CONFIG["default_cycle_velocity"]),
                        "current": step.get("current", MOTION_CONFIG["default_cycle_current"]),
                        "interval": step.get("interval", MOTION_CONFIG["default_cycle_interval"]),
                    })
                    continue

                positions = step.get("positions")
                velocities = step.get("velocities", MOTION_CONFIG["default_cycle_velocity"])
                currents = step.get("currents", MOTION_CONFIG["default_cycle_current"])
                interval = step.get("interval", MOTION_CONFIG["default_cycle_interval"])
            else:
                positions = step
                velocities = MOTION_CONFIG["default_cycle_velocity"]
                currents = MOTION_CONFIG["default_cycle_current"]
                interval = MOTION_CONFIG["default_cycle_interval"]

            if positions is None:
                raise ValueError(f"CYCLE_MOVE_POSITIONS[{index}] missing positions")

            normalized_positions.append({
                "positions": positions,
                "velocities": velocities,
                "currents": currents,
                "interval": interval,
            })

        return normalized_positions

    def _get_cycle_velocity_scale(self, cycle_index):
        elapsed_cycles = 0
        for stage in self.cycle_run_plan:
            elapsed_cycles += stage["cycles"]
            if cycle_index < elapsed_cycles:
                return stage["velocity_scale"]
        return self.cycle_run_plan[-1]["velocity_scale"]

    @staticmethod
    def _scale_velocity(velocities, velocity_scale):
        if isinstance(velocities, int):
            return max(1, int(velocities * velocity_scale))
        return [max(1, int(velocity * velocity_scale)) for velocity in velocities]

    def start(self):
        if not self.session.controller.is_connected:
            logging.warning("设备未连接，无法开始循环运动")
            return

        if not self.runtime_state.start():
            logging.warning("循环运动已在执行中")
            return

        self.session.set_running_status()
        import threading
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.runtime_state.stop()
        self.session.controller.stop_motors()
        import time
        time.sleep(0.1)
        self.session.move_to_zero()
        self.session.set_ready_status()

    def _run(self):
        logging.info("开始循环运动")
        try:
            cycle_count = 0
            while not self.runtime_state.stop_flag.is_set() and cycle_count < DEFAULT_CYCLE_COUNT:
                velocity_scale = self._get_cycle_velocity_scale(cycle_count)
                logging.info(
                    f"cycle {cycle_count + 1}/{DEFAULT_CYCLE_COUNT}, velocity_scale={velocity_scale}"
                )

                for index, cycle_step in enumerate(self.cycle_steps):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("循环运动被停止")
                        return

                    if ENABLE_ALARM_CHECK and self.session.controller.get_alarm():
                        logging.warning("检测到报警，循环运动停止")
                        return

                    if "gesture_id" in cycle_step:
                        success = self.session.controller.play_gesture(
                            gesture_id=cycle_step["gesture_id"],
                            velocity=self._scale_velocity(cycle_step["velocity"], velocity_scale),
                            current=cycle_step["current"],
                        )
                        if success and cycle_step["interval"] > 0:
                            import time
                            time.sleep(cycle_step["interval"] / velocity_scale)
                    else:
                        success = self.session.controller.move_to_positions_with_params(
                            positions=cycle_step["positions"],
                            velocities=self._scale_velocity(cycle_step["velocities"], velocity_scale),
                            max_currents=cycle_step["currents"],
                            wait_time=cycle_step["interval"] / velocity_scale,
                        )
                    if not success:
                        logging.warning(f"循环位置 {index} 执行失败")
                        continue

                    if index == len(self.cycle_steps) - 1:
                        self.session.pulse_cycle_complete()

                cycle_count += 1
                logging.info(f"准备下一循环... ({cycle_count}/{DEFAULT_CYCLE_COUNT})")

            if cycle_count >= DEFAULT_CYCLE_COUNT:
                self.session.controller.move_to_positions_with_params(
                    positions=CYCLE_FINISH_POSITION,
                    velocities=MOTION_CONFIG["default_cycle_velocity"],
                    max_currents=MOTION_CONFIG["default_cycle_current"],
                    wait_time=MOTION_CONFIG["default_cycle_interval"],
                )
                logging.info(f"已完成全部 {DEFAULT_CYCLE_COUNT} 次循环运动")
        except Exception as exc:
            logging.error(f"循环运动异常: {exc}")
        finally:
            self.runtime_state.mark_idle()
            self.session.set_ready_status()
            logging.info("循环运动结束")
