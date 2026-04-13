"""
Program entry for RaspberryPiDemo.
"""

import argparse
import sys

from log import setup_logging
from motion_system import MotionController


def main():
    parser = argparse.ArgumentParser(description="LHandPro GPIO 控制程序")
    parser.add_argument(
        "--device-index",
        "-i",
        type=int,
        default=None,
        choices=[0, 1, 2, 3],
        help="设备索引，可选值: 0, 1, 2, 3",
    )
    parser.add_argument(
        "--communication-mode",
        "-m",
        type=str,
        default=None,
        choices=["CANFD", "ECAT", "RS485"],
        help="通信模式，可选值: CANFD, ECAT, RS485；不指定时交互选择",
    )
    parser.add_argument(
        "--enable-gpio",
        "-g",
        action="store_true",
        default=True,
        help="启用 GPIO 控制（默认: True）",
    )
    parser.add_argument(
        "--no-enable-gpio",
        action="store_false",
        dest="enable_gpio",
        help="禁用 GPIO 控制",
    )
    args = parser.parse_args()

    if args.communication_mode is None:
        modes = ["CANFD", "ECAT", "RS485"]
        print("请选择通信模式:")
        for index, mode in enumerate(modes):
            print(f"  [{index}] {mode}")

        while True:
            try:
                choice = input(">>> ").strip()
                if choice == "":
                    args.communication_mode = modes[0]
                    print(f"使用默认模式: {args.communication_mode}")
                    break

                mode_index = int(choice)
                if 0 <= mode_index < len(modes):
                    args.communication_mode = modes[mode_index]
                    break

                print(f"请输入 0 - {len(modes) - 1}")
            except ValueError:
                print("请输入数字")

    setup_logging()
    motion_ctrl = MotionController(
        communication_mode=args.communication_mode,
        device_index=args.device_index,
        enable_gpio=args.enable_gpio,
    )
    return motion_ctrl.run()


if __name__ == "__main__":
    sys.exit(main())
