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
  - 循环执行上电、启动 `main.py` 子进程、断电、停止 `main.py` 子进程。

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

当前主电源通断测试 preset：

```python
ACTIVE_PRESET = "configs.config_DH116S_CANFD_power_cycle_test"
```

该 preset 启用：

```python
"enable_main_power_cycle": True
```

相关参数：

- `main_power_cycle_start_delay`
- `main_power_cycle_on_seconds`
- `main_power_cycle_off_seconds`
- `main_power_cycle_baud_rate`
- `main_power_cycle_port`
- `main_power_cycle_stop_timeout`

如果开机自启且现场可能有多个串口，建议把 `main_power_cycle_port` 固定成实际端口，例如：

```python
"main_power_cycle_port": "/dev/ttyXRUSB0"
```

避免启动时卡在交互选择。

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

## 主电源通断测试流程

当 `ENABLE_MAIN_POWER_CYCLE_SCRIPT=True` 时：

```text
launch.py
  -> main_power_cycle.py
      -> tools/setup_rs485_mode.py
      -> 打开主电源控制串口
      -> while True:
           发送上电
           等待 main_power_cycle_start_delay
           启动 N 个 main.py
           上电总时长达到 main_power_cycle_on_seconds
           发送断电
           停止本轮 main.py
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

注意：如果希望 `sudo systemctl stop <service>` 时优雅停止所有脚本，需要确保 service 使用合适的 `KillMode` 和 `TimeoutStopSec`。当前代码已经集中管理 `main.py` 子进程生命周期，但如果 systemd 直接发送 `SIGTERM`，仍应确认退出路径是否满足现场断电清理要求。

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
