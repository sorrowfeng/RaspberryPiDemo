"""
GPIO功能测试程序（仅硬件模式）
用于测试GPIO配置和使用，所有运动/连接仅打印，不实际驱动
需在树莓派硬件上运行，使用真实GPIO触发

测试目标：
1) 循环运动：持续打印循环，模拟运动
2) 停止并回零：触发 STOP_MOTION GPIO 时，应立刻停止循环并打印回零流程
3) 连接/断开：通过 GPIO 触发，打印对应流程
"""

import sys
import time
import threading
import keyboard
from gpio_controller import GPIOController, GPIO_PINS
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("警告: RPi.GPIO 未安装，无法运行硬件GPIO测试")


class GPIOTestController:
    """GPIO测试控制器，用打印代替实际功能（硬件GPIO触发）"""

    def __init__(self):
        if GPIO is None:
            raise RuntimeError("RPi.GPIO 未安装，无法运行GPIO测试")
        self.gpio = GPIOController()
        
        # 模拟状态
        self.device_connected = False
        self.motion_running = False
        self.motion_lock = threading.Lock()
        self.stop_motion_flag = threading.Event()
        
        # 模拟运动位置序列
        self.positions = [
            [10000, 10000, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 10000, 10000, 10000, 10000],
            [0, 0, 0, 0, 0, 0],
        ]

    def setup_gpio(self):
        """设置GPIO引脚和回调函数"""
        print("\n" + "="*60)
        print("开始配置GPIO...")
        print("="*60)
        
        # 设置输入引脚
        print(f"\n📥 配置输入引脚:")
        pull_cfg = GPIO.PUD_DOWN
        print(f"  GPIO {GPIO_PINS.START_MOTION} - 开始循环运动")
        self.gpio.setup_input(
            GPIO_PINS.START_MOTION,
            callback=self.on_start_motion,
            pull_up_down=pull_cfg
        )
        
        print(f"  GPIO {GPIO_PINS.STOP_MOTION} - 停止运动并回到0位置")
        self.gpio.setup_input(
            GPIO_PINS.STOP_MOTION,
            callback=self.on_stop_motion,
            pull_up_down=pull_cfg
        )
        
        print(f"  GPIO {GPIO_PINS.CONNECT} - 连接设备")
        self.gpio.setup_input(
            GPIO_PINS.CONNECT,
            callback=self.on_connect_device,
            pull_up_down=pull_cfg
        )
        
        print(f"  GPIO {GPIO_PINS.DISCONNECT} - 断开设备")
        self.gpio.setup_input(
            GPIO_PINS.DISCONNECT,
            callback=self.on_disconnect_device,
            pull_up_down=pull_cfg
        )
        
        # 设置输出引脚
        print(f"\n📤 配置输出引脚:")
        print(f"  GPIO {GPIO_PINS.CYCLE_COMPLETE} - 循环完成信号输出")
        self.gpio.setup_output(GPIO_PINS.CYCLE_COMPLETE, initial=False)
        
        print(f"  GPIO {GPIO_PINS.STATUS_LED} - 状态LED输出")
        self.gpio.setup_output(GPIO_PINS.STATUS_LED, initial=False)
        print(f"  GPIO {GPIO_PINS.READY_STATUS} - 程序待命指示")
        self.gpio.setup_output(GPIO_PINS.READY_STATUS, initial=False)
        print(f"  GPIO {GPIO_PINS.RUNNING_STATUS} - 运行中指示")
        self.gpio.setup_output(GPIO_PINS.RUNNING_STATUS, initial=False)
        # RGB 状态灯（硬件PWM）
        self.gpio.setup_rgb_pwm(GPIO_PINS.RGB_R, GPIO_PINS.RGB_G, GPIO_PINS.RGB_B, freq=1000)
        # 初始状态：断开/未就绪 -> 红色
        self.gpio.set_rgb_color(255, 0, 0)
        
        print("\n✅ GPIO配置完成!")
        print("="*60)

    def on_start_motion(self):
        """开始循环运动回调（模拟）"""
        print("\n" + "🔵"*30)
        print("🔵 GPIO触发: 开始循环运动")
        print("🔵"*30)
        
        # 测试场景允许未连接也继续打印运动
        if not self.device_connected:
            print("⚠️  设备未连接，继续以打印方式模拟运动")
        
        with self.motion_lock:
            if self.motion_running:
                print("⚠️  [模拟] 运动已在运行中")
                return
            
            self.motion_running = True
            self.stop_motion_flag.clear()
        
        # 状态指示：运行中 -> 蓝色
        self.gpio.output_high(GPIO_PINS.RUNNING_STATUS)
        self.gpio.output_low(GPIO_PINS.READY_STATUS)
        self.gpio.set_rgb_color(0, 0, 255)
        
        # 在单独线程中执行模拟运动
        motion_thread = threading.Thread(target=self._run_motion_cycle_simulate, daemon=True)
        motion_thread.start()

    def on_stop_motion(self):
        """停止运动并回到0位置回调（模拟）"""
        print("\n" + "🔴"*30)
        print("🔴 GPIO触发: 停止运动并回到0位置")
        print("🔴"*30)
        
        with self.motion_lock:
            if not self.motion_running:
                print("⚠️  [模拟] 当前没有运动在执行")
                return
            
            self.stop_motion_flag.set()
            self.motion_running = False
        
        print("⏹️  [模拟] 停止所有电机运动...")
        time.sleep(0.1)
        print("📍 [模拟] 正在移动到0位置...")
        print("    [模拟] 设置所有位置为: [0, 0, 0, 0, 0, 0]")
        print("    [模拟] 速度: 20000, 最大电流: 1000")
        time.sleep(0.5)
        print("✅ [模拟] 已回到0位置")
        # 状态指示：待命 -> 绿色
        self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
        self.gpio.output_high(GPIO_PINS.READY_STATUS)
        self.gpio.set_rgb_color(0, 255, 0)

    def on_connect_device(self):
        """连接设备回调（模拟）"""
        print("\n" + "🟢"*30)
        print("🟢 GPIO触发: 连接设备")
        print("🟢"*30)
        
        if self.device_connected:
            print("⚠️  [模拟] 设备已连接")
            return
        
        # 停止当前运动
        with self.motion_lock:
            self.stop_motion_flag.set()
            self.motion_running = False
        
        print("🔌 [模拟] 正在连接设备...")
        print("    [模拟] 创建 PyLHandProLib 实例...")
        time.sleep(0.3)
        print("    [模拟] 创建 EtherCAT 主站...")
        time.sleep(0.3)
        print("    [模拟] 扫描网口...")
        time.sleep(0.3)
        print("    [模拟] 初始化 EtherCAT...")
        time.sleep(0.3)
        print("    [模拟] 启动后台 IO...")
        time.sleep(0.3)
        print("    [模拟] 初始化 LHandProLib...")
        time.sleep(0.3)
        print("    [模拟] 获取自由度: 总共 6, 主动 6")
        time.sleep(0.3)
        print("    [模拟] 设置控制模式: 位置控制")
        time.sleep(0.3)
        print("    [模拟] 使能电机...")
        time.sleep(0.3)
        print("    [模拟] 回零操作...")
        time.sleep(0.5)
        
        self.device_connected = True
        self.gpio.output_high(GPIO_PINS.STATUS_LED)
        self.gpio.output_high(GPIO_PINS.READY_STATUS)
        self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
        self.gpio.set_rgb_color(0, 255, 0)  # 绿色：就绪
        print("✅ [模拟] 设备连接成功")
        print("💡 GPIO {} (STATUS_LED) 已设置为高电平".format(GPIO_PINS.STATUS_LED))

    def on_disconnect_device(self):
        """断开设备回调（模拟）"""
        print("\n" + "🟡"*30)
        print("🟡 GPIO触发: 断开设备")
        print("🟡"*30)
        
        # 停止当前运动
        with self.motion_lock:
            self.stop_motion_flag.set()
            self.motion_running = False
        
        print("🔌 [模拟] 正在断开设备连接...")
        print("    [模拟] 停止监控线程...")
        time.sleep(0.2)
        print("    [模拟] 关闭 LHandProLib...")
        time.sleep(0.2)
        print("    [模拟] 停止 EtherCAT 主站...")
        time.sleep(0.2)
        
        self.device_connected = False
        self.gpio.output_low(GPIO_PINS.STATUS_LED)
        self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
        self.gpio.output_low(GPIO_PINS.READY_STATUS)
        self.gpio.set_rgb_color(255, 0, 0)  # 红色：断开
        print("✅ [模拟] 设备已断开")
        print("💡 GPIO {} (STATUS_LED) 已设置为低电平".format(GPIO_PINS.STATUS_LED))

    def _run_motion_cycle_simulate(self):
        """执行循环运动（模拟）"""
        print("\n🚀 [模拟] 开始循环运动")
        print("   运动序列包含 {} 个位置".format(len(self.positions)))
        
        cycle_count = 0
        
        try:
            while not self.stop_motion_flag.is_set():
                cycle_count += 1
                print("\n" + "-"*60)
                print("🔄 [模拟] 开始第 {} 个循环".format(cycle_count))
                print("-"*60)
                
                for i, pos_list in enumerate(self.positions):
                    # 检查停止标志
                    if self.stop_motion_flag.is_set():
                        print("\n⏹️  [模拟] 运动被停止")
                        return
                    
                    # 模拟执行运动
                    print("\n📍 [模拟] 执行位置 {}: {}".format(i+1, pos_list))
                    print("    [模拟] 设置目标位置: {}".format(pos_list))
                    print("    [模拟] 设置速度: 20000")
                    print("    [模拟] 设置最大电流: 1000")
                    print("    [模拟] 发送运动指令...")
                    time.sleep(0.5)  # 模拟运动时间
                    print("    ✅ [模拟] 位置 {} 运动完成".format(i+1))
                    
                    # 检查是否完成一个循环
                    if i == len(self.positions) - 1:
                        # 完成一个循环，输出脉冲信号
                        print("\n" + "✨"*30)
                        print("✨ [模拟] 完成第 {} 个循环，输出完成信号".format(cycle_count))
                        print("✨ GPIO {} (CYCLE_COMPLETE) 输出高电平脉冲 (0.5秒)".format(GPIO_PINS.CYCLE_COMPLETE))
                        self.gpio.output_pulse(GPIO_PINS.CYCLE_COMPLETE, duration=0.5)
                        print("✨"*30)
                    
                    # 再次检查停止标志
                    if self.stop_motion_flag.is_set():
                        print("\n⏹️  [模拟] 运动被停止")
                        return
                
                print("\n🔄 [模拟] 准备下一个循环...")
                time.sleep(0.2)
        
        except Exception as e:
            print(f"\n❌ [模拟] 运动循环出错: {e}")
        finally:
            with self.motion_lock:
                self.motion_running = False
            # 状态指示：待命 -> 绿色
            self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_high(GPIO_PINS.READY_STATUS)
            self.gpio.set_rgb_color(0, 255, 0)
            print("\n🏁 [模拟] 循环运动结束")

    def test_gpio_outputs(self):
        """测试GPIO输出功能"""
        print("\n" + "="*60)
        print("测试GPIO输出功能")
        print("="*60)
        
        print("\n📤 测试 GPIO {} (CYCLE_COMPLETE):".format(GPIO_PINS.CYCLE_COMPLETE))
        print("   输出高电平...")
        self.gpio.output_high(GPIO_PINS.CYCLE_COMPLETE)
        time.sleep(1.0)
        print("   输出低电平...")
        self.gpio.output_low(GPIO_PINS.CYCLE_COMPLETE)
        
        print("\n📤 测试 GPIO {} (STATUS_LED):".format(GPIO_PINS.STATUS_LED))
        print("   输出高电平...")
        self.gpio.output_high(GPIO_PINS.STATUS_LED)
        time.sleep(1.0)
        print("   输出低电平...")
        self.gpio.output_low(GPIO_PINS.STATUS_LED)
        
        print("\n📤 测试脉冲输出:")
        print("   GPIO {} 输出0.5秒脉冲...".format(GPIO_PINS.CYCLE_COMPLETE))
        self.gpio.output_pulse(GPIO_PINS.CYCLE_COMPLETE, duration=0.5)
        print("   ✅ 脉冲输出完成")
        
        print("\n✅ GPIO输出测试完成")

    def print_status(self):
        """打印当前状态"""
        print("\n" + "="*60)
        print("当前状态")
        print("="*60)
        print("设备连接状态: {}".format("✅ 已连接" if self.device_connected else "❌ 未连接"))
        print("运动状态: {}".format("🔄 运行中" if self.motion_running else "⏸️  已停止"))
        print("="*60)

    def run(self):
        """主运行函数"""
        print("\n" + "="*60)
        print("GPIO功能测试程序")
        print("="*60)
        
        # 设置GPIO
        try:
            self.setup_gpio()
        except Exception as e:
            print(f"\n❌ GPIO设置失败: {e}")
            return -1
        
        # 测试GPIO输出
        print("\n是否先测试GPIO输出功能? (y/n): ", end='')
        try:
            test_output = input().strip().lower()
            if test_output == 'y':
                self.test_gpio_outputs()
        except:
            pass
        
        print("\n" + "="*60)
        print("GPIO功能说明:")
        print("="*60)
        print("输入引脚（触发时执行相应操作）:")
        print("  GPIO {}: 开始循环运动".format(GPIO_PINS.START_MOTION))
        print("  GPIO {}: 停止运动并回到0位置".format(GPIO_PINS.STOP_MOTION))
        print("  GPIO {}: 连接设备".format(GPIO_PINS.CONNECT))
        print("  GPIO {}: 断开设备".format(GPIO_PINS.DISCONNECT))
        print("\n输出引脚:")
        print("  GPIO {}: 循环完成信号输出（每次循环完成输出0.5秒脉冲）".format(GPIO_PINS.CYCLE_COMPLETE))
        print("  GPIO {}: 状态LED（连接=高电平，断开=低电平）".format(GPIO_PINS.STATUS_LED))
        print("  GPIO {}: READY_STATUS（待命指示，高=待命）".format(GPIO_PINS.READY_STATUS))
        print("  GPIO {}: RUNNING_STATUS（运行指示，高=运行中）".format(GPIO_PINS.RUNNING_STATUS))
        print("  GPIO {},{},{}: RGB 状态灯 (R,G,B)".format(GPIO_PINS.RGB_R, GPIO_PINS.RGB_G, GPIO_PINS.RGB_B))
        print("\n键盘控制:")
        print("  按 's' 键: 显示当前状态")
        print("  按 't' 键: 测试GPIO输出")
        print("  按 Esc 键: 退出程序")
        print("="*60 + "\n")
        
        try:
            # 主循环，等待用户操作
            while True:
                if keyboard.is_pressed('esc'):
                    print("\n\nEsc键按下，正在退出...")
                    break
                
                if keyboard.is_pressed('s'):
                    self.print_status()
                    time.sleep(0.3)  # 防抖
                
                if keyboard.is_pressed('t'):
                    self.test_gpio_outputs()
                    time.sleep(0.3)  # 防抖
                
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            print("\n\n程序被用户中断")
        
        finally:
            # 清理资源
            print("\n正在清理资源...")
            
            # 停止运动
            with self.motion_lock:
                self.stop_motion_flag.set()
                self.motion_running = False
            
            # 清理GPIO
            self.gpio.cleanup()
            
            print("✅ 资源清理完成")
        
        return 0


def main():
    """主函数（硬件模式）"""
    if GPIO is None:
        print("❌ 错误: RPi.GPIO 未安装")
        print("请先安装: sudo apt-get install python3-rpi.gpio")
        print("或: pip install RPi.GPIO")
        return -1
    
    try:
        test_ctrl = GPIOTestController()
        return test_ctrl.run()
    except RuntimeError as e:
        if "Not running on a RPi" in str(e) or "不在树莓派" in str(e):
            print("\n" + "="*60)
            print("❌ GPIO测试失败")
            print("="*60)
            print(str(e))
            print("\n提示:")
            print("  - 此程序必须在树莓派硬件上运行")
            print("  - 如果确实在树莓派上，请检查权限和GPIO占用情况")
            return -1
        else:
            raise


if __name__ == "__main__":
    sys.exit(main())

