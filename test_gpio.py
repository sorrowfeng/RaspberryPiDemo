"""
GPIO功能测试程序
"""

import sys
import time
import threading
import keyboard
from gpio_controller import GPIOController, GPIO_PINS
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("警告: RPi.GPIO 未安装，无法运行硬件GPIO测试")


def main():
    pin = 5
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(pin, GPIO.OUT)
    for _ in range(5):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.5)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())

