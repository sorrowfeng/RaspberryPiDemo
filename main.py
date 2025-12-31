"""
LHandProLib库 python 运行示例
集成树莓派GPIO控制
"""

import sys
import time
import threading
import keyboard
import argparse
import logging
from log import setup_logging
from lhandpro_controller import LHandProController
from gpio_controller import GPIOController, GPIO_PINS
from udp_receiver import UDPReceiver
from udp_receiver import SimpleGloveData
from config import (
    DEFAULT_HOME_TIME,
    DEFAULT_CYCLE_COUNT,
    DEFAULT_CYCLE_VELOCITY,
    DEFAULT_CYCLE_INTERVAL,
    DEFAULT_CYCLE_CURRENT,
    CYCLE_MOVE_POSITIONS
)
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None



class MotionController:
    """运动控制器，集成GPIO和LHandPro控制"""

    def __init__(self, communication_mode: str, device_index: int = None, enable_gpio: bool = True):
        self.controller = LHandProController(communication_mode=communication_mode)
        self.gpio = GPIOController()
        self.device_index = device_index  # 存储设备索引
        self.enable_gpio = enable_gpio  # 保存GPIO启用状态
        
        # 运动控制标志
        self.motion_running = False
        self.motion_lock = threading.Lock()
        self.stop_motion_flag = threading.Event()
        
        # 定义循环运动位置序列
        self.cycle_move_positions = CYCLE_MOVE_POSITIONS

        # 定义抓握位置
        self.grasp_positions = [
            [5000, 0, 0, 0, 0, 0],
            [5000, 0, 10000, 10000, 10000, 10000],
            [5000, 10000, 10000, 10000, 10000, 10000],
            [5000, 0, 10000, 10000, 10000, 10000],
        ]
        
        # 手套监听控制
        self.glove_listener = None
        self.glove_listening = False
        self.glove_lock = threading.Lock()

    def setup_gpio(self):
        """设置GPIO引脚和回调函数"""
        if not self.enable_gpio:
            return

        # 设置输入引脚
        if GPIO is None:
            raise RuntimeError("RPi.GPIO 未安装")
        
        self.gpio.setup_input(
            GPIO_PINS.START_MOTION,
            callback=self.on_start_motion,
            pull_up_down=GPIO.PUD_DOWN
        )
        self.gpio.setup_input(
            GPIO_PINS.STOP_MOTION,
            callback=self.on_stop_motion,
            pull_up_down=GPIO.PUD_DOWN
        )
        self.gpio.setup_input(
            GPIO_PINS.CONNECT,
            callback=self.on_connect_device,
            pull_up_down=GPIO.PUD_DOWN
        )
        self.gpio.setup_input(
            GPIO_PINS.DISCONNECT,
            callback=self.on_disconnect_device,
            pull_up_down=GPIO.PUD_DOWN
        )
        self.gpio.setup_input(
            GPIO_PINS.START_GLOVE_LISTEN,
            callback=self.on_start_glove_listen,
            pull_up_down=GPIO.PUD_DOWN
        )
        self.gpio.setup_input(
            GPIO_PINS.START_GRASP,
            callback=self.on_start_grasp,
            pull_up_down=GPIO.PUD_DOWN
        )
        
        # 设置输出引脚
        self.gpio.setup_output(GPIO_PINS.CYCLE_COMPLETE, initial=False)
        self.gpio.setup_output(GPIO_PINS.STATUS_LED, initial=False)
        self.gpio.setup_output(GPIO_PINS.READY_STATUS, initial=False)
        self.gpio.setup_output(GPIO_PINS.RUNNING_STATUS, initial=False)
        
        logging.info("✅ GPIO设置完成")

    def on_start_motion(self):
        """开始循环运动回调"""
        logging.info("🔵 GPIO触发: 开始循环运动")
        if not self.controller.is_connected:
            logging.warning("⚠️ 设备未连接，无法开始运动")
            return
        
        with self.motion_lock:
            if self.motion_running:
                logging.warning("⚠️ 运动已在运行中")
                return
            
            self.motion_running = True
            self.stop_motion_flag.clear()
        
        if self.enable_gpio:
            # 状态指示：运行中
            self.gpio.output_high(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_low(GPIO_PINS.READY_STATUS)
        
        # 在单独线程中执行运动
        motion_thread = threading.Thread(target=self._run_motion_cycle, daemon=True)
        motion_thread.start()

    def on_stop_motion(self):
        """停止运动并回到0位置回调"""
        logging.info("🔴 GPIO触发: 停止运动并回到0位置")
        
        with self.motion_lock:
            if self.motion_running:
                self.stop_motion_flag.set()
                self.motion_running = False
            
        # 停止电机
        self.controller.stop_motors()
        time.sleep(0.1)
        
        # 停止手套监听
        self.stop_glove_listening()
        
        # 移动到0位置
        logging.info("正在移动到0位置...")
        self.controller.move_to_zero(velocity=20000, max_current=1000, wait_time=2.0)
        logging.info("✅ 已回到0位置")
        if self.enable_gpio:
            # 状态指示：待命
            self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_high(GPIO_PINS.READY_STATUS)

    def on_connect_device(self):
        """连接设备回调"""
        logging.info("🟢 GPIO触发: 连接设备")
        
        if self.controller.is_connected:
            logging.warning("⚠️ 设备已连接")
            return
        
        # 停止当前运动
        with self.motion_lock:
            self.stop_motion_flag.set()
            self.motion_running = False
        
        # 自动连接设备并开始循环运动
        logging.info("🔍 正在尝试自动连接设备...")
        if self.controller.connect(
                enable_motors=True, 
                home_motors=True, 
                home_wait_time=DEFAULT_HOME_TIME,
                device_index=self.device_index, 
                auto_select=self.device_index is None):
            logging.info("✅ 设备自动连接成功")
            if self.enable_gpio:
                self.gpio.output_high(GPIO_PINS.STATUS_LED)  # 状态LED亮起
                self.gpio.output_high(GPIO_PINS.READY_STATUS)
                self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
        else:
            logging.error("❌ 设备连接失败")
            if self.enable_gpio:
                self.gpio.output_low(GPIO_PINS.STATUS_LED)
                self.gpio.output_low(GPIO_PINS.READY_STATUS)
                self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)

    def on_disconnect_device(self):
        """断开设备回调"""
        logging.info("🟡 GPIO触发: 断开设备")
        
        # 停止当前运动
        with self.motion_lock:
            self.stop_motion_flag.set()
            self.motion_running = False
        
        # 断开连接
        self.controller.disconnect()
        if self.enable_gpio:
            self.gpio.output_low(GPIO_PINS.STATUS_LED)  # 状态LED熄灭
            self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            self.gpio.output_low(GPIO_PINS.READY_STATUS)
        logging.info("✅ 设备已断开")

    def _run_motion_cycle(self):
        """执行循环运动（在单独线程中运行）"""
        logging.info("🚀 开始循环运动")
        
        try:
            cycle_count = 0
            while not self.stop_motion_flag.is_set() and cycle_count < DEFAULT_CYCLE_COUNT:
                # 遍历循环位置
                for i, pos_list in enumerate(self.cycle_move_positions):
                    # 检查停止标志
                    if self.stop_motion_flag.is_set():
                        logging.info("⏹️ 运动被停止")
                        return
                    
                    # 运动前检查报警
                    # if self.controller.get_alarm():
                    #     logging.warning("⚠️ 检测到报警")
                    #     continue
                    
                    # 执行运动
                    success = self.controller.move_to_positions(
                        positions=pos_list,
                        velocity=DEFAULT_CYCLE_VELOCITY,
                        max_current=DEFAULT_CYCLE_CURRENT,
                        wait_time=DEFAULT_CYCLE_INTERVAL
                    )
                    
                    if not success:
                        logging.warning(f"⚠️ 位置 {i} 运动失败")
                        continue
                    
                    # 检查是否完成一个循环（回到第一个位置）
                    if i == len(self.cycle_move_positions) - 1:
                        # 完成一个循环，输出脉冲信号
                        logging.info("✅ 完成一个循环，输出完成信号")
                        if self.enable_gpio:
                            self.gpio.output_pulse(GPIO_PINS.CYCLE_COMPLETE, duration=0.5)
                    
                    # 再次检查停止标志
                    if self.stop_motion_flag.is_set():
                        logging.info("⏹️ 运动被停止")
                        return
                
                cycle_count += 1
                logging.info(f"🔄 准备下一个循环... (已完成 {cycle_count}/{DEFAULT_CYCLE_COUNT})")
            
            if cycle_count >= DEFAULT_CYCLE_COUNT:
                logging.info(f"✅ 完成全部 {DEFAULT_CYCLE_COUNT} 次循环运动")
            
        except Exception as e:
            logging.error(f"❌ 运动循环出错: {e}")
        finally:
            with self.motion_lock:
                self.motion_running = False
            if self.enable_gpio:
                # 状态指示：待命
                self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
                self.gpio.output_high(GPIO_PINS.READY_STATUS)
            logging.info("🏁 循环运动结束")
    
    def on_start_glove_listen(self):
        """开始手套监听回调"""
        logging.info("🟢 GPIO触发: 开始手套监听")
        if not self.controller.is_connected:
            logging.warning("⚠️ 设备未连接，无法开始手套监听")
            return
        
        with self.glove_lock:
            if self.glove_listening:
                logging.warning("⚠️ 手套监听已在运行中")
                return
            
            self.glove_listening = True
        
        # 启动手套监听
        self.start_glove_listening()
    
    def on_start_grasp(self):
        """开始抓握"""
        logging.info("✅ 开始抓握")
        
        # 检查是否有循环运动在运行，如果有则先停止
        with self.motion_lock:
            if self.motion_running:
                logging.info("⏹️ 检测到循环运动正在运行，先停止循环运动")
                self.stop_motion_flag.set()
                time.sleep(0.5)
            
            # 清除停止标志，准备开始抓握
            self.stop_motion_flag.clear()
            
            # 设置抓握运动状态
            self.motion_running = True
        
        try:
            for i in range(3):
                for i, pos_list in enumerate(self.grasp_positions):
                    # 检查停止标志
                    if self.stop_motion_flag.is_set():
                        logging.info("⏹️ 抓握被停止")
                        return
                    
                    # 执行抓握位置
                    success = self.controller.move_to_positions(
                        positions=pos_list,
                        velocity=DEFAULT_CYCLE_VELOCITY,
                        max_current=DEFAULT_CYCLE_CURRENT,
                        wait_time=2
                    )
                    
                    if not success:
                        logging.warning(f"⚠️ 抓握位置 {i} 运动失败")
                        continue
            
            logging.info("✅ 完成3次抓握")
                
            # 移动到0位置
            print("正在移动到0位置...")
            self.controller.move_to_zero(velocity=20000, max_current=1000, wait_time=2.0)
            logging.info("✅ 已回到0位置")
            
        finally:
            # 确保无论如何都能重置运动状态
            with self.motion_lock:
                self.motion_running = False
                # 保持stop_motion_flag的状态不变，以便外部可以知道是否是被停止的


    def start_glove_listening(self):
        """开始监听手套数据"""
        logging.info("🎧 开始监听手套数据")
        
        # 创建并启动UDP接收器
        try:
            self.glove_listener = UDPReceiver(self.glove_data_callback)
            self.glove_listener.start()
            logging.info("✅ 手套UDP接收器已启动")
        except Exception as e:
            logging.error(f"❌ 启动手套UDP接收器失败: {e}")
            with self.glove_lock:
                self.glove_listening = False
    
    def stop_glove_listening(self):
        """停止监听手套数据"""
        with self.glove_lock:
            if not self.glove_listening:
                return
            
            self.glove_listening = False
        
        logging.info("🛑 停止监听手套数据")
        
        # 停止UDP接收器
        if self.glove_listener:
            self.glove_listener.stop()
            self.glove_listener = None
            logging.info("✅ 手套UDP接收器已停止")
    
    def glove_data_callback(self, simple_glove_data_list):
        """手套数据回调函数
        
        Args:
            simple_glove_data_list: SimpleGloveData对象列表
        """
        if not simple_glove_data_list:
            return
        
        # 切换使用左右手，默认使用右手
        use_right_hand = True  # True 表示使用右手，False 表示使用左手
        
        for simple_glove_data in simple_glove_data_list:
            # 打印设备信息和校准状态
            logging.debug(f"手套设备: {simple_glove_data.device_name}")
            # 如果设备名称不是以teleop_开头则略过
            if not simple_glove_data.device_name.startswith("teleop_"):
                logging.debug(f"设备 {simple_glove_data.device_name} 不符合，跳过")
                continue
            
            # 根据选择检查校准状态，未校准则直接返回
            if use_right_hand:
                if not simple_glove_data.right_calibrated:
                    logging.warning("右手未校准，跳过此次数据")
                    return
                if simple_glove_data.right_angles:
                    logging.debug(f"右手角度数据: {simple_glove_data.right_angles}")
                    self.controller.move_to_angles(
                        angles=simple_glove_data.right_angles, 
                        velocity=200, 
                        max_current=1000, 
                        wait_time=0
                    )
            else:
                if not simple_glove_data.left_calibrated:
                    logging.warning("左手未校准，跳过此次数据")
                    return
                if simple_glove_data.left_angles:
                    logging.debug(f"左手角度数据: {simple_glove_data.left_angles}")
                    self.controller.move_to_angles(
                        angles=simple_glove_data.left_angles, 
                        velocity=200, 
                        max_current=1000, 
                        wait_time=0
                    )
            
            logging.debug("-" * 50)

    def run(self):
        """主运行函数"""
        logging.info("=" * 50)
        logging.info("LHandPro GPIO控制程序")
        logging.info("=" * 50)
        
        # 设置GPIO
        try:
            self.setup_gpio()
        except RuntimeError as e:
            error_msg = str(e)
            if "Not running on a RPi" in error_msg or "不在树莓派" in error_msg:
                logging.error("\n" + "="*60)
                logging.error("❌ GPIO设置失败")
                logging.error("="*60)
                logging.error(str(e))
                logging.error("\n提示:")
                logging.error("  - 此程序必须在树莓派硬件上运行")
                logging.error("  - 如果确实在树莓派上，请检查:")
                logging.error("    1. 是否正确安装了 RPi.GPIO")
                logging.error("    2. 是否有足够的权限 (sudo 或加入 gpio 组)")
                logging.error("    3. GPIO 是否被其他程序占用")
            else:
                logging.error(f"❌ GPIO设置失败: {e}")
            return -1
        except Exception as e:
            logging.error(f"❌ GPIO设置失败: {e}")
            logging.error("提示: 请确保在树莓派上运行，且已安装RPi.GPIO库")
            return -1
        
        logging.info("\nGPIO功能说明:")
        logging.info(f"  GPIO {GPIO_PINS.START_MOTION}: 开始循环运动")
        logging.info(f"  GPIO {GPIO_PINS.STOP_MOTION}: 停止运动并回到0位置")
        logging.info(f"  GPIO {GPIO_PINS.CONNECT}: 连接设备")
        logging.info(f"  GPIO {GPIO_PINS.DISCONNECT}: 断开设备")
        logging.info(f"  GPIO {GPIO_PINS.START_GLOVE_LISTEN}: 开始手套监听")
        logging.info(f"  GPIO {GPIO_PINS.CYCLE_COMPLETE}: 循环完成信号输出")
        logging.info(f"  GPIO {GPIO_PINS.STATUS_LED}: 状态LED输出")
        logging.info("\n按 Esc 键退出程序...\n")
        
        # 自动连接设备并开始循环运动
        logging.info("🔍 正在尝试自动连接设备...")
        if self.controller.connect(
                enable_motors=True,
                home_motors=True,
                home_wait_time=DEFAULT_HOME_TIME,
                device_index=self.device_index,
                auto_select=self.device_index is None):
            logging.info("✅ 设备自动连接成功")
            if self.enable_gpio:
                self.gpio.output_high(GPIO_PINS.STATUS_LED)  # 状态LED亮起
                self.gpio.output_high(GPIO_PINS.READY_STATUS)
                self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            
            # 自动开始循环运动
            logging.info("🚀 自动开始执行循环运动")
            self.on_start_motion()
        else:
            logging.error("❌ 设备自动连接失败")
            
            if self.enable_gpio:
                self.gpio.output_low(GPIO_PINS.STATUS_LED)
                self.gpio.output_low(GPIO_PINS.READY_STATUS)
                self.gpio.output_low(GPIO_PINS.RUNNING_STATUS)
            else:
                logging.error("❌ 设备自动连接失败，程序退出")
                return -1
        
        try:
            # 主循环，等待用户退出
            while True:
                if keyboard.is_pressed('esc'):
                    logging.info("\nEsc键按下，正在退出...")
                    break
                time.sleep(0.1)
        
        except KeyboardInterrupt:
            logging.info("\n程序被用户中断")
        
        finally:
            # 清理资源
            logging.info("正在清理资源...")
            
            # 停止运动
            with self.motion_lock:
                self.stop_motion_flag.set()
                self.motion_running = False
            
            # 停止手套监听
            self.stop_glove_listening()
            
            # 断开设备
            if self.controller.is_connected:
                self.controller.disconnect()
            
            # 清理GPIO
            if self.enable_gpio:
                self.gpio.cleanup()
            
            logging.info("✅ 资源清理完成")
        
        return 0


def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='LHandPro GPIO控制程序')
    
    # 添加设备索引参数
    parser.add_argument('--device-index', '-i', 
                      type=int, 
                      default=None, 
                      choices=[0, 1, 2, 3],
                      help='设备索引（用于区分不同USB接口的设备，可选值：0、1、2、3）')
    
    # 添加通信模式参数
    parser.add_argument('--communication-mode', '-m',
                      type=str,
                      default='ECAT',
                      choices=['CANFD', 'ECAT'],
                      help='设备通信模式（可选值：CANFD、ECAT）')
    
    # 添加GPIO启用参数
    parser.add_argument('--enable-gpio', '-g',
                      action='store_true',
                      default=True,
                      help='启用GPIO控制（默认：True）')
    parser.add_argument('--no-enable-gpio',
                      action='store_false',
                      dest='enable_gpio',
                      help='禁用GPIO控制')
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 配置日志系统
    setup_logging()
    
    # 创建运动控制器实例，传入通信模式、设备索引和GPIO启用状态
    motion_ctrl = MotionController(
        communication_mode=args.communication_mode,
        device_index=args.device_index,
        enable_gpio=args.enable_gpio
    )
    return motion_ctrl.run()


if __name__ == "__main__":
    sys.exit(main())