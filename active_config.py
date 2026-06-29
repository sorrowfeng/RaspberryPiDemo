"""Selects which preset is active at runtime."""
"""Default: config_runtime_default"""

ACTIVE_PRESET = "configs.config_DH116S_RS485_aging"

RUNTIME_OVERRIDES = {
    "device": {
        "canfd_node_id": 1,
    },
}
