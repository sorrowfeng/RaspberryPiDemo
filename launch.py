#!/usr/bin/env python3
"""Launch one or more controller processes based on the selected bus mode."""

import argparse
import os
import subprocess
import sys
import time

from config import DEFAULT_COMMUNICATION_MODE, DEFAULT_LAUNCH_COUNT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(BASE_DIR, "tools")


def main() -> int:
    os.chdir(BASE_DIR)

    parser = argparse.ArgumentParser(description="Launch LHandPro devices")
    parser.add_argument(
        "--communication-mode",
        "-m",
        type=str,
        choices=["CANFD", "ECAT", "RS485"],
        help="Communication mode. Overrides DEFAULT_COMMUNICATION_MODE in config.py.",
    )
    parser.add_argument(
        "--launch-count",
        "-n",
        type=int,
        help="Number of processes to launch. Overrides DEFAULT_LAUNCH_COUNT in config.py.",
    )
    args = parser.parse_args()

    communication_mode = args.communication_mode or DEFAULT_COMMUNICATION_MODE
    launch_count = args.launch_count if args.launch_count is not None else DEFAULT_LAUNCH_COUNT

    print(f"Launching LHandPro devices. mode={communication_mode}, count={launch_count}")

    if communication_mode == "RS485":
        print("Preparing USB-to-RS485 adapters...")
        subprocess.run([sys.executable, os.path.join(TOOLS_DIR, "setup_rs485_mode.py")], check=False)

    if sys.platform.startswith("win32"):
        python_cmd = ["python3"] if sys.executable.endswith("python3") else ["python"]
    else:
        python_cmd = ["sudo", "python3"]

    for index in range(launch_count):
        try:
            cmd = python_cmd + [
                "main.py",
                f"--communication-mode={communication_mode}",
            ]
            if launch_count > 1:
                cmd.append(f"--device-index={index}")

            process = subprocess.Popen(cmd)
            label = f"device {index}" if launch_count > 1 else "device"
            print(f"{label} started, pid={process.pid}")
            time.sleep(1)
        except Exception as exc:
            label = str(index) if launch_count > 1 else ""
            print(f"Failed to start device {label}: {exc}")

    print("All launch requests submitted. Press Ctrl+C to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting launcher...")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
