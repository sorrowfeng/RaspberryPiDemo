import logging

from config import (
    CYCLE_FINISH_POSITION,
    CYCLE_MOVE_POSITIONS,
    DEFAULT_CYCLE_COUNT,
    DEFAULT_CYCLE_CURRENT,
    DEFAULT_CYCLE_INTERVAL,
    DEFAULT_CYCLE_VELOCITY,
    ENABLE_ALARM_CHECK,
)


class CycleMotionManager:
    """Handles cyclic motion execution."""

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        self.cycle_steps = self._normalize_cycle_move_positions(CYCLE_MOVE_POSITIONS)

    @staticmethod
    def _normalize_cycle_move_positions(cycle_move_positions):
        normalized_positions = []
        for index, step in enumerate(cycle_move_positions):
            if isinstance(step, dict):
                positions = step.get("positions")
                interval = step.get("interval", DEFAULT_CYCLE_INTERVAL)
            else:
                positions = step
                interval = DEFAULT_CYCLE_INTERVAL

            if positions is None:
                raise ValueError(f"CYCLE_MOVE_POSITIONS[{index}] missing positions")

            normalized_positions.append({
                "positions": positions,
                "interval": interval,
            })

        return normalized_positions

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
                for index, cycle_step in enumerate(self.cycle_steps):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("循环运动被停止")
                        return

                    if ENABLE_ALARM_CHECK and self.session.controller.get_alarm():
                        logging.warning("检测到报警，循环运动停止")
                        return

                    success = self.session.controller.move_to_positions(
                        positions=cycle_step["positions"],
                        velocity=DEFAULT_CYCLE_VELOCITY,
                        max_current=DEFAULT_CYCLE_CURRENT,
                        wait_time=cycle_step["interval"],
                    )
                    if not success:
                        logging.warning(f"循环位置 {index} 执行失败")
                        continue

                    if index == len(self.cycle_steps) - 1:
                        self.session.pulse_cycle_complete()

                cycle_count += 1
                logging.info(f"准备下一循环... ({cycle_count}/{DEFAULT_CYCLE_COUNT})")

            if cycle_count >= DEFAULT_CYCLE_COUNT:
                self.session.controller.move_to_positions(
                    positions=CYCLE_FINISH_POSITION,
                    velocity=DEFAULT_CYCLE_VELOCITY,
                    max_current=DEFAULT_CYCLE_CURRENT,
                    wait_time=DEFAULT_CYCLE_INTERVAL,
                )
                logging.info(f"已完成全部 {DEFAULT_CYCLE_COUNT} 次循环运动")
        except Exception as exc:
            logging.error(f"循环运动异常: {exc}")
        finally:
            self.runtime_state.mark_idle()
            self.session.set_ready_status()
            logging.info("循环运动结束")
