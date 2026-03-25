#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
绿联 USB 转 RS485 模式配置脚本
对所有 /dev/ttyXRUSB* 设备调用 utek_gpio_mode_select_util 切换到 RS485 模式
"""

import glob
import subprocess
import sys

UTIL_PATH = "/home/ubuntu/Documents/ll-usb2rs485-driver/Utility/utek_gpio_mode_select_util/utek_gpio_mode_select_util"
SUDO_PASSWORD = "leadshine"


def configure_device(device: str) -> bool:
    """对指定设备执行 RS485 模式配置"""
    cmd = ["sudo", "-S", UTIL_PATH, device, "RS485"]
    print(f"正在配置 {device} -> RS485 模式...")
    try:
        result = subprocess.run(
            cmd,
            input=SUDO_PASSWORD + "\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            print(f"  ✅ {device} 配置成功")
            if result.stdout.strip():
                print(f"  {result.stdout.strip()}")
            return True
        else:
            print(f"  ❌ {device} 配置失败 (返回码: {result.returncode})")
            if result.stderr.strip():
                # 过滤掉 sudo 密码提示行
                err = "\n".join(
                    line for line in result.stderr.splitlines()
                    if "[sudo]" not in line and "password" not in line.lower()
                )
                if err.strip():
                    print(f"  错误信息: {err.strip()}")
            return False
    except FileNotFoundError:
        print(f"  ❌ 工具未找到: {UTIL_PATH}")
        print("  请确认驱动工具路径是否正确")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ {device} 配置超时")
        return False


def main():
    devices = sorted(glob.glob("/dev/ttyXRUSB*"))

    if not devices:
        print("未找到 ttyXRUSB 设备，请确认 USB 转 485 已连接且驱动已加载")
        sys.exit(1)

    print(f"找到 {len(devices)} 个设备: {', '.join(devices)}\n")

    success_count = 0
    for device in devices:
        if configure_device(device):
            success_count += 1

    print(f"\n完成: {success_count}/{len(devices)} 个设备配置成功")
    sys.exit(0 if success_count == len(devices) else 1)


if __name__ == "__main__":
    main()
