import logging
import threading
import time

from config import (
    CYCLE_FINISH_POSITION,
    DEFAULT_CYCLE_COUNT,
    ENABLE_ALARM_CHECK,
    MOTION_CONFIG,
)


class CycleMotionManager:
    """Handles cyclic motion execution."""

    MOTION_THREAD_JOIN_TIMEOUT = 2.0

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        self.cycle_steps = self._normalize_cycle_move_positions(MOTION_CONFIG["cycle_move_positions"])
        self.cycle_run_plan = MOTION_CONFIG["cycle_run_plan"]
        self._thread_lock = threading.Lock()
        self._motion_thread = None

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
            return False

        with self._thread_lock:
            if self._motion_thread and self._motion_thread.is_alive():
                logging.warning("循环运动线程已在执行中")
                return False

            if not self.runtime_state.start():
                logging.warning("循环运动已在执行中")
                return False

            motion_thread = threading.Thread(
                target=self._run,
                name="CycleMotion",
                daemon=True,
            )
            self._motion_thread = motion_thread
            try:
                self.session.set_running_status()
                # 在线程成功启动前保持锁，避免停止请求对尚未启动的线程执行 join。
                motion_thread.start()
            except Exception:
                if self._motion_thread is motion_thread:
                    self._motion_thread = None
                self.runtime_state.mark_idle()
                raise
        return True

    def wait_until_stopped(self, timeout=None):
        """Request cycle motion to stop and wait until its worker has exited."""
        if timeout is None:
            timeout = self.MOTION_THREAD_JOIN_TIMEOUT

        with self._thread_lock:
            # 与 start() 使用相同的加锁顺序，保证停止事件和线程引用同步切换。
            self.runtime_state.stop()
            motion_thread = self._motion_thread

        if motion_thread is None:
            logging.debug("循环运动线程当前未运行")
            return True
        if motion_thread is threading.current_thread():
            logging.error("不能从循环运动线程内部等待自身退出")
            return False

        started_at = time.monotonic()
        motion_thread.join(timeout=max(0.0, timeout))
        join_duration = time.monotonic() - started_at
        if motion_thread.is_alive():
            logging.error(
                "循环运动线程未在超时时间内退出: thread=%s, timeout=%.3fs, join_duration=%.3fs",
                motion_thread.name,
                timeout,
                join_duration,
            )
            return False

        with self._thread_lock:
            if self._motion_thread is motion_thread:
                self._motion_thread = None
        logging.info(
            "循环运动线程已停止: thread=%s, join_duration=%.3fs",
            motion_thread.name,
            join_duration,
        )
        return True

    def stop(self):
        if not self.wait_until_stopped():
            return False
        self.session.controller.stop_motors()
        time.sleep(0.1)
        self.session.move_to_zero()
        self.session.set_ready_status()
        return True

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
                            if self.runtime_state.stop_flag.wait(
                                cycle_step["interval"] / velocity_scale
                            ):
                                logging.info("循环运动被停止")
                                return
                    else:
                        success = self.session.controller.move_to_positions_with_params(
                            positions=cycle_step["positions"],
                            velocities=self._scale_velocity(cycle_step["velocities"], velocity_scale),
                            max_currents=cycle_step["currents"],
                            wait_time=0,
                        )
                        if success and cycle_step["interval"] > 0:
                            if self.runtime_state.stop_flag.wait(
                                cycle_step["interval"] / velocity_scale
                            ):
                                logging.info("循环运动被停止")
                                return
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
            logging.exception("循环运动异常: %s", exc)
        finally:
            self.runtime_state.mark_idle()
            self.session.set_ready_status()
            logging.info("循环运动结束")
