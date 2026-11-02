# RaspberryPiDemo Agent Notes

本文件记录项目维护、部署和现场排查要点，供后续 agent 或维护人员快速接手。

## 项目概览

这是 LHandPro 在 Raspberry Pi 场景下的 Python 控制示例，支持：

- CANFD
- EtherCAT / ECAT
- RS485
- GPIO 触发
- UDP 手套输入
- 动作循环、抓握动作
- 主电源通断循环测试

项目当前不是标准 Python package，而是顶层脚本加若干业务目录。

## 主要入口

- `main.py`
  - 单个控制进程入口。
  - 解析通信模式、设备索引、GPIO 开关。
  - 创建 `motion_system.MotionController`。

- `launch.py`
  - 统一启动入口。
  - 根据配置启动一个或多个 `main.py`。
  - 当配置启用主电源通断测试时，转交给 `main_power_cycle.py` 管理生命周期。

- `main_power_cycle.py`
  - 主电源通断测试入口。
  - 先执行 USB-to-RS485 模式配置脚本；该脚本会尝试加载 Exar `xr_usb_serial_common` 驱动并等待 `/dev/ttyXRUSB*` 出现。
  - 打开主电源控制串口。
  - 启动长驻 `main.py` 子进程后不按轮次退出；每轮通过控制命令让子进程连接、回零、开始运动、停止运动并断开设备。

- `main_runtime_control.py`
  - `main.py` 长驻进程控制接口。
  - 通过 `runtime/` 下的 PID、命令、响应 JSON 文件实现外部命令调用。

- `main_lifecycle.py`
  - `main.py` 生命周期共享模块。
  - 被 `launch.py` 和 `main_power_cycle.py` 共同使用。
  - 负责构造 Python 命令、RS485 前置准备、启动/停止多个 `main.py` 进程。

## 配置体系

配置入口是 `config.py`，运行时代码应优先从这里读取配置，不要直接读取具体 preset。

配置来源：

- `active_config.py`
  - 指定当前激活的 preset。
  - 可提供现场覆盖参数。

- `configs/config_*.py`
  - preset 元数据。
  - 描述设备类型、通信方式、启动数量、动作序列、功能开关等。

- `sequences/*.py`
  - 动作序列。
  - 统一描述 `positions`、`velocities`、`currents`、`interval`。

主电源通断测试 preset：

- `configs.config_DH116S_CANFD_power_cycle_test`
- `configs.config_DH116S_ECAT_power_cycle_test`
- `configs.config_DH116S_RS485_power_cycle_test`

其中 ECAT preset 的 `default_launch_count=1`，单个长驻 `main.py` 会自动选择唯一可用网口；CANFD 和 RS485 preset 的 `default_launch_count=4`。

这三个 preset 都启用：

```python
"enable_main_power_cycle": True
```

相关参数：

- `main_power_cycle_start_delay`
- `main_power_cycle_on_seconds`（从上电指令到断电指令的目标时长）
- `main_power_cycle_disconnect_lead_seconds`（在目标断电时刻前，预留给停止运动和断开通信的时间）
- `main_power_cycle_force_off_at_deadline`（断开未完成时，是否仍在目标时刻强制物理断电）
- `main_power_cycle_connect_retry_interval`（ECAT 同一上电窗口内扫描不到从站时的重试间隔，`0` 表示禁用）
- `main_power_cycle_off_seconds`（从断电指令到下一次上电指令的目标时长）
- `main_power_cycle_baud_rate`
- `main_power_cycle_port`
- `main_power_cycle_rs485_ports`（仅 RS485 设备通讯，可选的固定四串口列表）
- `main_power_cycle_stop_timeout`
- `main_power_cycle_control_timeout`

当前 ECAT 主电源通断测试时间：

- 上电后等待 `main_power_cycle_start_delay=5.0s` 开始连接
- 从发送上电指令起，物理上电窗口持续 `main_power_cycle_on_seconds=20.0s`
- 在目标断电时刻前 `main_power_cycle_disconnect_lead_seconds=2.0s` 开始清理
- `main_power_cycle_force_off_at_deadline=True`：清理未完成也会在第 20 秒发送物理断电
- `main_power_cycle_connect_retry_interval=1.0s`：第 5 秒首次扫描失败后，在本轮上电窗口内继续扫描
- 从实际断电指令起，物理断电窗口持续 `main_power_cycle_off_seconds=3.0s`

如果开机自启且现场可能有多个串口，建议把 `main_power_cycle_port` 固定成实际端口，例如：

```python
"main_power_cycle_port": "/dev/ttyXRUSB0"
```

避免启动时卡在交互选择。

RS485 上下电模式会从设备候选中排除 `main_power_cycle_port`，并在启动四个长驻进程时固定 `device_index -> 串口` 映射。如果现场还有其他 USB 串口，应同时明确配置四个设备口，例如：

```python
"main_power_cycle_rs485_ports": [
    "/dev/ttyXRUSB1",
    "/dev/ttyXRUSB2",
    "/dev/ttyXRUSB3",
    "/dev/ttyXRUSB4",
]
```

## 普通启动流程

当 `ENABLE_MAIN_POWER_CYCLE_SCRIPT=False` 时：

```text
launch.py
  -> 根据 DEFAULT_COMMUNICATION_MODE / DEFAULT_LAUNCH_COUNT 启动 main.py
```

如果 `launch_count > 1`，会启动：

```text
main.py --communication-mode=<mode> --device-index=0
main.py --communication-mode=<mode> --device-index=1
...
```

运行中的 `main.py` 会在 `runtime/` 下写入 PID 文件。可以用命令行请求已运行的 `main.py` 停止运动并断开连接：

```text
sudo python3 main.py --stop-existing -m CANFD
sudo python3 main.py --stop-existing -m CANFD -i 0
sudo python3 main.py --stop-existing
```

`--disconnect-existing`、`--shutdown-existing`、`--disconnect` 是同一个停止命令的别名。该命令通过 `SIGTERM` 通知已运行的 `main.py` 优雅退出；具体释放 CANFD、ECAT 或 RS485 资源由正在运行的 `main.py` 按当前通讯模式执行。

## 主电源通断测试流程

当 `ENABLE_MAIN_POWER_CYCLE_SCRIPT=True` 时：

```text
launch.py
  -> main_power_cycle.py
      -> 清理同通信模式下已存在的 main.py
      -> tools/setup_rs485_mode.py
      -> 打开主电源控制串口
      -> RS485 模式排除电源口并固定 N 个设备串口
      -> 启动 N 个长驻 main.py --managed-by-power-cycle
      -> while True:
           发送上电
           等待 main_power_cycle_start_delay
           按 device index 顺序发送 start_cycle 控制命令，不同 main.py 间隔 1s
           ECAT 扫描不到从站时，每隔 main_power_cycle_connect_retry_interval 重建主站并再次扫描
           每次 ECAT 扫描前记录网口 carrier 和 operstate；到断电前清理时刻停止重试
           从站发现过晚且剩余时间不足以完成使能、回零时，本轮不再启动运动
           main.py 内部连接、回零并开始循环运动
           任意一个 main.py 发出 home_started 进度后，GPIO12 输出一次计数脉冲
           未接设备的 start_cycle 失败只记录，不中断电源循环；下一轮上电后重新连接
           在目标断电时刻前 main_power_cycle_disconnect_lead_seconds 开始发送 stop_cycle
           main.py 等待循环运动线程退出，然后停止电机并断开 CANFD、ECAT 或 RS485 通信
           若通信提前断开，等待到原目标时刻再发送物理断电
           force_off_at_deadline=True 时，即使通信断开未完成，也会在目标时刻强制物理断电并记录 forced_power_off
           从实际断电指令时刻起等待 main_power_cycle_off_seconds 后进入下一轮上电
```

上电指令：

```text
01 06 00 00 00 00 89 CA
```

断电指令：

```text
01 06 00 00 00 01 48 0A
```

主电源控制串口默认波特率：

```text
9600
```

主电源通断测试回零启动计数：

```text
GPIO12
```

每次上电后，任意一个长驻 `main.py` 在 `start_cycle` 流程中成功发出回零指令，会输出一次 0.5s 计数脉冲，并在日志中记录累计次数。多脚本场景同一轮只记一次。

## 日志

日志目录：

```text
logs/<run_id>/
```

`launch.py` 每次启动会创建一个 `run_id` 批次目录，`main_power_cycle.py` 和全部
`main.py` 子进程继承同一个批次。直接执行任一入口时也会自动创建独立批次。

批次内文件名包含入口和 pid，例如：

```text
logs/20260715_173000_pid1234/session.json
logs/latest.txt
logs/20260715_173000_pid1234/launch_pid1234.log
logs/20260715_173000_pid1234/main_power_cycle_pid1235.log
logs/20260715_173000_pid1234/main_CANFD_device_0_pid1236.log
```

日志格式包含：

- 时间，含毫秒
- level
- run_id
- communication mode
- device
- power cycle
- control command id
- pid
- 线程名
- 模块和行号
- 消息

`setup_logging()` 会把 `stdout/stderr` 转成带完整上下文的日志记录，所以旧代码中的
`print()` 输出也会进入对应设备日志。日志按每文件 20 MiB 滚动，每个进程保留当前文件
和 5 个备份；默认保留最近 30 个完整运行批次。父进程发送控制命令时会记录对应
`main.py` 的日志绝对路径，连接失败时应同时查看 `main_power_cycle` 和该设备日志。
`logs/latest.txt` 保存最近一次启动批次的绝对路径。

每个正常完成或可恢复失败的上下电轮次都会输出一条 `POWER_CYCLE_SUMMARY`，包含连接、
回零、运动、实际通断时间及下一步动作。RS485 驱动准备脚本的 stdout/stderr 以
`RS485_SETUP` 前缀进入父进程日志。

### 日志磁盘上限

日志有四层清理，全部在启动时由创建批次的进程执行一次（子进程继承批次，不重复清理）：

| 层级 | 机制 | 默认值 | 配置键 |
| --- | --- | --- | --- |
| 单文件 | `RotatingFileHandler` | 20 MiB × (5 备份 + 1 当前) = 120 MiB/进程 | `log_max_bytes` / `log_backup_count` |
| 批次数量 | 保留最近 N 个完整批次 | 30 | `log_max_sessions` |
| **批次总字节** | **`logs/` 总量超限时按时间删除最旧批次** | **1 GiB** | `log_max_total_bytes` |
| 遗留平铺文件 | 删 `logs/*.log` | 100 个 | 无（保留 `max_files` 形参默认值） |

前两层组合无法给出确定的磁盘上限（单批次占用 = 进程数 × 120 MiB，进程数或重启频率一变，
总量就跟着放大），因此以 `log_max_total_bytes` 作为硬上限：无论进程数和重启频率如何，
`logs/` 总量都会被压回该值以内。

规则与边界：

- 配置键写在 preset 的 `features` 中，经 `config.py` 的 `LOG_RETENTION_CONFIG` 传给
  `setup_logging()`；不写则用 [log.py](/D:/Project/PyProject/RaspberryPiDemo/log.py) 的默认值，
  所以只有需要收紧的场景（例如三个 `*_power_cycle_test` preset）才需要显式配置。
- 当前批次和 `_is_pid_running()` 判定仍活着的批次只计入总量、永不删除。因此**单个会话自身
  超过上限时无法再回收**，此时会记录一条 warning；该情况仍受单文件轮转约束
  （≈ 进程数 × 120 MiB）。
- 为避免误删，按字节清理只删「含 `session.json`」或「目录名匹配 `<run_id>` 格式」的目录，
  `logs/` 下手动放置的其他目录不会被触碰。这一点也顺带修掉了旧逻辑里
  「缺 `session.json` 的批次永久残留」的问题。
- 上限设为 `0` 或负数可关闭按字节清理。
- 创建批次的进程启动后会输出一条
  `日志保留策略: sessions=... total_limit_bytes=... retained_bytes=... removed_sessions=...`；
  子进程继承批次、不执行清理，因此不会重复输出。现场排查磁盘占用时先看这行。

## RS485 串口准备脚本

脚本：

```text
tools/setup_rs485_mode.py
```

用途：

- 检查 `/dev/ttyXRUSB*` 是否存在。
- 如果不存在，检测 `lsusb` 中是否有 `04e2:1411 Exar Corp. XR21B1411`。
- 尝试通过 `modprobe xr_usb_serial_common` 加载驱动。
- 如果 `modprobe` 不可用或失败，尝试 `insmod /home/ubuntu/Documents/ll-usb2rs485-driver/Driver/xr_usb_serial_common.ko`。
- 等待 `/dev/ttyXRUSB*` 出现。
- 对检测到的 `/dev/ttyXRUSB*` 执行 RS485 模式配置。

该脚本会被普通 RS485 启动流程和主电源通断测试流程调用。

## CANFD 传输后端（gs_usb）

### 为什么选择 gs_usb

这块适配器的 USB ID 是 `a8fa:8598`，**本身就是 gs_usb 协议设备**：

- `gsusb_canfd` 把 `(0xA8FA, 0x8598)` 列为已知设备，且它就是默认 VID/PID；
- SDK 自带的 socketcan 测试指令就是这台硬件的 gs_usb 用法
  （`modprobe gs_usb` + `echo "a8fa 8598" > .../new_id` + `ip link set can0 ... fd on`）。

因此项目直接使用 gs_usb，**不需要在 Pi 上安装任何厂商动态库**。现在项目用的是
SDK 示例同源的实现：

| 项目文件 | 来源 | 说明 |
| --- | --- | --- |
| `canfd_lib.py` | SDK 包 `.../examples/CANFD_python/canfd_lib.py` | gsusb / socketcan 双后端 + `CANFD()` 工厂 |
| `gsusb_canfd/` | SDK 包 `.../examples/CANFD_python/gsusb_canfd/` | 上游 `gsusb-canfd` 0.1.3（MIT），纯用户态 gs_usb，依赖 pyusb |

注意：本仓库的 `canfd_lib.py` 已裁剪为只保留 gsusb / socketcan 两条后端路径；
从 SDK 重新同步该文件时，需要保留这份裁剪，否则会重新引入已废弃的厂商后端。

### 后端选择

`canfd_lib.CANFD(driver=...)` 是工厂函数，可选值 `gsusb` / `socketcan`；
不传或传 `None` 时由 `_AutoCANFD` 运行期择优（优先 gsusb，扫不到再回退到 socketcan）。
项目在 preset 的 `features` 里用 `canfd_driver` 固定后端，缺省值见
`config_support.DEFAULT_CANFD_DRIVER`（当前 **`"gsusb"`**）：

```python
# configs/config_*.py
"features": {
    "canfd_driver": "gsusb",   # 省略即用默认值；None = 运行期自动择优
}
```

链路是 `features.canfd_driver` → `config.CANFD_DRIVER` → `CANFD(driver=...)`。
之所以默认**固定**成 gsusb 而不是自动择优：一旦内核 `gs_usb` 绑定过适配器，
`_AutoCANFD` 会在下次启动时静默改走 socketcan，4 实例老化测试跑在不同后端上很难排查。

### 运行环境要求

```bash
sudo apt install libusb-1.0-0        # pyusb 需要系统 libusb-1.0
pip install 'pyusb>=1.2.1'
```

`gsusb_canfd` 已随项目 vendored 到项目根目录（`canfd_lib.py` 的源码搜索根第一个就是
项目根），不需要 pip 安装；它要求自身 `>= 0.1.2`（`open(adapter)` 与
`BusConfig.drop_echo`），vendored 版本是 0.1.3。udev 权限规则（适配器
`a8fa:8598` → `MODE=0666`）**继续需要**，非 root 运行时靠它拿权限；
`tools/setup_canfd_mode.py` 会扫描 `/etc/udev/rules.d/*.rules` 检查是否已有匹配规则。

### 内核 gs_usb 与 pyusb 互斥

内核 `gs_usb` 驱动和 pyusb 抢同一个 USB 接口，谁先绑定谁独占：

- 用 **gsusb（pyusb）** 后端 → 应当确保 `gs_usb` **没有**绑定适配器：
  `sudo modprobe -r gs_usb`。注意 `CanFdBus.open()` 会先尝试
  `detach_kernel_driver(0)`，失败时静默忽略（`bus.py:369-373`），所以以 root 运行时
  即使模块已绑定也可能侥幸打开；显式解绑更可靠，也能避免内核驱动随后重新绑定。
- 用 **socketcan** 后端 → 反过来要用内核驱动（该后端会自己 `modprobe -r gs_usb` →
  `modprobe gs_usb` → 写 `new_id`）

准备脚本：

```bash
sudo python3 tools/setup_canfd_mode.py
```

它依次检查 pyusb/libusb、确认并解除 `gs_usb` 绑定（`modprobe -r` 失败时退回 sysfs
逐接口 `unbind`）、检查 udev 规则、并用 `gsusb_canfd.scan_adapters()` 枚举适配器。
该脚本**不会**被启动流程自动调用（避免把有意使用 socketcan 的现场改坏）；
`main.py -m CANFD` 扫不到设备时会打印提示指向它。

### 接收路径不要改回 sleep 轮询

`canfd_lib.py` 的 gsusb 后端把收帧交给库自带的工作线程（`bus.start(callback)`，全程不
sleep）。**不要**照搬旧版实现的「批量收 500 帧 + 每轮 `time.sleep(0.001)`」写法：
gs_usb 每个 USB 包只承载一帧，而灵巧手反馈流约 2 kHz，一旦每收一帧就 sleep，
接收端追不上到达速率，适配器 RX FIFO 会持续溢出并随机丢弃 SDO 应答（`0x581`），
SDK 会在 50 ms 超时后报 `LER_COMM_RECV(7)`。

### 位时序与 5 Mbps 数据段

gsusb 后端的位时序由 `gsusb_canfd` 依据设备上报的时钟（`BREQ_BT_CONST` /
`BREQ_BT_CONST_EXT`）用 `calculate_bit_timing`（对齐内核 `can_calc_bittiming`）自动推导，
采样点固定 1 Mbps@80% / 5 Mbps@75%。用宽松约束离线扫过常见适配器时钟的结果：

- `1 Mbps@80%`：8/16/20/24/36/40/45/48/60/72/80/96/120/144/160 MHz 均可推导；
- `5 Mbps@75%`：只有时钟接近 5 MHz 整数倍时成立（20/40/45/60/80/120/144/160 MHz），
  8/16/24/36/48/72/96 MHz 会报 `cannot derive bit timing`。

厂商的 `socketcan初始化测试指令.txt` 用的就是 `dbitrate 5000000`，SDK 也把 5 Mbps 作为
默认值，所以现场适配器应当满足。若启动时确实报 `cannot derive bit timing`，
下调数据段波特率即可（当前是 `connect()` 的默认参数）：

```text
lhandpro_controller.py:201    canfd_dat_baudrate: int = 5000000   # 例如降到 2000000
```

`canfd_nom_baudrate` 保持 `1000000`。这两项目前没有做成 preset 配置项。

### 多设备（4 实例）与总线占用登记

CANFD preset 基本都是 `default_launch_count: 4`（4 个 main.py = 4 个适配器）。

gs_usb（pyusb）**没有设备独占语义**：`scan_adapters()` 始终列出全部适配器，而且
`CanFdBus.open()` 不调用 `claim_interface`，多个进程会静默打开同一个适配器、两路 CAN
流量互相干扰（表现为随机的 SDO 超时 / `LER_COMM_RECV(7)`）。为此
[canfd_bus_claim.py](/D:/Project/PyProject/RaspberryPiDemo/canfd_bus_claim.py)
实现了应用层的跨进程总线占用登记：

- 每个适配器对应一个占位文件 `runtime/canfd_claims/<标识>.claim`，内容记录持有者 pid；
- 标识优先用 USB 序列号，无序列号时用 `bus<bus>-addr<address>`；
- 占位文件用 `O_CREAT|O_EXCL` **原子创建**，写不进就认为被别人持有；
- `scan()` 只返回"没有被其它存活进程持有"的适配器 —— 即恢复"扫描自动少一个"；
- 连接成功后一直持有，`disconnect()`（正常退出/收到 SIGTERM）时释放；
- 进程被 `kill -9` 或掉电后占位文件仍在，但持有者 pid 已不存活，会被自动回收并删除；
- 创建占位到写入 pid 之间有极短窗口，该窗口内（`CLAIM_WRITE_GRACE_SECONDS=2s`）的
  占位一律视为已占用，避免把别的进程刚建好的占位当失效文件删掉。

**device_index 在 gsusb 后端不再表示物理位置**：总线由占用登记分配，`_connect_canfd`
会忽略 `--device-index=N`（`launch.py` 在 `launch_count>1` 时对所有模式都会传它）并记一条
日志，各进程统一"取第一条空闲总线"。原因是 USB 枚举顺序本身不稳定，按序号固定物理
对应关系并不可靠；需要固定"某适配器 ↔ 某只手"时应改用序列号定位（尚未做成配置项）。

用假 pyusb 设备 + 真实多进程验证过的行为：

| 场景 | 结果 |
| --- | --- |
| 4 个存活进程同时抢 4 条总线 | 各自拿到不同总线，无重复 ✓ |
| 4 条总线都被占用时再起一个进程 | 第 5 个进程看到 0 条空闲，报"全部已被其它 main.py 占用" ✓ |
| 某个 main.py 被 `kill -9` | 占位残留但持有者已死，同总线可被后续进程接管 ✓ |
| 正常退出 | 占位全部释放，`runtime/canfd_claims/` 清空 ✓ |
| 4 个适配器**序列号完全相同** | 只允许一个进程占用，其余显式报"全部已被占用"（不再静默共用）✓ |

最后一行是序列号重复时的降级行为：占位标识会撞成同一个文件，所以从原来的"静默共用"
变成"只有一个能跑、其余报错"。多实例前仍然建议先确认序列号：

```bash
sudo python3 tools/setup_canfd_mode.py     # 逐个打印 serial/bus/addr，并检测重复
```

`channel_index` 在 gsusb 后端被忽略（单通道型号）。

### 性能

4 × 约 2 kHz 的反馈流 ≈ 8000 次 USB 传输/秒，全部在用户态处理，**CPU 需要实测**：

- 默认 gsusb（pyusb）：装机最省事；
- 如 CPU 吃紧或出现 `LER_COMM_RECV(7)`，把 `canfd_driver` 改成 `"socketcan"`
  （内核 gs_usb + `pip install 'python-can~=4.6.1'`），USB 由内核批处理，吞吐更好。

`channel_index` 在 gsusb 后端被忽略（单通道型号）；`device_index` 是
`scan_adapters()` 的枚举序号，插拔/重启后可能变化。`gsusb_canfd` 的 `DeviceSelector`
支持按 USB `serial` 定位，需要时可用它把「适配器 ↔ 进程」固定下来。

CANFD 只保留 gs_usb 与 socketcan 两条路径，不再保留厂商动态库回退。

## SDK 版本与升级

### 当前版本

项目内置的 SDK 副本已更新到 **LHandProLib aarch64 20261031**
（`build.utc_time = 2026-10-31T01:11:42Z`，`source_rev = e1f485e`）。

来源包：

```text
D:\Project\HandProject\LHandProLib\packages\20261031\LHandProLib-API-Linux-aarch64-20261031.tar.gz
```

项目内对应的文件：

| 项目文件 | 来源 | 说明 |
| --- | --- | --- |
| `lib/LHandProLib.h` | `aarch64/include/LHandProLib/LHandProLib.h` | 与 `lhandprolib_loader.py` 的原型表一一对应 |
| `lib/LHandProLib.hpp` | `aarch64/include/LHandProLib/LHandProLib.hpp` | C++ 头文件，随包附带 |
| `lib/libLHandProLib.so` | `aarch64/lib/libLHandProLib.so` | release 版；改用 Debug 版时为 `libLHandProLibd.so` |
| `lib/LHandProLib.dll` | Windows 包 `x64/bin/LHandProLib.dll` | **仍为 20261014**；20261031 只发布了 Linux aarch64 / macOS 包 |

该包要求客户机 **glibc ≥ 2.17**，且已静态链接 libstdc++/libgcc，不依赖目标机的
`libstdc++` 版本；只有 CANFD 示例额外需要 `libusb-1.0.so.0`（由系统提供）。

### 动态库查找顺序

`lhandprolib_loader.py` 的 `_find_library()` 按顺序取第一个存在的文件，**项目自带的
`lib/` 优先于 SDK 安装目录**：

```text
1. <项目>/libLHandProLib.so
2. <项目>/lib/libLHandProLib.so        <-- 本次放入的位置
3. <项目>/thirdParty/{bin,lib}/...
4. <aarch64 根>/bin/libLHandProLib.so
5. <aarch64 根>/lib/libLHandProLib.so  <-- 设备上原有的 SDK 安装目录
6. <项目>/../install/{bin,lib}/... , /usr/local/lib , /usr/lib
```

设备上项目位于 `<aarch64 根>/share/LHandProLib/examples/RaspberryPiDemo`，所以第 5 项
等于 `/home/ubuntu/Documents/aarch64/lib/libLHandProLib.so`。因为第 2 项优先，**只更新
SDK 安装目录而不更新项目 `lib/` 不会生效**；反之只更新项目 `lib/` 也能独立升级库版本。
升级库版本时建议两处一起换，避免下次误判。

### 手型枚举变更（破坏性）

20260921 起 SDK 新增 `C_LAC_DOF_6_V2`（DH116V2），`LAC_DOF_6_S` 与 `LAC_DOF_16`
的取值整体后移。这些值直接传给 `lhandprolib_set_hand_type`，**新旧库不能混用**：

| 枚举 | 旧值 | 20261031 |
| --- | --- | --- |
| `LAC_DOF_6` | 0 | 0 |
| `LAC_DOF_6_V2` | 不存在 | **1** |
| `LAC_DOF_6_S` | 1 | **2** |
| `LAC_DOF_16` | 2 | **3** |
| `LAC_DOF_GENERIC` | 不存在 | **4** |

`lhandprolib_loader.py` 已同步这些取值，`HAND_TYPE_MAP` 也已支持 `LAC_DOF_6_V2` 和
`LAC_DOF_GENERIC`。preset 里的 `current_hand_type` 仍写字符串名，不需要改动。

Linux `.so` 已同步到 20261031，`lhandprolib_loader._FUNCTION_TABLE` 共 115 个符号
**全部解析成功、无缺失符号警告**。Windows `lib/LHandProLib.dll` 仍为 20261014，
两平台枚举取值一致但库版本不同，升级/回退时应以对应平台包为准：

| 平台 | 20261031 | 回退参考（升级前） |
| --- | --- | --- |
| Linux aarch64 | `lib/libLHandProLib.so` 1,902,232 B / sha256 `d321b6d8…ce907e` | 用旧包的 `aarch64/lib/libLHandProLib.so` |
| Windows x64 | 未更新，仍为 20261014 `lib/LHandProLib.dll` 201,216 B | 177,664 B / sha256 `379b7626…871b22` |

### 新增 API

20261031 相对 20261014 新增 1 个接口，已加入 loader 原型表和 wrapper：

```text
lhandprolib_set_ecat_sdo_callback   # EtherCAT CoE SDO 传输回调
```

回调签名 `bool(index, subindex, is_write, value, out_value)`，Python 侧通过
`PyLHandProLib.set_ecat_sdo_callback()` 注册；必须在 `initial(LCN_ECAT)` 之前设置，
且 EtherCAT 主站已 `run()`。未注册时 ECAT 初始化跳过 SDO 自识别，保持旧行为。

20261014 相对上一版新增的 5 个接口（共享总线事务间隔、单实例 RS485 事务间隔、
OTA、`apply_motion_params`）保持不变，wrapper 仍未全部封装。

### 升级步骤

1. 解包 `packages/<日期>/LHandProLib-API-Linux-aarch64-<日期>.tar.gz`；
2. 用 `aarch64/include/LHandProLib/LHandProLib.h` 覆盖 `lib/LHandProLib.h`；
3. 用 `aarch64/lib/libLHandProLib.so` 覆盖 `lib/libLHandProLib.so`；
4. 对照新头文件更新 `lhandprolib_loader.py`：手型枚举取值、新增/删除的函数原型；
5. 在设备上确认 `ldd lib/libLHandProLib.so | grep "not found"` 无输出；
6. 起一次普通启动，确认日志中没有
   `当前动态库未导出以下接口` 的 `RuntimeWarning`（该警告会列出缺失符号）。

注意：`lib/` 被 `.gitignore` 的 `lib/` 规则忽略，**替换 `lib/` 下的文件不会进入 git**，
只影响本地工作副本和后续部署上传的内容。

## 部署

当前远端设备：

```text
ubuntu@192.168.137.137
```

当前远端项目目录：

```text
/home/ubuntu/Documents/aarch64/share/LHandProLib/examples/RaspberryPiDemo
```

部署时通常上传整个项目，但排除：

- `.git`
- `__pycache__`
- `logs`
- `runtime`

部署后建议验证：

```bash
cd /home/ubuntu/Documents/aarch64/share/LHandProLib/examples/RaspberryPiDemo
mkdir -p /tmp/rpdemo_pycache
find . \
  -path './.git' -prune -o \
  -path '*/__pycache__' -prune -o \
  -path './logs' -prune -o \
  -name '*.py' -print0 | \
  xargs -0 env PYTHONPYCACHEPREFIX=/tmp/rpdemo_pycache python3 -m py_compile
```

## systemd 开机自启

现场通常只需要开机启动 `launch.py`。

是否进入普通启动还是主电源通断测试，由当前配置决定。

注意：`main.py` 已处理 `SIGTERM` / `SIGINT`，收到退出信号时会停止运动、断开连接并清理 GPIO。主电源通断模式下，GPIO 业务输入会被禁用，避免停止与断开期间由按钮、抓握或手套回调重新发起通信；状态和循环计数输出仍保留。`main_power_cycle.py` 正常轮次只发送 `start_cycle` / `stop_cycle` 控制命令，不重启 `main.py` 子进程；退出或异常流程才会终止长驻子进程。脚本会在目标物理断电时刻前预留清理窗口；ECAT 预设启用硬断电截止，断开未完成也会在目标时刻物理断电，完整保持配置的断电窗口，并在下一轮重新尝试连接。systemd 服务仍建议配置足够的 `TimeoutStopSec`。

## 绿联 USB-to-RS485 适配器识别问题

### 现象

树莓派系统可能能通过 `lsusb` 看到绿联 USB-to-RS485 设备：

```text
04e2:1411 Exar Corp. XR21B1411
```

但没有出现常见的 `/dev/ttyUSB0`。

### 原因

该适配器芯片是 Exar XR21B1411，需要加载/绑定 Exar 驱动：

```text
xr_usb_serial_common
```

驱动加载成功后生成的串口设备是：

```text
/dev/ttyXRUSB0
```

不是：

```text
/dev/ttyUSB0
```

项目代码中的串口扫描逻辑应支持 `/dev/ttyXRUSB*`。现场配置固定串口时，应使用 `/dev/ttyXRUSB0`。

`tools/setup_rs485_mode.py` 已包含自动加载该驱动的逻辑；如果驱动文件存在且内核匹配，启动流程会自动尝试恢复 `/dev/ttyXRUSB*`。

### 临时加载验证

SSH 到目标设备：

```bash
ssh ubuntu@192.168.137.137
```

进入驱动目录：

```bash
cd /home/ubuntu/Documents/ll-usb2rs485-driver/Driver
```

临时加载驱动并验证：

```bash
sudo insmod ./xr_usb_serial_common.ko
ls -l /dev/ttyXRUSB*
```

如果成功，应能看到类似：

```text
/dev/ttyXRUSB0
```

### 永久安装

在驱动目录执行：

```bash
cd /home/ubuntu/Documents/ll-usb2rs485-driver/Driver
sudo make modules_install
sudo depmod -a
```

配置开机自动加载：

```bash
echo xr_usb_serial_common | sudo tee /etc/modules-load.d/xr_usb_serial_common.conf
```

### 验证命令

```bash
modinfo xr_usb_serial_common | grep -E 'filename|vermagic|04E2p1411'
ls -l /dev/ttyXRUSB0
stty -F /dev/ttyXRUSB0 -a
```

### 排查要点

如果 `lsusb` 能看到 `04e2:1411 Exar Corp. XR21B1411`，但没有 `/dev/ttyXRUSB0`，重点检查：

- `xr_usb_serial_common` 是否已经加载。
- 驱动是否安装到 `/lib/modules/$(uname -r)/extra`。
- 是否执行过 `sudo depmod -a`。
- 是否写入 `/etc/modules-load.d/xr_usb_serial_common.conf`。
- 当前系统内核是否和驱动编译时的内核一致。

树莓派升级或切换内核后，需要针对新内核重新编译并安装该驱动。

### 给以后排查用的提示词

SSH 到 `ubuntu@192.168.137.137`，检查绿联 USB-to-RS485 是否被识别。设备芯片应为 Exar XR21B1411，USB ID 为 `04e2:1411`。如果 `lsusb` 能看到设备但没有 `/dev/ttyXRUSB0`，检查 `xr_usb_serial_common` 驱动是否加载、是否安装到 `/lib/modules/$(uname -r)/extra`、是否执行 `depmod`、是否写入 `/etc/modules-load.d/xr_usb_serial_common.conf`。注意该驱动生成的串口是 `/dev/ttyXRUSB0`，不是 `/dev/ttyUSB0`。驱动源码在 `/home/ubuntu/Documents/ll-usb2rs485-driver/Driver`。

## 开机自启启动链（service 约定）

```text
systemd rpd.service
  └─ launch.py                 # 唯一入口
       ├─ 读 active_config.py  # ACTIVE_PRESET 决定模式
       ├─ 读 config.py         # 展开 preset + sequences
       ├─ [enable_main_power_cycle=False] N × main.py
       └─ [enable_main_power_cycle=True]  main_power_cycle.py → 受控 main.py
```

- **模式切换只动 `active_config.py`**（GPIO `config_switcher` 或 `setup.py`），重启后仍由 service 拉起。
- `launch.py` 监督子进程，`main.py` 异常退出按当前 preset 重拉。
- unit 样例：[deploy/rpd.service](deploy/rpd.service)；部署说明：[deploy/README.md](deploy/README.md)。
- `config_switcher` 使用明文 sudo 密码执行重启（现场约定，按需求保留）。
