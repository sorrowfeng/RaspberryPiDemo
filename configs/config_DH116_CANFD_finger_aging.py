DISPLAY_NAME = 'DH116 / CANFD / finger / aging'

PRESET = {'communication': {'default_mode': 'CANFD', 'default_launch_count': 4},
 'device': {'current_hand_type': 'LAC_DOF_6', 'canfd_node_id': 1, 'rs485_port_name': None},
 'motion': {'default_home_time': 5,
            'default_cycle_count': 5000,
            'cycle_finish_position': [0, 0, 0, 0, 0, 0],
            'cycle_sequence': 'sequences.dh116_canfd_finger_aging_cycle'},
 'grasp': {'mode': 'repeat',
           'repeat_count': 3,
           'repeat_sequence': 'sequences.dh116_canfd_finger_aging_repeat',
           'hold_grip_sequence': 'sequences.dh116_canfd_finger_aging_hold_grip',
           'hold_release_sequence': 'sequences.dh116_canfd_finger_aging_hold_release'},
 'features': {'auto_connect': True,
              'auto_cycle_running': True,
              'enable_alarm_check': False,
              'enable_home_check': False,
              'enable_torque_control': False}}
