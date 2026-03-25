#!/usr/bin/env python3
import subprocess
import time
import sys
import argparse
from config import DEFAULT_COMMUNICATION_MODE, DEFAULT_LAUNCH_COUNT

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 LHandPro 设备")
    parser.add_argument('--communication-mode', '-m', type=str,
                        choices=['CANFD', 'ECAT', 'RS485'],
                        help='通信模式（覆盖 config 中的 DEFAULT_COMMUNICATION_MODE）')
    parser.add_argument('--launch-count', '-n', type=int,
                        help='启动脚本数量（覆盖 config 中的 DEFAULT_LAUNCH_COUNT）')
    args = parser.parse_args()

    communication_mode = args.communication_mode or DEFAULT_COMMUNICATION_MODE
    launch_count = args.launch_count if args.launch_count is not None else DEFAULT_LAUNCH_COUNT

    print(f"启动 LHandPro 设备... 通信模式: {communication_mode}, 启动数量: {launch_count}")

    # RS485 模式下先配置所有 USB 转 485 设备
    if communication_mode == "RS485":
        print("RS485 模式：正在配置 USB 转 485 设备...")
        subprocess.run([sys.executable, "setup_rs485_mode.py"])

    # 根据操作系统决定是否使用 sudo
    if sys.platform.startswith('win32'):
        python_cmd = ["python3"] if sys.executable.endswith('python3') else ["python"]
    else:
        python_cmd = ["sudo", "python3"]

    for i in range(launch_count):
        try:
            cmd = python_cmd + [
                "main.py",
                f"--communication-mode={communication_mode}",
            ]
            # 多实例时传入设备索引
            if launch_count > 1:
                cmd.append(f"--device-index={i}")

            process = subprocess.Popen(cmd)
            label = f"设备 {i}" if launch_count > 1 else "设备"
            print(f"{label} 已启动，PID: {process.pid}")
            time.sleep(1)

        except Exception as e:
            label = str(i) if launch_count > 1 else ""
            print(f"启动设备 {label} 失败: {e}")

    print("所有设备启动完成，按 Ctrl+C 退出")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("正在退出...")
