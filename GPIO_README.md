# GPIO控制使用说明

## 概述

本程序集成了树莓派GPIO控制功能，可以通过GPIO输入触发各种操作，并通过GPIO输出反馈状态。

## GPIO引脚定义

**注意**: 本程序使用 **BCM编号模式**（Broadcom编号），不是物理引脚编号。

### 输入引脚（需要外部触发，默认下拉）

| GPIO (BCM) | 物理引脚 | 功能 | 说明 |
|-----------|---------|------|------|
| GPIO 17 | 引脚 11 | START_MOTION | 触发时开始循环运动 |
| GPIO 27 | 引脚 13 | STOP_MOTION | 触发时停止运动并回到0位置 |
| GPIO 22 | 引脚 15 | CONNECT | 触发时连接设备 |
| GPIO 23 | 引脚 16 | DISCONNECT | 触发时断开设备连接 |

### 输出引脚

| GPIO (BCM) | 物理引脚 | 功能 | 说明 |
|-----------|---------|------|------|
| GPIO 24 | 引脚 18 | CYCLE_COMPLETE | 每次循环完成时输出0.5秒高电平脉冲 |
| GPIO 25 | 引脚 22 | STATUS_LED | 设备连接状态LED（连接=高电平，断开=低电平） |
| GPIO 5  | 引脚 29 | READY_STATUS | 程序已准备好/待命状态 |
| GPIO 6  | 引脚 31 | RUNNING_STATUS | 循环运行中状态 |
| GPIO 12 | 引脚 32 | RGB_R | RGB红色通道（PWM） |
| GPIO 13 | 引脚 33 | RGB_G | RGB绿色通道（PWM） |
| GPIO 19 | 引脚 35 | RGB_B | RGB蓝色通道（PWM） |

**引脚选择说明**: 所有引脚均为常规GPIO，避开了I2C、SPI、UART、PCM、PWM等复用功能引脚，确保稳定可靠。

参考引脚定义: https://pinout.vvzero.com/

## 使用方法

### 1. 安装依赖

```bash
# 安装RPi.GPIO库（树莓派上）
sudo apt-get update
sudo apt-get install python3-rpi.gpio
# 或使用pip
pip install RPi.GPIO
```

### 2. 硬件连接

- **输入引脚**: 连接到按钮或开关，另一端连接到GND（下拉模式）
- **输出引脚**: 可以连接到LED（通过限流电阻）或其他设备

### 3. 运行程序

```bash
python3 main.py
```

### 4. 操作流程

1. **连接设备**: 触发 GPIO 22 / 物理引脚15 (CONNECT) 连接LHandPro设备
2. **开始运动**: 触发 GPIO 17 / 物理引脚11 (START_MOTION) 开始循环运动
3. **停止运动**: 触发 GPIO 27 / 物理引脚13 (STOP_MOTION) 停止运动并回到0位置
4. **断开连接**: 触发 GPIO 23 / 物理引脚16 (DISCONNECT) 断开设备连接

### 5. 状态反馈

- **GPIO 24 / 物理引脚18 (CYCLE_COMPLETE)**: 每次完成一个运动循环时，会输出0.5秒的高电平脉冲
- **GPIO 25 / 物理引脚22 (STATUS_LED)**: 
  - 高电平 = 设备已连接
  - 低电平 = 设备未连接
- **GPIO 5 / 物理引脚29 (READY_STATUS)**: 
  - 高电平 = 程序已准备好/待命状态
  - 低电平 = 程序未准备好
- **GPIO 6 / 物理引脚31 (RUNNING_STATUS)**: 
  - 高电平 = 循环运动中
  - 低电平 = 未在运动
- **RGB LED**: 通过颜色表示不同的设备和运行状态
  - **黄色**: 设备断开/未就绪状态
  - **绿色**: 设备连接成功/待命状态
  - **蓝色**: 循环运动运行中
  - **红色**: 检测到电机报警

## 修改GPIO引脚定义

如果需要修改GPIO引脚定义，请编辑 `gpio_controller.py` 文件中的 `GPIO_PINS` 类：

```python
class GPIO_PINS:
    # 输入引脚定义（BCM编号）
    START_MOTION = 17     # 开始循环运动 (物理引脚11)
    STOP_MOTION = 27      # 停止运动并回到0 (物理引脚13)
    CONNECT = 22          # 连接设备 (物理引脚15)
    DISCONNECT = 23       # 断开连接 (物理引脚16)
    
    # 输出引脚定义（BCM编号）
    READY_STATUS = 5      # 程序已准备好/待命状态 (物理引脚29)
    RUNNING_STATUS = 6    # 循环运行中状态 (物理引脚31)
    CYCLE_COMPLETE = 24   # 循环完成信号输出 (物理引脚18)
    STATUS_LED = 25       # 连接状态LED输出 (物理引脚22)
    RGB_R = 12            # RGB 红 (物理引脚32，PWM)
    RGB_G = 13            # RGB 绿 (物理引脚33，PWM)
    RGB_B = 19            # RGB 蓝 (物理引脚35，PWM)
```

**建议**: 选择常规GPIO引脚，避开I2C、SPI、UART、PCM、PWM等复用功能引脚。参考: https://pinout.vvzero.com/

## 注意事项

1. **GPIO编号**: 本程序使用BCM编号模式（Broadcom编号），不是物理引脚编号
   - BCM编号：GPIO 17, 27, 22, 23, 24, 25
   - 物理引脚：11, 13, 15, 16, 18, 22
   - 参考: https://pinout.vvzero.com/
2. **引脚选择**: 所有引脚均为常规GPIO，避开了I2C、SPI、UART、PCM、PWM等复用功能
3. **权限**: 运行程序可能需要root权限或GPIO组权限
4. **防抖**: 输入引脚已设置200ms防抖时间
5. **线程安全**: 所有GPIO操作都是线程安全的

## 故障排除

1. **无法导入RPi.GPIO**: 
   - 确保在树莓派上运行
   - 检查是否已安装: `pip list | grep RPi.GPIO`

2. **GPIO无响应**:
   - 检查硬件连接是否正确
   - 检查GPIO引脚是否被其他程序占用
   - 尝试使用 `gpio readall` 命令检查GPIO状态

3. **权限错误**:
   - 使用sudo运行: `sudo python3 main.py`
   - 或将用户添加到gpio组: `sudo usermod -a -G gpio $USER`

4. **电机报警**:
   - 如果RGB灯显示红色，表示检测到电机报警
   - 检查电机是否过载或出现其他故障
   - 可尝试重启设备或使用程序中的报警清除功能
   - 报警时会自动停止循环运动，确保安全

