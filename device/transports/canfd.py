"""CANFD transport connect/disconnect helpers for LHandProController."""

import logging

from device.canfd.bus_claim import create_canfd
from app.config import CANFD_DRIVER, DEVICE_CONFIG
from device.lhandprolib_wrapper import LCN_CANFD

logger = logging.getLogger(__name__)


class CanfdTransportMixin:
    """CANFD-specific callbacks and connection setup."""

    def _canfd_send_callback(self, msg_id: int, data: bytes) -> bool:
        """CANFD 发送回调函数"""
        if self.canfd and self.is_connected:
            try:
                # 使用传入的msg_id作为CANFD消息ID
                return self.canfd.send(msg_id, data)
            except Exception as e:
                logger.exception("CANFD 发送失败: msg_id=%s, error=%s", msg_id, e)
        return False

    def _canfd_receive_callback(self, msg):
        """CANFD 接收回调函数"""
        if self.lhp and self.is_connected:
            # 处理接收到的CANFD消息
            self.lhp.set_canfd_data_decode(msg["id"], msg["data"])

    def _connect_canfd(
        self,
        enable_motors,
        home_motors,
        home_wait_time,
        canfd_nom_baudrate,
        canfd_dat_baudrate,
        device_index,
        auto_select,
        on_home_start=None,
        non_interactive=False,
    ):
        """使用CANFD模式连接设备"""
        # 初始化CANFD。driver 由 preset 的 features.canfd_driver 决定；
        # "gsusb" 走 device/canfd/bus_claim.create_canfd()，带上跨进程总线占用登记，
        # 使 scan() 只返回空闲总线，多个 main.py 各自拿到不同总线。
        logger.info("正在使用CANFD通讯 (后端: %s)", CANFD_DRIVER or "auto")
        self.canfd = create_canfd(CANFD_DRIVER)

        # 扫描CANFD设备
        device_count = self.canfd.scan()
        scan_info = getattr(self.canfd, "last_scan", None) or {}
        if scan_info.get("taken"):
            logger.info(
                "找到可用CANFD设备数量：%s（共 %s 个，%s 个已被其它 main.py 占用）",
                device_count,
                scan_info.get("total"),
                scan_info.get("taken"),
            )
        else:
            logger.info("找到CANFD设备数量：%s", device_count)

        if device_count == 0:
            if scan_info.get("total"):
                logger.error(
                    "没有空闲 CANFD 设备: 共 %s 个适配器，全部已被其它 main.py 占用",
                    scan_info["total"],
                )
            else:
                logger.error("未找到 CANFD 设备")
            if (CANFD_DRIVER or "gsusb") == "gsusb":
                logger.error(
                    "gsusb 后端没有可用适配器：请运行 "
                    "sudo python3 tools/setup_canfd_mode.py 检查 pyusb/libusb 是否就绪、"
                    "内核 gs_usb 是否仍绑定着适配器（内核驱动与 pyusb 互斥）、"
                    "udev 权限是否生效，以及其它 main.py 是否已把总线全部占用"
                )
            self.lhp.close()
            self.lhp = None
            self.canfd = None
            return False

        # 处理设备索引
        if getattr(self.canfd, "claim_aware", False) and device_index is not None:
            # 多实例由 runtime/canfd_claims/ 的占用登记分配总线，device_index 不再表示
            # 物理位置（USB 枚举顺序本身不稳定），统一改成"取第一条空闲总线"。
            logger.info(
                "gs_usb 总线由跨进程占用登记分配，忽略 device_index=%s；"
                "各 main.py 自动取第一条空闲总线",
                device_index,
            )
            device_index = 0

        if device_index is None:
            if device_count == 1:
                # 只有一个设备时自动选择
                logger.info("检测到单个设备，自动选择设备索引: 0")
                device_index = 0
            elif auto_select or non_interactive:
                logger.info("自动选择设备索引: 0 (non_interactive=%s)", non_interactive)
                device_index = 0
            else:
                # 多个设备时让用户选择
                print(f"请选择对应设备 [0 - {device_count - 1}]")
                while True:
                    try:
                        user_input = input(">>> ")
                        if user_input.strip() == "":
                            print(f"使用默认选择: 0")
                            device_index = 0
                            break

                        device_index = int(user_input)
                        if 0 <= device_index < device_count:
                            print(f"已选择设备索引: {device_index}")
                            break
                        else:
                            print(f"请输入 [0 - {device_count - 1}]")
                    except ValueError:
                        print("请输入数字")
        else:
            if not (0 <= device_index < device_count):
                logger.error(
                    "CANFD 设备索引无效: device_index=%s, device_count=%s",
                    device_index,
                    device_count,
                )
                self.lhp.close()
                self.lhp = None
                self.canfd = None
                return False
            logger.info("使用指定设备索引: %s", device_index)

        # 连接CANFD设备
        logger.info(
            "正在连接CANFD设备，标称波特率: %sbps，数据波特率: %sbps",
            canfd_nom_baudrate,
            canfd_dat_baudrate,
        )
        if not self.canfd.connect(
            device_index=device_index,
            channel_index=0,
            nom_baudrate=canfd_nom_baudrate,
            dat_baudrate=canfd_dat_baudrate,
        ):
            logger.error(
                "CANFD 设备连接失败: device_index=%s, nominal_baudrate=%s, data_baudrate=%s",
                device_index,
                canfd_nom_baudrate,
                canfd_dat_baudrate,
            )
            self.lhp.close()
            self.lhp = None
            self.canfd = None
            return False

        logger.info("CANFD设备连接成功")
        self.is_connected = True

        # 设置CANFD接收回调
        self.canfd.set_receive_callback(self._canfd_receive_callback)

        # 设置发送回调
        self.lhp.set_send_canfd_callback(self._canfd_send_callback)

        # 初始化LHandProLib为CANFD模式
        self.lhp.initial_ex(LCN_CANFD, DEVICE_CONFIG["canfd_node_id"])

        # 执行通用初始化步骤
        return self._common_initialization(
            enable_motors,
            home_motors,
            home_wait_time,
            on_home_start=on_home_start,
        )
