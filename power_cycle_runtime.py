"""Power-cycle timing, port selection, and cleanup state helpers.

拆出 main_power_cycle 中的时序魔数、串口选择与断电前清理状态，便于单测与复用。
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 断电指令发出后给串口驱动排空的时间，避免被下一轮覆盖。
SEND_DRAIN_SECONDS = 0.1
POWER_COMMAND_WRITE_TIMEOUT_SECONDS = 2.0
SEND_COMMAND_LABEL_POWER_ON = "上电"
SEND_COMMAND_LABEL_POWER_OFF = "断电"


class PowerCyclePhase(str, enum.Enum):
    """上电窗口内的逻辑阶段，用于日志与断言。"""

    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    CLEANUP = "cleanup"
    POWER_OFF = "power_off"


@dataclass
class CleanupOutcome:
    """stop_motion_then_power_off 的结果摘要。"""

    cleanup_succeeded: bool
    communication_released: bool
    processes_stopped: Optional[bool]
    force_off_with_incomplete_cleanup: bool
    power_off_at: Optional[float]


def pick_serial_port(ports, *, non_interactive: bool = False, prompt: str = "请选择串口编号"):
    """选择串口；non_interactive 时自动取第一个，避免卡在 input()。"""
    if not ports:
        raise RuntimeError("未找到可用于电源控制的串口")
    if len(ports) == 1 or non_interactive:
        chosen = ports[0]
        if non_interactive and len(ports) > 1:
            logger.warning("非交互模式自动选择电源串口: %s（建议在配置中固定）", chosen)
        return chosen

    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")
    while True:
        try:
            user_input = input(f"\n{prompt} [0-{len(ports) - 1}]: ")
            index = int(user_input)
            if 0 <= index < len(ports):
                return ports[index]
            print("请输入有效的编号")
        except ValueError:
            print("请输入数字")


def sleep_until(deadline: float, *, poll: float = 0.5, should_abort: Optional[Callable[[], bool]] = None) -> None:
    """可中断地睡到 deadline。"""
    while True:
        if should_abort is not None and should_abort():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, poll))
