DISPLAY_NAME = 'DH116S / CANFD / grasp / aging'

PRESET = {'communication': {'default_mode': 'CANFD', 'default_launch_count': 4},
 'device': {'current_hand_type': 'LAC_DOF_6_S', 'canfd_node_id': 1, 'rs485_port_name': None},
 'motion': {'default_home_time': 5.0,
            'default_cycle_count': 2000,
            'cycle_finish_position': [2500, 5000, 5000, 0, 0, 0],
            'cycle_sequence': 'sequences.common_cycle_dh116s_grasp'},
 'grasp': {'mode': 'hold',
           'repeat_count': 3,
           'repeat_sequence': 'sequences.common_grasp_dh116s_repeat',
           'hold_grip_sequence': 'sequences.common_grasp_dh116s_hold_grip',
           'hold_release_sequence': 'sequences.common_grasp_dh116s_hold_release'},
 'features': {'auto_connect': True,
              'auto_cycle_running': True,
              'enable_alarm_check': True,
              'enable_home_check': True,
              'enable_torque_control': False}}
