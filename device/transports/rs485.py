"""RS485 transport connect/disconnect helpers for LHandProController."""

import logging

from device.lhandprolib_wrapper import LCN_RS485
from device.serial_port import SerialPort

logger = logging.getLogger(__name__)


class Rs485TransportMixin:
    """RS485-specific callbacks and connection setup."""

    def _rs485_send_callback(self, data: bytes) -> bool:
        """RS485 发送回调函数"""
        try:
            with self._rs485_callback_lock:
                if not self.is_connected:
                    return False
                serial_port = self.serial_port
                if not serial_port:
                    return False
                return serial_port.write(data) > 0
        except Exception as e:
            logger.exception("RS485 发送失败: %s", e)
        return False

    def _rs485_receive_callback(self, data: bytes):
        """RS485 接收回调函数"""
        try:
            with self._rs485_callback_lock:
                if self.lhp and self.is_connected:
                    self.lhp.set_rs485_data_decode(data)
        except Exception as e:
            logger.exception("RS485 接收解析失败: %s", e)

    def _connect_rs485(
        self,
        enable_motors,
        home_motors,
        home_wait_time,
        port_name,
        baud_rate,
        node_id,
        device_index=None,
        on_home_start=None,
        non_interactive=False,
    ):
        """使用RS485模式连接设备"""
        self.serial_port = self._serial_cls()

        logger.info("正在使用RS485通讯")

        # 选择串口
        if port_name is None:
            available_ports = self.serial_port.scan_available_ports()
            if not available_ports:
                logger.error("未找到可用于 RS485 的串口")
                self.lhp.close()
                self.lhp = None
                self.serial_port = None
                return False

            logger.info("可用串口列表: %s", available_ports)

            if device_index is not None:
                # 多进程场景：用 device_index 直接映射到对应串口
                if device_index < len(available_ports):
                    port_name = available_ports[device_index]
                    logger.info("根据设备索引 %s 自动选择串口: %s", device_index, port_name)
                else:
                    logger.error(
                        "RS485 设备索引超出可用串口数量: device_index=%s, port_count=%s",
                        device_index,
                        len(available_ports),
                    )
                    self.lhp.close()
                    self.lhp = None
                    self.serial_port = None
                    return False
            elif len(available_ports) == 1 or non_interactive:
                port_name = available_ports[0]
                logger.info("自动选择串口: %s", port_name)
            else:
                while True:
                    try:
                        user_input = input(
                            f"\n请选择串口编号 [0-{len(available_ports) - 1}]: "
                        )
                        port_index = int(user_input)
                        if 0 <= port_index < len(available_ports):
                            port_name = available_ports[port_index]
                            break
                        print("请输入有效的编号")
                    except ValueError:
                        print("请输入数字")

        # 打开串口
        logger.info("正在打开串口 %s，波特率: %sbps", port_name, baud_rate)
        if not self.serial_port.open(port_name, baud_rate):
            logger.error(
                "打开 RS485 串口失败: port=%s, baudrate=%s",
                port_name,
                baud_rate,
            )
            self.lhp.close()
            self.lhp = None
            self.serial_port = None
            return False

        logger.info("串口打开成功")
        self.is_connected = True

        # 设置发送回调
        self.lhp.set_send_rs485_callback(self._rs485_send_callback)

        # 设置接收回调
        self.serial_port.set_read_callback(self._rs485_receive_callback)

        # 初始化LHandProLib为RS485模式
        logger.info("正在初始化 (RS485, node_id=%s)", node_id)
        try:
            self.lhp.initial_ex(LCN_RS485, node_id)
        except Exception as e:
            logger.exception(
                "LHandProLib RS485 初始化失败: port=%s, node_id=%s, error=%s",
                port_name,
                node_id,
                e,
            )
            self.disconnect()
            return False
        logger.info("RS485 初始化成功")

        # 执行通用初始化步骤
        return self._common_initialization(
            enable_motors,
            home_motors,
            home_wait_time,
            on_home_start=on_home_start,
        )

