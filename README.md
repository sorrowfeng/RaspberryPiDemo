# RaspberryPiDemo

LHandPro 在 Raspberry Pi 场景下的 Python 控制示例，支持 `CANFD`、`ECAT`、`RS485` 三种通讯方式，并包含循环运动、抓握动作、GPIO 触发和手套 UDP 输入。

CANFD 默认使用 **gs_usb 用户态实现**（pyusb + 随项目的 `gsusb_canfd`），Linux 上可切换到 `socketcan` 后端；后端可在 preset 的 `features.canfd_driver` 中切换。多开 `main.py` 时通过 `runtime/canfd_claims/` 的跨进程占用登记分配总线，`scan()` 只返回空闲总线。

## 目录结构

```text
RaspberryPiDemo/
├─ launch.py                 # systemd 入口
├─ main.py                   # 单实例入口
├─ active_config.py          # 当前 preset
├─ setup.py                  # 现场部署 / 快速切换配置工具
├─ app/                      # 配置、日志、生命周期、运行时控制
├─ power_cycle/              # 上下电测试
├─ device/                   # LHandPro / 传输层 / 硬件驱动
│  ├─ transports/            # CANFD / ECAT / RS485
│  └─ canfd/                 # CANFD 后端与 gs_usb
├─ motion_system/            # 运动、抓握、手套、GPIO 协调
├─ configs/                  # preset
├─ sequences/                # 动作序列
├─ tools/                    # 现场准备/测试/遗留工具
├─ deploy/                   # systemd unit 与部署说明
├─ docs/assets/              # 文档图片
├─ tests/
└─ lib/                      # SDK 二进制（gitignore）
```

- `app/config.py`：统一配置入口，运行时代码只从这里读取配置
- `active_config.py`：当前激活的 preset，以及现场覆盖参数
- `configs/`：preset 元数据，描述设备、总线、功能开关，以及引用哪些动作序列
- `sequences/`：动作序列定义，统一描述每一步的 `positions`、`velocities`、`currents`、`interval`

## 配置体系

当前配置系统拆成两层：

1. `preset`
   负责设备类型、通讯方式、循环次数、抓握模式、功能开关，以及引用的动作序列。
2. `sequence`
   负责具体动作步骤。每个 step 至少包含 `positions`，并可携带自己的 `velocities`、`currents`、`interval`。

运行时仍然只需要：

```python
from app.config import COMMUNICATION_CONFIG, MOTION_CONFIG, GRASP_CONFIG
```

`app/config.py` 会自动读取 [active_config.py](active_config.py) 中指定的 preset，并加载对应 sequence。

## 切换当前配置

### 方式 1：手动编辑

修改 [active_config.py](active_config.py)：

```python
ACTIVE_PRESET = "configs.config_DH116S_CANFD_grasp_aging"

RUNTIME_OVERRIDES = {
    "device": {
        "canfd_node_id": 2,
    },
}
```

### 方式 2：GPIO 按键

运行中的 `main.py` 支持 GPIO `SWITCH_CONFIG`：

- 短按切换下一个 preset
- 长按约 1.5 秒回到第一个 preset
- 30 秒无操作后写回 `active_config.py` 并重启生效

### 方式 3：`setup.py` 现场工具

把项目根目录的 `setup.py` 复制到树莓派 `~/Documents`（与 `aarch64/` 同级），并把
SDK 压缩包和 `RaspberryPiDemo.7z` 放在同一目录，运行：

```bash
cd ~/Documents
python3 setup.py
```

- 选择 SDK 包：解压 SDK、清理 examples、解压 `RaspberryPiDemo.7z`，再选择 preset；
- 选择“跳过（不解压 SDK）”：只切换 preset 并写回 `active_config.py`，不修改 SDK/examples；
- 最后可选择立即关机。

该脚本是现场部署工具，不由 systemd 调用；开机启动仍由 `launch.py` 负责。

## 动作序列格式

`sequences/` 中每个文件都导出一个统一结构：

```python
SEQUENCE = {
    "default_velocities": [20000, 20000, 20000, 20000, 20000, 20000],
    "default_currents": [1000, 1000, 1000, 1000, 1000, 1000],
    "default_interval": 0.8,
    "steps": [
        {"positions": [9000, 0, 0, 0, 0, 0]},
        {
            "positions": [9000, 10000, 10000, 10000, 10000, 10000],
            "interval": 4.0,
            "currents": [1000, 1000, 1000, 1000, 400, 400],
        },
    ],
}
```

规则：

- `positions` 必填
- `velocities` / `currents` / `interval` 可省略
- 缺省时继承 sequence 顶层默认值

## 运行方式

### 直接启动

```bash
sudo python3 main.py -m CANFD
sudo python3 main.py -m ECAT
sudo python3 main.py -m RS485
```

### 多实例启动

```bash
sudo python3 launch.py
sudo python3 launch.py -m CANFD -n 4
sudo python3 launch.py -m ECAT -n 1
sudo python3 launch.py -m RS485 -n 4
```

`launch.py` 会读取 [app/config.py](app/config.py) 导出的默认值，也支持命令行覆盖。

## 辅助脚本

```bash
sudo python3 tools/setup_canfd_mode.py
python3 tools/setup_rs485_mode.py
python3 tools/test_gpio.py
python3 tools/test_glove.py
python3 tools/pack.py
```

`tools/setup_canfd_mode.py` 用于 CANFD 默认的 gs_usb 用户态后端：检查 pyusb/libusb、
解除内核 `gs_usb` 绑定（与 pyusb 互斥）、检查 udev 规则并枚举适配器。

## 维护建议

- 新增机型/场景时，优先新增一个 `configs/config_*.py` preset
- 如果动作很多，不要继续塞进 preset，直接新增 `sequences/*.py`
- 业务运行代码只依赖 `app/config.py` 的结构化配置（`COMMUNICATION_CONFIG` / `DEVICE_CONFIG` / `MOTION_CONFIG` / `GRASP_CONFIG` / `FEATURE_FLAGS`），不要直接读取 preset 或 sequence 文件
- 平铺的全大写常量仅供旧脚本兼容，新代码不要再用
