#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CANFD communication wrapper.

Windows:
- use HCanbus.dll through ctypes

Linux:
- keep the existing .so-based implementation
"""

import os
import sys
import threading
import time
from ctypes import (
    CDLL,
    POINTER,
    RTLD_GLOBAL,
    Structure,
    byref,
    c_char,
    c_int,
    c_ubyte,
    c_uint,
    c_uint16,
    c_uint32,
    c_ushort,
    cast,
    cdll,
)
from typing import Callable, Optional


STATUS_OK = 0
dlc2len = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]
IS_WINDOWS = sys.platform.startswith("win")


class CANFDException(Exception):
    """CANFD operation error."""


if IS_WINDOWS:
    import ctypes

    class CanFD_Config(Structure):
        _fields_ = [
            ("NomBaud", c_uint),
            ("DatBaud", c_uint),
            ("NomPre", c_ushort),
            ("NomTseg1", c_ubyte),
            ("NomTseg2", c_ubyte),
            ("NomSJW", c_ubyte),
            ("DatPre", c_ubyte),
            ("DatTseg1", c_ubyte),
            ("DatTseg2", c_ubyte),
            ("DatSJW", c_ubyte),
            ("Config", c_ubyte),
            ("Model", c_ubyte),
            ("Cantype", c_ubyte),
        ]


    class CanFD_Msg(Structure):
        _fields_ = [
            ("ID", c_uint),
            ("TimeStamp", c_uint),
            ("FrameType", c_ubyte),
            ("DLC", c_ubyte),
            ("ExternFlag", c_ubyte),
            ("RemoteFlag", c_ubyte),
            ("BusSatus", c_ubyte),
            ("ErrSatus", c_ubyte),
            ("TECounter", c_ubyte),
            ("RECounter", c_ubyte),
            ("Data", c_ubyte * 64),
        ]


    def _load_windows_library():
        search_paths = [
            os.path.join(os.path.dirname(__file__), "lib", "HCanbus.dll"),
            os.path.join(os.path.dirname(__file__), "HCanbus.dll"),
            "HCanbus.dll",
        ]
        for path in search_paths:
            if os.path.exists(path):
                return ctypes.WinDLL(os.path.abspath(path))
        raise CANFDException("Could not find HCanbus.dll")


    def _len_to_dlc(length: int) -> int:
        if length <= 8:
            return length
        if length <= 12:
            return 9
        if length <= 16:
            return 10
        if length <= 20:
            return 11
        if length <= 24:
            return 12
        if length <= 32:
            return 13
        if length <= 48:
            return 14
        return 15


    class CANFD:
        """Windows CANFD implementation based on HCanbus.dll."""

        _RECV_BUF_SIZE = 500
        _RECV_TIMEOUT_MS = 50

        def __init__(self):
            self._libcan = _load_windows_library()
            self._is_connected = False
            self._device_index = 0
            self._channel_index = 0
            self._receive_thread: Optional[threading.Thread] = None
            self._receive_stop_event = threading.Event()
            self._receive_callback: Optional[Callable[[dict], None]] = None

        def scan(self) -> int:
            try:
                return int(self._libcan.CAN_ScanDevice())
            except Exception as exc:
                raise CANFDException(f"扫描设备异常: {exc}")

        def connect(
            self,
            device_index: int = 0,
            channel_index: int = 0,
            nom_baudrate: int = 1000000,
            dat_baudrate: int = 5000000,
        ) -> bool:
            try:
                if self._is_connected:
                    self.disconnect()

                self._device_index = device_index
                self._channel_index = channel_index

                ret = self._libcan.CAN_OpenDevice(c_uint(device_index))
                if ret != STATUS_OK:
                    raise CANFDException(f"打开设备失败，错误码: {ret}")

                can_initconfig = CanFD_Config()
                can_initconfig.Model = 0
                can_initconfig.NomBaud = nom_baudrate
                can_initconfig.DatBaud = dat_baudrate
                can_initconfig.Config = 0x01 | 0x02 | 0x04
                can_initconfig.Cantype = 1
                can_initconfig.NomPre = 2
                can_initconfig.NomTseg1 = 31
                can_initconfig.NomTseg2 = 8
                can_initconfig.NomSJW = 5
                can_initconfig.DatPre = 1
                can_initconfig.DatTseg1 = 11
                can_initconfig.DatTseg2 = 4
                can_initconfig.DatSJW = 2

                ret = self._libcan.CANFD_Init(c_uint(device_index), byref(can_initconfig))
                if ret != STATUS_OK:
                    self._libcan.CAN_CloseDevice(c_uint(device_index))
                    raise CANFDException(f"初始化CANFD通道失败，错误码: {ret}")

                self._is_connected = True
                return True
            except Exception as exc:
                raise CANFDException(f"连接设备异常: {exc}")

        def disconnect(self) -> bool:
            try:
                if not self._is_connected:
                    return True

                if self._receive_thread and self._receive_thread.is_alive():
                    self._receive_stop_event.set()
                    self._receive_thread.join(timeout=1.0)

                ret = self._libcan.CAN_CloseDevice(c_uint(self._device_index))
                if ret != STATUS_OK:
                    raise CANFDException(f"关闭设备失败，错误码: {ret}")

                self._is_connected = False
                self._receive_callback = None
                return True
            except Exception as exc:
                raise CANFDException(f"断开设备异常: {exc}")

        def send(
            self,
            id: int,
            data: bytes,
            frame_type: int = 0x04,
            extern_flag: int = 0,
            remote_flag: int = 0,
        ) -> bool:
            try:
                if not self._is_connected:
                    raise CANFDException("设备未连接")

                if len(data) > 64:
                    raise CANFDException("数据长度不能超过64字节")

                send_canmsg = CanFD_Msg()
                send_canmsg.ID = id
                send_canmsg.FrameType = frame_type
                send_canmsg.DLC = _len_to_dlc(64)
                send_canmsg.ExternFlag = extern_flag
                send_canmsg.RemoteFlag = remote_flag

                for index in range(64):
                    send_canmsg.Data[index] = 0
                for index, value in enumerate(data[:64]):
                    send_canmsg.Data[index] = value

                ret = self._libcan.CANFD_Transmit(
                    c_uint(self._device_index),
                    byref(send_canmsg),
                    c_uint(1),
                    c_int(100),
                )
                if ret != 1:
                    raise CANFDException(f"发送数据失败，错误码: {ret}")
                return True
            except Exception as exc:
                raise CANFDException(f"发送数据异常: {exc}")

        def set_receive_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
            self._receive_callback = callback
            if callback and not (self._receive_thread and self._receive_thread.is_alive()):
                self._start_receive_thread()

        def _start_receive_thread(self) -> None:
            if not self._is_connected:
                raise CANFDException("设备未连接")

            self._receive_stop_event.clear()
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()

        def _receive_loop(self) -> None:
            try:
                msg_array_type = CanFD_Msg * self._RECV_BUF_SIZE
                receive_canmsg = msg_array_type()

                while not self._receive_stop_event.is_set():
                    ret = self._libcan.CANFD_Receive(
                        c_uint(self._device_index),
                        receive_canmsg,
                        c_uint(self._RECV_BUF_SIZE),
                        c_int(self._RECV_TIMEOUT_MS),
                    )

                    if ret > 0 and self._receive_callback:
                        for index in range(ret):
                            msg = receive_canmsg[index]
                            data_len = dlc2len[msg.DLC] if msg.DLC < len(dlc2len) else 64
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
                                "data": bytes(msg.Data[:data_len]),
                            }
                            try:
                                self._receive_callback(canfd_msg)
                            except Exception as exc:
                                print(f"CANFD接收回调异常: {exc}")
                    time.sleep(0.001)
            except Exception as exc:
                print(f"CANFD接收线程异常: {exc}")

        @property
        def is_connected(self) -> bool:
            return self._is_connected

        def __del__(self):
            try:
                if self._is_connected:
                    self.disconnect()
            except Exception:
                pass


else:
    class Can_Config(Structure):
        _fields_ = [
            ("baudrate", c_uint),
            ("Pres", c_ushort),
            ("Tseg1", c_ubyte),
            ("Tseg2", c_ubyte),
            ("SJW", c_ubyte),
            ("config", c_ubyte),
            ("Model", c_ubyte),
            ("Reserved", c_ubyte),
        ]


    class CanFD_Config(Structure):
        _fields_ = [
            ("NomBaud", c_uint),
            ("DatBaud", c_uint),
            ("NomPres", c_ushort),
            ("NomTseg1", c_char),
            ("NomTseg2", c_char),
            ("NomSJW", c_char),
            ("DatPres", c_char),
            ("DatTseg1", c_char),
            ("DatTseg2", c_char),
            ("DatSJW", c_char),
            ("Config", c_char),
            ("Model", c_char),
            ("Cantype", c_char),
        ]


    class Can_Msg(Structure):
        _fields_ = [
            ("ID", c_uint),
            ("TimeStamp", c_uint),
            ("FrameType", c_ubyte),
            ("DataLen", c_ubyte),
            ("ExternFlag", c_ubyte),
            ("RemoteFlag", c_ubyte),
            ("BusSatus", c_ubyte),
            ("ErrSatus", c_ubyte),
            ("TECounter", c_ubyte),
            ("RECounter", c_ubyte),
            ("Data", c_ubyte * 8),
        ]


    class CanFD_Msg(Structure):
        _fields_ = [
            ("ID", c_uint),
            ("TimeStamp", c_uint),
            ("FrameType", c_ubyte),
            ("DLC", c_ubyte),
            ("ExternFlag", c_ubyte),
            ("RemoteFlag", c_ubyte),
            ("BusSatus", c_ubyte),
            ("ErrSatus", c_ubyte),
            ("TECounter", c_ubyte),
            ("RECounter", c_ubyte),
            ("Data", c_ubyte * 64),
        ]


    class CanFD_Msg_ARRAY(Structure):
        _fields_ = [
            ("SIZE", c_uint16),
            ("STRUCT_ARRAY", POINTER(CanFD_Msg)),
        ]

        def __init__(self, num_of_structs: int):
            self.STRUCT_ARRAY = cast((CanFD_Msg * num_of_structs)(), POINTER(CanFD_Msg))
            self.SIZE = num_of_structs
            self.ADDR = self.STRUCT_ARRAY[0]


    class CANFD:
        """Linux CANFD implementation based on libusb/libcanbus .so."""

        def __init__(self):
            self._load_library()
            self._is_connected = False
            self._device_index = 0
            self._channel_index = 0
            self._receive_thread = None
            self._receive_stop_event = threading.Event()
            self._receive_callback = None

        def _load_library(self):
            try:
                CDLL("/usr/local/lib/libusb-1.0.so", RTLD_GLOBAL)
                self._libcan = cdll.LoadLibrary("/usr/local/lib/libcanbus.so")
            except Exception as exc:
                raise CANFDException(f"加载CANFD库失败: {exc}")

        def scan(self) -> int:
            try:
                ret = self._libcan.CAN_ScanDevice()
                if ret < 0:
                    raise CANFDException(f"扫描设备失败，错误码: {ret}")
                return ret
            except Exception as exc:
                raise CANFDException(f"扫描设备异常: {exc}")

        def connect(
            self,
            device_index: int = 0,
            channel_index: int = 0,
            nom_baudrate: int = 1000000,
            dat_baudrate: int = 5000000,
        ) -> bool:
            try:
                self._device_index = device_index
                self._channel_index = channel_index

                ret = self._libcan.CAN_OpenDevice(device_index, channel_index)
                if ret != STATUS_OK:
                    raise CANFDException(f"打开设备失败，错误码: {ret}")

                can_initconfig = CanFD_Config(
                    nom_baudrate,
                    dat_baudrate,
                    0x0,
                    0x0,
                    0x0,
                    0x0,
                    0x0,
                    0x0,
                    0x0,
                    0x0,
                    0x0007,
                    0x0,
                    0x1,
                )

                ret = self._libcan.CANFD_Init(device_index, channel_index, byref(can_initconfig))
                if ret != STATUS_OK:
                    self._libcan.CAN_CloseDevice(device_index, channel_index)
                    raise CANFDException(f"初始化CANFD通道失败，错误码: {ret}")

                self._is_connected = True
                return True
            except Exception as exc:
                raise CANFDException(f"连接设备异常: {exc}")

        def disconnect(self) -> bool:
            try:
                if not self._is_connected:
                    return True

                if self._receive_thread and self._receive_thread.is_alive():
                    self._receive_stop_event.set()
                    self._receive_thread.join(timeout=1.0)

                ret = self._libcan.CAN_CloseDevice(self._device_index, self._channel_index)
                if ret != STATUS_OK:
                    raise CANFDException(f"关闭设备失败，错误码: {ret}")

                self._is_connected = False
                self._receive_callback = None
                return True
            except Exception as exc:
                raise CANFDException(f"断开设备异常: {exc}")

        def send(
            self,
            id: int,
            data: bytes,
            frame_type: int = 0x04,
            extern_flag: int = 0,
            remote_flag: int = 0,
        ) -> bool:
            try:
                if not self._is_connected:
                    raise CANFDException("设备未连接")

                data_len = len(data)
                if data_len > 64:
                    raise CANFDException("数据长度不能超过64字节")

                dlc = next((i for i, val in enumerate(dlc2len) if val == 64), 15)
                ubyte_array = c_ubyte * 64
                data_array = ubyte_array()
                for index in range(64):
                    data_array[index] = 0
                for index in range(data_len):
                    data_array[index] = data[index]

                send_canmsg = CanFD_Msg(
                    ID=id,
                    FrameType=frame_type,
                    DLC=dlc,
                    ExternFlag=extern_flag,
                    RemoteFlag=remote_flag,
                    Data=data_array,
                )

                ret = self._libcan.CANFD_Transmit(
                    self._device_index,
                    self._channel_index,
                    byref(send_canmsg),
                    1,
                    100,
                )
                if ret != 1:
                    raise CANFDException(f"发送数据失败，错误码: {ret}")
                return True
            except Exception as exc:
                raise CANFDException(f"发送数据异常: {exc}")

        def set_receive_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
            self._receive_callback = callback
            if callback and not (self._receive_thread and self._receive_thread.is_alive()):
                self._start_receive_thread()

        def _start_receive_thread(self) -> None:
            if not self._is_connected:
                raise CANFDException("设备未连接")
            self._receive_stop_event.clear()
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()

        def _receive_loop(self) -> None:
            try:
                receive_canmsg = CanFD_Msg_ARRAY(500)
                while not self._receive_stop_event.is_set():
                    ret = self._libcan.CANFD_Receive(
                        self._device_index,
                        self._channel_index,
                        byref(receive_canmsg.ADDR),
                        500,
                        100,
                    )
                    if ret > 0 and self._receive_callback:
                        for index in range(ret):
                            msg = receive_canmsg.STRUCT_ARRAY[index]
                            data_len = dlc2len[msg.DLC]
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
                                "data": bytes(msg.Data[:data_len]),
                            }
                            try:
                                self._receive_callback(canfd_msg)
                            except Exception as exc:
                                print(f"CANFD接收回调异常: {exc}")
                    time.sleep(0.001)
            except Exception as exc:
                print(f"CANFD接收线程异常: {exc}")
                if self._is_connected:
                    try:
                        self.disconnect()
                    except Exception:
                        pass

        @property
        def is_connected(self) -> bool:
            return self._is_connected

        def __del__(self):
            try:
                if self._is_connected:
                    self.disconnect()
            except Exception:
                pass
