"""One EtherCAT master process controlling multiple slaves (hands)."""

import logging
import threading
import time

import keyboard

from app.config import FEATURE_FLAGS
from app.log import logging_context, set_process_logging_context
from app.runtime_control import complete_control_command, read_control_command
from device.ethercat_master import EthercatMaster
from device.gpio_controller import GPIO_AVAILABLE, GPIO_PINS, GPIOController

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

from .controller import MotionController


class EcatMultiHandController:
    """Compose one EtherCAT master with one MotionController per slave.

    ``launch.py`` starts a single process for ECAT. This class scans the bus,
    binds each selected slave to its own LHandProLib instance through a shared
    EtherCAT master, and fans GPIO start/stop commands out to all hands.
    """

    def __init__(
        self,
        device_index: int = None,
        enable_gpio: bool = True,
        ecat_slave_ids=None,
    ):
        self.communication_mode = "ECAT"
        self.device_index = device_index
        self.enable_gpio = enable_gpio
        self.ecat_slave_ids = ecat_slave_ids
        self.ec_master = None
        self.gpio = None
        self.hands = []
        self.session = None
        self.config_switcher = None
        self.glove_service = None
        self.shutdown_requested = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleaned_up = False

    # ------------------------------------------------------------------ public
    def request_shutdown(self, reason: str = ""):
        if reason:
            logging.info("收到退出请求: %s", reason)
        else:
            logging.info("收到退出请求")
        self.shutdown_requested.set()
        for hand in self.hands:
            hand.request_shutdown()

    def start_managed_cycle(self, command=None):
        payload = (command or {}).get("payload") or {}
        if not self.hands and not self._ensure_ready(
            enable_inputs=False,
            connect_retry_interval_seconds=payload.get(
                "connect_retry_interval_seconds", 0.0
            ),
            connect_deadline_monotonic=payload.get(
                "connect_deadline_monotonic"
            ),
        ):
            return False, "EtherCAT 主站/从站初始化失败"
        started = 0
        all_ok = True
        for index, hand in enumerate(self.hands):
            # 进度只由第一只手写一次，避免多个实例争用同一个 progress 文件。
            hand_command = command if index == 0 else None
            try:
                ok, message = hand.start_managed_cycle(hand_command)
            except Exception as exc:  # noqa: BLE001
                logging.exception("EtherCAT 从站启动失败: index=%s, error=%s", index, exc)
                ok, message = False, str(exc)
            if ok:
                started += 1
            else:
                all_ok = False
                logging.error(
                    "EtherCAT 从站启动失败: slave_id=%s, message=%s",
                    hand.session.controller.ecat_slave_id,
                    message,
                )
        if started == 0:
            return False, "全部从站启动失败"
        return True, "全部从站已启动" if all_ok else "部分从站启动失败"

    def stop_managed_cycle(self):
        if not self.hands:
            return False, "没有可控制的 EtherCAT 从站"
        all_ok = True
        for index, hand in enumerate(self.hands):
            try:
                ok, message = hand.stop_managed_cycle()
            except Exception as exc:  # noqa: BLE001
                logging.exception("EtherCAT 从站停止失败: index=%s, error=%s", index, exc)
                ok, message = False, str(exc)
            if not ok:
                all_ok = False
                logging.error(
                    "EtherCAT 从站停止失败: slave_id=%s, message=%s",
                    hand.session.controller.ecat_slave_id,
                    message,
                )
        return all_ok, "全部从站已停止" if all_ok else "部分从站停止失败"

    def run(self, managed_control: bool = False):
        logging.info("=" * 50)
        logging.info("LHandPro EtherCAT 多从站控制程序")
        logging.info("=" * 50)

        # 托管模式下 main.py 在物理上电前启动，不能立刻扫描主站；等
        # start_cycle 命令到达后再初始化 EtherCAT/从站。
        if not managed_control:
            if not self._ensure_ready(enable_inputs=True):
                return 1
            self._auto_connect_all()
        else:
            logging.info("main.py 进入电源通断托管模式，等待外部控制命令")

        try:
            while True:
                if self.shutdown_requested.is_set():
                    logging.info("检测到退出请求，准备退出主循环")
                    break
                if managed_control:
                    self._poll_control_command()
                else:
                    for hand in self.hands:
                        hand._retry_auto_connect_if_needed()
                if keyboard.is_pressed("esc"):
                    logging.info("Esc 键按下，正在退出...")
                    break
                time.sleep(0.1)
        except KeyboardInterrupt:
            logging.info("程序被用户中断")
        finally:
            self._cleanup()

        return 0

    # --------------------------------------------------------------- bus setup
    def _ensure_ready(
        self,
        *,
        enable_inputs: bool,
        connect_retry_interval_seconds: float = 0.0,
        connect_deadline_monotonic=None,
    ) -> bool:
        if not self.hands:
            if not self._initialize_bus(
                connect_retry_interval_seconds=connect_retry_interval_seconds,
                connect_deadline_monotonic=connect_deadline_monotonic,
            ):
                return False
            if not self._create_hands():
                self._stop_master()
                return False
            self._setup_gpio(enable_inputs=enable_inputs)
        if self.enable_gpio and self.session is not None:
            self.session.set_disconnected_status()
        return True

    def _initialize_bus(
        self,
        *,
        connect_retry_interval_seconds: float = 0.0,
        connect_deadline_monotonic=None,
    ) -> bool:
        if self.ec_master is not None:
            return True
        master = EthercatMaster()
        names = master.scanNetworkInterfaces()
        logging.info("找到 EtherCAT 网口数量：%s", len(names))
        if not names:
            logging.error("未找到可用于 EtherCAT 的网口")
            return False

        channel_index = self.device_index
        if channel_index is None:
            channel_index = 0
        if not (0 <= channel_index < len(names)):
            logging.error(
                "EtherCAT 网口索引无效: channel_index=%s, interface_count=%s",
                channel_index,
                len(names),
            )
            return False

        logger_channel = names[channel_index]
        logging.info("EtherCAT 使用网口: [%s] %s", channel_index, logger_channel)
        if not master.init(
            channel_index,
            names,
            discovery_retry_interval_seconds=connect_retry_interval_seconds,
            discovery_deadline_monotonic=connect_deadline_monotonic,
        ):
            logging.error("EtherCAT 主站初始化失败: interface=%s", logger_channel)
            master.stop()
            return False
        if not master.start():
            logging.error("EtherCAT 主站启动失败: interface=%s", logger_channel)
            master.stop()
            return False

        master.run()
        if not master.isConnected():
            logging.error("EtherCAT 主站未进入运行状态: interface=%s", logger_channel)
            master.stop()
            return False

        self.ec_master = master
        logging.info(
            "EtherCAT 主站就绪: interface=%s, slaves=%s",
            logger_channel,
            master.getSlaveCount(),
        )
        return True

    def _resolve_slave_ids(self):
        slave_count = self.ec_master.getSlaveCount()
        if slave_count <= 0:
            logging.error("EtherCAT 未发现任何从站")
            return []

        configured = self.ecat_slave_ids
        if configured is None:
            ids = list(range(1, slave_count + 1))
        elif isinstance(configured, int):
            ids = [configured]
        else:
            try:
                ids = [int(value) for value in configured]
            except (TypeError, ValueError):
                logging.error("ECAT_SLAVE_IDS 配置无效: %r", configured)
                return []

        invalid = [value for value in ids if not (1 <= value <= slave_count)]
        if invalid:
            logging.error(
                "ECAT_SLAVE_IDS 超出从站数量: ids=%s, slave_count=%s",
                ids,
                slave_count,
            )
            return []
        if not ids:
            logging.error("ECAT_SLAVE_IDS 为空")
            return []

        # 去重并保持配置顺序，避免重复控制同一只手。
        unique_ids = []
        for value in ids:
            if value not in unique_ids:
                unique_ids.append(value)
        return unique_ids

    def _create_hands(self) -> bool:
        slave_ids = self._resolve_slave_ids()
        if not slave_ids:
            return False

        slave_info = {item["index"]: item for item in self.ec_master.getSlaveInfoList()}
        for slave_id in slave_ids:
            logging.info(
                "EtherCAT 从站: slave_id=%s, name=%s",
                slave_id,
                slave_info.get(slave_id, {}).get("name", "-"),
            )

        if self.enable_gpio and GPIO_AVAILABLE:
            try:
                self.gpio = GPIOController()
            except RuntimeError as exc:
                logging.warning("GPIO 初始化失败，GPIO 功能已自动禁用: %s", exc)
                self.gpio = None
        else:
            self.gpio = None
        self.enable_gpio = self.gpio is not None

        for index, slave_id in enumerate(slave_ids):
            hand = MotionController(
                communication_mode="ECAT",
                device_index=self.device_index,
                enable_gpio=self.enable_gpio,
                ec_master=self.ec_master,
                ecat_slave_id=slave_id,
                gpio=self.gpio,
                owns_gpio=False,
                cycle_complete_index=index,
            )
            self.hands.append(hand)

        self.session = self.hands[0].session
        self.config_switcher = self.hands[0].config_switcher
        self.glove_service = self.hands[0].glove_service
        return True

    # ------------------------------------------------------------------- GPIO
    def _setup_gpio(self, *, enable_inputs: bool = True):
        if not self.gpio or GPIO is None:
            self._log_gpio_summary()
            return

        if enable_inputs:
            self._setup_gpio_inputs()
        else:
            logging.info("托管模式禁用 GPIO 业务输入，仅保留状态/循环完成输出")

        for hand in self.hands:
            self.gpio.setup_output(hand.session.cycle_complete_pin, initial=False)
        self.gpio.setup_output(GPIO_PINS.STATUS_LED, initial=False)
        self.gpio.setup_output(GPIO_PINS.READY_STATUS, initial=False)
        self.gpio.setup_output(GPIO_PINS.RUNNING_STATUS, initial=False)
        self._log_gpio_summary()

    def _setup_gpio_inputs(self):
        self.gpio.setup_input(
            GPIO_PINS.START_MOTION,
            callback=self.on_start_motion,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.gpio.setup_input(
            GPIO_PINS.STOP_MOTION,
            callback=self.on_stop_motion,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.gpio.setup_input(
            GPIO_PINS.CONNECT,
            callback=self.on_connect_device,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.gpio.setup_input(
            GPIO_PINS.DISCONNECT,
            callback=self.on_disconnect_device,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.gpio.setup_input(
            GPIO_PINS.START_GLOVE_LISTEN,
            callback=self.on_start_glove_listen,
            pull_up_down=GPIO.PUD_DOWN,
        )
        self.gpio.setup_input(
            GPIO_PINS.SWITCH_CONFIG,
            callback=self.config_switcher.on_button_press,
            pull_up_down=GPIO.PUD_DOWN,
            edge=GPIO.BOTH,
        )
        edge = self.hands[0].grasp_manager.resolve_gpio_edge(GPIO)
        self.gpio.setup_input(
            GPIO_PINS.START_GRASP,
            callback=self.on_start_grasp,
            pull_up_down=GPIO.PUD_DOWN,
            edge=edge,
        )

    def _log_gpio_summary(self):
        if not self.enable_gpio:
            logging.info("GPIO 未启用，多从站仅自动连接/循环")
            return
        logging.info("EtherCAT 多从站 GPIO:")
        logging.info("  GPIO %s: 全部从站开始循环", GPIO_PINS.START_MOTION)
        logging.info("  GPIO %s: 全部从站停止并回零", GPIO_PINS.STOP_MOTION)
        logging.info("  GPIO %s: 全部从站连接", GPIO_PINS.CONNECT)
        logging.info("  GPIO %s: 全部从站断开", GPIO_PINS.DISCONNECT)
        logging.info("  GPIO %s: 开始手套监听（第一只手）", GPIO_PINS.START_GLOVE_LISTEN)
        logging.info("  GPIO %s: 全部从站抓握", GPIO_PINS.START_GRASP)
        for hand in self.hands:
            logging.info(
                "  slave_id=%s: 循环完成信号 GPIO %s",
                hand.session.controller.ecat_slave_id,
                hand.session.cycle_complete_pin,
            )

    def on_start_motion(self):
        logging.info("GPIO 触发: 全部 EtherCAT 从站开始循环运动")
        results = [hand.on_start_motion() for hand in self.hands]
        return all(results)

    def on_stop_motion(self):
        logging.info("GPIO 触发: 全部 EtherCAT 从站停止运动并回零")
        results = [hand.on_stop_motion() for hand in self.hands]
        return all(results)

    def on_connect_device(self):
        logging.info("GPIO 触发: 连接全部 EtherCAT 从站")
        for hand in self.hands:
            hand.on_connect_device()

    def on_disconnect_device(self):
        logging.info("GPIO 触发: 断开全部 EtherCAT 从站")
        for hand in self.hands:
            hand.on_disconnect_device()

    def on_start_glove_listen(self):
        # UDP 手套只有一个接收端口，默认跟随第一只手。
        if self.glove_service:
            self.glove_service.start()

    def on_start_grasp(self):
        logging.info("GPIO 触发: 全部 EtherCAT 从站执行抓握")
        for hand in self.hands:
            hand.on_start_grasp()

    # ------------------------------------------------------------ auto connect
    def _auto_connect_all(self):
        if not FEATURE_FLAGS["auto_connect"]:
            logging.info("自动连接已禁用，等待手动连接")
            if self.enable_gpio:
                self.session.set_disconnected_status()
            else:
                logging.error("自动连接已禁用且 GPIO 未启用，程序退出")
            return

        # 先让所有手完成连接/回零，再统一开始循环，避免第一只手先动、
        # 其它手还在初始化。
        connected_hands = []
        for hand in self.hands:
            if hand._auto_connect_once(start_cycle=False):
                connected_hands.append(hand)
            else:
                hand._next_auto_connect_at = (
                    time.monotonic()
                    + hand.AUTO_CONNECT_RETRY_INTERVAL_SECONDS
                )

        if FEATURE_FLAGS["auto_cycle_running"]:
            for hand in connected_hands:
                logging.info(
                    "多从站同步启动: slave_id=%s",
                    hand.session.controller.ecat_slave_id,
                )
                hand.on_start_motion()

    # --------------------------------------------------------------- control
    def _handle_control_command(self, command):
        action = command.get("action")
        if action == "start_cycle":
            return self.start_managed_cycle(command)
        if action == "stop_cycle":
            return self.stop_managed_cycle()
        if action == "shutdown":
            self.request_shutdown("control command")
            return True, "已请求 main.py 退出"
        return False, f"未知控制命令: {action}"

    def _poll_control_command(self):
        device_index = self.session.device_index if self.session else self.device_index
        command = read_control_command(self.communication_mode, device_index)
        if not command:
            return

        command_log_context = command.get("log_context") or {}
        set_process_logging_context(
            cycle=command_log_context.get("cycle"),
            command_id=command.get("id"),
        )
        with logging_context(
            cycle=command_log_context.get("cycle"),
            command_id=command.get("id"),
        ):
            logging.info(
                "收到控制命令: action=%s, id=%s",
                command.get("action"),
                command.get("id"),
            )
            try:
                ok, message = self._handle_control_command(command)
            except Exception as exc:  # noqa: BLE001
                logging.exception("执行控制命令异常: %s", exc)
                ok = False
                message = str(exc)

            complete_control_command(
                self.communication_mode,
                device_index,
                command,
                ok,
                message,
            )

    # ---------------------------------------------------------------- cleanup
    def _stop_master(self):
        master = self.ec_master
        self.ec_master = None
        if master is not None:
            try:
                master.stop()
            except Exception as exc:  # noqa: BLE001
                logging.exception("停止 EtherCAT 主站异常: %s", exc)

    def _cleanup(self):
        with self._cleanup_lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True

        logging.info("正在清理 EtherCAT 多从站资源...")
        for hand in self.hands:
            try:
                if not hand.cycle_manager.wait_until_stopped():
                    logging.error(
                        "EtherCAT 从站循环线程未停止: slave_id=%s",
                        hand.session.controller.ecat_slave_id,
                    )
                hand.glove_service.stop()
                if hand.session.controller.is_connected:
                    hand.session.stop_and_settle()
                hand.session.disconnect()
                hand.session.set_disconnected_status()
            except Exception as exc:  # noqa: BLE001
                logging.exception("清理 EtherCAT 从站异常: %s", exc)

        if self.gpio is not None:
            try:
                self.gpio.cleanup()
            except Exception as exc:  # noqa: BLE001
                logging.exception("清理共享 GPIO 异常: %s", exc)
        self._stop_master()
        logging.info("EtherCAT 多从站资源清理完成")


__all__ = ["EcatMultiHandController"]
