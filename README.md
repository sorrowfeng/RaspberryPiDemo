# LHandProLib Python 示例项目

## 项目简介

这是一个基于 LHandProLib 库的 Python 控制示例项目，专为树莓派环境设计，提供了 LHandPro 灵巧手的全面控制解决方案。

- **双通信模式**：支持 CANFD 和 EtherCAT 两种通信协议
- **GPIO 集成**：通过树莓派 GPIO 引脚实现硬件触发控制
- **多功能运动控制**：支持循环运动、抓握动作、手套数据实时控制
- **自动化操作**：自动连接设备、回零、故障检测

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                       应用层                             │
├─────────────────┬─────────────────┬─────────────────────┤
│   main.py       │   launch.py     │  test_gpio.py       │
│                 │                 │  test_glove.py      │
└────────┬────────┴────────┬────────┴──────────┬──────────┘
         │                 │                   │
         ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                       控制层                             │
├──────────────────────┬──────────────┬───────────────────┤
│ lhandpro_controller  │ gpio_controller │ udp_receiver   │
└──────────┬───────────┴──────────────┴───────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│           驱动层                │
├─────────────────┬───────────────┤
│   canfd_lib     │ ethercat_master│
└────────┬────────┴───────┬───────┘
         │                │
         ▼                ▼
┌─────────────────────────────────┐
│           封装层                │
├─────────────────┬───────────────┤
│ lhandprolib_    │ lhandprolib_  │
│ wrapper         │ loader        │
└─────────────────┴───────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                       硬件层                             │
├──────────────────┬──────────────┬───────────────────────┤
│  LHandPro 灵巧手  │ 树莓派 GPIO  │  手套 UDP 数据        │
└──────────────────┴──────────────┴───────────────────────┘
```

## 项目结构

```
RaspberryPiDemo/
├── main.py                   # 主程序，MotionController 核心控制逻辑
├── launch.py                 # 启动脚本（ECAT 单进程 / CANFD 多进程）
├── lhandpro_controller.py    # 灵巧手控制器（连接、运动、回零、报警）
├── gpio_controller.py        # GPIO 管理（6 输入 + 4 输出引脚）
├── udp_receiver.py           # UDP 手套数据接收器
├── canfd_lib.py              # CANFD 通信库封装
├── ethercat_master.py        # EtherCAT 主站库封装（pysoem）
├── lhandprolib_wrapper.py    # LHandProLib C 库的 Python OOP 封装
├── lhandprolib_loader.py     # 动态库跨平台加载器（Win/Linux/Mac）
├── config.py                 # 主配置文件（运动参数、位置序列等）
├── log.py                    # 日志系统（按时间戳轮转、自动清理）
├── requirements.txt          # 依赖项
├── configs/                  # 预设配置文件目录
│   ├── config_DH116_CANFD_exhibit.py    # DH116 CANFD 展览模式
│   ├── config_DH116_CANFD_aging.py      # DH116 CANFD 老化测试
│   ├── config_DH116_ECAT_exhibit.py     # DH116 ECAT 展览模式
│   ├── config_DH116_ECAT_aging.py       # DH116 ECAT 老化测试
│   ├── config_DH116S_CANFD_exhibit.py   # DH116S CANFD 展览模式
│   ├── config_DH116S_CANFD_aging.py     # DH116S CANFD 老化测试
│   ├── config_Module_CANFD_aging.py     # 模块 CANFD 老化测试
│   └── config_Module_ECAT_aging.py      # 模块 ECAT 老化测试
└── README.md
```

## 快速开始

### 环境要求

- **硬件**：树莓派 4B
- **系统**：Ubuntu 20.04
- **Python**：3.9+

### 安装

```bash
git clone <项目地址>
cd RaspberryPiDemo
pip install -r requirements.txt

# 树莓派 GPIO 支持（树莓派专用）
sudo apt-get install python3-rpi.gpio
```

### 运行

```bash
# EtherCAT 模式（单进程，控制 1 个设备）
sudo python3 launch.py --ecat-mode

# CANFD 模式（多进程，最多控制 4 个设备）
sudo python3 launch.py
```

### 命令行参数

| 参数 | 简写 | 描述 | 默认值 |
|------|------|------|--------|
| `--device-index` | `-i` | 设备索引（0-3） | 自动选择 |
| `--communication-mode` | `-m` | 通信模式（CANFD/ECAT） | ECAT |
| `--ecat-mode` | - | 使用 EtherCAT 模式启动 | - |
| `--enable-gpio` | `-g` | 启用 GPIO 控制 | True |
| `--no-enable-gpio` | - | 禁用 GPIO 控制 | - |

## 硬件连接

### 所需硬件

- 树莓派 4B + 电源适配器
- LHandPro 灵巧手（DH116 / DH116S / 模块型）
- CANFD 通信模块（CANFD 模式）或以太网连接（EtherCAT 模式）
- GPIO 按钮和 LED（硬件控制和状态指示）

### GPIO 引脚定义（BCM 编号）

#### 输入引脚

| GPIO | 物理引脚 | 功能 | 说明 |
|------|---------|------|------|
| 17 | 11 | START_MOTION | 开始循环运动 |
| 27 | 13 | STOP_MOTION | 停止运动并回零 |
| 22 | 15 | START_GRASP | 执行抓握动作 |
| 23 | 16 | CONNECT | 连接设备 |
| 24 | 18 | DISCONNECT | 断开设备 |
| 25 | 22 | START_GLOVE_LISTEN | 开始手套监听 |

> 所有输入引脚默认使用下拉电阻，高电平触发。

#### 输出引脚

| GPIO | 物理引脚 | 功能 | 说明 |
|------|---------|------|------|
| 5  | 29 | CYCLE_COMPLETE[0] | 循环完成信号（设备索引 0） |
| 6  | 31 | CYCLE_COMPLETE[1] | 循环完成信号（设备索引 1） |
| 13 | 33 | CYCLE_COMPLETE[2] | 循环完成信号（设备索引 2） |
| 19 | 35 | CYCLE_COMPLETE[3] | 循环完成信号（设备索引 3） |
| 16 | 36 | READY_STATUS | 程序就绪状态 |
| 20 | 38 | RUNNING_STATUS | 运动运行中状态 |
| 21 | 40 | STATUS_LED | 设备连接状态 LED |

## 配置说明

### 配置参数（config.py）

| 参数 | 说明 |
|------|------|
| `DEFAULT_HOME_TIME` | 回零等待时间（秒） |
| `DEFAULT_CYCLE_COUNT` | 循环运动次数 |
| `DEFAULT_CYCLE_VELOCITY` | 循环运动速度 |
| `DEFAULT_CYCLE_INTERVAL` | 相邻位置间隔时间（秒） |
| `DEFAULT_CYCLE_CURRENT` | 最大电流（mA） |
| `CYCLE_MOVE_POSITIONS` | 循环运动位置序列 |
| `CYCLE_FINISH_POSITION` | 循环结束位置 |
| `ENABLE_ALARM_CHECK` | 是否启用报警检测 |

### 切换预设配置

`configs/` 目录提供了 8 种场景的预设配置，覆盖 3 种设备型号 × 2 种通信模式 × 2 种工作模式的组合。直接将目标配置文件覆盖主配置文件即可生效：

```bash
# 示例：切换为 DH116 CANFD 展览模式
cp configs/config_DH116_CANFD_exhibit.py config.py

# 示例：切换为 DH116S ECAT 老化测试
cp configs/config_DH116_ECAT_aging.py config.py
```

| 文件名 | 设备 | 通信 | 模式 |
|--------|------|------|------|
| `config_DH116_CANFD_exhibit.py` | DH116 | CANFD | 展览 |
| `config_DH116_CANFD_aging.py` | DH116 | CANFD | 老化测试 |
| `config_DH116_ECAT_exhibit.py` | DH116 | ECAT | 展览 |
| `config_DH116_ECAT_aging.py` | DH116 | ECAT | 老化测试 |
| `config_DH116S_CANFD_exhibit.py` | DH116S | CANFD | 展览 |
| `config_DH116S_CANFD_aging.py` | DH116S | CANFD | 老化测试 |
| `config_Module_CANFD_aging.py` | 模块型 | CANFD | 老化测试 |
| `config_Module_ECAT_aging.py` | 模块型 | ECAT | 老化测试 |

## 日志系统

日志文件存储于项目根目录的 `logs/` 文件夹，命名格式为 `app_YYYYMMDD_HHMMSS.log`。

- 每次启动自动创建新日志文件
- 自动清理旧日志，最多保留最新 100 个文件
- 文件输出级别：DEBUG；控制台输出级别：INFO

```bash
# 查看最新日志
cat logs/app*.log

# 实时跟踪日志
tail -f logs/app*.log
```

## 依赖项

| 依赖包 | 版本 | 用途 |
|--------|------|------|
| `keyboard` | ~=0.13.5 | 键盘事件监听（ESC 退出） |
| `pysoem` | ~=1.1.12 | EtherCAT 主站通信 |
| `RPi.GPIO` | >=0.7.0 | 树莓派 GPIO 控制 |

## 故障排除

| 问题 | 排查步骤 |
|------|----------|
| GPIO 初始化失败 | 确认运行在树莓派硬件上；确认已安装 `RPi.GPIO`；以 `sudo` 运行或将用户加入 `gpio` 组 |
| 设备连接失败 | 检查通信线缆；确认设备供电正常；确认通信模式与实际硬件一致 |
| 运动控制异常 | 检查电机使能状态；确认设备已回零；查看日志中的报警信息并清除报警 |

## 注意事项

1. **安全操作**：运行前确保灵巧手周围无障碍物，避免造成人员伤害或设备损坏
2. **权限要求**：GPIO 操作需要 `sudo` 权限；非树莓派平台请使用 `--no-enable-gpio` 禁用 GPIO
3. **通信选择**：根据实际硬件连接选择正确的通信模式（CANFD/ECAT）和设备索引

## 许可证

本项目采用 Apache-2.0 许可证。
