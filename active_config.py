"""Selects which preset is active at runtime."""
"""Default: config_runtime_default"""

ACTIVE_PRESET = "configs.config_DH116_CANFD_exhibit"

RUNTIME_OVERRIDES = {
    "device": {
        "canfd_node_id": 1,
    },
}
