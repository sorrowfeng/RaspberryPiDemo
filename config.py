"""Runtime configuration loader for RaspberryPiDemo."""

from active_config import ACTIVE_PRESET, RUNTIME_OVERRIDES
from config_support import (
    DEFAULT_ACTIVE_PRESET,
    build_runtime_configuration,
    export_legacy_config,
)

CONFIG_LOAD_ERROR = None

try:
    raw_runtime_config = build_runtime_configuration(
        preset_module=ACTIVE_PRESET or DEFAULT_ACTIVE_PRESET,
        runtime_overrides=RUNTIME_OVERRIDES,
    )
except Exception as exc:
    CONFIG_LOAD_ERROR = exc
    raw_runtime_config = build_runtime_configuration(
        preset_module=DEFAULT_ACTIVE_PRESET,
        runtime_overrides={"device": {}},
    )

# 兼容现有 dict 访问路径（MOTION_CONFIG["..."]）
COMMUNICATION_CONFIG = raw_runtime_config["communication"]
DEVICE_CONFIG = raw_runtime_config["device"]
MOTION_CONFIG = raw_runtime_config["motion"]
GRASP_CONFIG = raw_runtime_config["grasp"]
FEATURE_FLAGS = raw_runtime_config["features"]

export_legacy_config(
    globals(),
    COMMUNICATION_CONFIG,
    DEVICE_CONFIG,
    MOTION_CONFIG,
    GRASP_CONFIG,
    FEATURE_FLAGS,
)
