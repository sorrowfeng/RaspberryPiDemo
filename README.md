# LHandProLib EtherCAT Python 示例项目

## 项目概述

LHandProLib EtherCAT Python 示例项目是一个基于树莓派的灵巧手演示项目，集成了 EtherCAT 通信、GPIO 硬件控制和手套数据监听功能。该项目提供了简洁易用的接口，允许用户通过 GPIO 按钮或程序控制灵巧手的运动，同时支持通过 UDP 接收手套数据进行实时监控。

## 主要功能特性

### 核心功能
- **EtherCAT 通信**: 基于 pysoem 库实现与 LHandPro 灵巧手的 EtherCAT 通信
- **GPIO 硬件控制**: 支持通过树莓派 GPIO 引脚触发各种操作
- **手套数据监听**: 通过 UDP 实时接收和处理手套角度数据
- **多任务并行**: 支持同时运行灵巧手运动和手套数据监听
- **状态反馈**: 通过 LED、RGB 灯和 GPIO 输出提供直观的状态指示

### 具体功能
1. **设备连接管理**: 自动连接和断开 LHandPro 设备
2. **循环运动控制**: 执行预设的位置序列循环运动
3. **实时状态监控**: 监控设备连接状态、运动状态和手套数据
4. **安全保障**: 支持紧急停止和报警处理
5. **测试工具**: 提供 GPIO 测试和手套数据测试工具

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     应用层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ main.py       │ test_gpio.py  │ test_glove.py           │
└───────────────┴───────────────┴─────────────────────────┘
        │                  │                  │
        ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                     控制层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ motion_controller │ gpio_controller  │ udp_receiver        │
└───────────────┴───────────────┴─────────────────────────┘
        │                  │                  │
        ▼                  ▼                  │
┌─────────────────────────────────┐          │
│       设备驱动层                │          │
├───────────────┬───────────────┤          │
│ lhandpro_controller │ ethercat_master │<─────────┘
└───────────────┴───────────────┘
        │                  │
        ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                     硬件层                               │
├───────────────┬───────────────┬─────────────────────────┤
│ LHandPro 机械臂 │ 树莓派 GPIO  │ 手套 UDP 数据           │
└───────────────┴───────────────┴─────────────────────────┘
```

## 硬件要求

### 主要硬件
- 树莓派 4B
- LHandPro 灵巧手
- 电源适配器

### GPIO 引脚连接

#### 输入引脚（BCM 编号模式）

| GPIO (BCM) | 物理引脚 | 功能 |
|-----------|---------|------|
| GPIO 17 | 引脚 11 | START_MOTION：开始循环运动 |
| GPIO 27 | 引脚 13 | STOP_MOTION：停止运动并回到0位置 |
| GPIO 22 | 引脚 15 | CONNECT：连接设备 |
| GPIO 23 | 引脚 16 | DISCONNECT：断开设备连接 |
| GPIO 26 | 引脚 37 | START_GLOVE_LISTEN：开始手套监听 |

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

## 安装步骤

### 1. 系统要求
- Ubuntu 20.04 LTS 
- Python 3.7 或更高版本
- root 权限（用于 GPIO 和 EtherCAT 操作）

### 2. 安装依赖

```bash
# 安装系统依赖
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev git
sudo apt-get install -y build-essential libi2c-dev libssl-dev

# 安装 Python 依赖
pip3 install -r requirements.txt
```

### 3. 克隆项目

```bash
# 进入工作目录
cd /home/ubuntu/Documents

cd aarch64/share/LHandProLib/examples/EtherCAT_python
```

## 使用指南

### 快速开始

1. **连接硬件**:
   - 将 LHandPro 灵巧手通过 EtherCAT 连接到树莓派
   - 连接 GPIO 按钮和 LED 到相应引脚
   - 确保电源连接稳定

2. **运行主程序**:

```bash
# 以 root 权限运行（需要 GPIO 和 EtherCAT 权限）
sudo python3 main.py
```

3. **操作流程**:
   - 按下 GPIO 22（连接设备）按钮
   - 按下 GPIO 17（开始运动）按钮
   - 按下 GPIO 27（停止运动）按钮
   - 按下 GPIO 26（开始手套监听）按钮
   - 按下 GPIO 23（断开设备）按钮

### 程序功能说明

#### main.py
主程序，包含以下功能：
- 自动连接 LHandPro 设备
- 执行预设的循环运动序列
- 通过 GPIO 控制灵巧手
- 监听手套 UDP 数据

#### test_gpio.py
GPIO 测试工具，用于测试 GPIO 引脚的输入和输出功能：

```bash
sudo python3 test_gpio.py
```

#### test_glove.py
手套数据测试工具，用于测试 UDP 手套数据接收功能：

```bash
python3 test_glove.py
```

## 配置说明

### GPIO 引脚配置

可以在 `gpio_controller.py` 文件中修改 GPIO 引脚定义：

```python
class GPIO_PINS:
    # 输入引脚定义（BCM编号）
    START_MOTION = 17     # 开始循环运动 (物理引脚11)
    STOP_MOTION = 27      # 停止运动并回到0 (物理引脚13)
    CONNECT = 22          # 连接设备 (物理引脚15)
    DISCONNECT = 23       # 断开连接 (物理引脚16)
    START_GLOVE_LISTEN = 26  # 开始手套监听 (物理引脚37)
    
    # 输出引脚定义（BCM编号）
    READY_STATUS = 5      # 程序已准备好/待命状态 (物理引脚29)
    RUNNING_STATUS = 6    # 循环运行中状态 (物理引脚31)
    CYCLE_COMPLETE = 24   # 循环完成信号输出 (物理引脚18)
    STATUS_LED = 25       # 连接状态LED输出 (物理引脚22)
    RGB_R = 12            # RGB 红 (物理引脚32，PWM)
    RGB_G = 13            # RGB 绿 (物理引脚33，PWM)
    RGB_B = 19            # RGB 蓝 (物理引脚35，PWM)
```

### 运动序列配置

在 `main.py` 文件中修改 `positions` 列表以调整循环运动序列：

```python
self.positions = [
    [10000, 10000, 0, 0, 0, 0],   # 位置 1
    [0, 0, 0, 0, 0, 0],           # 位置 2
    [0, 0, 10000, 10000, 10000, 10000],  # 位置 3
    [0, 0, 0, 0, 0, 0],           # 位置 4
]
```

### UDP 端口配置

在 `udp_receiver.py` 文件中修改 UDP 端口：

```python
class UDPReceiver:
    def __init__(self, port=7777, callback=None):
        self.port = port
        self.callback = callback
        # ...
```

## 状态指示说明

### RGB 状态灯

| 颜色 | 状态 | 说明 |
|------|------|------|
| 红色 | 错误/断开 | 设备连接失败或出现错误 |
| 黄色 | 未就绪 | 程序初始化中或设备未连接 |
| 绿色 | 就绪 | 设备已连接，等待命令 |
| 蓝色 | 运动中 | 灵巧手正在执行循环运动 |
| 青色 | 手套监听中 | 正在接收手套数据 |

### 状态输出

| 输出 | 状态 | 说明 |
|------|------|------|
| STATUS_LED | 高电平 | 设备已连接 |
| STATUS_LED | 低电平 | 设备未连接 |
| READY_STATUS | 高电平 | 程序就绪 |
| READY_STATUS | 低电平 | 程序未就绪 |
| RUNNING_STATUS | 高电平 | 运动运行中 |
| RUNNING_STATUS | 低电平 | 运动已停止 |
| CYCLE_COMPLETE | 高电平脉冲 | 循环运动完成一次 |

## 贡献指南

我们欢迎社区成员参与项目贡献。如果您希望为项目做出贡献，请遵循以下步骤：

1. **Fork 项目**：在 GitHub 上 fork 本项目到您的个人账户
2. **创建分支**：为您的功能或修复创建一个新的分支
3. **开发**：实现您的功能或修复，并确保代码质量
4. **测试**：运行测试确保您的修改不会破坏现有功能
5. **提交 PR**：提交 Pull Request 到主分支，并详细描述您的修改

### 代码规范
- 为新功能添加文档和注释
- 确保所有修改都有对应的测试用例

## 故障排除

### 常见问题

1. **无法导入 RPi.GPIO**
   - 确保在树莓派上运行
   - 检查是否已安装：`pip list | grep RPi.GPIO`

2. **GPIO 无响应**
   - 检查硬件连接是否正确
   - 确保使用 root 权限运行程序
   - 检查 GPIO 引脚是否被其他程序占用

3. **EtherCAT 连接失败**
   - 检查 EtherCAT 线缆连接
   - 确保以太网卡已启用
   - 检查 LHandPro 设备电源

4. **手套数据接收失败**
   - 检查 UDP 端口设置
   - 确保网络连接正常
   - 检查手套设备是否正常发送数据

### 调试技巧

- 使用 `test_gpio.py` 测试 GPIO 功能
- 使用 `test_glove.py` 测试手套数据接收
- 查看程序输出的日志信息

## 许可证信息

本项目基于 Apache-2.0 许可证开源，详见 LICENSE 文件。

## 更新日志

### v1.0.0 (2023-12-01)
- 初始版本发布
- 支持 EtherCAT 通信和 GPIO 控制
- 实现循环运动和手套数据监听功能

### v1.1.0 (2024-01-15)
- 优化 GPIO 控制逻辑
- 增加手套数据模拟功能
- 完善状态指示系统
- 修复已知 bug

## 致谢

感谢所有为 LHandProLib 项目做出贡献的开发者和用户！