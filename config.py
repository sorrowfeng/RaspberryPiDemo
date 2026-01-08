"""
配置文件 - 集中管理所有可配置参数
"""

# 手型类型配置 - lhandpro_controller.py
from lhandprolib_wrapper import LAC_DOF_6, LAC_DOF_6_S

# 可选值: LAC_DOF_6 或 LAC_DOF_6_S
CURRENT_HAND_TYPE = LAC_DOF_6


# 循环运动配置 - main.py
# 默认回零时间（秒）
DEFAULT_HOME_TIME = 5.0
# 默认循环运动次数
DEFAULT_CYCLE_COUNT = 10000
# 默认循环运动速度
DEFAULT_CYCLE_VELOCITY = 20000
# 默认循环运动间隔（秒）
DEFAULT_CYCLE_INTERVAL = 0.6
# 默认循环运动最大电流
DEFAULT_CYCLE_CURRENT = 1000
# 循环运动位置序列
CYCLE_MOVE_POSITIONS = [
    [10000, 10000, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0],
    [0, 0, 10000, 10000, 10000, 10000],
    [0, 0, 0, 0, 0, 0],
]
# 循环结束的动作
CYCLE_FINISH_POSITION = [2500, 5000, 5000, 0, 0, 0]