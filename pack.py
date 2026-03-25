#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包当前目录所有文件为 7z，输出到上一层路径
"""

import os
import subprocess
import sys

if __name__ == "__main__":
    current_dir = os.path.abspath(os.path.dirname(__file__))
    parent_dir = os.path.dirname(current_dir)
    folder_name = os.path.basename(current_dir)
    output_path = os.path.join(parent_dir, f"{folder_name}.7z")

    print(f"打包目录: {current_dir}")
    print(f"输出文件: {output_path}")

    cmd = [
        "7z", "a", output_path,
        folder_name,
        "-xr!.git",
        "-xr!logs",
        "-xr!__pycache__",
        f"-x!{folder_name}/lib/LHandProLib.dll",
    ]

    try:
        result = subprocess.run(cmd, cwd=parent_dir)
        if result.returncode == 0:
            print(f"✅ 打包成功: {output_path}")
        else:
            print(f"❌ 打包失败，返回码: {result.returncode}")
            sys.exit(result.returncode)
    except FileNotFoundError:
        print("❌ 未找到 7z 命令，请先安装 7-Zip：")
        print("  Ubuntu: sudo apt install p7zip-full")
        print("  Windows: https://www.7-zip.org/")
        sys.exit(1)
