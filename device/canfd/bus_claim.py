"""跨进程 CANFD 总线占用登记，为 gs_usb 后端提供"扫描自动少一个"的行为。

gs_usb（pyusb）没有设备独占语义：`scan_adapters()` 始终列出全部适配器，而且
`CanFdBus.open()` 不 claim USB 接口，于是多个 main.py 会静默打开同一个适配器、
两路 CAN 流量互相干扰（表现为随机的 SDO 超时 / LER_COMM_RECV(7)）。

本模块用 `runtime/canfd_claims/<适配器标识>.claim` 做应用层占用登记：

- 占位文件用 `O_CREAT|O_EXCL` 原子创建，内容记录持有者 pid 与占用时间；
- 扫描时排除"被其它存活进程持有"的适配器，所以 `scan()` 返回值会随连接数递减；
- 连接成功后一直持有，`disconnect()` 释放；
- 进程被 SIGKILL 或掉电后占位文件仍在，但持有者 pid 已不存活，会被自动回收；
- 并发启动时用 `try_acquire()` 原子抢占，抢不到就顺延到下一个候选，不会静默共用。

只作用于 gs_usb 后端；socketcan 后端由内核驱动负责设备独占。
"""

import json
import logging
import os
import time

from device.canfd import canfd_lib
from app.runtime_control import RUNTIME_DIR, is_pid_running

logger = logging.getLogger(__name__)

CLAIM_DIR = os.path.join(RUNTIME_DIR, "canfd_claims")
CLAIM_SUFFIX = ".claim"

# O_CREAT|O_EXCL 建好文件到写入 pid 之间有个极短窗口，此时文件已存在但读不出 pid。
# 这种"刚创建"的占位必须当成已被占用，否则别的进程会把它当失效占位删掉并抢占。
# 超过该宽限期仍读不出 pid 的文件才按失效处理（回收异常残留）。
CLAIM_WRITE_GRACE_SECONDS = 2.0

# canfd_lib.CANFD(driver=...) 里代表 gs_usb 后端的取值
GSUSB_DRIVER_KEYS = ("gsusb", "gsusb-canfd", "gsusb_canfd")

_GsUsbBackend = getattr(canfd_lib, "_GsUsbCANFD", None)
if _GsUsbBackend is None:  # pragma: no cover - 仅当 device/canfd/canfd_lib.py 被换成其它版本
    raise RuntimeError(
        "device/canfd/canfd_lib.py 中没有 _GsUsbCANFD，bus_claim 依赖它实现跨进程总线占用登记；"
        "请对照 SDK 的 examples/CANFD_python/canfd_lib.py 重新同步该文件"
    )


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))


def adapter_identity(adapter) -> str:
    """适配器的稳定标识：优先序列号，否则用 USB bus/address。"""
    serial = (getattr(adapter, "serial", "") or "").strip()
    if serial:
        return "serial-" + _safe_name(serial)
    return "bus{0}-addr{1}".format(
        getattr(adapter, "bus", 0),
        getattr(adapter, "address", 0),
    )


def adapter_label(adapter) -> str:
    """用于日志的适配器描述，附带 bus/addr 便于现场定位。"""
    name = " ".join(
        part for part in (
            str(getattr(adapter, "manufacturer", "") or "").strip(),
            str(getattr(adapter, "product", "") or "").strip(),
        ) if part
    )
    name = name or "gs_usb adapter"
    serial = (getattr(adapter, "serial", "") or "").strip()
    return "{0} [serial={1} bus={2} addr={3}]".format(
        name,
        serial or "-",
        getattr(adapter, "bus", "?"),
        getattr(adapter, "address", "?"),
    )


class BusClaimRegistry:
    """基于占位文件的跨进程总线占用登记。"""

    def __init__(self, claim_dir: str = None, owner_pid: int = None):
        self.claim_dir = claim_dir or CLAIM_DIR
        self.pid = int(owner_pid if owner_pid is not None else os.getpid())

    # ---------------------------------------------------------------- internals
    def _claim_path(self, adapter) -> str:
        return os.path.join(self.claim_dir, adapter_identity(adapter) + CLAIM_SUFFIX)

    @staticmethod
    def _read_owner(path: str):
        try:
            with open(path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except (OSError, ValueError):
            return None
        try:
            return int(data.get("pid"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _remove(path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("删除 CANFD 总线占位文件失败: path=%s, error=%s", path, exc)

    def holder_pid(self, adapter):
        """返回当前持有者 pid；空闲返回 None，并顺带回收失效占位。"""
        path = self._claim_path(adapter)
        owner = self._read_owner(path)
        if owner is None:
            if not os.path.exists(path):
                return None  # 不存在即空闲
            if self._recently_created(path):
                return -1  # 创建者正在写入 pid，视为占用
            logger.info(
                "回收无法解析的 CANFD 总线占位: adapter=%s", adapter_identity(adapter)
            )
            self._remove(path)
            return None
        if owner == self.pid or is_pid_running(owner):
            return owner
        logger.info(
            "回收失效的 CANFD 总线占位: adapter=%s, 原持有者 pid=%s 已退出",
            adapter_identity(adapter),
            owner,
        )
        self._remove(path)
        return None

    @staticmethod
    def _recently_created(path: str, grace_seconds: float = CLAIM_WRITE_GRACE_SECONDS) -> bool:
        """占位文件是否刚被创建（即创建者还没来得及写入 pid）。"""
        try:
            return (time.time() - os.path.getmtime(path)) < grace_seconds
        except OSError:
            return False

    # ------------------------------------------------------------------- public
    def is_held_by_other(self, adapter) -> bool:
        owner = self.holder_pid(adapter)
        return owner is not None and owner != self.pid

    def partition(self, adapters):
        """返回 (可用列表, 被其它进程占用列表)。"""
        available, taken = [], []
        for adapter in adapters:
            (taken if self.is_held_by_other(adapter) else available).append(adapter)
        return available, taken

    def try_acquire(self, adapter) -> bool:
        """原子抢占；抢不到返回 False。"""
        os.makedirs(self.claim_dir, exist_ok=True)
        path = self._claim_path(adapter)
        payload = json.dumps(
            {
                "pid": self.pid,
                "claimed_at": time.time(),
                "adapter": adapter_identity(adapter),
            },
            ensure_ascii=False,
        ) + "\n"

        for _ in range(2):
            try:
                handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                owner = self._read_owner(path)
                if owner is None:
                    if not os.path.exists(path):
                        continue  # 对方刚释放，立刻重试
                    if self._recently_created(path):
                        return False  # 对方刚创建、尚未写入 pid，不可抢占
                elif owner != self.pid and is_pid_running(owner):
                    return False  # 被存活的其它进程持有
                logger.info(
                    "回收 CANFD 总线占位后重试: adapter=%s, owner=%s, self_pid=%s, "
                    "刚创建=%s",
                    adapter_identity(adapter),
                    owner,
                    self.pid,
                    self._recently_created(path),
                )
                self._remove(path)  # 失效占位或本进程残留，回收后重试
                continue
            except OSError as exc:
                logger.warning("创建 CANFD 总线占位文件失败: path=%s, error=%s", path, exc)
                return False

            try:
                os.write(handle, payload.encode("utf-8"))
            except OSError as exc:
                logger.warning("写入 CANFD 总线占位文件失败: path=%s, error=%s", path, exc)
                self._remove(path)
                return False
            finally:
                os.close(handle)
            return True
        return False

    def release(self, adapter) -> None:
        path = self._claim_path(adapter)
        owner = self._read_owner(path)
        if owner is not None and owner != self.pid:
            logger.warning(
                "CANFD 总线占位已被其它进程接管，不删除: adapter=%s, owner=%s",
                adapter_identity(adapter),
                owner,
            )
            return
        self._remove(path)


class ClaimAwareGsUsbCANFD(_GsUsbBackend):
    """gs_usb 后端 + 跨进程占用登记。

    依赖 `canfd_lib._GsUsbCANFD` 的以下内部结构（来自 SDK 20261014 的
    `examples/CANFD_python/canfd_lib.py`，本仓库内已 vendored）：

    - `_scan_adapters()`：scan() 与 connect() 共用的唯一枚举入口；
    - `connect(device_index=...)` 按 `self._adapters[device_index]` 取目标；
    - `_is_connected` / `_bus`。

    通过把 `_scan_adapters()` 收敛成"只返回候选适配器"，SDK 原有的 connect
    实现（BusConfig、采样点、drop_echo、错误包装）全部原样复用。
    """

    # 供调用方判断"总线由跨进程占用登记分配，device_index 不表示物理位置"
    claim_aware = True

    def __init__(self, registry: BusClaimRegistry = None):
        super().__init__()
        self._registry = registry or BusClaimRegistry()
        self._pinned = None
        self._claimed_adapter = None
        self.last_scan = {"total": 0, "available": 0, "taken": 0}

    def _scan_adapters(self):
        # super().connect() 期间只暴露已选定的那一个适配器
        if self._pinned is not None:
            return [self._pinned]

        adapters = super()._scan_adapters()
        available, taken = self._registry.partition(adapters)
        self.last_scan = {
            "total": len(adapters),
            "available": len(available),
            "taken": len(taken),
        }
        if taken:
            logger.info(
                "gs_usb 适配器: 共 %s 个，其中 %s 个已被其它 main.py 占用，可用 %s 个：%s",
                len(adapters),
                len(taken),
                len(available),
                ", ".join(adapter_identity(a) for a in taken),
            )
            for adapter in taken:
                logger.debug(
                    "已被占用: %s (pid=%s)",
                    adapter_label(adapter),
                    self._registry.holder_pid(adapter),
                )
        return available

    def connect(
        self,
        device_index: int = 0,
        channel_index: int = 0,
        nom_baudrate: int = 1000000,
        dat_baudrate: int = 5000000,
        nom_sampling: int = 0,
        dat_sampling: int = 0,
    ) -> bool:
        if self._is_connected:
            self.disconnect()

        candidates = self._scan_adapters()
        if not candidates:
            if self.last_scan.get("total"):
                raise canfd_lib.CANFDException(
                    "没有空闲的 gs_usb 适配器：共 {0} 个适配器，全部已被其它 main.py 占用".format(
                        self.last_scan["total"]
                    )
                )
            raise canfd_lib.CANFDException(
                "没有发现 gs_usb 适配器（检查适配器是否插好、pyusb/libusb 是否就绪、"
                "内核 gs_usb 是否仍绑定着适配器）"
            )

        start = 0 if device_index is None else max(0, int(device_index))
        if start >= len(candidates):
            # 占用登记才是权威分配者：device_index 只表示"优先取第几个空闲总线"，
            # 超过当前空闲数时退回第一条空闲总线（多实例启动时索引必然越界）。
            logger.warning(
                "请求 device_index=%s 超出当前 %s 条空闲总线，改为取第一条空闲总线"
                "（共 %s 个适配器，%s 个已被其它 main.py 占用）",
                device_index,
                len(candidates),
                self.last_scan.get("total", len(candidates)),
                self.last_scan.get("taken", 0),
            )
            start = 0

        for target in candidates[start:]:
            if not self._registry.try_acquire(target):
                logger.warning(
                    "并发抢占失败，顺延下一个候选: %s", adapter_label(target)
                )
                continue

            self._pinned = target
            try:
                connected = super().connect(
                    device_index=0,
                    channel_index=channel_index,
                    nom_baudrate=nom_baudrate,
                    dat_baudrate=dat_baudrate,
                    nom_sampling=nom_sampling,
                    dat_sampling=dat_sampling,
                )
            except Exception:
                self._registry.release(target)
                raise
            finally:
                self._pinned = None

            if connected:
                self._claimed_adapter = target
                logger.info("已占用 gs_usb 总线: %s", adapter_label(target))
                return True

            logger.warning("连接失败，释放占用并尝试下一个候选: %s", adapter_label(target))
            self._registry.release(target)

        raise canfd_lib.CANFDException(
            "没有空闲的 gs_usb 适配器：{0} 个候选全部连接失败".format(len(candidates))
        )

    def disconnect(self) -> bool:
        result = super().disconnect()
        if self._claimed_adapter is not None:
            self._registry.release(self._claimed_adapter)
            self._claimed_adapter = None
        return result


def create_canfd(driver=None):
    """创建 CANFD 实例；gs_usb 后端会带上跨进程总线占用登记。

    `driver=None`（运行期自动择优）时维持 SDK 行为，不做包装——自动择优可能落到
    socketcan 后端，该路径由内核驱动负责独占。需要多实例保护时应显式固定
    `canfd_driver: "gsusb"`（preset 默认值即是）。
    """
    key = driver
    if key is None:
        key = os.environ.get("LHANDPRO_CANFD_DRIVER") or None
    if key is not None and str(key).strip().lower() in GSUSB_DRIVER_KEYS:
        return ClaimAwareGsUsbCANFD()
    return canfd_lib.CANFD(driver=driver)
