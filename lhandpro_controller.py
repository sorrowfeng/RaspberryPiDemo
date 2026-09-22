"""
LHandPro 控制器封装类 - 支持ECAT、CANFD和RS485三模式
提供连接、断开、运动控制等功能
"""

import logging
import threading
import time
from functools import wraps
from typing import List, Optional, Tuple, Union

from config import DEVICE_CONFIG, FEATURE_FLAGS
from transport_canfd import CanfdTransportMixin
from transport_common import CommonInitMixin
from transport_ecat import EcatTransportMixin
from transport_rs485 import Rs485TransportMixin
from lhandprolib_wrapper import (
    LAC_DOF_6,
    LAC_DOF_6_S,
    LCM_POSITION,
    LCM_TORQUE,
    LCN_CANFD,
    LCN_ECAT,
    LCN_RS485,
    LHandProLibError,
    PyLHandProLib,
)

logger = logging.getLogger(__name__)


def _synchronized_lifecycle(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lifecycle_lock:
            return method(self, *args, **kwargs)

    return wrapper


class LHandProController(
    CanfdTransportMixin,
    EcatTransportMixin,
    Rs485TransportMixin,
    CommonInitMixin,
):
    """LHandPro 控制器封装类 - 支持ECAT、CANFD和RS485三模式"""

    ECAT_STARTUP_DEADLINE_MARGIN_SECONDS = 0.5

    def __init__(self, communication_mode: str):
        """初始化控制器

        Args:
            communication_mode: 通信模式，可选值为 "CANFD"、"ECAT" 或 "RS485"
        """
        self.lhp: Optional[PyLHandProLib] = None

        # 通讯后端类（按模式延迟导入）
        self._canfd_cls = None
        self._ecat_cls = None
        self._serial_cls = None

        # CANFD 相关属性
        self.canfd = None

        # ECAT 相关属性
        self.ec_master = None
        self.stop_flag = None
        self.monitor_thread = None
        self._ecat_callback_lock = threading.Lock()

        # RS485 相关属性
        self.serial_port = None
        self._rs485_callback_lock = threading.RLock()

        # 通用属性
        self._lifecycle_lock = threading.RLock()
        self.is_connected = False
        self.dof_total = 0
        self.dof_active = 0
        self.communication_mode = communication_mode.upper()

        # 验证通信模式
        if self.communication_mode not in ["CANFD", "ECAT", "RS485"]:
            raise ValueError(
                f"不支持的通信模式: {self.communication_mode}，请使用 'CANFD'、'ECAT' 或 'RS485'"
            )

        # 根据通信模式动态导入所需库
        self._import_communication_libs()

    def _import_communication_libs(self):
        """根据通信模式导入所需的库"""
        if self.communication_mode == "CANFD":
            from canfd_lib import CANFD as canfd_cls

            self._canfd_cls = canfd_cls
        elif self.communication_mode == "ECAT":
            from ethercat_master import EthercatMaster as ecat_cls

            self._ecat_cls = ecat_cls
        elif self.communication_mode == "RS485":
            from serial_port import SerialPort as serial_cls

            self._serial_cls = serial_cls

    @staticmethod
    def _handle_lhandpro_log(message: str) -> None:
        for line in str(message).splitlines():
            if line.strip():
                logger.debug("LHandProLib: %s", line.strip())

    def _configure_lhandpro_logging(self) -> None:
        try:
            self.lhp.set_log_callback(self._handle_lhandpro_log)
            self.lhp.log_on(True)
            logger.debug("LHandProLib 底层日志回调已启用")
        except Exception as exc:
            # Native diagnostics are optional and must not block device connection.
            logger.warning("启用 LHandProLib 底层日志失败: %s", exc, exc_info=True)

    def _has_communication_resources(self) -> bool:
        return any(
            (
                self.is_connected,
                self.lhp is not None,
                self.canfd is not None,
                self.ec_master is not None,
                self.serial_port is not None,
            )
        )

    @_synchronized_lifecycle
    def connect(
        self,
        enable_motors: bool = True,
        home_motors: bool = True,
        home_wait_time: float = 5.0,
        device_index: Optional[int] = None,
        auto_select: bool = True,
        # CANFD 特定参数
        canfd_nom_baudrate: int = 1000000,
        canfd_dat_baudrate: int = 5000000,
        # RS485 特定参数
        rs485_port_name: str = None,
        rs485_baud_rate: int = 500000,
        rs485_node_id: int = 1,
        on_home_start=None,
        ecat_connect_retry_interval_seconds: float = 0.0,
        ecat_connect_deadline_monotonic=None,
        non_interactive: bool = False,
    ) -> bool:
        """
        连接并初始化 LHandPro 设备

        Args:
            enable_motors: 是否自动使能电机
            home_motors: 是否自动回零
            home_wait_time: 回零等待时间（秒）

            # CANFD 特定参数
            canfd_nom_baudrate: CANFD标称波特率
            canfd_dat_baudrate: CANFD数据波特率
            device_index: 设备索引，如果为None则自动选择或让用户选择
                          （注意：通道固定为0）
            auto_select: 是否自动选择设备（当有多个设备时）

            # RS485 特定参数
            rs485_port_name: 串口名称，如 'COM1' 或 '/dev/ttyUSB0'，None则自动选择
            rs485_baud_rate: 波特率，None则使用config中的RS485_BAUD_RATE
            rs485_node_id: 节点ID，None则使用config中的RS485_NODE_ID
            on_home_start: 回零指令成功发出后的回调

        Returns:
            bool: 连接是否成功
        """
        try:
            if self._has_communication_resources():
                logger.info("检测到上一次连接资源，重新连接前先执行清理")
                self.disconnect()

            # 创建 PyLHandProLib 实例
            self.lhp = PyLHandProLib()
            self._configure_lhandpro_logging()

            retn = False

            if self.communication_mode == "CANFD":
                retn = self._connect_canfd(
                    enable_motors=enable_motors,
                    home_motors=home_motors,
                    home_wait_time=home_wait_time,
                    canfd_nom_baudrate=canfd_nom_baudrate,
                    canfd_dat_baudrate=canfd_dat_baudrate,
                    device_index=device_index,
                    auto_select=auto_select or non_interactive,
                    on_home_start=on_home_start,
                )
            elif self.communication_mode == "ECAT":
                retn = self._connect_ecat(
                    enable_motors=enable_motors,
                    home_motors=home_motors,
                    home_wait_time=home_wait_time,
                    channel_index=device_index,
                    auto_select=auto_select or non_interactive,
                    on_home_start=on_home_start,
                    connect_retry_interval_seconds=ecat_connect_retry_interval_seconds,
                    connect_deadline_monotonic=ecat_connect_deadline_monotonic,
                )
            elif self.communication_mode == "RS485":
                retn = self._connect_rs485(
                    enable_motors=enable_motors,
                    home_motors=home_motors,
                    home_wait_time=home_wait_time,
                    port_name=rs485_port_name,
                    baud_rate=rs485_baud_rate,
                    node_id=rs485_node_id,
                    device_index=device_index,
                    on_home_start=on_home_start,
                )

            if not retn:
                self.disconnect()
                return False

            self.lhp.set_hand_type(DEVICE_CONFIG["current_hand_type"])

            if FEATURE_FLAGS["enable_home_check"]:
                self.lhp.set_move_no_home(0)
            else:
                self.lhp.set_move_no_home(1)

            # 设置控制模式（力矩控制/位置控制）
            if FEATURE_FLAGS["enable_torque_control"]:
                self.lhp.set_control_mode(0, LCM_TORQUE)
            else:
                self.lhp.set_control_mode(0, LCM_POSITION)

            return retn

        except Exception as e:
            logger.exception(
                "设备连接或初始化异常: mode=%s, device_index=%s, error=%s",
                self.communication_mode,
                device_index,
                e,
            )
            try:
                self.disconnect()
            except Exception as cleanup_error:
                logger.exception("连接失败后的资源清理异常: %s", cleanup_error)
            return False

    def _cleanup_communication_resources(self):
        """清理通信资源"""
        if self.communication_mode == "CANFD" and self.canfd:
            self.canfd.disconnect()
            self.canfd = None
        elif self.communication_mode == "ECAT":
            if self.stop_flag:
                self.stop_flag.set()
            monitor_thread = self.monitor_thread
            if monitor_thread and monitor_thread.is_alive():
                monitor_thread.join(timeout=2.0)
                if monitor_thread.is_alive():
                    raise RuntimeError("EtherCAT TPDO 监控线程未在超时时间内退出")
            if monitor_thread:
                logger.info(
                    "EtherCAT TPDO 监控线程已停止: thread=%s, alive=%s",
                    monitor_thread.name,
                    monitor_thread.is_alive(),
                )
            self.monitor_thread = None
            self.stop_flag = None

            with self._ecat_callback_lock:
                ec_master = self.ec_master
                if ec_master:
                    ec_master.stop()
                    time.sleep(0.1)
                    if self.ec_master is ec_master:
                        self.ec_master = None
                    logger.info("EtherCAT 主站通信资源已释放")
        elif self.communication_mode == "RS485" and self.serial_port:
            # 先等待正在执行的收发回调结束；is_connected=False 会阻止新回调进入实际通信。
            with self._rs485_callback_lock:
                serial_port = self.serial_port
            serial_port.close()
            if self.serial_port is serial_port:
                self.serial_port = None

    @_synchronized_lifecycle
    def disconnect(self):
        """断开连接并清理资源"""
        if not self._has_communication_resources():
            return

        logger.info("正在断开连接...")

        if self.communication_mode == "ECAT":
            # ECAT 有两个后台线程，先禁止回调并停止线程，避免访问已关闭的库句柄。
            self.is_connected = False
            self._cleanup_communication_resources()
            if self.lhp:
                self.lhp.close()
                self.lhp = None
                logger.info("LHandProLib EtherCAT 资源已关闭")
        elif self.communication_mode == "RS485":
            # RS485 工作线程可能执行接收解码，必须在线程退出后再关闭库句柄。
            self.is_connected = False
            self._cleanup_communication_resources()
            if self.lhp:
                self.lhp.close()
                self.lhp = None
        else:
            # 保持 CANFD 原有的关闭顺序。
            if self.lhp:
                self.lhp.close()
                self.lhp = None
            self._cleanup_communication_resources()
            self.is_connected = False

        logger.info("已断开连接")

    def move_to_positions(
        self,
        positions: List[int],
        velocity: int = 20000,
        max_current: int = 1000,
        wait_time: float = 1.0,
    ) -> bool:
        """
        移动到指定位置

        Args:
            positions: 位置列表，长度为 dof_active
            velocity: 位置速度
            max_current: 最大电流
            wait_time: 运动后等待时间（秒）

        Returns:
            bool: 是否成功发送运动指令
        """
        return self.move_to_positions_with_params(
            positions=positions,
            velocities=velocity,
            max_currents=max_current,
            wait_time=wait_time,
        )

    def _normalize_axis_params(
        self,
        values: Union[int, List[int], Tuple[int, ...]],
        name: str,
    ) -> List[int]:
        """将单值或数组参数统一转换为每个轴对应的参数列表。"""
        if isinstance(values, int):
            return [values] * self.dof_active

        if len(values) != self.dof_active:
            raise ValueError(
                f"{name} count mismatch: expected {self.dof_active}, got {len(values)}"
            )

        return list(values)

    def move_to_positions_with_params(
        self,
        positions: List[int],
        velocities: Union[int, List[int], Tuple[int, ...]],
        max_currents: Union[int, List[int], Tuple[int, ...]],
        wait_time: float = 1.0,
    ) -> bool:
        """移动到指定位置，并允许为每个轴单独指定速度和电流。"""
        if not self.is_connected or not self.lhp:
            logger.warning("无法执行带参数位置运动：设备未连接")
            return False

        if len(positions) != self.dof_active:
            logger.error(
                "位置数量不匹配: expected=%s, actual=%s",
                self.dof_active,
                len(positions),
            )
            return False

        try:
            velocity_list = self._normalize_axis_params(velocities, "velocity")
            current_list = self._normalize_axis_params(max_currents, "max_current")

            for j in range(self.dof_active):
                motor_id = j + 1
                self.lhp.set_target_position(motor_id, positions[j])
                self.lhp.set_position_velocity(motor_id, velocity_list[j])
                self.lhp.set_max_current(motor_id, current_list[j])

            self.lhp.move_motors(0)
            logger.info(
                "运动指令发送成功: positions=%s, velocities=%s, max_currents=%s",
                positions,
                velocity_list,
                current_list,
            )
            if wait_time > 0:
                time.sleep(wait_time)
            return True
        except Exception as e:
            logger.exception("带参数运动控制失败: %s", e)
            return False

    def move_to_angles(
        self,
        angles: List[float],
        angular_velocity: float = 200.0,
        max_current: int = 1000,
        wait_time: float = 1.0,
    ) -> bool:
        """
        移动到指定角度

        Args:
            angles: 角度列表，长度为 dof_active
            angular_velocity: 角速度
            max_current: 最大电流
            wait_time: 运动后等待时间（秒）

        Returns:
            bool: 是否成功发送运动指令
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法执行角度运动：设备未连接")
            return False

        if len(angles) != self.dof_active:
            logger.error(
                "角度数量不匹配: expected=%s, actual=%s",
                self.dof_active,
                len(angles),
            )
            return False

        try:
            for j in range(self.dof_active):
                motor_id = j + 1
                self.lhp.set_target_angle(motor_id, angles[j])
                self.lhp.set_angular_velocity(motor_id, angular_velocity)
                self.lhp.set_max_current(motor_id, max_current)

            self.lhp.move_motors(0)
            logger.info("运动指令发送成功: angles=%s", angles)
            if wait_time > 0:
                time.sleep(wait_time)
            return True
        except Exception as e:
            logger.exception("角度运动控制失败: %s", e)
            return False

    def move_sequence(
        self,
        positions_list: List[List[int]],
        velocity: int = 20000,
        max_current: int = 1000,
        wait_time: float = 1.0,
    ) -> bool:
        """
        执行一系列位置运动

        Args:
            positions_list: 位置序列列表，每个元素是一个位置列表
            velocity: 位置速度
            max_current: 最大电流
            wait_time: 每个运动后等待时间（秒）

        Returns:
            bool: 是否成功执行所有运动
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法执行运动序列：设备未连接")
            return False

        try:
            for i, pos_list in enumerate(positions_list):
                success = self.move_to_positions(
                    pos_list, velocity, max_current, wait_time
                )
                if not success:
                    logger.error("运动序列位置失败: sequence_index=%s", i)
                    return False
                logger.info("line: %s positions: %s OK", i, pos_list)
            return True
        except Exception as e:
            logger.exception("运动序列执行失败: %s", e)
            return False

    def enable_motors(self, enable: bool = True):
        """
        使能/禁用电机

        Args:
            enable: True为使能，False为禁用
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法设置电机使能：设备未连接")
            return

        try:
            self.lhp.set_enable(0, enable)
            logger.info("电机%s成功", "使能" if enable else "禁用")
        except Exception as e:
            logger.exception("设置电机使能状态失败: enable=%s, error=%s", enable, e)

    def home(self, wait_time: float = 5.0):
        """
        回零操作

        Args:
            wait_time: 回零等待时间（秒）
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法执行回零：设备未连接")
            return

        try:
            logger.info("正在回零")
            self.lhp.home_motors(0)
            time.sleep(wait_time)
            logger.info("回零完成")
        except Exception as e:
            logger.exception("回零失败: %s", e)

    def stop_motors(self):
        """
        停止所有电机运动
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法停止电机：设备未连接")
            return

        try:
            self.lhp.stop_motors(0)
            logger.info("所有电机已停止")
        except Exception as e:
            logger.exception("停止电机失败: %s", e)

    def play_gesture(
        self, gesture_id: int, velocity: int = 20000, current: int = 1000
    ) -> bool:
        """
        执行指定手势

        Args:
            gesture_id: 执行的手势id
            velocity: 目标速度, 单位: 当量/秒（默认 20000）
            current: 最大电流, 单位 ‰(千分比)（默认 1000）

        Returns:
            bool: 是否执行成功
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法执行手势：设备未连接")
            return False

        try:
            self.lhp.play_gesture(gesture_id, velocity, current)
            logger.info(
                "手势执行成功: gesture_id=%s, velocity=%s, current=%s",
                gesture_id,
                velocity,
                current,
            )
            return True
        except Exception as e:
            logger.exception(
                "手势执行失败: gesture_id=%s, velocity=%s, current=%s, error=%s",
                gesture_id,
                velocity,
                current,
                e,
            )
            return False

    def move_to_zero(
        self, velocity: int = 20000, max_current: int = 1000, wait_time: float = 1.0
    ) -> bool:
        """
        移动到零位置（所有位置为0）

        Args:
            velocity: 位置速度
            max_current: 最大电流
            wait_time: 运动后等待时间（秒）

        Returns:
            bool: 是否成功发送运动指令
        """
        zero_positions = [0] * self.dof_active
        return self.move_to_positions(zero_positions, velocity, max_current, wait_time)

    def get_dof(self) -> Tuple[int, int]:
        """
        获取自由度信息

        Returns:
            Tuple[int, int]: (总自由度, 主动自由度)
        """
        return self.dof_total, self.dof_active

    def clear_alarm(self) -> None:
        """
        清除所有电机报警
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法清除报警：设备未连接")
            return

        try:
            self.lhp.set_clear_alarm(0)
            logger.info("已清除所有电机报警")
        except Exception as e:
            logger.exception("清除报警失败: %s", e)

    def get_alarm(self) -> bool:
        """
        获取所有电机的报警状态

        Returns:
            bool: 如果有任何一个电机报警，返回True；否则返回False
        """
        if not self.is_connected or not self.lhp:
            logger.warning("无法获取报警状态：设备未连接")
            return False

        try:
            for motor_id in range(1, self.dof_active + 1):
                alarm = self.lhp.get_now_alarm(motor_id)
                if alarm == 1:
                    logger.warning("检测到电机报警: motor_id=%s", motor_id)
                    return True
            return False
        except Exception as e:
            logger.exception("获取报警状态失败: %s", e)
            return False

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动断开连接"""
        self.disconnect()
        return False
