#!/usr/bin/env python3
"""Configure all detected USB-to-RS485 adapters into RS485 mode."""

import glob
import subprocess
import sys

UTIL_PATH = "/home/ubuntu/Documents/ll-usb2rs485-driver/Utility/utek_gpio_mode_select_util/utek_gpio_mode_select_util"
SUDO_PASSWORD = "leadshine"


def configure_device(device: str) -> bool:
    cmd = ["sudo", "-S", UTIL_PATH, device, "RS485"]
    print(f"Configuring {device} -> RS485 mode...")
    try:
        result = subprocess.run(
            cmd,
            input=SUDO_PASSWORD + "\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        print(f"  Tool not found: {UTIL_PATH}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  {device} configuration timed out")
        return False

    if result.returncode == 0:
        print(f"  OK: {device}")
        if result.stdout.strip():
            print(f"  {result.stdout.strip()}")
        return True

    print(f"  FAIL: {device} (code {result.returncode})")
    if result.stderr.strip():
        filtered = "\n".join(
            line
            for line in result.stderr.splitlines()
            if "[sudo]" not in line and "password" not in line.lower()
        )
        if filtered.strip():
            print(f"  {filtered.strip()}")
    return False


def main() -> int:
    devices = sorted(glob.glob("/dev/ttyXRUSB*"))
    if not devices:
        print("No ttyXRUSB devices found.")
        return 1

    print(f"Found {len(devices)} devices: {', '.join(devices)}\n")
    success_count = sum(1 for device in devices if configure_device(device))
    print(f"\nDone: {success_count}/{len(devices)} devices configured successfully.")
    return 0 if success_count == len(devices) else 1


if __name__ == "__main__":
    raise SystemExit(main())
