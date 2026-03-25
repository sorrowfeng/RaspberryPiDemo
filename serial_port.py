#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 串口封装类
用于 RS485 通信
"""

import os
import threading
import time
from typing import Optional, List, Callable


class SerialPort:
    """串口封装类"""

    def __init__(self):
        self.serial = None
        self.is_open = False
        self.read_thread = None
        self.running = False
        self.read_callback = None

        # 尝试导入 pyserial
        try:
            import serial
            import serial.tools.list_ports
            self.serial_module = serial
        except ImportError:
            raise ImportError("需要安装 pyserial 库: pip install pyserial")

    def scan_available_ports(self) -> List[str]:
        """扫描可用串口"""
        ports = []
        try:
            for port in self.serial_module.tools.list_ports.comports():
                ports.append(port.device)
        except Exception as e:
            print(f"扫描串口失败: {e}")
        return ports

    def open(self, port_name: str, baud_rate: int = 500000,
             bytesize: int = 8, parity: str = 'N',
             stopbits: int = 1, timeout: float = 0.1) -> bool:
        """打开串口

        Args:
            port_name: 串口名称，如 'COM1' 或 '/dev/ttyUSB0'
            baud_rate: 波特率，默认 500000
            bytesize: 数据位，默认 8
            parity: 校验位，默认 'N' (无校验)
            stopbits: 停止位，默认 1
            timeout: 超时时间，默认 0.1 秒

        Returns:
            是否成功打开
        """
        if self.is_open:
            return False

        try:
            self.serial = self.serial_module.Serial(
                port=port_name,
                baudrate=baud_rate,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=timeout
            )
            self.is_open = True
            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            return True
        except Exception as e:
            print(f"打开串口失败: {e}")
            return False

    def close(self):
        """关闭串口"""
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        if self.serial and self.is_open:
            self.serial.close()
            self.serial = None
        self.is_open = False

    def write(self, data: bytes) -> int:
        """发送数据

        Args:
            data: 要发送的字节数据

        Returns:
            发送的字节数
        """
        if not self.is_open or not self.serial:
            return 0
        try:
            return self.serial.write(data)
        except Exception as e:
            print(f"串口发送失败: {e}")
            return 0

    def set_read_callback(self, callback: Callable[[bytes], None]):
        """设置读取回调

        Args:
            callback: 回调函数，参数为接收到的字节数据
        """
        self.read_callback = callback

    def _read_loop(self):
        """读取循环"""
        buffer = bytearray()
        last_recv_time = time.time()

        while self.running and self.is_open:
            try:
                if self.serial and self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    if data:
                        buffer.extend(data)
                        last_recv_time = time.time()
                else:
                    # 检查是否需要发送粘包数据
                    if buffer:
                        current_time = time.time()
                        if current_time - last_recv_time >= 0.005:  # 5ms 间隔
                            if self.read_callback:
                                self.read_callback(bytes(buffer))
                            buffer.clear()
                    time.sleep(0.001)
            except Exception as e:
                print(f"串口读取失败: {e}")
                time.sleep(0.01)

        # 最后剩余数据
        if buffer and self.read_callback:
            self.read_callback(bytes(buffer))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
