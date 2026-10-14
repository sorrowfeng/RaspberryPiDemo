"""EtherCAT transport connect/disconnect helpers for LHandProController."""

import logging
import threading
import time

from ethercat_master import EthercatMaster
from lhandprolib_wrapper import LCN_ECAT, LHandProLibError

logger = logging.getLogger(__name__)


class EcatTransportMixin:
    """EtherCAT-specific callbacks, monitor thread, and connection setup."""

    def _ec_send_callback(self, data: bytes) -> bool:
        """EtherCAT 发送回调函数"""
        try:
            with self._ecat_callback_lock:
                if not self.is_connected:
                    return False
                ec_master = self.ec_master
                if not ec_master or not ec_master.running:
                    return False
                return ec_master.setOutputs(data, len(data))
        except Exception as e:
            logger.exception("EtherCAT 发送失败: %s", e)
        return False

    def _monitor_thread_func(self):
        """监控线程函数：刷新解析 TPDO 数据"""
        try:
            while not self.stop_flag.is_set() and self.is_connected:
                if self.ec_master:
                    input_size = self.ec_master.getInputSize()
                    inputs = self.ec_master.getInputs(input_size)
                    if inputs is not None and self.lhp:
                        self.lhp.set_tpdo_data_decode(inputs)
                time.sleep(0.01)  # 10ms
        except Exception as e:
            if self.stop_flag and not self.stop_flag.is_set():
                logger.exception("EtherCAT 接收监控线程异常: %s", e)

    def _connect_ecat(
        self,
        enable_motors,
        home_motors,
        home_wait_time,
        channel_index,
        auto_select,
        on_home_start=None,
        connect_retry_interval_seconds=0.0,
        connect_deadline_monotonic=None,
        non_interactive=False,
    ):
        """使用ECAT模式连接设备"""
        # 创建 EtherCAT 主站
        self.ec_master = self._ecat_cls()

        logger.info("正在使用EtherCAT通讯(100M)")

        # 扫描网口
        names = self.ec_master.scanNetworkInterfaces()
        logger.info("找到网口数量：%s", len(names))

        if len(names) == 0:
            logger.error("未找到可用于 EtherCAT 的网口")
            self.lhp.close()
            self.lhp = None
            return False

        # 选择网口
        if channel_index is None:
            if len(names) == 1:
                # 只有一个网口时自动选择
                logger.info("检测到单个网口，自动选择: %s", names[0])
                channel_index = 0
            elif auto_select or non_interactive:
                logger.info("自动选择网口: %s", names[0])
                channel_index = 0
            else:
                # 多个网口时让用户选择
                print(f"请选择对应网口 [0 - {len(names) - 1}]")
                print("可用网口列表:")
                for i, name in enumerate(names):
                    print(f"  [{i}] {name}")

                while True:
                    try:
                        user_input = input(">>> ")
                        if user_input.strip() == "":
                            print(f"使用默认选择: 0 ({names[0]})")
                            channel_index = 0
                            break

                        channel_index = int(user_input)
                        if 0 <= channel_index < len(names):
                            print(f"已选择: [{channel_index}] {names[channel_index]}")
                            break
                        else:
                            print(f"请输入 [0 - {len(names) - 1}]")
                    except ValueError:
                        print("请输入数字")
        else:
            if not (0 <= channel_index < len(names)):
                logger.error(
                    "EtherCAT 网口索引无效: channel_index=%s, interface_count=%s",
                    channel_index,
                    len(names),
                )
                self.lhp.close()
                self.lhp = None
                return False
            logger.info("使用指定网口: [%s] %s", channel_index, names[channel_index])

        # 初始化 EtherCAT
        if not self.ec_master.init(
            channel_index,
            names,
            discovery_retry_interval_seconds=connect_retry_interval_seconds,
            discovery_deadline_monotonic=connect_deadline_monotonic,
        ):
            logger.error(
                "EtherCAT 主站初始化失败: channel_index=%s, interface=%s",
                channel_index,
                names[channel_index],
            )
            self.lhp.close()
            self.lhp = None
            return False

        if connect_deadline_monotonic is not None:
            required_startup_seconds = (
                (1.0 if enable_motors else 0.0)
                + (home_wait_time if home_motors else 0.0)
                + self.ECAT_STARTUP_DEADLINE_MARGIN_SECONDS
            )
            remaining_seconds = connect_deadline_monotonic - time.monotonic()
            if remaining_seconds < required_startup_seconds:
                logger.warning(
                    "EtherCAT 从站发现时间过晚，剩余上电时间不足以安全完成使能和回零；"
                    "remaining=%.3fs, required=%.3fs, 本轮不启动运动",
                    remaining_seconds,
                    required_startup_seconds,
                )
                return False

        logger.info("EtherCAT 连接成功")
        self.is_connected = True

        if not self.ec_master.start():
            logger.error("EtherCAT 主站启动失败: interface=%s", names[channel_index])
            self.lhp.close()
            self.lhp = None
            return False

        # 启动后台 IO
        self.ec_master.run()

        # 设置回调
        self.lhp.set_send_rpdo_callback(self._ec_send_callback)

        # 启动监控线程
        self.stop_flag = threading.Event()
        self.monitor_thread = threading.Thread(
            target=self._monitor_thread_func,
            name="EtherCAT-Monitor",
            daemon=True,
        )
        self.monitor_thread.start()

        # 初始化 LHandProLib
        try:
            self.lhp.initial(LCN_ECAT)
        except LHandProLibError as e:
            logger.exception("LHandProLib EtherCAT 初始化失败: %s", e)
            self.disconnect()
            return False

        # 执行通用初始化步骤
        return self._common_initialization(
            enable_motors,
            home_motors,
            home_wait_time,
            on_home_start=on_home_start,
        )

