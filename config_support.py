"""Shared helpers for structured project configuration files."""

from typing import Any, Dict, List, MutableMapping


def axis_defaults(value: int, axis_count: int = 6) -> List[int]:
    return [value] * axis_count


def export_legacy_config(
    namespace: MutableMapping[str, Any],
    communication_config: Dict[str, Any],
    device_config: Dict[str, Any],
    motion_config: Dict[str, Any],
    grasp_config: Dict[str, Any],
    feature_flags: Dict[str, Any],
) -> None:
    """Populate backward-compatible flat exports for existing imports."""

    namespace.update(
        {
            "DEFAULT_COMMUNICATION_MODE": communication_config["default_mode"],
            "DEFAULT_LAUNCH_COUNT": communication_config["default_launch_count"],
            "CURRENT_HAND_TYPE": device_config["current_hand_type"],
            "CANFD_NODE_ID": device_config["canfd_node_id"],
            "RS485_PORT_NAME": device_config["rs485_port_name"],
            "DEFAULT_HOME_TIME": motion_config["default_home_time"],
            "DEFAULT_CYCLE_COUNT": motion_config["default_cycle_count"],
            "DEFAULT_CYCLE_VELOCITY": motion_config["default_cycle_velocity"],
            "DEFAULT_CYCLE_INTERVAL": motion_config["default_cycle_interval"],
            "DEFAULT_CYCLE_CURRENT": motion_config["default_cycle_current"],
            "CYCLE_MOVE_POSITIONS": motion_config["cycle_move_positions"],
            "CYCLE_FINISH_POSITION": motion_config["cycle_finish_position"],
            "GRASP_MODE": grasp_config["mode"],
            "GRASP_REPEAT_COUNT": grasp_config["repeat_count"],
            "GRASP_REPEAT_POSITIONS": grasp_config["repeat"]["positions"],
            "GRASP_REPEAT_VELOCITIES": grasp_config["repeat"]["velocities"],
            "GRASP_REPEAT_CURRENTS": grasp_config["repeat"]["currents"],
            "GRASP_GRIP_POSITIONS": grasp_config["hold"]["grip"]["positions"],
            "GRASP_GRIP_VELOCITIES": grasp_config["hold"]["grip"]["velocities"],
            "GRASP_GRIP_CURRENTS": grasp_config["hold"]["grip"]["currents"],
            "GRASP_RELEASE_POSITIONS": grasp_config["hold"]["release"]["positions"],
            "GRASP_RELEASE_VELOCITIES": grasp_config["hold"]["release"]["velocities"],
            "GRASP_RELEASE_CURRENTS": grasp_config["hold"]["release"]["currents"],
            "AUTO_CONNECT": feature_flags["auto_connect"],
            "AUTO_CYCLE_RUNNING": feature_flags["auto_cycle_running"],
            "ENABLE_ALARM_CHECK": feature_flags["enable_alarm_check"],
            "ENABLE_HOME_CHECK": feature_flags["enable_home_check"],
            "ENABLE_TORQUE_CONTROL": feature_flags["enable_torque_control"],
        }
    )
