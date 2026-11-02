"""Typed runtime configuration models.

替代裸 dict 配置：键名/类型错误在构造时暴露，而不是运行到一半才炸。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from log import (
    DEFAULT_BACKUP_COUNT as LOG_DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES as LOG_DEFAULT_MAX_BYTES,
    DEFAULT_MAX_SESSIONS as LOG_DEFAULT_MAX_SESSIONS,
    DEFAULT_MAX_TOTAL_BYTES as LOG_DEFAULT_MAX_TOTAL_BYTES,
)

# CANFD 传输后端默认值：gs_usb 用户态实现（pyusb + vendored gsusb_canfd）。
# 同时被 config_support.DEFAULT_CANFD_DRIVER 复用，保持单一来源。
CANFD_DRIVER_DEFAULT = "gsusb"


@dataclass(frozen=True)
class CommunicationConfig:
    default_mode: str
    default_launch_count: int


@dataclass(frozen=True)
class DeviceConfig:
    current_hand_type: Any  # LAC_DOF_6 / LAC_DOF_6_S
    canfd_node_id: int
    rs485_port_name: Optional[str]


@dataclass(frozen=True)
class CycleStage:
    cycles: int
    velocity_scale: float


@dataclass(frozen=True)
class MotionConfig:
    default_home_time: float
    default_cycle_count: int
    default_cycle_velocity: int
    default_cycle_velocities: Tuple[int, ...]
    default_cycle_interval: float
    default_cycle_current: int
    default_cycle_currents: Tuple[int, ...]
    cycle_run_plan: Tuple[CycleStage, ...]
    cycle_move_positions: Tuple[Dict[str, Any], ...]
    cycle_finish_position: Tuple[int, ...]


@dataclass(frozen=True)
class GraspConfig:
    mode: str
    repeat_count: int
    repeat: Dict[str, Any]
    hold: Dict[str, Any]


@dataclass(frozen=True)
class FeatureFlags:
    auto_connect: bool
    auto_cycle_running: bool
    enable_alarm_check: bool
    enable_home_check: bool
    enable_torque_control: bool
    enable_main_power_cycle: bool = False
    main_power_cycle_start_delay: float = 2.0
    main_power_cycle_on_seconds: float = 10.0
    main_power_cycle_disconnect_lead_seconds: float = 0.0
    main_power_cycle_force_off_at_deadline: bool = False
    main_power_cycle_connect_retry_interval: float = 0.0
    main_power_cycle_off_seconds: float = 1.0
    main_power_cycle_baud_rate: int = 9600
    main_power_cycle_port: Optional[str] = None
    main_power_cycle_rs485_ports: Optional[Tuple[str, ...]] = None
    main_power_cycle_stop_timeout: float = 5.0
    main_power_cycle_control_timeout: float = 15.0
    # CANFD 后端：gsusb / socketcan / libcanbus / hcanbus，None 表示运行期自动择优
    canfd_driver: Optional[str] = CANFD_DRIVER_DEFAULT
    # 日志磁盘保留上限（见 log.py）
    log_max_bytes: int = LOG_DEFAULT_MAX_BYTES
    log_backup_count: int = LOG_DEFAULT_BACKUP_COUNT
    log_max_sessions: int = LOG_DEFAULT_MAX_SESSIONS
    log_max_total_bytes: int = LOG_DEFAULT_MAX_TOTAL_BYTES


@dataclass(frozen=True)
class RuntimeConfig:
    communication: CommunicationConfig
    device: DeviceConfig
    motion: MotionConfig
    grasp: GraspConfig
    features: FeatureFlags


def build_runtime_config(raw: Dict[str, Any]) -> RuntimeConfig:
    """把 config_support.build_runtime_configuration 的 dict 收成 dataclass。"""
    comm = raw["communication"]
    device = raw["device"]
    motion = raw["motion"]
    grasp = raw["grasp"]
    flags = raw["features"]

    stages = tuple(
        CycleStage(cycles=int(s["cycles"]), velocity_scale=float(s["velocity_scale"]))
        for s in motion["cycle_run_plan"]
    )
    return RuntimeConfig(
        communication=CommunicationConfig(
            default_mode=comm["default_mode"],
            default_launch_count=int(comm["default_launch_count"]),
        ),
        device=DeviceConfig(
            current_hand_type=device["current_hand_type"],
            canfd_node_id=int(device["canfd_node_id"]),
            rs485_port_name=device["rs485_port_name"],
        ),
        motion=MotionConfig(
            default_home_time=float(motion["default_home_time"]),
            default_cycle_count=int(motion["default_cycle_count"]),
            default_cycle_velocity=int(motion["default_cycle_velocity"]),
            default_cycle_velocities=tuple(motion["default_cycle_velocities"]),
            default_cycle_interval=float(motion["default_cycle_interval"]),
            default_cycle_current=int(motion["default_cycle_current"]),
            default_cycle_currents=tuple(motion["default_cycle_currents"]),
            cycle_run_plan=stages,
            cycle_move_positions=tuple(motion["cycle_move_positions"]),
            cycle_finish_position=tuple(motion["cycle_finish_position"]),
        ),
        grasp=GraspConfig(
            mode=grasp["mode"],
            repeat_count=int(grasp["repeat_count"]),
            repeat=grasp["repeat"],
            hold=grasp["hold"],
        ),
        features=FeatureFlags(
            auto_connect=bool(flags["auto_connect"]),
            auto_cycle_running=bool(flags["auto_cycle_running"]),
            enable_alarm_check=bool(flags["enable_alarm_check"]),
            enable_home_check=bool(flags["enable_home_check"]),
            enable_torque_control=bool(flags["enable_torque_control"]),
            enable_main_power_cycle=bool(flags.get("enable_main_power_cycle", False)),
            main_power_cycle_start_delay=float(flags.get("main_power_cycle_start_delay", 2.0)),
            main_power_cycle_on_seconds=float(flags.get("main_power_cycle_on_seconds", 10.0)),
            main_power_cycle_disconnect_lead_seconds=float(
                flags.get("main_power_cycle_disconnect_lead_seconds", 0.0)
            ),
            main_power_cycle_force_off_at_deadline=bool(
                flags.get("main_power_cycle_force_off_at_deadline", False)
            ),
            main_power_cycle_connect_retry_interval=float(
                flags.get("main_power_cycle_connect_retry_interval", 0.0)
            ),
            main_power_cycle_off_seconds=float(flags.get("main_power_cycle_off_seconds", 1.0)),
            main_power_cycle_baud_rate=int(flags.get("main_power_cycle_baud_rate", 9600)),
            main_power_cycle_port=flags.get("main_power_cycle_port"),
            main_power_cycle_rs485_ports=(
                tuple(flags["main_power_cycle_rs485_ports"])
                if flags.get("main_power_cycle_rs485_ports")
                else None
            ),
            main_power_cycle_stop_timeout=float(flags.get("main_power_cycle_stop_timeout", 5.0)),
            main_power_cycle_control_timeout=float(
                flags.get("main_power_cycle_control_timeout", 15.0)
            ),
            canfd_driver=flags.get("canfd_driver", CANFD_DRIVER_DEFAULT),
            log_max_bytes=int(flags.get("log_max_bytes", LOG_DEFAULT_MAX_BYTES)),
            log_backup_count=int(flags.get("log_backup_count", LOG_DEFAULT_BACKUP_COUNT)),
            log_max_sessions=int(flags.get("log_max_sessions", LOG_DEFAULT_MAX_SESSIONS)),
            log_max_total_bytes=int(
                flags.get("log_max_total_bytes", LOG_DEFAULT_MAX_TOTAL_BYTES)
            ),
        ),
    )
