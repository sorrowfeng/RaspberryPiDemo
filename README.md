# LHandProLib Python 示例项目

## 项目简介

这是一个基于 LHandProLib 库的 Python 控制示例项目，专为树莓派环境设计，提供了 LHandPro 灵巧手的全面控制解决方案。

- **双通信模式支持**：同时支持 CANFD 和 EtherCAT 通信协议
- **树莓派 GPIO 集成**：通过 GPIO 引脚实现硬件触发控制
- **多功能运动控制**：支持循环运动、抓握动作、手套数据实时控制
- **自动化操作**：自动连接设备、回零、故障检测等功能

## 项目结构

```
RaspberryPiDemo/
├── configs/                # 配置文件目录
│   ├── config_DH116_CANFD_aging.py
│   ├── config_DH116_CANFD_exhibit.py
│   ├── config_DH116_ECAT_aging.py
│   ├── config_DH116_ECAT_exhibit.py
│   ├── config_DH116S_CANFD_aging.py
│   ├── config_DH116S_CANFD_exhibit.py
│   └── config_Module_ECAT_aging.py
├── launch.py                 # 启动文件
├── main.py                 # 主函数文件
├── lhandpro_controller.py  # LHandPro 控制器核心类
├── canfd_lib.py            # CANFD 通信库
├── ethercat_master.py      # EtherCAT 通信库
├── gpio_controller.py      # GPIO 控制器
├── udp_receiver.py         # UDP 数据接收器（手套控制）
├── config.py               # 通用配置
├── log.py                  # 日志配置
├── requirements.txt        # 依赖项
└── README.md               # 项目说明
```

## 主要功能

### 1. 双通信模式

- **CANFD 模式**：通过 CANFD 总线通信，支持高速数据传输
- **EtherCAT 模式**：通过以太网通信，支持 100M 高速实时控制

### 2. GPIO 控制

| GPIO 引脚功能 | 描述 |
|-------------|------|
| START_MOTION | 开始循环运动 |
| STOP_MOTION | 停止运动并回到零位置 |
| CONNECT | 连接设备 |
| DISCONNECT | 断开设备 |
| START_GLOVE_LISTEN | 开始手套监听 |
| CYCLE_COMPLETE | 循环完成信号输出 |
| STATUS_LED | 状态 LED 输出 |
| READY_STATUS | 就绪状态输出 |
| RUNNING_STATUS | 运行状态输出 |

### 3. 运动控制

- **循环运动**：按照预设位置序列循环执行
- **抓握动作**：执行预设的抓握动作序列
- **手套控制**：通过 UDP 接收手套数据，实时控制灵巧手
- **零位校准**：自动回零和手动回零功能

### 4. 安全监控

- **报警检测**：实时检测电机报警状态
- **故障处理**：遇到报警时自动停止运动
- **紧急停止**：支持通过 GPIO 和键盘紧急停止

## 快速开始

### 环境要求

- **硬件**：树莓派 4B
- **操作系统**：Ubuntu 20.04
- **Python**：Python 3.9+
- **依赖项**：见 `requirements.txt`

### 安装步骤

1. **克隆项目**

```bash
git clone <项目地址>
cd RaspberryPiDemo
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **安装 RPi.GPIO**（树莓派专用）

```bash
pip install RPi.GPIO
# 或
sudo apt-get install python3-rpi.gpio
```

### 运行项目

#### 基本运行

```bash
sudo python3 launch.py
```

#### 命令行参数

| 参数 | 简写 | 描述 | 默认值 |
|------|------|------|--------|
| --device-index | -i | 设备索引（0-3） | None（自动选择） |
| --communication-mode | -m | 通信模式（CANFD/ECAT） | ECAT |
| --enable-gpio | -g | 启用 GPIO 控制 | True |
| --no-enable-gpio | - | 禁用 GPIO 控制 | False |

## 配置说明

### 通用配置

在 `config.py` 中可以修改以下参数：

- `DEFAULT_HOME_TIME`：回零等待时间
- `DEFAULT_CYCLE_COUNT`：循环运动次数
- `DEFAULT_CYCLE_VELOCITY`：循环运动速度
- `DEFAULT_CYCLE_INTERVAL`：循环运动间隔时间
- `DEFAULT_CYCLE_CURRENT`：循环运动最大电流
- `CYCLE_MOVE_POSITIONS`：循环运动位置序列
- `CYCLE_FINISH_POSITION`：循环运动结束位置
- `ENABLE_ALARM_CHECK`：是否启用报警检测

### 专用配置

在 `configs/` 目录下提供了多种场景的配置文件：

- `config_DH116_CANFD_exhibit.py`：DH116 CANFD 展览模式配置
- `config_DH116_CANFD_aging.py`：DH116 CANFD 老化测试配置
- `config_DH116_ECAT_exhibit.py`：DH116 ECAT 展览模式配置
- `config_DH116_ECAT_aging.py`：DH116 ECAT 老化测试配置
- `config_DH116S_CANFD_exhibit.py`：DH116S CANFD 展览模式配置
- `config_DH116S_CANFD_aging.py`：DH116S CANFD 老化测试配置
- `config_Module_ECAT_aging.py`：模块 ECAT 老化测试配置

### 配置文件使用方法

要使用 `configs/` 目录下的配置文件，只需将对应配置文件的内容复制到主目录的 `config.py` 文件中即可：

```bash
# 使用 DH116 CANFD 老化测试配置
cp configs/config_DH116_CANFD_aging.py config.py

# 使用 DH116 CANFD 展览模式配置
cp configs/config_DH116_CANFD_exhibit.py config.py

# 使用 DH116 ECAT 老化测试配置
cp configs/config_DH116_ECAT_aging.py config.py

# 使用 DH116 ECAT 展览模式配置
cp configs/config_DH116_ECAT_exhibit.py config.py

# 使用 DH116S CANFD 老化测试配置
cp configs/config_DH116S_CANFD_aging.py config.py

# 使用 DH116S CANFD 展览模式配置
cp configs/config_DH116S_CANFD_exhibit.py config.py

# 使用 模组 ECAT 老化测试配置
cp configs/config_Module_ECAT_aging.py config.py
```

替换完成后，重启时会自动使用新的配置参数。

## 使用指南

### GPIO 控制

1. **连接硬件**：将对应的功能按钮连接到树莓派的 GPIO 引脚
2. **启动程序**：运行 `launch.py` 程序
3. **硬件控制**：
   - 按下 START_MOTION 按钮：开始循环运动
   - 按下 STOP_MOTION 按钮：停止运动并回到零位置
   - 按下 CONNECT 按钮：连接设备
   - 按下 DISCONNECT 按钮：断开设备
   - 按下 START_GLOVE_LISTEN 按钮：开始手套监听

### 手套控制

1. **启动手套设备**：确保手套设备正常运行并发送 UDP 数据
2. **开始监听**：通过 GPIO 按钮或程序内部函数启动手套监听
3. **实时控制**：手套的动作将实时传递给灵巧手

### 循环运动

1. **配置参数**：在 `config.py` 中设置循环运动参数
2. **启动运动**：通过 GPIO 按钮或程序内部函数启动循环运动
3. **监控状态**：循环完成时会输出完成信号

## 故障排除

### 常见问题

1. **GPIO 设置失败**
   - 确保在树莓派硬件上运行
   - 确保安装了 RPi.GPIO 库
   - 确保有足够的权限（使用 sudo 或加入 gpio 组）

2. **设备连接失败**
   - 检查通信线缆连接
   - 确认设备电源正常
   - 检查通信模式设置是否正确

3. **运动控制失败**
   - 检查电机是否正常使能
   - 确认设备已正确回零
   - 检查报警状态并清除报警

### 日志查看

程序运行时会输出详细的日志信息，包括：
- 设备连接状态
- 运动执行情况
- 错误和警告信息
- GPIO 触发事件

## 依赖项

| 依赖项 | 版本 | 用途 |
|--------|------|------|
| keyboard | ~=0.13.5 | 键盘事件监听 |
| pysoem | ~=1.1.12 | EtherCAT 通信 |
| RPi.GPIO | >=0.7.0 | 树莓派 GPIO 控制 |

## 许可证

本项目采用 Apache-2.0 license 许可证。

## 注意事项

1. **安全操作**：在操作灵巧手时，请确保周围环境安全，避免造成人员伤害或设备损坏
2. **硬件要求**：GPIO 功能仅在树莓派硬件上可用，其他平台可使用 `--no-enable-gpio` 选项禁用
3. **权限问题**：操作 GPIO 需要相应的权限，请确保以正确的用户身份运行程序
4. **通信设置**：根据实际硬件连接选择正确的通信模式和设备索引

## 联系信息

如有问题或建议，请联系项目维护人员。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     应用层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ main.py       │ test_gpio.py  │ test_glove.py           │
│ launch.py     │ log.py        │ config_loader.py        │
└───────────────┴───────────────┴─────────────────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                     控制层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ lhandpro_controller │ gpio_controller  │ udp_receiver        │
└───────────────┴───────────────┴─────────────────────────┘
        │                  │                  │
        ▼                  ▼                  │
┌─────────────────────────────────┐          │
│       设备驱动层                │          │
├───────────────┬───────────────┤          │
│ canfd_lib     │ ethercat_master │<─────────┘
└───────────────┴───────────────┘
        │                  │
        ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                     硬件层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ LHandPro 灵巧手 │ 树莓派 GPIO  │ 手套 UDP 数据           │
└───────────────┴───────────────┴─────────────────────────┘
```

## 硬件要求

### 主要硬件
- 树莓派 4B 
- LHandPro 灵巧手
- 电源适配器
- CANFD 通信模块（可选，用于 CANFD 通信模式）
- EtherCAT 通信模块（可选，用于 EtherCAT 通信模式）
- GPIO 按钮和 LED（用于硬件控制和状态指示）

### GPIO 引脚连接

#### 输入引脚（BCM 编号模式）

| GPIO (BCM) | 物理引脚 | 功能 |
|-----------|---------|------|
| GPIO 17 | 引脚 11 | START_MOTION：开始循环运动 |
| GPIO 27 | 引脚 13 | STOP_MOTION：停止运动并回到0位置 |
| GPIO 22 | 引脚 15 | CONNECT：连接设备 |
| GPIO 23 | 引脚 16 | DISCONNECT：断开设备连接 |
| GPIO 26 | 引脚 37 | START_GLOVE_LISTEN：开始手套监听 |
| GPIO 20 | 引脚 38 | START_GRASP：开始抓握 |

#### 输出引脚（BCM 编号模式）

| GPIO (BCM) | 物理引脚 | 功能 |
|-----------|---------|------|
| GPIO 24 | 引脚 18 | CYCLE_COMPLETE：循环完成信号（0.5秒脉冲） |
| GPIO 25 | 引脚 22 | STATUS_LED：设备连接状态LED |
| GPIO 5  | 引脚 29 | READY_STATUS：程序就绪状态 |
| GPIO 6  | 引脚 31 | RUNNING_STATUS：运动运行状态 |
| GPIO 12 | 引脚 32 | RGB_R：RGB 红色通道（PWM） |
| GPIO 13 | 引脚 33 | RGB_G：RGB 绿色通道（PWM） |
| GPIO 19 | 引脚 35 | RGB_B：RGB 蓝色通道（PWM） |

**注意**: 所有输入引脚默认使用下拉电阻，需要连接到 GND 以触发操作。

## 日志系统

### 日志文件管理

项目使用 `log.py` 实现了智能日志管理系统，具有以下特点：

- **自动日志轮转**：定期创建新的日志文件，防止单个日志文件过大
- **日志级别控制**：支持不同级别的日志输出（DEBUG、INFO、WARNING、ERROR）
- **文件数量限制**：自动管理日志文件数量，防止磁盘空间不足
- **详细的日志内容**：记录设备连接状态、运动执行情况、错误信息等

### 日志查看

日志文件默认存储在项目目录`logs`，可通过以下方式查看：

```bash
# 查看最新日志
cat logs/app*.log

# 实时查看日志
tail -f logs/app*.log
```