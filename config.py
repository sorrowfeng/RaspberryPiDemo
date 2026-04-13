"""Runtime configuration loader for RaspberryPiDemo."""

from active_config import ACTIVE_PRESET, RUNTIME_OVERRIDES
from config_support import (
    DEFAULT_ACTIVE_PRESET,
    build_runtime_configuration,
    export_legacy_config,
)

try:
    runtime_config = build_runtime_configuration(
        preset_module=ACTIVE_PRESET or DEFAULT_ACTIVE_PRESET,
        runtime_overrides=RUNTIME_OVERRIDES,
    )
except Exception:
    runtime_config = build_runtime_configuration(
        preset_module=DEFAULT_ACTIVE_PRESET,
        runtime_overrides={"device": {}},
    )

COMMUNICATION_CONFIG = runtime_config["communication"]
DEVICE_CONFIG = runtime_config["device"]
MOTION_CONFIG = runtime_config["motion"]
GRASP_CONFIG = runtime_config["grasp"]
FEATURE_FLAGS = runtime_config["features"]

export_legacy_config(
    globals(),
    COMMUNICATION_CONFIG,
    DEVICE_CONFIG,
    MOTION_CONFIG,
    GRASP_CONFIG,
    FEATURE_FLAGS,
)
