"""
配置文件 - 集中管理所有可配置参数
"""

from lhandprolib_wrapper import LAC_DOF_6, LAC_DOF_6_S


# 默认通信模式：CANFD / ECAT / RS485
DEFAULT_COMMUNICATION_MODE = "RS485"

# 默认启动脚本数量
DEFAULT_LAUNCH_COUNT = 1

# 手型类型配置
# 可选值: LAC_DOF_6 或 LAC_DOF_6_S
CURRENT_HAND_TYPE = LAC_DOF_6

# CANFD NODE ID配置
CANFD_NODE_ID = 1

# RS485配置
RS485_PORT_NAME = None

# 默认回零时间（秒）
DEFAULT_HOME_TIME = 5.0
# 默认循环运动次数
DEFAULT_CYCLE_COUNT = 10000
# 默认循环运动速度
DEFAULT_CYCLE_VELOCITY = 20000
# 默认循环运动间隔（秒）
DEFAULT_CYCLE_INTERVAL = 0.7
# 默认循环运动最大电流
DEFAULT_CYCLE_CURRENT = 1000
# 循环运动位置序列
CYCLE_MOVE_POSITIONS = [
    [10000, 10000, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0],
    [0, 0, 10000, 10000, 10000, 10000],
    [0, 0, 0, 0, 0, 0]
]
# 循环结束的动作
CYCLE_FINISH_POSITION = [2500, 5000, 5000, 0, 0, 0]
# 开机自动循环运动
AUTO_CYCLE_RUNNING = True
# 是否启用循环时的报警检测
ENABLE_ALARM_CHECK = True
# 是否启用回零完成检测
ENABLE_HOME_CHECK = True
# 是否启用扭矩到位停止
ENABLE_TORQUE_CONTROL = False
