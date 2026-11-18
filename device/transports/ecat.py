"""EtherCAT transport connect/disconnect helpers for LHandProController."""

import logging
import threading
import time

from device.ethercat_master import EthercatMaster
from device.lhandprolib_wrapper import LCN_ECAT, LHandProLibError

logger = logging.getLogger(__name__)


class EcatTransportMixin:
    """EtherCAT-specific callbacks, monitor thread, and connection setup."""

    ECAT_STARTUP_DEADLINE_MARGIN_SECONDS = 0.5

    def _ec_send_callback(self, data: bytes) -> bool:
        """EtherCAT 发送回调：只写当前实例绑定的从站。"""
        try:
            with self._ecat_callback_lock:
                if not self.is_connected:
                    return False
                ec_master = self.ec_master
                if not ec_master or not ec_master.running:
                    return False
                set_slave_outputs = getattr(ec_master, "setSlaveOutputs", None)
                if set_slave_outputs is not None:
                    return bool(
                        set_slave_outputs(self.ecat_slave_id, data, len(data))
                    )
                # 兼容旧主站实现（仅单从站聚合缓冲）
                return ec_master.setOutputs(data, len(data))
        except Exception as e:
            logger.exception("EtherCAT 发送失败: %s", e)
        return False

    def _ecat_sdo_callback(self, index, subindex, is_write, value):
        """SDK 的 CoE SDO 请求 → 当前实例绑定的从站。

        写：返回 bool；读：返回 32 位值，失败返回 None。
        """
        ec_master = self.ec_master
        if not ec_master or not self.is_connected:
            return False if is_write else None
        if is_write:
            return bool(
                ec_master.sdoWrite(
                    index,
                    subindex,
                    value,
                    self.ecat_slave_id,
                )
            )
        return ec_master.sdoRead(index, subindex, self.ecat_slave_id)

    def _monitor_thread_func(self):
        """监控线程：只刷新当前实例绑定从站的 TPDO。"""
        try:
            while not self.stop_flag.is_set() and self.is_connected:
                ec_master = self.ec_master
                if ec_master:
                    get_slave_input_size = getattr(
                        ec_master, "getSlaveInputSize", None
                    )
                    get_slave_inputs = getattr(ec_master, "getSlaveInputs", None)
                    if get_slave_input_size is not None and get_slave_inputs is not None:
                        input_size = get_slave_input_size(self.ecat_slave_id)
                        inputs = get_slave_inputs(self.ecat_slave_id, input_size)
                    else:
                        input_size = ec_master.getInputSize()
                        inputs = ec_master.getInputs(input_size)
                    if inputs is not None and self.lhp:
                        self.lhp.set_tpdo_data_decode(inputs)
                time.sleep(0.01)  # 10ms
        except Exception as e:
            if self.stop_flag and not self.stop_flag.is_set():
                logger.exception("EtherCAT 接收监控线程异常: %s", e)

    def _select_ecat_channel(self, names, channel_index, auto_select, non_interactive):
        if channel_index is None:
            if len(names) == 1:
                logger.info("检测到单个网口，自动选择: %s", names[0])
                return 0
            if auto_select or non_interactive:
                logger.info("自动选择网口: %s", names[0])
                return 0

            print(f"请选择对应网口 [0 - {len(names) - 1}]")
            print("可用网口列表:")
            for i, name in enumerate(names):
                print(f"  [{i}] {name}")
            while True:
                try:
                    user_input = input(">>> ")
                    if user_input.strip() == "":
                        print(f"使用默认选择: 0 ({names[0]})")
                        return 0
                    index = int(user_input)
                    if 0 <= index < len(names):
                        print(f"已选择: [{index}] {names[index]}")
                        return index
                    print(f"请输入 [0 - {len(names) - 1}]")
                except ValueError:
                    print("请输入数字")

        if not (0 <= channel_index < len(names)):
            logger.error(
                "EtherCAT 网口索引无效: channel_index=%s, interface_count=%s",
                channel_index,
                len(names),
            )
            return None
        logger.info("使用指定网口: [%s] %s", channel_index, names[channel_index])
        return channel_index

    def _init_ecat_hand(
        self,
        *,
        enable_motors,
        home_motors,
        home_wait_time,
        on_home_start,
        connect_deadline_monotonic,
    ) -> bool:
        """在已初始化的主站上完成当前手的回调、监控和 SDK 初始化。"""
        ec_master = self.ec_master
        if ec_master is None:
            return False

        get_slave_count = getattr(ec_master, "getSlaveCount", None)
        if get_slave_count is not None:
            slave_count = int(get_slave_count())
        else:
            slave_count = len(getattr(ec_master, "slaves", []) or [])

        if slave_count <= 0:
            logger.error("EtherCAT 未发现任何从站")
            return False

        slave_id = self.ecat_slave_id
        if slave_id is None:
            slave_id = 1
        if not (1 <= int(slave_id) <= slave_count):
            logger.error(
                "EtherCAT 从站索引无效: slave_id=%s, slave_count=%s",
                slave_id,
                slave_count,
            )
            return False
        self.ecat_slave_id = int(slave_id)

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

        is_connected = getattr(ec_master, "isConnected", None)
        if is_connected is not None and not is_connected():
            logger.error("EtherCAT 主站未处于连接状态")
            return False

        slave_info = None
        get_slave_info_list = getattr(ec_master, "getSlaveInfoList", None)
        if get_slave_info_list is not None:
            for item in get_slave_info_list():
                if int(item.get("index", 0)) == self.ecat_slave_id:
                    slave_info = item
                    break

        logger.info(
            "EtherCAT 连接成功: slave_id=%s, name=%s",
            self.ecat_slave_id,
            (slave_info or {}).get("name", "-"),
        )
        self.is_connected = True

        # 发送回调只路由到本实例的从站。
        self.lhp.set_send_rpdo_callback(self._ec_send_callback)

        # SDO（CoE 邮箱）：每个实例必须绑定自己的 slave_id，initial() 的
        # 手型/左右手/固件/SN 自识别和 SDO 参数接口才能命中正确从站。
        set_sdo_callback = getattr(self.lhp, "set_ecat_sdo_callback", None)
        if set_sdo_callback is not None:
            set_sdo_callback(self._ecat_sdo_callback)
        else:
            logger.warning("当前 SDK 封装不支持 EtherCAT SDO 回调，跳过自识别")

        # 启动当前手的 TPDO 监控线程。
        self.stop_flag = threading.Event()
        self.monitor_thread = threading.Thread(
            target=self._monitor_thread_func,
            name=f"EtherCAT-Monitor-{self.ecat_slave_id}",
            daemon=True,
        )
        self.monitor_thread.start()

        try:
            self.lhp.initial(LCN_ECAT)
        except LHandProLibError as e:
            logger.exception("LHandProLib EtherCAT 初始化失败: %s", e)
            self.disconnect()
            return False

        return self._common_initialization(
            enable_motors,
            home_motors,
            home_wait_time,
            on_home_start=on_home_start,
        )

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
        """使用 ECAT 模式连接设备。

        如果实例带有共享主站（多手模式），复用主站并只初始化本手的从站；
        否则创建并独占一个主站，默认选择 slave_id=1。
        """
        shared_master = getattr(self, "_shared_ec_master", None)
        if shared_master is not None:
            self.ec_master = shared_master
            self._owns_ec_master = False
            logger.info(
                "复用共享 EtherCAT 主站，初始化 slave_id=%s",
                self.ecat_slave_id if self.ecat_slave_id is not None else 1,
            )
            return self._init_ecat_hand(
                enable_motors=enable_motors,
                home_motors=home_motors,
                home_wait_time=home_wait_time,
                on_home_start=on_home_start,
                connect_deadline_monotonic=connect_deadline_monotonic,
            )

        # 创建独占的 EtherCAT 主站
        self.ec_master = self._ecat_cls()
        self._owns_ec_master = True

        logger.info("正在使用EtherCAT通讯(100M)")

        names = self.ec_master.scanNetworkInterfaces()
        logger.info("找到网口数量：%s", len(names))
        if len(names) == 0:
            logger.error("未找到可用于 EtherCAT 的网口")
            self.lhp.close()
            self.lhp = None
            return False

        selected_channel = self._select_ecat_channel(
            names, channel_index, auto_select, non_interactive
        )
        if selected_channel is None:
            self.lhp.close()
            self.lhp = None
            return False

        if not self.ec_master.init(
            selected_channel,
            names,
            discovery_retry_interval_seconds=connect_retry_interval_seconds,
            discovery_deadline_monotonic=connect_deadline_monotonic,
        ):
            logger.error(
                "EtherCAT 主站初始化失败: channel_index=%s, interface=%s",
                selected_channel,
                names[selected_channel],
            )
            self.lhp.close()
            self.lhp = None
            return False

        if not self.ec_master.start():
            logger.error(
                "EtherCAT 主站启动失败: interface=%s", names[selected_channel]
            )
            self.lhp.close()
            self.lhp = None
            return False

        # 启动后台 IO
        self.ec_master.run()

        return self._init_ecat_hand(
            enable_motors=enable_motors,
            home_motors=home_motors,
            home_wait_time=home_wait_time,
            on_home_start=on_home_start,
            connect_deadline_monotonic=connect_deadline_monotonic,
        )
