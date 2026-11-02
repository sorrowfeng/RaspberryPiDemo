import logging
import threading
import time

from app.config import FEATURE_FLAGS, MOTION_CONFIG


class CycleMotionManager:
    """Handles cyclic motion execution."""

    # 停止请求后等待 worker 退出的时间。慢速大位移一步可能 >2s，超时会误报
    # “线程未退出”，现场如见该错误可调大，或看是否卡在总线 IO。
    MOTION_THREAD_JOIN_TIMEOUT = 5.0

    def __init__(self, session, runtime_state):
        self.session = session
        self.runtime_state = runtime_state
        # 步骤已在 config_support.normalize_sequence 中补齐，无需二次归一化。
        self.cycle_steps = MOTION_CONFIG["cycle_move_positions"]
        self.cycle_run_plan = MOTION_CONFIG["cycle_run_plan"]
        self._thread_lock = threading.Lock()
        self._motion_thread = None

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
        self.session.stop_and_settle()
        self.session.move_to_zero()
        self.session.set_ready_status()
        return True

    def _run(self):
        logging.info("开始循环运动")
        try:
            cycle_count = 0
            cycle_total = MOTION_CONFIG["default_cycle_count"]
            while not self.runtime_state.stop_flag.is_set() and cycle_count < cycle_total:
                velocity_scale = self._get_cycle_velocity_scale(cycle_count)
                logging.info(
                    "cycle %s/%s, velocity_scale=%s",
                    cycle_count + 1,
                    cycle_total,
                    velocity_scale,
                )

                for index, cycle_step in enumerate(self.cycle_steps):
                    if self.runtime_state.stop_flag.is_set():
                        logging.info("循环运动被停止")
                        return

                    if FEATURE_FLAGS["enable_alarm_check"] and self.session.controller.get_alarm():
                        logging.warning("检测到报警，循环运动停止")
                        return

                    if "gesture_id" in cycle_step:
                        success = self.session.controller.play_gesture(
                            gesture_id=cycle_step["gesture_id"],
                            velocity=self._scale_velocity(cycle_step["velocity"], velocity_scale),
                            current=cycle_step["current"],
                        )
                        if success and cycle_step["interval"] > 0:
                            # interval 是 scale=1 时的停留；速度缩放后到位耗时约
                            # 1/scale 倍，等待同步放大，避免慢速段未到位就发下一步。
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
                            # 同上：位置步的 interval 随 velocity_scale 反比放大。
                            if self.runtime_state.stop_flag.wait(
                                cycle_step["interval"] / velocity_scale
                            ):
                                logging.info("循环运动被停止")
                                return
                    if not success:
                        logging.warning("循环位置 %s 执行失败", index)
                        continue

                    if index == len(self.cycle_steps) - 1:
                        self.session.pulse_cycle_complete()

                cycle_count += 1
                logging.info("准备下一循环... (%s/%s)", cycle_count, cycle_total)

            if cycle_count >= cycle_total:
                self.session.controller.move_to_positions_with_params(
                    positions=MOTION_CONFIG["cycle_finish_position"],
                    velocities=MOTION_CONFIG["default_cycle_velocities"],
                    max_currents=MOTION_CONFIG["default_cycle_currents"],
                    wait_time=MOTION_CONFIG["default_cycle_interval"],
                )
                logging.info("已完成全部 %s 次循环运动", cycle_total)
        except Exception as exc:
            logging.exception("循环运动异常: %s", exc)
        finally:
            self.runtime_state.mark_idle()
            self.session.set_ready_status()
            logging.info("循环运动结束")
