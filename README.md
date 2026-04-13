# RaspberryPiDemo

LHandPro 在 Raspberry Pi 场景下的 Python 控制示例，支持 `CANFD`、`ECAT`、`RS485` 三种通讯方式，并包含循环运动、抓握动作、GPIO 触发和手套 UDP 输入。

## 目录结构

```text
RaspberryPiDemo/
├─ main.py
├─ launch.py
├─ setup.py
├─ active_config.py
├─ config.py
├─ config_support.py
├─ configs/
├─ sequences/
├─ motion_system/
├─ tools/
├─ assets/
└─ ...
```

- `config.py`：统一配置入口，运行时代码只从这里读取配置
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
from config import DEFAULT_COMMUNICATION_MODE, MOTION_CONFIG, GRASP_CONFIG
```

`config.py` 会自动读取 [active_config.py](/D:/Project/PyProject/RaspberryPiDemo/active_config.py) 中指定的 preset，并加载对应 sequence。

## 切换当前配置

### 方式 1：手动编辑

修改 [active_config.py](/D:/Project/PyProject/RaspberryPiDemo/active_config.py)：

```python
ACTIVE_PRESET = "configs.config_DH116S_CANFD_grasp_aging"

RUNTIME_OVERRIDES = {
    "device": {
        "canfd_node_id": 2,
    },
}
```

### 方式 2：使用 `setup.py`

`setup.py` 现在会：

- 选择一个 preset
- 写入 `active_config.py`
- 在 CANFD 场景下写入 `canfd_node_id` 覆盖值

不再通过覆盖整份 `config.py` 来切换配置。

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

`launch.py` 会读取 [config.py](/D:/Project/PyProject/RaspberryPiDemo/config.py) 导出的默认值，也支持命令行覆盖。

## 辅助脚本

```bash
python3 tools/setup_rs485_mode.py
python3 tools/test_gpio.py
python3 tools/test_glove.py
python3 tools/pack.py
```

## 维护建议

- 新增机型/场景时，优先新增一个 `configs/config_*.py` preset
- 如果动作很多，不要继续塞进 preset，直接新增 `sequences/*.py`
- 业务运行代码继续只依赖 [config.py](/D:/Project/PyProject/RaspberryPiDemo/config.py)，不要直接读取 preset 或 sequence 文件
