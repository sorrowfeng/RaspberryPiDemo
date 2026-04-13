"""Quick GPIO output pulse test."""

import sys
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("Warning: RPi.GPIO is not installed; hardware GPIO test cannot run.")


def main() -> int:
    if GPIO is None:
        return 1

    pin = 5
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(pin, GPIO.OUT)

    for _ in range(5):
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.5)
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
