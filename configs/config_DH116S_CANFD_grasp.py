"""DH116S CANFD grasp preset."""

from config_support import axis_defaults, export_legacy_config
from lhandprolib_wrapper import LAC_DOF_6_S


COMMUNICATION_CONFIG = {"default_mode": "CANFD", "default_launch_count": 1}
DEVICE_CONFIG = {"current_hand_type": LAC_DOF_6_S, "canfd_node_id": 1, "rs485_port_name": None}
MOTION_CONFIG = {
    "default_home_time": 5.0,
    "default_cycle_count": 10000,
    "default_cycle_velocity": 20000,
    "default_cycle_interval": 0.7,
    "default_cycle_current": 1000,
    "cycle_move_positions": [
        {"positions": [10000, 10000, 0, 0, 0, 0], "interval": 0.7},
        {"positions": [0, 0, 0, 0, 0, 0], "interval": 0.7},
        {"positions": [0, 0, 10000, 10000, 10000, 10000], "interval": 0.7},
        {"positions": [0, 0, 0, 0, 0, 0], "interval": 0.7},
    ],
    "cycle_finish_position": [2500, 5000, 5000, 0, 0, 0],
}
GRASP_CONFIG = {
    "mode": "hold",
    "repeat_count": 3,
    "repeat": {
        "positions": [
            [9000, 0, 0, 0, 0, 0],
            [9000, 0, 10000, 10000, 10000, 10000],
            [9000, 10000, 10000, 10000, 10000, 10000],
            [9000, 0, 10000, 10000, 10000, 10000],
        ],
        "velocities": axis_defaults(20000),
        "currents": axis_defaults(1000),
    },
    "hold": {
        "grip": {
            "positions": [
                [9000, 0, 0, 0, 0, 0],
                [9000, 10000, 10000, 10000, 10000, 10000],
            ],
            "velocities": axis_defaults(20000),
            "currents": axis_defaults(1000),
        },
        "release": {
            "positions": [[9000, 0, 0, 0, 0, 0]],
            "velocities": axis_defaults(20000),
            "currents": axis_defaults(1000),
        },
    },
}
FEATURE_FLAGS = {
    "auto_connect": True,
    "auto_cycle_running": False,
    "enable_alarm_check": False,
    "enable_home_check": False,
    "enable_torque_control": False,
}

export_legacy_config(globals(), COMMUNICATION_CONFIG, DEVICE_CONFIG, MOTION_CONFIG, GRASP_CONFIG, FEATURE_FLAGS)
