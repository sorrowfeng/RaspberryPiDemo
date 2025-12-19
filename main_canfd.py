#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LHandProLib库 Python CANFD运行示例

该示例程序展示了如何使用LHandProController类通过CANFD通信控制LHandPro设备
执行循环运动，并支持用户交互控制。

功能特性：
- 自动连接CANFD设备
- 执行预设的位置序列循环运动
- 支持Esc键中断程序
- 自动处理设备连接和断开
- 完善的异常处理
- 实时状态反馈
"""

import sys
import time
import keyboard
from lhandpro_controller import LHandProController


def main():
    """
    主函数：初始化LHandPro设备并执行循环运动
    """
    print("LHandPro CANFD 循环运动示例")
    print("=" * 50)
    
    # 创建控制器实例并连接设备
    with LHandProController(communication_mode="CANFD") as controller:
        try:
            # 连接CANFD设备
            print("\n正在连接CANFD设备...")
            connected = controller.connect(
                enable_motors=True,
                home_motors=True,  # 自动回零
                home_wait_time=5.0,
                canfd_nom_baudrate=1000000,
                canfd_dat_baudrate=5000000
            )
            
            if not connected:
                print("❌ 设备连接失败，请检查硬件连接和CANFD配置")
                return 1
            
            print("✅ 设备连接成功")

            # 获取自由度信息
            dof_total, dof_active = controller.get_dof()
            print(f"\n设备信息:")
            print(f"  - 总共自由度: {dof_total}")
            print(f"  - 主动自由度: {dof_active}")
            
            # 设置运动参数
            velocity = 20000       # 运动速度
            max_current = 1000      # 最大电流
            wait_time = 1.0        # 位置间等待时间
            
            # 定义循环运动的位置序列
            # 注意：位置列表长度应与主动自由度数量匹配
            positions = [
                [10000, 10000, 0, 0, 0, 0][:dof_active],    # 位置1
                [0, 0, 0, 0, 0, 0][:dof_active],             # 位置2
                [0, 0, 10000, 10000, 10000, 10000][:dof_active],  # 位置3
                [0, 0, 0, 0, 0, 0][:dof_active]              # 位置4
            ]
            
            print("\n开始执行循环运动")
            print(f"运动速度: {velocity}, 最大电流: {max_current}")
            print("按 Esc 键退出程序")
            
            cycle_count = 0
            while True:
                cycle_count += 1
                print(f"\n=== 循环 {cycle_count} ===")
                
                # 遍历所有位置
                for i, pos_list in enumerate(positions):
                    # 检查Esc键
                    if keyboard.is_pressed('esc'):
                        print("\nEsc键被按下，程序退出...")
                        raise KeyboardInterrupt
                    
                    print(f"  移动到位置 {i+1}: {pos_list}")
                    
                    # 移动到指定位置
                    success = controller.move_to_positions(
                        positions=pos_list,
                        velocity=velocity,
                        max_current=max_current,
                        wait_time=wait_time
                    )
                    
                    if success:
                        print(f"  ✅ 位置 {i+1} 到达")
                    else:
                        print(f"  ❌ 位置 {i+1} 运动失败")
            
        except KeyboardInterrupt:
            print("\n程序被用户中断")
        except Exception as e:
            print(f"\n程序运行出错: {e}")
            return 1
        finally:
            # 确保电机停止
            print("\n停止所有电机...")
            controller.stop_motors()
            print("✅ 电机已停止")
    
    print("\n" + "=" * 50)
    print("程序执行完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())