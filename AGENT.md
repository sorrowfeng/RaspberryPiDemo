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
- `main_power_cycle_on_seconds`
- `main_power_cycle_off_seconds`
- `main_power_cycle_baud_rate`
- `main_power_cycle_port`
- `main_power_cycle_rs485_ports`（仅 RS485 设备通讯，可选的固定四串口列表）
- `main_power_cycle_stop_timeout`
- `main_power_cycle_control_timeout`

当前主电源通断测试默认时间：

- 上电后等待 `main_power_cycle_start_delay=2.0s`
- 首个设备开始运动后，运动窗口持续 `main_power_cycle_on_seconds=10.0s`
- 断电后等待 `main_power_cycle_off_seconds=1.0s`

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
           main.py 内部连接、回零并开始循环运动
           任意一个 main.py 发出 home_started 进度后，GPIO12 输出一次计数脉冲
           未接设备的 start_cycle 失败只记录，不中断本轮
           任意一个 main.py 发出 motion_started 进度后，运动窗口持续 main_power_cycle_on_seconds
           发送 stop_cycle 控制命令，main.py 内部停止运动并断开设备
           stop_cycle 成功后发送断电
           等待 main_power_cycle_off_seconds
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
logs/
```

日志文件名包含入口和 pid，例如：

```text
launch_YYYYMMDD_HHMMSS_pid1234.log
main_CANFD_device_0_YYYYMMDD_HHMMSS_pid1235.log
main_power_cycle_YYYYMMDD_HHMMSS_pid1236.log
```

日志格式包含：

- 时间，含毫秒
- level
- pid
- 线程名
- 模块和行号
- 消息

`setup_logging()` 会把 `stdout/stderr` tee 到日志文件，所以旧代码中的 `print()` 输出也会进入日志。

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

注意：`main.py` 已处理 `SIGTERM` / `SIGINT`，收到退出信号时会停止运动、断开连接并清理 GPIO。主电源通断模式下，`main_power_cycle.py` 正常轮次只发送 `start_cycle` / `stop_cycle` 控制命令，不重启 `main.py` 子进程；退出或异常流程才会终止长驻子进程。确认 `stop_cycle` 完成后，才会发送断电指令。systemd 服务仍建议配置足够的 `TimeoutStopSec`，避免清理尚未完成就被系统强杀。

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
