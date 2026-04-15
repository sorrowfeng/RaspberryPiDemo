"""Helpers for loading preset and sequence driven project configuration."""

from copy import deepcopy
import importlib
from typing import Any, Dict, List, MutableMapping, Optional

from lhandprolib_wrapper import LAC_DOF_6, LAC_DOF_6_S


HAND_TYPE_MAP = {
    "LAC_DOF_6": LAC_DOF_6,
    "LAC_DOF_6_S": LAC_DOF_6_S,
}

DEFAULT_ACTIVE_PRESET = "configs.config_runtime_default"


def axis_defaults(value: int, axis_count: int = 6) -> List[int]:
    return [value] * axis_count


def import_module_attr(module_path: str, attr_name: str) -> Any:
    module = importlib.import_module(module_path)
    return deepcopy(getattr(module, attr_name))


def merge_overrides(base: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = deepcopy(base)
    if not overrides:
        return merged

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_overrides(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def normalize_axis_values(values: Any, axis_count: int, field_name: str) -> List[int]:
    if isinstance(values, int):
        return axis_defaults(values, axis_count)

    normalized = list(values)
    if len(normalized) != axis_count:
        raise ValueError(
            f"{field_name} length mismatch: expected {axis_count}, got {len(normalized)}"
        )
    return normalized


def normalize_sequence(sequence: Dict[str, Any], axis_count: int) -> Dict[str, Any]:
    normalized_sequence = deepcopy(sequence)
    default_velocities = normalize_axis_values(
        normalized_sequence.get("default_velocities", 20000),
        axis_count,
        "default_velocities",
    )
    default_currents = normalize_axis_values(
        normalized_sequence.get("default_currents", 1000),
        axis_count,
        "default_currents",
    )
    default_interval = float(normalized_sequence.get("default_interval", 1.0))

    normalized_steps = []
    for index, step in enumerate(normalized_sequence.get("steps", [])):
        if "gesture_id" in step:
            normalized_step = {
                "gesture_id": int(step["gesture_id"]),
                "velocity": int(step.get("velocity", default_velocities[0])),
                "current": int(step.get("current", default_currents[0])),
                "interval": float(step.get("interval", default_interval)),
            }
            if "name" in step:
                normalized_step["name"] = step["name"]
            normalized_steps.append(normalized_step)
            continue

        positions = list(step["positions"])
        if len(positions) != axis_count:
            raise ValueError(
                f"steps[{index}].positions length mismatch: expected {axis_count}, got {len(positions)}"
            )

        normalized_step = {
            "positions": positions,
            "velocities": normalize_axis_values(
                step.get("velocities", default_velocities),
                axis_count,
                f"steps[{index}].velocities",
            ),
            "currents": normalize_axis_values(
                step.get("currents", default_currents),
                axis_count,
                f"steps[{index}].currents",
            ),
            "interval": float(step.get("interval", default_interval)),
        }
        if "name" in step:
            normalized_step["name"] = step["name"]
        normalized_steps.append(normalized_step)

    normalized_sequence["default_velocities"] = default_velocities
    normalized_sequence["default_currents"] = default_currents
    normalized_sequence["default_interval"] = default_interval
    normalized_sequence["steps"] = normalized_steps
    return normalized_sequence


def build_runtime_configuration(
    preset_module: str,
    runtime_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    preset = import_module_attr(preset_module, "PRESET")
    preset = merge_overrides(preset, runtime_overrides)

    hand_type_name = preset["device"]["current_hand_type"]
    if hand_type_name not in HAND_TYPE_MAP:
        raise ValueError(f"Unsupported hand type preset value: {hand_type_name}")

    communication_config = deepcopy(preset["communication"])
    device_config = deepcopy(preset["device"])
    device_config["current_hand_type"] = HAND_TYPE_MAP[hand_type_name]

    axis_count = len(preset["motion"]["cycle_finish_position"])
    cycle_sequence = normalize_sequence(
        import_module_attr(preset["motion"]["cycle_sequence"], "SEQUENCE"),
        axis_count,
    )
    repeat_sequence = normalize_sequence(
        import_module_attr(preset["grasp"]["repeat_sequence"], "SEQUENCE"),
        axis_count,
    )
    hold_grip_sequence = normalize_sequence(
        import_module_attr(preset["grasp"]["hold_grip_sequence"], "SEQUENCE"),
        axis_count,
    )
    hold_release_sequence = normalize_sequence(
        import_module_attr(preset["grasp"]["hold_release_sequence"], "SEQUENCE"),
        axis_count,
    )

    motion_config = {
        "default_home_time": preset["motion"]["default_home_time"],
        "default_cycle_count": preset["motion"]["default_cycle_count"],
        "default_cycle_velocity": cycle_sequence["default_velocities"][0],
        "default_cycle_interval": cycle_sequence["default_interval"],
        "default_cycle_current": cycle_sequence["default_currents"][0],
        "cycle_move_positions": cycle_sequence["steps"],
        "cycle_finish_position": list(preset["motion"]["cycle_finish_position"]),
    }

    grasp_config = {
        "mode": preset["grasp"]["mode"],
        "repeat_count": preset["grasp"]["repeat_count"],
        "repeat": repeat_sequence,
        "hold": {
            "grip": hold_grip_sequence,
            "release": hold_release_sequence,
        },
    }

    feature_flags = deepcopy(preset["features"])

    return {
        "communication": communication_config,
        "device": device_config,
        "motion": motion_config,
        "grasp": grasp_config,
        "features": feature_flags,
    }


def export_legacy_config(
    namespace: MutableMapping[str, Any],
    communication_config: Dict[str, Any],
    device_config: Dict[str, Any],
    motion_config: Dict[str, Any],
    grasp_config: Dict[str, Any],
    feature_flags: Dict[str, Any],
) -> None:
    """Populate backward-compatible flat exports for existing imports."""

    repeat_sequence = grasp_config["repeat"]
    grip_sequence = grasp_config["hold"]["grip"]
    release_sequence = grasp_config["hold"]["release"]

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
            "GRASP_REPEAT_POSITIONS": [step.get("positions") for step in repeat_sequence["steps"]],
            "GRASP_REPEAT_VELOCITIES": repeat_sequence["default_velocities"],
            "GRASP_REPEAT_CURRENTS": repeat_sequence["default_currents"],
            "GRASP_GRIP_POSITIONS": [step.get("positions") for step in grip_sequence["steps"]],
            "GRASP_GRIP_VELOCITIES": grip_sequence["default_velocities"],
            "GRASP_GRIP_CURRENTS": grip_sequence["default_currents"],
            "GRASP_RELEASE_POSITIONS": [step.get("positions") for step in release_sequence["steps"]],
            "GRASP_RELEASE_VELOCITIES": release_sequence["default_velocities"],
            "GRASP_RELEASE_CURRENTS": release_sequence["default_currents"],
            "AUTO_CONNECT": feature_flags["auto_connect"],
            "AUTO_CYCLE_RUNNING": feature_flags["auto_cycle_running"],
            "ENABLE_ALARM_CHECK": feature_flags["enable_alarm_check"],
            "ENABLE_HOME_CHECK": feature_flags["enable_home_check"],
            "ENABLE_TORQUE_CONTROL": feature_flags["enable_torque_control"],
        }
    )
