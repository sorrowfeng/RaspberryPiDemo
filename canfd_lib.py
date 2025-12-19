#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CANFD通信库封装
提供扫描、连接、断开、发送以及接收回调功能
"""

from ctypes import *
import threading
import time
from typing import Optional, Callable, List

# 常量定义
STATUS_OK = 0

# DLC到数据长度的映射
dlc2len = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]

# CAN配置结构体
class Can_Config(Structure):  
    _fields_ = [
        ("baudrate", c_uint),
        ("Pres", c_ushort),
        ("Tseg1", c_ubyte),
        ("Tseg2", c_ubyte),
        ("SJW", c_ubyte),
        ("config", c_ubyte),
        ("Model", c_ubyte),
        ("Reserved", c_ubyte)
    ]
    
# CANFD配置结构体
class CanFD_Config(Structure):  
    _fields_ = [
        ("NomBaud", c_uint),     # 标称波特率
        ("DatBaud", c_uint),     # 数据波特率
        ("NomPres", c_ushort),   # 标称波特率预分频
        ("NomTseg1", c_char),    # 标称波特率时间段1
        ("NomTseg2", c_char),    # 标称波特率时间段2
        ("NomSJW", c_char),      # 标称波特率同步跳转宽度
        ("DatPres", c_char),     # 数据波特率预分频
        ("DatTseg1", c_char),    # 数据波特率时间段1
        ("DatTseg2", c_char),    # 数据波特率时间段2
        ("DatSJW", c_char),      # 数据波特率同步跳转宽度
        ("Config", c_char),      # 配置
        ("Model", c_char),       # 模式
        ("Cantype", c_char)      # CAN类型 (0: CAN, 1: CANFD)
    ]
    
# CAN消息结构体
class Can_Msg(Structure):  
    _fields_ = [
        ("ID", c_uint),          # 标识符
        ("TimeStamp", c_uint),   # 时间戳
        ("FrameType", c_ubyte),  # 帧类型
        ("DataLen", c_ubyte),    # 数据长度
        ("ExternFlag", c_ubyte), # 扩展帧标志
        ("RemoteFlag", c_ubyte), # 远程帧标志
        ("BusSatus", c_ubyte),   # 总线状态
        ("ErrSatus", c_ubyte),   # 错误状态
        ("TECounter", c_ubyte),  # 发送错误计数器
        ("RECounter", c_ubyte),  # 接收错误计数器
        ("Data", c_ubyte * 8)    # 数据
    ]
    
# CANFD消息结构体
class CanFD_Msg(Structure):  
    _fields_ = [
        ("ID", c_uint),          # 标识符
        ("TimeStamp", c_uint),   # 时间戳
        ("FrameType", c_ubyte),  # 帧类型
        ("DLC", c_ubyte),        # 数据长度代码
        ("ExternFlag", c_ubyte), # 扩展帧标志
        ("RemoteFlag", c_ubyte), # 远程帧标志
        ("BusSatus", c_ubyte),   # 总线状态
        ("ErrSatus", c_ubyte),   # 错误状态
        ("TECounter", c_ubyte),  # 发送错误计数器
        ("RECounter", c_ubyte),  # 接收错误计数器
        ("Data", c_ubyte * 64)   # 数据
    ]

# CANFD消息数组
class CanFD_Msg_ARRAY(Structure):
    _fields_ = [
        ('SIZE', c_uint16), 
        ('STRUCT_ARRAY', POINTER(CanFD_Msg))
    ]
    
    def __init__(self, num_of_structs: int):
        self.STRUCT_ARRAY = cast((CanFD_Msg * num_of_structs)(), POINTER(CanFD_Msg))
        self.SIZE = num_of_structs
        self.ADDR = self.STRUCT_ARRAY[0]


class CANFDException(Exception):
    """CANFD操作异常"""
    pass


class CANFD:
    """CANFD通信类"""
    
    def __init__(self):
        """初始化CANFD实例"""
        # 加载动态库
        self._load_library()
        
        # 内部状态
        self._is_connected = False
        self._device_index = 0
        self._channel_index = 0
        self._receive_thread = None
        self._receive_stop_event = threading.Event()
        self._receive_callback = None
    
    def _load_library(self):
        """加载CANFD动态库"""
        try:
            # 先加载依赖的libusb库
            CDLL("/usr/local/lib/libusb-1.0.so", RTLD_GLOBAL)
            # 加载CANBUS库
            self._libcan = cdll.LoadLibrary("/usr/local/lib/libcanbus.so")
        except Exception as e:
            raise CANFDException(f"加载CANFD库失败: {e}")
    
    def scan(self) -> int:
        """扫描CANFD设备
        
        Returns:
            int: 找到的设备数量
            
        Raises:
            CANFDException: 扫描失败时抛出
        """
        try:
            ret = self._libcan.CAN_ScanDevice()
            if ret < 0:
                raise CANFDException(f"扫描设备失败，错误码: {ret}")
            return ret
        except Exception as e:
            raise CANFDException(f"扫描设备异常: {e}")
    
    def connect(self, device_index: int = 0, channel_index: int = 0,
                nom_baudrate: int = 1000000, dat_baudrate: int = 5000000) -> bool:
        """连接CANFD设备
        
        Args:
            device_index: 设备索引
            channel_index: 通道索引
            nom_baudrate: 标称波特率
            dat_baudrate: 数据波特率
            
        Returns:
            bool: 连接成功返回True，否则返回False
            
        Raises:
            CANFDException: 连接失败时抛出
        """
        try:
            # 保存设备和通道索引
            self._device_index = device_index
            self._channel_index = channel_index
            
            # 打开设备
            ret = self._libcan.CAN_OpenDevice(device_index, channel_index)
            if ret != STATUS_OK:
                raise CANFDException(f"打开设备失败，错误码: {ret}")
            
            # 初始化CANFD配置
            can_initconfig = CanFD_Config(
                nom_baudrate, dat_baudrate, 0x0, 0x0, 0x0, 0x0, 
                0x0, 0x0, 0x0, 0x0, 0x0007, 0x0, 0x1  # 0x1表示CANFD模式, 0x0007=终端电阻+唤醒+重传
            )
            
            # 初始化CANFD通道
            ret = self._libcan.CANFD_Init(device_index, channel_index, byref(can_initconfig))
            if ret != STATUS_OK:
                self._libcan.CAN_CloseDevice(device_index, channel_index)
                raise CANFDException(f"初始化CANFD通道失败，错误码: {ret}")
            
            # 设置连接状态
            self._is_connected = True
            return True
            
        except Exception as e:
            raise CANFDException(f"连接设备异常: {e}")
    
    def disconnect(self) -> bool:
        """断开CANFD设备连接
        
        Returns:
            bool: 断开成功返回True，否则返回False
            
        Raises:
            CANFDException: 断开失败时抛出
        """
        try:
            if not self._is_connected:
                return True
            
            # 停止接收线程
            if self._receive_thread and self._receive_thread.is_alive():
                self._receive_stop_event.set()
                self._receive_thread.join(timeout=1.0)
            
            # 关闭设备
            ret = self._libcan.CAN_CloseDevice(self._device_index, self._channel_index)
            if ret != STATUS_OK:
                raise CANFDException(f"关闭设备失败，错误码: {ret}")
            
            # 重置状态
            self._is_connected = False
            self._receive_callback = None
            return True
            
        except Exception as e:
            raise CANFDException(f"断开设备异常: {e}")
    
    def send(self, id: int, data: bytes, frame_type: int = 0x04, extern_flag: int = 0,
             remote_flag: int = 0) -> bool:
        """发送CANFD数据
        
        Args:
            id: 消息ID
            data: 要发送的数据
            frame_type: 帧类型 (默认0x04表示CANFD帧)
            extern_flag: 扩展帧标志 (0: 标准帧, 1: 扩展帧)
            remote_flag: 远程帧标志 (0: 数据帧, 1: 远程帧)
            
        Returns:
            bool: 发送成功返回True，否则返回False
            
        Raises:
            CANFDException: 发送失败时抛出
        """
        try:
            if not self._is_connected:
                raise CANFDException("设备未连接")
            
            # 检查数据长度
            data_len = len(data)
            if data_len > 64:
                raise CANFDException("数据长度不能超过64字节")
            
            # 固定使用64字节DLC值（与Windows版本保持一致）
            dlc = next((i for i, val in enumerate(dlc2len) if val == 64), 15)
            
            # 准备数据数组
            ubyte_array = c_ubyte * 64
            data_array = ubyte_array()
            # 清零并填充数据
            for i in range(64):
                data_array[i] = 0
            for i in range(data_len):
                data_array[i] = data[i]
            
            # 创建CANFD消息
            send_canmsg = CanFD_Msg(
                ID=id,
                FrameType=frame_type,
                DLC=dlc,
                ExternFlag=extern_flag,
                RemoteFlag=remote_flag,
                Data=data_array
            )
            
            # 发送消息
            ret = self._libcan.CANFD_Transmit(
                self._device_index, self._channel_index, 
                byref(send_canmsg), 1, 100
            )
            
            if ret != 1:
                raise CANFDException(f"发送数据失败，错误码: {ret}")
            
            return True
            
        except Exception as e:
            raise CANFDException(f"发送数据异常: {e}")
    
    def set_receive_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
        """设置接收回调函数
        
        Args:
            callback: 接收回调函数，参数为字典格式的CANFD消息
        """
        self._receive_callback = callback
        
        # 如果回调不为None且未启动接收线程，则启动接收线程
        if callback and not (self._receive_thread and self._receive_thread.is_alive()):
            self._start_receive_thread()
    
    def _start_receive_thread(self) -> None:
        """启动接收线程"""
        if not self._is_connected:
            raise CANFDException("设备未连接")
        
        self._receive_stop_event.clear()
        self._receive_thread = threading.Thread(target=self._receive_loop)
        self._receive_thread.daemon = True
        self._receive_thread.start()
    
    def _receive_loop(self) -> None:
        """接收循环线程"""
        try:
            # 创建消息数组
            receive_canmsg = CanFD_Msg_ARRAY(500)
            
            while not self._receive_stop_event.is_set():
                # 接收数据
                ret = self._libcan.CANFD_Receive(
                    self._device_index, self._channel_index, 
                    byref(receive_canmsg.ADDR), 500, 100
                )
                
                if ret > 0 and self._receive_callback:
                    for i in range(ret):
                        msg = receive_canmsg.STRUCT_ARRAY[i]
                        # 转换为字典格式
                        data_len = dlc2len[msg.DLC]
                        data = bytes(msg.Data[:data_len])
                        
                        canfd_msg = {
                            "id": msg.ID,
                            "timestamp": msg.TimeStamp,
                            "frame_type": msg.FrameType,
                            "dlc": msg.DLC,
                            "data_len": data_len,
                            "extern_flag": msg.ExternFlag,
                            "remote_flag": msg.RemoteFlag,
                            "bus_status": msg.BusSatus,
                            "err_status": msg.ErrSatus,
                            "te_counter": msg.TECounter,
                            "re_counter": msg.RECounter,
                            "data": data
                        }
                        
                        # 调用回调函数
                        try:
                            self._receive_callback(canfd_msg)
                        except Exception as e:
                            print(f"CANFD接收回调异常: {e}")
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.001)
                
        except Exception as e:
            print(f"CANFD接收线程异常: {e}")
            # 发生异常时自动断开连接
            if self._is_connected:
                try:
                    self.disconnect()
                except:
                    pass
    
    @property
    def is_connected(self) -> bool:
        """设备是否已连接
        
        Returns:
            bool: 已连接返回True，否则返回False
        """
        return self._is_connected
    
    def __del__(self):
        """析构函数，确保资源释放"""
        try:
            if self._is_connected:
                self.disconnect()
        except:
            pass


# 示例用法
if __name__ == "__main__":
    def receive_callback(msg):
        """接收回调函数示例"""
        print(f"接收到CANFD消息:")
        print(f"  ID: 0x{msg['id']:X}")
        print(f"  数据长度: {msg['data_len']}")
        print(f"  数据: {[hex(b) for b in msg['data']]}")
        print(f"  时间戳: {msg['timestamp']}")
        print(f"  帧类型: {msg['frame_type']}")
    
    try:
        # 创建CANFD实例
        canfd = CANFD()
        
        # 扫描设备
        device_count = canfd.scan()
        print(f"扫描到 {device_count} 个CANFD设备")
        
        if device_count == 0:
            print("未找到CANFD设备")
            exit()
        
        # 连接设备
        print("正在连接CANFD设备...")
        canfd.connect(nom_baudrate=1000000, dat_baudrate=5000000)
        print("CANFD设备连接成功")
        
        # 设置接收回调
        canfd.set_receive_callback(receive_callback)
        
        # 发送测试数据
        print("发送测试数据...")
        test_data = bytes([0x01, 0x06, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01, 0x00, 0x01])
        canfd.send(0x500 + 1, test_data)      

        print("测试数据发送成功")
        
        # 保持程序运行
        print("按Ctrl+C退出程序")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n用户中断程序")
    except CANFDException as e:
        print(f"CANFD错误: {e}")
    except Exception as e:
        print(f"其他错误: {e}")
    finally:
        # 确保断开连接
        if 'canfd' in locals() and canfd.is_connected:
            print("正在断开CANFD设备连接...")
            canfd.disconnect()
            print("CANFD设备已断开连接")
