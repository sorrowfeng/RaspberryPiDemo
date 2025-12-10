"""
树莓派 GPIO 控制类
用于监控GPIO输入和控制GPIO输出
"""

import time
import threading
import platform
from typing import Optional, Callable, Dict, Tuple
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("警告: RPi.GPIO 未安装，GPIO功能将不可用")


def _is_raspberry_pi() -> bool:
    """检测是否在树莓派上运行"""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            cpuinfo = f.read()
            return 'Raspberry Pi' in cpuinfo or 'BCM' in cpuinfo
    except:
        # 也可以通过平台架构判断
        machine = platform.machine().lower()
        return 'arm' in machine or 'aarch64' in machine


class GPIOController:
    """树莓派 GPIO 控制器类"""

    def __init__(self):
        """初始化GPIO控制器"""
        if not GPIO_AVAILABLE:
            raise RuntimeError("RPi.GPIO 库未安装，无法使用GPIO功能")
        
        # 检测是否在树莓派上运行
        if not _is_raspberry_pi():
            raise RuntimeError(
                "❌ 错误: 检测到不在树莓派硬件上运行！\n"
                "RPi.GPIO 库只能在树莓派硬件上使用。\n"
                "当前平台: {}\n"
                "请确保在树莓派上运行此程序。".format(platform.platform())
            )
        
        try:
            # 使用BCM编号模式
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
        except RuntimeError as e:
            # 捕获 RPi.GPIO 的运行时错误（如 "Not running on a RPi!"）
            error_msg = str(e)
            if "Not running on a RPi" in error_msg or "not running on a RPi" in error_msg:
                raise RuntimeError(
                    "❌ 错误: RPi.GPIO 检测到不在树莓派硬件上运行！\n"
                    "RPi.GPIO 库只能在树莓派硬件上使用。\n"
                    "当前平台: {}\n"
                    "请确保在树莓派上运行此程序。\n"
                    "如果确实在树莓派上运行，请检查:\n"
                    "  1. 是否正确安装了 RPi.GPIO: pip install RPi.GPIO\n"
                    "  2. 是否有足够的权限: sudo python3 或加入 gpio 组\n"
                    "  3. GPIO 是否被其他程序占用".format(platform.platform())
                ) from e
            else:
                raise
        
        # 存储GPIO状态
        self.input_pins: Dict[int, bool] = {}  # pin -> 是否已设置
        self.output_pins: Dict[int, bool] = {}  # pin -> 当前状态
        self.callbacks: Dict[int, Callable] = {}  # pin -> 回调函数
        self.last_trigger_time: Dict[int, float] = {}  # pin -> 上次触发时间
        self.debounce_ms: Dict[int, int] = {}  # pin -> 防抖时间(ms)
        self.rgb_pwm: Optional[Tuple[GPIO.PWM, GPIO.PWM, GPIO.PWM]] = None
        self.rgb_pins: Optional[Tuple[int, int, int]] = None
        
        # 监控线程
        self.monitor_thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.monitor_interval = 0.01  # 10ms轮询间隔
        
        # 线程锁
        self.lock = threading.Lock()

    def setup_input(self, pin: int, pull_up_down: int = GPIO.PUD_DOWN, 
                   callback: Optional[Callable] = None, edge: int = GPIO.RISING,
                   debounce_ms: int = 300):
        """
        设置GPIO输入引脚

        Args:
            pin: GPIO引脚号（BCM编号）
            pull_up_down: 上拉/下拉设置 (GPIO.PUD_UP, GPIO.PUD_DOWN, GPIO.PUD_OFF)
            callback: 触发时的回调函数
            edge: 触发边沿 (GPIO.RISING, GPIO.FALLING, GPIO.BOTH)
        """
        if pin in self.input_pins:
            print(f"GPIO {pin} 已经设置为输入")
            return

        GPIO.setup(pin, GPIO.IN, pull_up_down=pull_up_down)
        self.input_pins[pin] = True
        self.debounce_ms[pin] = debounce_ms
        self.last_trigger_time[pin] = 0.0
        
        if callback:
            self.callbacks[pin] = callback
            # 使用硬件中断（如果可用）
            try:
                GPIO.add_event_detect(pin, edge, callback=self._gpio_callback, bouncetime=debounce_ms)
            except Exception as e:
                print(f"无法使用硬件中断，将使用轮询模式: {e}")
                # 如果硬件中断失败，使用轮询模式
                self._start_monitor_thread()

    def setup_output(self, pin: int, initial: bool = False):
        """
        设置GPIO输出引脚

        Args:
            pin: GPIO引脚号（BCM编号）
            initial: 初始输出状态（True=高电平，False=低电平）
        """
        if pin in self.output_pins:
            print(f"GPIO {pin} 已经设置为输出")
            return

        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if initial else GPIO.LOW)
        self.output_pins[pin] = initial
        print(f"GPIO {pin} 设置为输出，初始状态: {'HIGH' if initial else 'LOW'}")

    # ---------------- RGB PWM 输出 ----------------
    def setup_rgb_pwm(self, r_pin: int, g_pin: int, b_pin: int, freq: int = 1000):
        """
        设置RGB三色PWM输出

        Args:
            r_pin: 红色通道GPIO
            g_pin: 绿色通道GPIO
            b_pin: 蓝色通道GPIO
            freq: PWM频率，默认1000Hz
        """
        # 初始化引脚
        for pin in (r_pin, g_pin, b_pin):
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        r_pwm = GPIO.PWM(r_pin, freq)
        g_pwm = GPIO.PWM(g_pin, freq)
        b_pwm = GPIO.PWM(b_pin, freq)

        r_pwm.start(0)
        g_pwm.start(0)
        b_pwm.start(0)

        self.rgb_pwm = (r_pwm, g_pwm, b_pwm)
        self.rgb_pins = (r_pin, g_pin, b_pin)
        print(f"RGB PWM 已启动: R={r_pin}, G={g_pin}, B={b_pin}, freq={freq}Hz")

    def set_rgb_color(self, r: int, g: int, b: int):
        """
        设置RGB颜色，0-255
        """
        if not self.rgb_pwm:
            print("RGB PWM 未初始化")
            return
        r_pwm, g_pwm, b_pwm = self.rgb_pwm
        r_pwm.ChangeDutyCycle(max(0, min(100, r / 255 * 100)))
        g_pwm.ChangeDutyCycle(max(0, min(100, g / 255 * 100)))
        b_pwm.ChangeDutyCycle(max(0, min(100, b / 255 * 100)))

    def set_rgb_off(self):
        """关闭RGB"""
        self.set_rgb_color(0, 0, 0)

    def output_high(self, pin: int, duration: Optional[float] = None):
        """
        输出高电平

        Args:
            pin: GPIO引脚号
            duration: 持续时间（秒），如果为None则保持高电平
        """
        if pin not in self.output_pins:
            print(f"GPIO {pin} 未设置为输出")
            return

        with self.lock:
            GPIO.output(pin, GPIO.HIGH)
            self.output_pins[pin] = True

        if duration:
            threading.Thread(
                target=self._output_timer,
                args=(pin, duration),
                daemon=True
            ).start()

    def output_low(self, pin: int):
        """
        输出低电平

        Args:
            pin: GPIO引脚号
        """
        if pin not in self.output_pins:
            print(f"GPIO {pin} 未设置为输出")
            return

        with self.lock:
            GPIO.output(pin, GPIO.LOW)
            self.output_pins[pin] = False

    def output_pulse(self, pin: int, duration: float = 0.5):
        """
        输出一个脉冲（高电平 -> 低电平）

        Args:
            pin: GPIO引脚号
            duration: 高电平持续时间（秒）
        """
        self.output_high(pin, duration)

    def read_input(self, pin: int) -> bool:
        """
        读取输入引脚状态

        Args:
            pin: GPIO引脚号

        Returns:
            bool: True=高电平，False=低电平
        """
        if pin not in self.input_pins:
            print(f"GPIO {pin} 未设置为输入")
            return False

        return GPIO.input(pin) == GPIO.HIGH

    def _gpio_callback(self, pin: int):
        """GPIO硬件中断回调函数，增加软件防抖"""
        now = time.time()
        last = self.last_trigger_time.get(pin, 0.0)
        debounce = self.debounce_ms.get(pin, 0)
        if (now - last) * 1000 < debounce:
            return
        self.last_trigger_time[pin] = now

        if pin in self.callbacks:
            try:
                self.callbacks[pin]()
            except Exception as e:
                print(f"GPIO {pin} 回调函数执行错误: {e}")

    def _start_monitor_thread(self):
        """启动轮询监控线程（备用方案）"""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return

        self.stop_flag.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _monitor_loop(self):
        """轮询监控循环"""
        last_states = {}
        
        while not self.stop_flag.is_set():
            for pin in self.input_pins.keys():
                if pin in self.callbacks:
                    current_state = self.read_input(pin)
                    last_state = last_states.get(pin, False)
                    
                    # 检测上升沿 + 防抖
                    if current_state and not last_state:
                        now = time.time()
                        last = self.last_trigger_time.get(pin, 0.0)
                        debounce = self.debounce_ms.get(pin, 0)
                        if (now - last) * 1000 >= debounce:
                            self.last_trigger_time[pin] = now
                            try:
                                self.callbacks[pin]()
                            except Exception as e:
                                print(f"GPIO {pin} 回调函数执行错误: {e}")
                    
                    last_states[pin] = current_state
            
            time.sleep(self.monitor_interval)

    def _output_timer(self, pin: int, duration: float):
        """输出定时器线程"""
        time.sleep(duration)
        self.output_low(pin)

    def cleanup(self):
        """清理GPIO资源"""
        self.stop_flag.set()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        
        # 将所有输出设置为低电平
        for pin in self.output_pins.keys():
            try:
                GPIO.output(pin, GPIO.LOW)
            except:
                pass
        
        GPIO.cleanup()
        # 停止RGB PWM
        if self.rgb_pwm:
            for pwm in self.rgb_pwm:
                try:
                    pwm.stop()
                except:
                    pass
        self.input_pins.clear()
        self.output_pins.clear()
        self.callbacks.clear()
        self.rgb_pwm = None
        self.rgb_pins = None
        print("GPIO资源已清理")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动清理"""
        self.cleanup()
        return False


# GPIO引脚定义（使用常规GPIO，避开复用功能引脚）
class GPIO_PINS:
    """
    GPIO引脚定义常量类
    使用BCM编号模式，选择常规GPIO引脚，避开I2C、SPI、UART、PCM、PWM等复用功能
    
    参考: https://pinout.vvzero.com/
    
    输入引脚（物理引脚位置）:
    - GPIO 17 (物理引脚11) - 常规GPIO
    - GPIO 27 (物理引脚13) - 常规GPIO  
    - GPIO 22 (物理引脚15) - 常规GPIO
    - GPIO 23 (物理引脚16) - 常规GPIO
    
    输出引脚（物理引脚位置）:
    - GPIO 5  (物理引脚29) - 常规GPIO
    - GPIO 6  (物理引脚31) - 常规GPIO
    - GPIO 24 (物理引脚18) - 常规GPIO
    - GPIO 25 (物理引脚22) - 常规GPIO
    - GPIO 12 (物理引脚32) - 硬件PWM
    - GPIO 13 (物理引脚33) - 硬件PWM
    - GPIO 19 (物理引脚35) - 硬件PWM
    """
    # 输入引脚定义（常规GPIO，无复用功能）
    START_MOTION = 17     # 开始循环运动 (物理引脚11)
    STOP_MOTION = 27      # 停止运动并回到0 (物理引脚13)
    CONNECT = 22          # 连接设备 (物理引脚15)
    DISCONNECT = 23       # 断开连接 (物理引脚16)
    START_GLOVE_LISTEN = 26  # 开始手套监听 (物理引脚37)
    
    # 输出引脚定义（常规GPIO，无复用功能）
    READY_STATUS = 5      # 程序已准备好/待命状态 (物理引脚29)
    RUNNING_STATUS = 6    # 循环运行中状态 (物理引脚31)
    CYCLE_COMPLETE = 24   # 循环完成信号输出 (物理引脚18)
    STATUS_LED = 25       # 连接状态LED输出 (物理引脚22)
    RGB_R = 12            # RGB 红 (物理引脚32，PWM)
    RGB_G = 13            # RGB 绿 (物理引脚33，PWM)
    RGB_B = 19            # RGB 蓝 (物理引脚35，PWM)

