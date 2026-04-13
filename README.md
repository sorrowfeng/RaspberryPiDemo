# RaspberryPiDemo

LHandPro 灵巧手在树莓派场景下的 Python 控制示例工程，支持 `CANFD`、`EtherCAT`、`RS485` 三种通信方式，并提供循环运动、抓握动作、GPIO 触发、手套 UDP 输入等能力。

## 目录结构

```text
RaspberryPiDemo/
├─ main.py                    # 主程序入口
├─ launch.py                  # 多实例启动入口
├─ config.py                  # 当前生效配置
├─ config_support.py          # 配置公共 helper
├─ motion_system/             # 主业务调度层
│  ├─ controller.py
│  ├─ device_session.py
│  ├─ cycle_motion_manager.py
│  ├─ grasp_manager.py
│  ├─ glove_listener_service.py
│  └─ runtime_state.py
├─ configs/                   # 预设配置
│  ├─ README.md
│  └─ config_*.py
├─ tools/                     # 辅助脚本
│  ├─ setup_rs485_mode.py
│  ├─ pack.py
│  ├─ test_gpio.py
│  └─ test_glove.py
├─ assets/                    # 图片等静态资源
│  └─ GPIO.png
├─ lib/                       # 依赖库与驱动资源
├─ logs/                      # 运行日志输出目录
├─ lhandpro_controller.py     # 设备控制封装
├─ gpio_controller.py         # GPIO 封装
├─ udp_receiver.py            # UDP 接收器
├─ lhandprolib_wrapper.py     # SDK Python 封装
├─ lhandprolib_loader.py      # SDK 动态库加载
├─ canfd_lib.py               # CANFD 驱动适配
├─ ethercat_master.py         # EtherCAT 驱动适配
├─ serial_port.py             # RS485 串口适配
├─ log.py                     # 日志初始化
└─ setup.py                   # 菜单式部署/配置脚本
```

## 核心分层

- `main.py`
  负责参数解析、日志初始化和启动 `MotionController`。
- `motion_system/`
  负责运行时调度，是现在的主业务层。
- 顶层 `*_controller.py` / `*_master.py` / `serial_port.py`
  负责设备、总线、GPIO、UDP 等底层能力。
- `config.py` + `configs/`
  负责当前配置和预设配置。
- `tools/`
  放置部署、测试、打包这类辅助脚本，避免主目录被工具文件淹没。

## 配置说明

根目录 [config.py](/D:/Project/PyProject/RaspberryPiDemo/config.py) 和 `configs/` 下的预设文件现在统一使用同一套结构：

- `COMMUNICATION_CONFIG`
- `DEVICE_CONFIG`
- `MOTION_CONFIG`
- `GRASP_CONFIG`
- `FEATURE_FLAGS`

同时仍然保留旧的平铺常量导出，例如：

- `DEFAULT_COMMUNICATION_MODE`
- `DEFAULT_CYCLE_COUNT`
- `CYCLE_MOVE_POSITIONS`
- `GRASP_MODE`
- `AUTO_CONNECT`

这意味着工程内部已有依赖不需要一起重写，仍然可以继续 `from config import DEFAULT_CYCLE_COUNT`。

### 切换预设配置

把目标预设复制为根目录 `config.py` 即可：

```bash
cp configs/config_DH116_CANFD_aging.py config.py
```

常用预设示例：

- `config_DH116_CANFD_aging.py`
- `config_DH116_CANFD_exhibit.py`
- `config_DH116S_CANFD_grasp.py`
- `config_DH116S_CANFD_grasp_aging.py`
- `config_Module_ECAT_aging.py`

## 运行方式

### 直接启动

```bash
sudo python3 main.py -m CANFD
```

参数说明：

- `--communication-mode` / `-m`
  可选 `CANFD`、`ECAT`、`RS485`
- `--device-index` / `-i`
  多实例时用于指定设备索引
- `--enable-gpio` / `-g`
  启用 GPIO
- `--no-enable-gpio`
  禁用 GPIO

### 多实例启动

```bash
sudo python3 launch.py
sudo python3 launch.py -m ECAT -n 1
sudo python3 launch.py -m CANFD -n 4
sudo python3 launch.py -m RS485 -n 4
```

`launch.py` 会读取 [config.py](/D:/Project/PyProject/RaspberryPiDemo/config.py) 中的默认值，也支持命令行覆盖。

## tools 脚本

辅助脚本统一放在 `tools/` 下：

```bash
python3 tools/setup_rs485_mode.py
python3 tools/test_gpio.py
python3 tools/test_glove.py
python3 tools/pack.py
```

## 环境依赖

- Python 3.9+
- `keyboard`
- `pyserial`
- `pysoem`
- `RPi.GPIO`（仅树莓派 GPIO 场景需要）

安装：

```bash
pip install -r requirements.txt
```

## GPIO 与日志

- GPIO 定义见 [gpio_controller.py](/D:/Project/PyProject/RaspberryPiDemo/gpio_controller.py)
- GPIO 接线示意图在 [GPIO.png](/D:/Project/PyProject/RaspberryPiDemo/assets/GPIO.png)
- 日志默认输出到 `logs/`

## 维护建议

- 新增运行预设时，优先在 `configs/` 下添加新的结构化配置文件。
- 新增部署、测试、打包类脚本时，优先放到 `tools/`。
- `motion_system/` 负责流程编排，设备能力尽量留在顶层控制器/驱动模块中。
