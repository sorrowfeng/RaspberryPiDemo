"""
LHandProLib库加载器和函数原型定义

适配最新版 LHandProLib.h（SDK 2.x）：
- 所有函数原型均按“存在才定义”的方式探测，避免某个符号在新版 .so 中
  不存在时导致整个初始化失败。
- 缺失的符号记录在 missing_symbols 中，可通过 has_symbol() 查询。
"""

import ctypes
import sys
import warnings
from pathlib import Path
from typing import Optional
from ctypes import (
    c_void_p, c_int, c_float, c_bool, c_uint, c_ubyte, c_char, c_char_p,
    POINTER,
)

# 错误码定义
LER_NONE = 0
LER_PARAMETER = 1
LER_KEY_FUNC_UNINIT = 2
LER_GET_CONFIGURATION = 3
LER_DATA_ANOMALY = 4
LER_COMM_CONNECT = 5
LER_COMM_SEND = 6
LER_COMM_RECV = 7
LER_COMM_DATA_FORMAT = 8
LER_INVALID_PATH = 9
LER_LOG_SAVE_FAIL = 10
LER_NOT_HOME = 11
LER_UNKNOWN = 999

# 型号枚举
LAC_DOF_6 = 0
LAC_DOF_6_S = 1
LAC_DOF_16 = 2

# 通讯类型枚举
LCN_ECAT = 0
LCN_CANFD = 1
LCN_RS485 = 2
LCN_CAN = 3

# 控制模式枚举
LCM_POSITION = 0
LCM_VELOCITY = 1
LCM_TORQUE = 2
LCM_VEL_TOR = 3
LCM_POS_TOR = 4
LCM_HOME = 5

# 运行状态枚举
LST_STOPPED = 0
LST_RUNNING = 1
LST_ALARM = 2
LST_POS_LIMIT = 3
LST_NEG_LIMIT = 4
LST_BOTH_LIMIT = 5
LST_EMG_STOP = 6
LST_HOMING = 7

# 报警类型枚举
LAM_NULL = 0
LAM_POS_ERR = 1
LAM_OVER_SPD = 2
LAM_OVER_CUR = 3
LAM_OVER_LOAD = 4
LAM_OVER_VOL = 5
LAM_UNDER_VOL = 6
LAM_ENC_ERR = 7
LAM_STALL = 8
LAM_OTHER = 9

# 传感器ID枚举
LSS_FINGER_1_1 = 1
LSS_FINGER_1_2 = 2
LSS_FINGER_2_1 = 3
LSS_FINGER_2_2 = 4
LSS_FINGER_3_1 = 5
LSS_FINGER_3_2 = 6
LSS_FINGER_4_1 = 7
LSS_FINGER_4_2 = 8
LSS_FINGER_5_1 = 9
LSS_FINGER_5_2 = 10
LSS_HAND_PALM = 11
LSS_MAX_COUNT = 12

# 左右手枚举
LDR_HAND_RIGHT = 0
LDR_HAND_LEFT = 1

# 回调函数类型定义（与 LHandProLib.h 中的 typedef 一一对应）
LogAddCallbackWrapper = ctypes.CFUNCTYPE(None, c_char_p)
ECSendDataCallbackWrapper = ctypes.CFUNCTYPE(c_bool, POINTER(c_char), c_uint)
# CANFD 发送回调：bool(unsigned int id, const unsigned char* data,
#                      unsigned int size, int is_extended)
CANFDSendDataCallbackWrapper = ctypes.CFUNCTYPE(
    c_bool, c_uint, POINTER(c_char), c_uint, c_int
)
RS485SendDataCallbackWrapper = ctypes.CFUNCTYPE(c_bool, POINTER(c_char), c_uint)
CANSendDataCallbackWrapper = ctypes.CFUNCTYPE(c_bool, c_uint, POINTER(c_char), c_uint)


class LHandProLibLoader:
    """LHandProLib库加载器

    加载动态库后，按“符号存在才定义原型”的方式绑定 C 函数，
    避免某个接口在新版 SDK 中不存在时初始化直接崩溃。
    """

    # 必需的核心函数：缺失时直接抛错
    _REQUIRED_SYMBOLS = frozenset([
        "lhandprolib_create",
        "lhandprolib_destroy",
        "lhandprolib_initial",
        "lhandprolib_initial_ex",
        "lhandprolib_close",
    ])

    # 函数原型表：与 lib/LHandProLib.h 声明的 C API 一一对应
    # (symbol, restype, argtypes)
    _FUNCTION_TABLE = [
        # ---------- 共享 RS485 总线 ----------
        ("lhandprolib_rs485_shared_bus_create", c_void_p, []),
        ("lhandprolib_rs485_shared_bus_destroy", None, [c_void_p]),
        ("lhandprolib_rs485_shared_bus_set_send_callback",
         None, [c_void_p, RS485SendDataCallbackWrapper]),
        ("lhandprolib_rs485_shared_bus_set_receive_data",
         c_int, [c_void_p, POINTER(c_char), c_int]),
        ("lhandprolib_rs485_shared_bus_close", None, [c_void_p]),
        # ---------- 创建/销毁 ----------
        ("lhandprolib_create", c_void_p, []),
        ("lhandprolib_destroy", None, [c_void_p]),
        ("lhandprolib_free_buffer", None, [c_void_p]),
        # ---------- 初始化/关闭/监控 ----------
        ("lhandprolib_initial", c_int, [c_void_p, c_int]),
        ("lhandprolib_initial_ex", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_close", None, [c_void_p]),
        ("lhandprolib_start_monitor", None, [c_void_p]),
        ("lhandprolib_stop_monitor", None, [c_void_p]),
        ("lhandprolib_set_dry_run_mode", None, [c_void_p, c_bool]),
        ("lhandprolib_get_dry_run_mode", c_bool, [c_void_p]),
        # ---------- 回调设置 ----------
        ("lhandprolib_set_send_rpdo_callback",
         None, [c_void_p, ECSendDataCallbackWrapper]),
        ("lhandprolib_set_send_canfd_callback",
         None, [c_void_p, CANFDSendDataCallbackWrapper]),
        ("lhandprolib_set_log_callback", None, [c_void_p, LogAddCallbackWrapper]),
        ("lhandprolib_set_send_rs485_callback",
         None, [c_void_p, RS485SendDataCallbackWrapper]),
        ("lhandprolib_set_rs485_shared_bus", None, [c_void_p, c_void_p]),
        ("lhandprolib_set_send_can_callback",
         None, [c_void_p, CANSendDataCallbackWrapper]),
        # ---------- 数据接收解码 ----------
        ("lhandprolib_set_tpdo_data_decode",
         c_int, [c_void_p, POINTER(c_char), c_int]),
        ("lhandprolib_set_canfd_data_decode",
         c_int, [c_void_p, c_uint, POINTER(c_char), c_int]),
        ("lhandprolib_set_rs485_data_decode",
         c_int, [c_void_p, POINTER(c_char), c_int]),
        ("lhandprolib_set_can_data_decode",
         c_int, [c_void_p, c_uint, POINTER(c_char), c_int]),
        # ---------- 预发送数据获取 ----------
        ("lhandprolib_get_pre_send_rs485_data",
         c_int, [c_void_p, POINTER(c_char), POINTER(c_int)]),
        ("lhandprolib_get_pre_send_can_data",
         c_int, [c_void_p, POINTER(c_char), POINTER(c_int)]),
        ("lhandprolib_get_pre_send_rpdo_data",
         c_int, [c_void_p, POINTER(c_char), POINTER(c_int)]),
        ("lhandprolib_get_pre_send_canfd_data",
         c_int, [c_void_p, POINTER(c_char), POINTER(c_int)]),
        # ---------- 版本/SN/SDO ----------
        ("lhandprolib_get_firmware_version", c_int, [c_void_p, POINTER(c_float)]),
        ("lhandprolib_get_serial_number", c_int, [c_void_p, c_char_p, c_int]),
        ("lhandprolib_set_sdo_drive_param",
         c_int, [c_void_p, c_uint, c_ubyte, c_uint]),
        ("lhandprolib_get_sdo_drive_param",
         c_int, [c_void_p, c_uint, c_ubyte, POINTER(c_uint)]),
        ("lhandprolib_save_sdo_drive_param", c_int, [c_void_p]),
        # ---------- 手型/方向 ----------
        ("lhandprolib_get_dof", c_int, [c_void_p, POINTER(c_int), POINTER(c_int)]),
        ("lhandprolib_set_hand_type", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_hand_type", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_hand_direction", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_hand_direction", c_int, [c_void_p, POINTER(c_int)]),
        # ---------- 控制模式 ----------
        ("lhandprolib_set_control_mode", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_get_control_mode", c_int, [c_void_p, c_int, POINTER(c_int)]),
        # ---------- 电流/节点/波特率配置 ----------
        ("lhandprolib_set_safe_current_enable", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_safe_current_enable", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_home_current", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_home_current", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_can_node_id", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_can_node_id", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_canfd_arb_baudrate", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_canfd_arb_baudrate", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_canfd_data_baudrate", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_canfd_data_baudrate", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_rs485_node_id", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_rs485_node_id", c_int, [c_void_p, POINTER(c_int)]),
        ("lhandprolib_set_rs485_baudrate", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_rs485_baudrate", c_int, [c_void_p, POINTER(c_int)]),
        # ---------- 使能/状态 ----------
        ("lhandprolib_set_enable", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_get_enable", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_get_position_reached", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_get_torque_reached", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_set_clear_alarm", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_now_alarm", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_set_move_no_home", c_int, [c_void_p, c_int]),
        ("lhandprolib_set_angle_conversion_enable", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_angle_conversion_enable",
         c_int, [c_void_p, POINTER(c_int)]),
        # ---------- 运动/目标设置 ----------
        ("lhandprolib_home_motors", c_int, [c_void_p, c_int]),
        ("lhandprolib_get_limit_target_angle",
         c_int, [c_void_p, c_int, POINTER(c_float), POINTER(c_float)]),
        ("lhandprolib_set_target_angle", c_int, [c_void_p, c_int, c_float]),
        ("lhandprolib_get_target_angle", c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_set_target_position", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_get_target_position", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_set_velocity", c_int, [c_void_p, c_int, c_float]),
        ("lhandprolib_get_velocity", c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_set_angular_velocity", c_int, [c_void_p, c_int, c_float]),
        ("lhandprolib_get_angular_velocity",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_set_position_velocity", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_get_position_velocity",
         c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_set_max_current", c_int, [c_void_p, c_int, c_int]),
        ("lhandprolib_get_max_current", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_move_motors", c_int, [c_void_p, c_int]),
        ("lhandprolib_stop_motors", c_int, [c_void_p, c_int]),
        ("lhandprolib_play_gesture", c_int, [c_void_p, c_int, c_int, c_int]),
        ("lhandprolib_sync_position_to_target", c_int, [c_void_p, c_int]),
        # ---------- 状态获取 ----------
        ("lhandprolib_get_now_status", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_get_now_angle", c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_now_position", c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_get_now_velocity", c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_now_angular_velocity",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_now_position_velocity",
         c_int, [c_void_p, c_int, POINTER(c_int)]),
        ("lhandprolib_get_now_current", c_int, [c_void_p, c_int, POINTER(c_int)]),
        # ---------- 触觉传感器 ----------
        ("lhandprolib_set_sensor_enable", c_int, [c_void_p, c_int]),
        ("lhandprolib_set_sensor_data_format", c_int, [c_void_p, c_int]),
        ("lhandprolib_set_sensor_order", c_int, [c_void_p, POINTER(c_int), c_int]),
        ("lhandprolib_get_finger_sensor_pos",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)),
                 POINTER(POINTER(c_float)), POINTER(c_int)]),
        ("lhandprolib_get_finger_pressure",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)), POINTER(c_int)]),
        ("lhandprolib_set_finger_pressure_reset", c_int, [c_void_p]),
        ("lhandprolib_get_finger_normal_force",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_finger_normal_force_ex",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)), POINTER(c_int)]),
        ("lhandprolib_get_finger_tangential_force",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_finger_tangential_force_ex",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)), POINTER(c_int)]),
        ("lhandprolib_get_finger_force_direction",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_finger_force_direction_ex",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)), POINTER(c_int)]),
        ("lhandprolib_get_finger_proximity",
         c_int, [c_void_p, c_int, POINTER(c_float)]),
        ("lhandprolib_get_finger_proximity_ex",
         c_int, [c_void_p, c_int, POINTER(POINTER(c_float)), POINTER(c_int)]),
        # ---------- 日志管理 ----------
        ("lhandprolib_log_on", None, [c_void_p, c_bool, c_int]),
        ("lhandprolib_log_send", c_int, [c_void_p, POINTER(c_int), c_int]),
        ("lhandprolib_log_recv", c_int, [c_void_p, POINTER(c_int), c_int]),
        ("lhandprolib_log_reset", None, [c_void_p, c_bool, c_bool]),
        ("lhandprolib_log_save", c_int, [c_void_p, c_char_p]),
        ("lhandprolib_log_clear", None, [c_void_p]),
    ]

    def __init__(self, lib_path: Optional[str] = None):
        """
        初始化库加载器

        Args:
            lib_path: 可选的库文件路径，如果为None则自动查找
        """
        self._lib = None
        # 头文件中声明但当前动态库未导出的符号
        self.missing_symbols = []
        self._load_library(lib_path)
        self._define_function_prototypes()

    def _find_library(self) -> Path:
        """查找库文件"""
        # 根据平台确定库文件名
        if sys.platform == "win32":
            lib_name = "LHandProLib.dll"
        elif sys.platform == "darwin":
            lib_name = "libLHandProLib.dylib"
        else:
            lib_name = "libLHandProLib.so"

        # 尝试在常见位置查找库文件
        lib_paths = [
            Path(__file__).parent / lib_name,
            Path(__file__).parent / "lib" / lib_name,
            Path(__file__).parent / "thirdParty/bin" / lib_name,
            Path(__file__).parent / "thirdParty/lib" / lib_name,
            Path(__file__).parent / "../../../../bin" / lib_name,
            Path(__file__).parent / "../../../../lib" / lib_name,
            Path(__file__).parent / "../install/bin" / lib_name,
            Path(__file__).parent / "../install/lib" / lib_name,
            Path("/usr/local/lib") / lib_name,
            Path("/usr/lib") / lib_name,
        ]

        for path in lib_paths:
            if path.exists():
                return path

        raise FileNotFoundError(f"无法找到库文件 {lib_name}")

    def _load_library(self, lib_path: Optional[str] = None):
        """加载动态库"""
        if lib_path is None:
            lib_path = self._find_library()
        else:
            lib_path = Path(lib_path)

        if not lib_path.exists():
            raise FileNotFoundError(f"指定的库文件不存在: {lib_path}")

        try:
            self._lib = ctypes.CDLL(str(lib_path))
        except Exception as e:
            raise RuntimeError(f"加载库失败: {e}") from e

    def has_symbol(self, name: str) -> bool:
        """查询动态库是否导出了指定函数"""
        return getattr(self._lib, name, None) is not None

    def _define_function_prototypes(self):
        """按“符号存在才定义”的方式绑定 C 函数原型

        若仍用 getattr 硬编码绑定，某个符号在新版 SDK 中不存在时会在
        初始化时抛 "undefined symbol" 错误。这里改为探测：缺失的符号
        跳过并记录，只有核心函数缺失时才抛错。
        """
        for symbol, restype, argtypes in self._FUNCTION_TABLE:
            func = getattr(self._lib, symbol, None)
            if func is None:
                if symbol in self._REQUIRED_SYMBOLS:
                    raise RuntimeError(
                        f"库中缺少必需函数: {symbol}，请检查动态库版本是否匹配"
                    )
                self.missing_symbols.append(symbol)
                continue
            func.restype = restype
            func.argtypes = argtypes

        if self.missing_symbols:
            warnings.warn(
                "当前动态库未导出以下接口（共 %d 个）：%s。"
                "如已升级到新版 SDK 属正常现象，相关功能不可用；"
                "调用对应封装方法时会抛出明确错误。"
                % (len(self.missing_symbols), ", ".join(self.missing_symbols)),
                RuntimeWarning,
                stacklevel=2,
            )

    @property
    def lib(self):
        """获取底层的ctypes库对象"""
        return self._lib


# 全局单例实例
_global_lhandpro_lib = None


def get_global_lhandpro_lib(lib_path: Optional[str] = None) -> LHandProLibLoader:
    """
    获取全局单例LHandProLib实例

    Args:
        lib_path: 可选的库文件路径，仅在第一次调用时有效

    Returns:
        全局LHandProLibLoader实例
    """
    global _global_lhandpro_lib
    if _global_lhandpro_lib is None:
        _global_lhandpro_lib = LHandProLibLoader(lib_path)
    return _global_lhandpro_lib
