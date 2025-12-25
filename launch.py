#!/usr/bin/env python3
"""
启动脚本：同时启动四个LHandPro设备实例
分别指定设备索引0、1、2、3，通讯模式均为CANFD
"""

import subprocess
import time
import sys


def launch_device(device_index: int):
    """启动指定设备索引的设备实例
    
    Args:
        device_index: 设备索引（0-3）
    """
    print(f"正在启动设备索引 {device_index}...")
    
    # 构建命令行参数
    cmd = [
        "sudo",
        "python3",
        "main.py",
        f"--device-index={device_index}",
        "--communication-mode=CANFD"
    ]
    
    try:
        # 启动子进程
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        return process
    except Exception as e:
        print(f"启动设备索引 {device_index} 失败: {e}")
        return None


def main():
    """主函数：启动所有设备"""
    print("=" * 60)
    print("LHandPro 多设备启动脚本")
    print("=" * 60)
    print("正在启动4个设备实例...")
    print("设备索引: 0, 1, 2, 3")
    print("通讯模式: CANFD")
    print("=" * 60)
    
    # 启动所有设备
    processes = []
    for i in range(4):
        process = launch_device(i)
        if process:
            processes.append(process)
            time.sleep(1)  # 延迟1秒启动下一个设备
    
    print(f"\n成功启动 {len(processes)} 个设备实例")
    print("\n按 Ctrl+C 停止所有设备并退出...")
    
    try:
        # 等待所有进程完成（或者用户中断）
        while True:
            time.sleep(1)
            # 检查进程是否还在运行
            for i, process in enumerate(processes):
                if process.poll() is not None:
                    print(f"\n设备索引 {i} 已退出，返回码: {process.returncode}")
                    # 打印退出进程的输出
                    stdout, stderr = process.communicate()
                    if stdout:
                        print(f"设备索引 {i} 标准输出:\n{stdout}")
                    if stderr:
                        print(f"设备索引 {i} 错误输出:\n{stderr}")
                    # 从列表中移除已退出的进程
                    processes[i] = None
            
            # 清理None值
            processes = [p for p in processes if p is not None]
            
            # 如果所有进程都已退出，结束循环
            if not processes:
                print("\n所有设备实例已退出")
                break
                
    except KeyboardInterrupt:
        print("\n用户中断，正在停止所有设备...")
        
        # 终止所有进程
        for i, process in enumerate(processes):
            if process and process.poll() is None:
                print(f"终止设备索引 {i}...")
                process.terminate()
                # 等待进程终止
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"设备索引 {i} 终止超时，强制杀死")
                    process.kill()
    
    print("\n✅ 所有设备已停止，脚本退出")


if __name__ == "__main__":
    main()