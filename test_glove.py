from udp_receiver import UDPReceiver


def glove_data_callback(glove_data_list):
    """
    手套数据回调函数
    :param glove_data_list: 解析后的SimpleGloveData对象列表
    """
    for simple_glove_data in glove_data_list:
        # 打印设备名称
        print(f"设备名称: {simple_glove_data.device_name}")
        
        # 打印校准状态
        print(f"左手校准状态: {'已校准' if simple_glove_data.left_calibrated else '未校准'}")
        print(f"右手校准状态: {'已校准' if simple_glove_data.right_calibrated else '未校准'}")
        
        # 打印角度数据
        right_angles_str = ",".join([f"{angle:.2f}" for angle in simple_glove_data.right_angles])
        left_angles_str = ",".join([f"{angle:.2f}" for angle in simple_glove_data.left_angles])
        print(f"右手角度: {right_angles_str}")
        print(f"左手角度: {left_angles_str}")
        print("-" * 50)


def main():
    """
    主函数
    """
    # 创建UDP接收器
    udp_receiver = UDPReceiver(host='127.0.0.1', port=7777, buffer_size=4096)
    
    # 设置回调函数
    udp_receiver.set_callback(glove_data_callback)
    
    # 启动UDP接收器
    udp_receiver.start()
    
    try:
        # 保持程序运行
        print("手套数据接收器已启动，按Ctrl+C停止...")
        while True:
            pass
    except KeyboardInterrupt:
        print("\n程序正在停止...")
    finally:
        # 停止UDP接收器
        udp_receiver.stop()


if __name__ == "__main__":
    main()
