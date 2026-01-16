"""
配置文件 - 集中管理所有可配置参数
"""

from lhandprolib_wrapper import LAC_DOF_6, LAC_DOF_6_S


# 宏定义：默认启动模式
# True: 启动1个脚本，使用ECAT通信模式
# False: 启动4个脚本，使用CANFD通信模式
DEFAULT_USE_ECAT_MODE = True

# 手型类型配置
# 可选值: LAC_DOF_6 或 LAC_DOF_6_S
CURRENT_HAND_TYPE = LAC_DOF_6

# 默认回零时间（秒）
DEFAULT_HOME_TIME = 10.0
# 默认循环运动次数
DEFAULT_CYCLE_COUNT = 3000
# 默认循环运动速度
DEFAULT_CYCLE_VELOCITY = 25000
# 默认循环运动间隔（秒）
DEFAULT_CYCLE_INTERVAL = 2.0
# 默认循环运动最大电流
DEFAULT_CYCLE_CURRENT = 1000
# 循环运动位置序列
CYCLE_MOVE_POSITIONS = [
    [10000, 10000, 10000, 10000, 10000, 10000],
    [0, 0, 0, 0, 0, 0]
]
# 循环结束的动作
CYCLE_FINISH_POSITION = [0, 0, 0, 0, 0, 0]
# 是否启用循环时的报警检测
ENABLE_ALARM_CHECK = False
# 是否启用回零完成检测
ENABLE_HOME_CHECK = False
# 是否启用扭矩到位停止
ENABLE_TORQUE_CONTROL = False