#!/usr/bin/env python3
import subprocess
import time
import sys

# 检查是否以root运行
if __name__ == "__main__":
    print("启动 LHandPro 设备...")
    
    for i in range(4):
        try:
            # 直接使用 sudo 运行，不加 preexec_fn
            process = subprocess.Popen([
                "sudo", "python3", "main.py",
                f"--device-index={i}",
                "--communication-mode=CANFD",
                "--no-enable-gpio"
            ])
            
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