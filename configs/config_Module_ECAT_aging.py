DISPLAY_NAME = 'Module / ECAT / aging'

PRESET = {'communication': {'default_mode': 'ECAT', 'default_launch_count': 1},
 'device': {'current_hand_type': 'LAC_DOF_6', 'canfd_node_id': 1, 'rs485_port_name': None},
 'motion': {'default_home_time': 10.0,
            'default_cycle_count': 3000,
            'cycle_finish_position': [0, 0, 0, 0, 0, 0],
            'cycle_sequence': 'sequences.module_ecat_aging_cycle'},
 'grasp': {'mode': 'repeat',
           'repeat_count': 3,
           'repeat_sequence': 'sequences.module_ecat_aging_repeat',
           'hold_grip_sequence': 'sequences.module_ecat_aging_hold_grip',
           'hold_release_sequence': 'sequences.module_ecat_aging_hold_release'},
 'features': {'auto_connect': True,
              'auto_cycle_running': True,
              'enable_alarm_check': False,
              'enable_home_check': False,
              'enable_torque_control': False}}
