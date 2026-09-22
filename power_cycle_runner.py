"""Explicit power-cycle state machine.

把原先 stop_motion_then_power_off 里交织的布尔标志收成有序阶段，
便于日志断言与单元测试。真正的串口/子进程动作通过回调注入。
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class PowerCyclePhase(str, enum.Enum):
    IDLE = "idle"
    POWER_ON = "power_on"
    CONNECTING = "connecting"
    RUNNING = "running"
    CLEANUP = "cleanup"
    POWER_OFF = "power_off"
    FAILED = "failed"


# 允许的状态迁移（用于断言非法跳转）
ALLOWED_TRANSITIONS = {
    PowerCyclePhase.IDLE: {PowerCyclePhase.POWER_ON, PowerCyclePhase.FAILED},
    PowerCyclePhase.POWER_ON: {PowerCyclePhase.CONNECTING, PowerCyclePhase.FAILED},
    PowerCyclePhase.CONNECTING: {
        PowerCyclePhase.RUNNING,
        PowerCyclePhase.CLEANUP,
        PowerCyclePhase.FAILED,
    },
    PowerCyclePhase.RUNNING: {PowerCyclePhase.CLEANUP, PowerCyclePhase.FAILED},
    PowerCyclePhase.CLEANUP: {PowerCyclePhase.POWER_OFF, PowerCyclePhase.FAILED},
    PowerCyclePhase.POWER_OFF: {PowerCyclePhase.IDLE, PowerCyclePhase.POWER_ON, PowerCyclePhase.FAILED},
    PowerCyclePhase.FAILED: {PowerCyclePhase.IDLE, PowerCyclePhase.POWER_OFF},
}


class IllegalTransition(RuntimeError):
    pass


@dataclass
class CleanupOutcome:
    cleanup_succeeded: bool
    communication_released: bool
    processes_stopped: Optional[bool] = None
    forced_off: bool = False
    power_off_at: Optional[float] = None


@dataclass
class PowerCycleRunner:
    """单轮上电窗口的状态机。

    注入回调：
      on_power_on / on_connect / on_start_motion / on_stop_motion /
      on_disconnect / on_power_off
    """

    on_power_on: Callable[[], float]
    on_connect: Callable[[], bool]
    on_start_motion: Callable[[], bool]
    on_stop_motion: Callable[[], bool]
    on_disconnect: Callable[[], bool]
    on_power_off: Callable[[], float]
    on_kill_processes: Optional[Callable[[], bool]] = None

    phase: PowerCyclePhase = PowerCyclePhase.IDLE
    history: List[str] = field(default_factory=list)

    def _transition(self, new_phase: PowerCyclePhase, note: str = "") -> None:
        allowed = ALLOWED_TRANSITIONS[self.phase]
        if new_phase not in allowed and new_phase != self.phase:
            raise IllegalTransition(f"{self.phase} -> {new_phase} ({note})")
        old = self.phase
        self.phase = new_phase
        entry = f"{old.value}->{new_phase.value}" + (f": {note}" if note else "")
        self.history.append(entry)
        logger.info("电源通断阶段: %s", entry)

    def run_cycle(
        self,
        *,
        start_delay: float,
        on_seconds: float,
        disconnect_lead_seconds: float,
        force_off_at_deadline: bool,
        off_seconds: float,
    ) -> CleanupOutcome:
        """执行一轮：上电 → 连接/运动 → 到点前清理 → 断电。"""
        self.history.clear()
        self.phase = PowerCyclePhase.IDLE

        power_on_at = self.on_power_on()
        self._transition(PowerCyclePhase.POWER_ON, "power-on command sent")

        if start_delay > 0:
            time.sleep(start_delay)

        deadline = power_on_at + on_seconds
        cleanup_deadline = deadline - min(disconnect_lead_seconds, on_seconds)

        connected = self.on_connect()
        if connected:
            self._transition(PowerCyclePhase.CONNECTING, "connect ok")
            if self.on_start_motion():
                self._transition(PowerCyclePhase.RUNNING, "motion started")
            else:
                self._transition(PowerCyclePhase.CLEANUP, "motion start failed")
                return self._finish_cleanup_and_power_off(
                    deadline=deadline,
                    force_off_at_deadline=force_off_at_deadline,
                    pre_cleanup_ok=False,
                )
        else:
            self._transition(PowerCyclePhase.CONNECTING, "connect failed")
            self._transition(PowerCyclePhase.CLEANUP, "skip running")
            return self._finish_cleanup_and_power_off(
                deadline=deadline,
                force_off_at_deadline=force_off_at_deadline,
                pre_cleanup_ok=False,
            )

        # 等到清理窗口
        remaining = cleanup_deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

        return self._finish_cleanup_and_power_off(
            deadline=deadline,
            force_off_at_deadline=force_off_at_deadline,
            pre_cleanup_ok=True,
        )

    def _finish_cleanup_and_power_off(
        self,
        *,
        deadline: float,
        force_off_at_deadline: bool,
        pre_cleanup_ok: bool,
    ) -> CleanupOutcome:
        if self.phase not in (PowerCyclePhase.RUNNING, PowerCyclePhase.CLEANUP, PowerCyclePhase.CONNECTING):
            self._transition(PowerCyclePhase.CLEANUP, "enter cleanup")
        elif self.phase == PowerCyclePhase.RUNNING:
            self._transition(PowerCyclePhase.CLEANUP, "deadline cleanup")

        stopped = self.on_stop_motion()
        released = stopped and self.on_disconnect()
        processes_stopped = None
        forced_off = False

        if not released and force_off_at_deadline:
            forced_off = True
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
        elif not released and self.on_kill_processes is not None:
            processes_stopped = self.on_kill_processes()
            released = bool(processes_stopped)

        if not released and not force_off_at_deadline:
            # 电气安全：仍强制物理断电，但标记 forced
            forced_off = True

        power_off_at = self.on_power_off()
        self._transition(PowerCyclePhase.POWER_OFF, "power-off command sent")

        return CleanupOutcome(
            cleanup_succeeded=pre_cleanup_ok and stopped and released,
            communication_released=bool(released),
            processes_stopped=processes_stopped,
            forced_off=forced_off,
            power_off_at=power_off_at,
        )


def make_managed_runner(
    *,
    power_on: Callable[[], float],
    request_start: Callable[[], bool],
    request_stop: Callable[[], bool],
    power_off: Callable[[], float],
    kill_processes: Optional[Callable[[], bool]] = None,
) -> PowerCycleRunner:
    """把 main_power_cycle 的托管命令包装成状态机回调。"""

    return PowerCycleRunner(
        on_power_on=power_on,
        on_connect=lambda: True,  # 连接合并在 start 命令里
        on_start_motion=request_start,
        on_stop_motion=request_stop,
        on_disconnect=lambda: True,
        on_power_off=power_off,
        on_kill_processes=kill_processes,
    )
