#!/usr/bin/env python3
import subprocess
import time
import sys
import argparse
from config import DEFAULT_USE_ECAT_MODE

if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="启动 LHandPro 设备")
    parser.add_argument('--communication-mode', type=str, choices=['CANFD', 'ECAT'], 
                        help='通信模式')
    parser.add_argument('--ecat-mode', action='store_true', 
                        help='使用ECAT模式（启动1个脚本）')
    args = parser.parse_args()
    
    print("启动 LHandPro 设备...")
    
    # 确定是否使用ECAT模式
    # 优先级：命令行参数 --ecat-mode > 命令行参数 --communication-mode=ECAT > 默认宏
    use_ecat_mode = DEFAULT_USE_ECAT_MODE
    if args.communication_mode == 'ECAT':
        use_ecat_mode = True
    if args.ecat_mode:
        use_ecat_mode = True
    
    # 根据操作系统决定是否使用sudo
    if sys.platform.startswith('win32'):
        python_cmd = ["python3"] if sys.executable.endswith('python3') else ["python"]
    else:
        python_cmd = ["sudo", "python3"]
    
    if use_ecat_mode:
        # 启动1个脚本，使用ECAT通信模式
        try:
            # 构造命令
            cmd = python_cmd + [
                "main.py",
                "--communication-mode=ECAT"
            ]
            process = subprocess.Popen(cmd)
            
            print(f"ECAT设备已启动，PID: {process.pid}")
            time.sleep(1)
            
        except Exception as e:
            print(f"启动ECAT设备失败: {e}")
    else:
        # 启动4个脚本，使用CANFD通信模式
        for i in range(4):
            try:
                # 构造命令
                cmd = python_cmd + [
                    "main.py",
                    f"--device-index={i}",
                    "--communication-mode=CANFD",
                    "--no-enable-gpio"
                ]
                process = subprocess.Popen(cmd)
                
                print(f"设备 {i} 已启动，PID: {process.pid}")
                time.sleep(1)
                
            except Exception as e:
                print(f"启动设备 {i} 失败: {e}")
    
    print("所有设备启动完成，按 Ctrl+C 退出")
    
    try:
        # 保持脚本运行
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("正在退出...")