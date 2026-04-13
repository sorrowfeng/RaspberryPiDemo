import logging

from udp_receiver import UDPReceiver


class GloveListenerService:
    """Handles UDP glove listening."""

    def __init__(self, session):
        self.session = session
        self.listener = None
        self.listening = False
        self.lock = __import__("threading").Lock()

    def start(self):
        logging.info("GPIO 触发: 开始手套监听")
        if not self.session.controller.is_connected:
            logging.warning("设备未连接，无法开始手套监听")
            return

        with self.lock:
            if self.listening:
                logging.warning("手套监听已在运行中")
                return
            self.listening = True

        try:
            self.listener = UDPReceiver(self.data_callback)
            self.listener.start()
            logging.info("手套 UDP 接收器已启动")
        except Exception as exc:
            logging.error(f"启动手套 UDP 接收器失败: {exc}")
            with self.lock:
                self.listening = False

    def stop(self):
        with self.lock:
            if not self.listening:
                return
            self.listening = False

        logging.info("停止监听手套数据")
        if self.listener:
            self.listener.stop()
            self.listener = None
            logging.info("手套 UDP 接收器已停止")

    def data_callback(self, simple_glove_data_list):
        if not simple_glove_data_list:
            return

        use_right_hand = True
        for simple_glove_data in simple_glove_data_list:
            if not simple_glove_data.device_name.startswith("teleop_"):
                continue

            if use_right_hand:
                if not simple_glove_data.right_calibrated:
                    logging.warning("右手未校准，跳过本次数据")
                    return
                if simple_glove_data.right_angles:
                    self.session.controller.move_to_angles(
                        angles=simple_glove_data.right_angles,
                        angular_velocity=200,
                        max_current=1000,
                        wait_time=0,
                    )
            else:
                if not simple_glove_data.left_calibrated:
                    logging.warning("左手未校准，跳过本次数据")
                    return
                if simple_glove_data.left_angles:
                    self.session.controller.move_to_angles(
                        angles=simple_glove_data.left_angles,
                        angular_velocity=200,
                        max_current=1000,
                        wait_time=0,
                    )
