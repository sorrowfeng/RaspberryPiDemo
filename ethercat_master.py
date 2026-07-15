"""
EtherCAT 主站封装库
"""

import logging
import threading
import time
import pysoem
from typing import List, Optional

logger = logging.getLogger(__name__)

class EthercatMaster:
    """EtherCAT 主站封装类"""

    IO_THREAD_JOIN_TIMEOUT = 2.0

    def __init__(self):
        self.master = pysoem.Master()
        self.slaves = []
        self.input_size = 0
        self.output_size = 0
        self.running = False
        self.thread = None
        self.ifname = None
        self._master_opened = False

    def scanNetworkInterfaces(self) -> List[str]:
        """扫描可用网口，过滤虚拟/无线/回环接口，返回物理网卡设备名列表"""
        adapters = pysoem.find_adapters()
        if not adapters:
            logger.warning("未检测到任何可用网口；请检查网卡权限、驱动或 Npcap")
            return []

        # 过滤名单：这些名字中包含的关键词将被排除
        exclude_keywords = [
            'lo',        # Linux 回环接口
            'docker',    # Docker虚拟网卡
            'veth',      # 虚拟以太网设备
            'br-',       # 网桥接口
            'virbr',     # 虚拟网桥
            'vmnet',     # VMware虚拟网卡
            'tap',       # TAP虚拟设备
            'tun',       # TUN虚拟设备
            'wlan',      # 无线网卡
            'wlp',       # 无线网卡(新命名)
            'wlx',       # 无线网卡
            'wifi',      # WiFi接口
            'wwan',      # 无线广域网
            'bluetooth', # 蓝牙
            'vboxnet',   # VirtualBox虚拟网卡
            'wintun',    # Windows TUN设备
            'p2p',       # P2P连接
            'loopback',  # 回环(Windows)
            'teredo',    # Teredo隧道
            'isatap'     # ISATAP隧道
        ]

        print("🔍 检测到以下物理网卡：")
        filtered_adapters = []
        
        for adapter in adapters:
            # 确保name是字符串并转换为小写便于比较
            if isinstance(adapter.name, bytes):
                name = adapter.name.decode('utf-8', errors='ignore').lower()
            else:
                name = str(adapter.name).lower()
            
            # 检查是否需要排除
            should_exclude = any(keyword in name for keyword in exclude_keywords)
            
            if should_exclude:
                continue  # 跳过这个接口
            
            # 获取描述用于显示
            if isinstance(adapter.desc, bytes):
                desc = adapter.desc.decode('utf-8', errors='ignore')
            else:
                desc = str(adapter.desc)
            
            print(f"  【{len(filtered_adapters)}】{desc}")
            filtered_adapters.append(adapter)
        
        # 如果所有接口都被过滤掉了
        if not filtered_adapters:
            logger.warning("未找到可用的物理网卡")
            # 可选：显示被过滤的接口用于调试
            print("  被过滤的接口:")
            for adapter in adapters:
                if isinstance(adapter.name, bytes):
                    name = adapter.name.decode('utf-8', errors='ignore')
                else:
                    name = str(adapter.name)
                print(f"    - {adapter.desc} ({name})")
        
        return [adapter.name if isinstance(adapter.name, str) else 
                adapter.name.decode('utf-8', errors='ignore') 
                for adapter in filtered_adapters]

    def _print_slave_states(self):
        """打印从站状态和错误码"""
        self.master.read_state()
        for i, slave in enumerate(self.slaves):
            state_str = {
                pysoem.INIT_STATE: "INIT",
                pysoem.PREOP_STATE: "PREOP",
                pysoem.SAFEOP_STATE: "SAFEOP",
                pysoem.OP_STATE: "OP"
            }.get(slave.state, f"UNKNOWN({slave.state})")
            logger.error(
                "EtherCAT 从站状态异常: slave=%s, name=%s, state=%s, "
                "al_status=%s, al_message=%s",
                i,
                slave.name,
                state_str,
                hex(slave.al_status),
                pysoem.al_status_code_to_string(slave.al_status),
            )

    def init(self, channel_index: int, ifaces: List[str]) -> bool:
        """初始化 EtherCAT 主站和从站（更贴近SOEM流程）"""
        initialized = False
        try:
            self.ifname = ifaces[channel_index]
            print(f"🔌 正在初始化 EtherCAT 主站，使用网口: {self.ifname}")
            self.master.open(self.ifname)
            self._master_opened = True

            # 初始化从站配置
            if self.master.config_init() <= 0:
                logger.error(
                    "未发现任何 EtherCAT 从站设备: interface=%s",
                    self.ifname,
                )
                return False

            self.slaves = self.master.slaves
            print(f"✅ 发现 {len(self.slaves)} 个从站设备")
            for i, slave in enumerate(self.slaves):
                print(f"  Slave {i}: {slave.name} (Vendor: {hex(slave.man)}, Product: {hex(slave.id)})")

            # 映射过程数据
            self.master.config_map()
            print("✅ PDO 缓冲区映射完成")

            # 配置分布式时钟（DC）
            self.master.config_dc()
            print("✅ 分布式时钟(DC)配置完成")

            # 等待进入 SAFEOP 状态
            print("⏳ 等待从站进入 SAFEOP 状态...")
            if self.master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE:
                self._print_slave_states()
                logger.error("EtherCAT 未能进入 SAFEOP_STATE: interface=%s", self.ifname)
                return False

            # 先发一次 processdata
            self.master.send_processdata()
            self.master.receive_processdata(1000)

            # 进入 OP 状态
            print("🚀 正在切换到 OP 状态...")
            self.master.state = pysoem.OP_STATE
            self.master.write_state()

            # 多次 processdata 检查状态
            for _ in range(10):
                self.master.send_processdata()
                self.master.receive_processdata(1000)
                if self.master.state_check(pysoem.OP_STATE, 5000) == pysoem.OP_STATE:
                    break
                time.sleep(0.05)

            if self.master.state_check(pysoem.OP_STATE, 5000) != pysoem.OP_STATE:
                self._print_slave_states()
                logger.error("EtherCAT 未能进入 OP_STATE: interface=%s", self.ifname)
                return False

            print("✅ 成功进入 OP 状态")

            # 获取输入输出缓冲区大小
            self.input_size = sum(len(slave.input) for slave in self.slaves)
            self.output_size = sum(len(slave.output) for slave in self.slaves)

            print(f"📊 输入总长度: {self.input_size} 字节")
            print(f"📊 输出总长度: {self.output_size} 字节")

            # 初始化输出缓冲区
            for slave in self.slaves:
                slave.output = bytes(len(slave.output))

            initialized = True
            return True

        except Exception as e:
            logger.exception(
                "EtherCAT 初始化失败: interface=%s, error=%s",
                self.ifname,
                e,
            )
            return False
        finally:
            if not initialized:
                self.stop()

    def start(self) -> bool:
        """已包含在 init 中，可留空"""
        return True

    def stop(self):
        """停止 PDO 线程并关闭主站，可安全重复调用。"""
        self.running = False

        io_thread = self.thread
        if io_thread and io_thread.is_alive():
            if io_thread is threading.current_thread():
                raise RuntimeError("不能从 EtherCAT PDO 线程内部关闭主站")
            io_thread.join(timeout=self.IO_THREAD_JOIN_TIMEOUT)
            if io_thread.is_alive():
                raise RuntimeError("EtherCAT PDO 线程未在超时时间内退出")
        self.thread = None

        if self.master and self._master_opened:
            try:
                self.master.state = pysoem.INIT_STATE
                self.master.write_state()
                time.sleep(0.1)
            except Exception as e:
                logger.warning(
                    "EtherCAT 主站切换到 INIT 状态失败: interface=%s, error=%s",
                    self.ifname,
                    e,
                    exc_info=True,
                )

            try:
                self.master.close()
            except Exception as e:
                raise RuntimeError(f"EtherCAT 主站关闭失败: {e}") from e
            self._master_opened = False

        self.slaves = []
        self.input_size = 0
        self.output_size = 0
        self.ifname = None

    def run(self):
        """启动后台 IO 线程"""
        if self.running and self.thread and self.thread.is_alive():
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._process_io,
            name="EtherCAT-PDO",
            daemon=True,
        )
        self.thread.start()

    def _process_io(self):
        """IO 处理循环"""
        try:
            while self.running:
                self.master.send_processdata()
                self.master.receive_processdata(1000)  # 1ms 超时
                time.sleep(0.001)  # 1ms
        except Exception as e:
            if self.running:
                logger.exception("EtherCAT PDO 通讯线程异常: %s", e)
        finally:
            self.running = False

    def setOutputs(self, data: bytes, size: int) -> bool:
        """设置输出数据"""
        if len(data) != self.output_size:
            logger.error(
                "EtherCAT 输出数据长度不匹配: expected=%s, actual=%s",
                self.output_size,
                len(data),
            )
            return False

        offset = 0
        for slave in self.slaves:
            slave_out_len = len(slave.output)
            if offset + slave_out_len > len(data):
                logger.error(
                    "EtherCAT 输出数据偏移越界: slave=%s, offset=%s, slave_size=%s, data_size=%s",
                    slave.name,
                    offset,
                    slave_out_len,
                    len(data),
                )
                return False
            slave.output = data[offset:offset + slave_out_len]
            offset += slave_out_len

        return True

    def getInputs(self, size: int) -> Optional[bytes]:
        """获取输入数据"""
        if size != self.input_size:
            logger.error(
                "EtherCAT 输入数据长度不匹配: expected=%s, actual=%s",
                self.input_size,
                size,
            )
            return None

        inputs = bytearray()
        for slave in self.slaves:
            slave_in_len = len(slave.input)
            inputs.extend(slave.input[:slave_in_len])
        return bytes(inputs)

    def getInputSize(self) -> int:
        return self.input_size

    def getOutputSize(self) -> int:
        return self.output_size
