#!/usr/bin/env python3
"""Configure all detected USB-to-RS485 adapters into RS485 mode."""

import glob
import os
import subprocess
import sys
import time

UTIL_PATH = "/home/ubuntu/Documents/ll-usb2rs485-driver/Utility/utek_gpio_mode_select_util/utek_gpio_mode_select_util"
DRIVER_DIR = "/home/ubuntu/Documents/ll-usb2rs485-driver/Driver"
DRIVER_MODULE = "xr_usb_serial_common"
DRIVER_KO_PATH = f"{DRIVER_DIR}/{DRIVER_MODULE}.ko"
EXAR_USB_ID = "04e2:1411"
TTYXR_PATTERN = "/dev/ttyXRUSB*"
SUDO_PASSWORD = "leadshine"
TTYXR_WAIT_SECONDS = 3.0


def filter_sudo_stderr(stderr: str) -> str:
    return "\n".join(
        line
        for line in stderr.splitlines()
        if "[sudo]" not in line and "password" not in line.lower()
    ).strip()


def run_sudo_command(cmd, timeout=10):
    return subprocess.run(
        ["sudo", "-S"] + cmd,
        input=SUDO_PASSWORD + "\n",
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def list_ttyxr_devices():
    return sorted(glob.glob(TTYXR_PATTERN))


def is_driver_loaded() -> bool:
    try:
        with open("/proc/modules", "r", encoding="utf-8") as file_obj:
            return any(line.startswith(f"{DRIVER_MODULE} ") for line in file_obj)
    except OSError:
        return False


def detect_exar_adapter() -> bool:
    try:
        result = subprocess.run(
            ["lsusb"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        print("lsusb command not found; skip USB ID detection.")
        return False
    except subprocess.TimeoutExpired:
        print("lsusb timed out; skip USB ID detection.")
        return False

    matched_lines = [
        line for line in result.stdout.splitlines()
        if EXAR_USB_ID.lower() in line.lower()
    ]
    for line in matched_lines:
        print(f"Detected Exar USB-to-RS485 adapter: {line}")
    return bool(matched_lines)


def wait_for_ttyxr_devices(timeout=TTYXR_WAIT_SECONDS):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        devices = list_ttyxr_devices()
        if devices:
            return devices
        time.sleep(0.2)
    return list_ttyxr_devices()


def load_driver_with_modprobe() -> bool:
    print(f"Trying modprobe {DRIVER_MODULE}...")
    try:
        result = run_sudo_command(["modprobe", DRIVER_MODULE])
    except FileNotFoundError:
        print("  sudo or modprobe command not found")
        return False
    except subprocess.TimeoutExpired:
        print("  modprobe timed out")
        return False

    if result.returncode == 0:
        print(f"  OK: modprobe {DRIVER_MODULE}")
        return True

    filtered = filter_sudo_stderr(result.stderr)
    if filtered:
        print(f"  modprobe failed: {filtered}")
    return False


def load_driver_with_insmod() -> bool:
    if not os.path.exists(DRIVER_KO_PATH):
        print(f"  Driver file not found: {DRIVER_KO_PATH}")
        return False

    print(f"Trying insmod {DRIVER_KO_PATH}...")
    try:
        result = run_sudo_command(["insmod", DRIVER_KO_PATH])
    except FileNotFoundError:
        print("  sudo or insmod command not found")
        return False
    except subprocess.TimeoutExpired:
        print("  insmod timed out")
        return False

    stderr = filter_sudo_stderr(result.stderr)
    if result.returncode == 0:
        print(f"  OK: insmod {DRIVER_KO_PATH}")
        return True

    if "File exists" in stderr:
        print(f"  OK: {DRIVER_MODULE} already loaded")
        return True

    if stderr:
        print(f"  insmod failed: {stderr}")
    return False


def ensure_ttyxr_devices():
    devices = list_ttyxr_devices()
    if devices:
        return devices

    print(f"No {TTYXR_PATTERN} devices found. Checking Exar driver...")
    has_exar_adapter = detect_exar_adapter()
    if not has_exar_adapter:
        print(f"USB device {EXAR_USB_ID} was not detected by lsusb.")

    if is_driver_loaded():
        print(f"Driver {DRIVER_MODULE} is already loaded.")
    else:
        if not load_driver_with_modprobe():
            load_driver_with_insmod()

    devices = wait_for_ttyxr_devices()
    if devices:
        print(f"Found ttyXR devices after driver setup: {', '.join(devices)}")
    else:
        print(
            "No ttyXRUSB devices found after driver setup. "
            f"Expected device path is /dev/ttyXRUSB0 for USB ID {EXAR_USB_ID}."
        )
    return devices


def configure_device(device: str) -> bool:
    cmd = [UTIL_PATH, device, "RS485"]
    print(f"Configuring {device} -> RS485 mode...")
    try:
        result = run_sudo_command(cmd)
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
        filtered = filter_sudo_stderr(result.stderr)
        if filtered.strip():
            print(f"  {filtered.strip()}")
    return False


def main() -> int:
    devices = ensure_ttyxr_devices()
    if not devices:
        print("No ttyXRUSB devices found.")
        print(f"Driver source path: {DRIVER_DIR}")
        print(f"Expected module: {DRIVER_MODULE}")
        print(f"Expected USB ID: {EXAR_USB_ID}")
        return 1

    print(f"Found {len(devices)} devices: {', '.join(devices)}\n")
    success_count = sum(1 for device in devices if configure_device(device))
    print(f"\nDone: {success_count}/{len(devices)} devices configured successfully.")
    return 0 if success_count == len(devices) else 1


if __name__ == "__main__":
    raise SystemExit(main())
