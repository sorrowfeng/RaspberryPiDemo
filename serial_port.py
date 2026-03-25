#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python 串口封装类
用于 RS485 通信

发送/接收模型（与 RS485Master.cpp 一致）：
  发送数据 → 等待接收窗口（SEND_TIMEOUT_MS）→ 一次性回调
  队列空时短暂休眠，避免空转
"""

import sys
import queue
import threading
import time
from typing import Optional, List, Callable


# 发送后等待接收响应的窗口时间（ms），可按设备响应时间调整
SEND_TIMEOUT_MS = 50


class SerialPort:
    """串口封装类"""

    def __init__(self):
        self.serial = None
        self.is_open = False
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self.read_callback: Optional[Callable[[bytes], None]] = None
        self._send_queue: queue.Queue = queue.Queue()

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
                device = port.device
                # Linux 下只显示 USB 串口设备（过滤掉板载 UART 如 ttyAMA0）
                if sys.platform.startswith('linux'):
                    if 'ttyUSB' not in device and 'ttyACM' not in device:
                        continue
                ports.append(device)
        except Exception as e:
            print(f"扫描串口失败: {e}")
        return ports

    def open(self, port_name: str, baud_rate: int = 500000,
             bytesize: int = 8, parity: str = 'N',
             stopbits: int = 1, timeout: float = 0.001) -> bool:
        """打开串口

        Args:
            port_name: 串口名称，如 'COM1' 或 '/dev/ttyUSB0'
            baud_rate: 波特率，默认 500000
            bytesize: 数据位，默认 8
            parity: 校验位，默认 'N' (无校验)
            stopbits: 停止位，默认 1
            timeout: 串口读取超时（秒），设小值使工作线程可快速轮询

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
            self._running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
            return True
        except Exception as e:
            print(f"打开串口失败: {e}")
            return False

    def close(self):
        """关闭串口"""
        self._running = False
        # 投入一个哨兵值唤醒阻塞中的 get()
        self._send_queue.put(None)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        if self.serial and self.is_open:
            self.serial.close()
            self.serial = None
        self.is_open = False

    def write(self, data: bytes) -> int:
        """发送数据（放入队列，由工作线程统一发送）

        Args:
            data: 要发送的字节数据

        Returns:
            入队字节数（实际发送由工作线程完成）
        """
        if not self.is_open:
            return 0
        self._send_queue.put(data)
        return len(data)

    def set_read_callback(self, callback: Callable[[bytes], None]):
        """设置接收回调

        Args:
            callback: 回调函数，参数为接收到的字节数据
        """
        self.read_callback = callback

    # ------------------------------------------------------------------
    # 内部工作线程：与 RS485Master.cpp run() 逻辑对齐
    #   1. 取出待发送数据
    #   2. 发送
    #   3. 在 SEND_TIMEOUT_MS 窗口内持续读取响应（处理粘包）
    #   4. 回调完整响应帧
    #   队列为空时短暂休眠，避免空转
    # ------------------------------------------------------------------
    def _worker_loop(self):
        """工作线程：发送 → 接收窗口 → 回调"""
        timeout_sec = SEND_TIMEOUT_MS / 1000.0

        while self._running:
            try:
                # 阻塞等待队列，最长 1ms，保持退出响应
                data = self._send_queue.get(timeout=0.001)
            except queue.Empty:
                continue

            # 哨兵：关闭信号
            if data is None:
                break

            if not self.is_open or not self.serial:
                continue

            # 1. 发送
            try:
                self.serial.write(data)
                self.serial.flush()
            except Exception as e:
                print(f"串口发送失败: {e}")
                continue

            # 2. 接收窗口：持续 SEND_TIMEOUT_MS 读取响应（处理粘包）
            receive_buffer = bytearray()
            start_time = time.monotonic()

            while self._running:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout_sec:
                    break
                try:
                    chunk = self.serial.read(self.serial.in_waiting or 1)
                    if chunk:
                        receive_buffer.extend(chunk)
                except Exception as e:
                    print(f"串口读取失败: {e}")
                    break

            # 3. 回调完整响应
            if receive_buffer and self.read_callback:
                try:
                    self.read_callback(bytes(receive_buffer))
                except Exception as e:
                    print(f"读取回调执行失败: {e}")

        # 工作线程退出前关闭串口
        if self.serial and self.is_open:
            self.serial.close()
            self.serial = None
        self.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
