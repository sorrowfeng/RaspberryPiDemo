DISPLAY_NAME = "DH116S / ECAT / power cycle test"

PRESET = {
    "communication": {"default_mode": "ECAT", "default_launch_count": 1},
    "device": {
        "current_hand_type": "LAC_DOF_6_S",
        "canfd_node_id": 1,
        "rs485_port_name": None,
    },
    "motion": {
        "default_home_time": 5.0,
        "default_cycle_count": 9999999,
        "cycle_finish_position": [7000, 5000, 5000, 0, 0, 0],
        "cycle_sequence": "sequences.common_cycle_aging",
    },
    "grasp": {
        "mode": "repeat",
        "repeat_count": 3,
        "repeat_sequence": "sequences.common_grasp_dh116s_repeat",
        "hold_grip_sequence": "sequences.common_grasp_dh116s_hold_grip",
        "hold_release_sequence": "sequences.common_grasp_dh116s_hold_release",
    },
    "features": {
        "auto_connect": True,
        "auto_cycle_running": True,
        "enable_alarm_check": False,
        "enable_home_check": False,
        "enable_torque_control": False,
        "enable_main_power_cycle": True,
        "main_power_cycle_start_delay": 5.0,
        "main_power_cycle_on_seconds": 20.0,
        "main_power_cycle_disconnect_lead_seconds": 2.0,
        "main_power_cycle_force_off_at_deadline": True,
        "main_power_cycle_connect_retry_interval": 1.0,
        "main_power_cycle_off_seconds": 3.0,
        "main_power_cycle_baud_rate": 9600,
        "main_power_cycle_port": None,
        "main_power_cycle_stop_timeout": 5.0,
        "main_power_cycle_control_timeout": 15.0,
    },
}
