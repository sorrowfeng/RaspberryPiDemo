import socket
import threading
import json


class Parameter:
    """
    参数类，存储名称和值
    """
    def __init__(self):
        self.name = ""
        self.value = 0.0


class SimpleGloveData:
    """
    简化的手套数据类，只包含需要的信息
    """
    def __init__(self):
        self.device_name = ""         # 设备名称
        self.left_calibrated = False    # 左手校准状态
        self.right_calibrated = False   # 右手校准状态
        self.left_angles = [0.0] * 6    # 左手角度列表
        self.right_angles = [0.0] * 6   # 右手角度列表


class UDPReceiver:
    def __init__(self, host='127.0.0.1', port=7777, buffer_size=1024):
        """
        UDP接收器初始化
        :param host: 监听主机地址
        :param port: 监听端口
        :param buffer_size: 接收缓冲区大小
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.socket = None
        self.running = False
        self.thread = None
        self.callback = None

    def set_callback(self, callback):
        """
        设置数据接收回调函数
        :param callback: 回调函数，接收解析后的GloveData对象列表作为参数
        """
        self.callback = callback

    def start(self):
        """
        启动UDP接收器
        """
        if self.running:
            print("UDP接收器已经在运行中")
            return

        try:
            # 创建UDP套接字
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind((self.host, self.port))
            self.running = True
            
            # 启动接收线程
            self.thread = threading.Thread(target=self._receive_loop)
            self.thread.daemon = True
            self.thread.start()
            print(f"UDP接收器已启动，监听 {self.host}:{self.port}")
            
        except Exception as e:
            print(f"启动UDP接收器失败: {e}")
            self.running = False
            if self.socket:
                self.socket.close()
                self.socket = None

    def stop(self):
        """
        停止UDP接收器
        """
        if not self.running:
            return

        self.running = False
        
        if self.thread and self.thread.is_alive():
            # 发送一个空数据包到自己以唤醒阻塞的recvfrom调用
            try:
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b'', (self.host, self.port))
            except:
                pass
            
        if self.socket:
            self.socket.close()
            self.socket = None
            
        print("UDP接收器已停止")

    def _receive_loop(self):
        """
        接收数据的内部循环
        """
        while self.running:
            try:
                data, addr = self.socket.recvfrom(self.buffer_size)
                if data:
                    # 解析JSON数据
                    glove_data_list = self._parse_json(data)
                    if self.callback:
                        self.callback(glove_data_list)
            except Exception as e:
                if self.running:  # 只有在接收器运行时才打印错误
                    print(f"UDP接收错误: {e}")

    def _parse_json(self, json_buffer):
        """
        解析JSON数据
        :param json_buffer: JSON数据缓冲区（bytes类型）
        :return: SimpleGloveData对象列表
        """
        simple_glove_data_list = []
        
        try:
            # 解析JSON数据
            received_data = json.loads(json_buffer.decode('utf-8'))
            
            for device_name, device_data in received_data.items():
                # 创建简化数据对象
                simple_data = SimpleGloveData()
                simple_data.device_name = device_name
                
                # 解析Parameter数据
                params = device_data.get("Parameter", [])
                if isinstance(params, list):
                    # 先收集所有参数
                    param_dict = {}
                    for param in params:
                        p_name = param.get("Name", "")
                        if p_name:
                            p_value = param.get("Value", 0.0)
                            if isinstance(p_value, (int, float)):
                                param_dict[p_name] = float(p_value)
                            elif isinstance(p_value, str):
                                try:
                                    param_dict[p_name] = float(p_value)
                                except ValueError:
                                    param_dict[p_name] = 0.0
                    
                    # 检查校准状态：只有L_CalibrationStatus和R_CalibrationStatus都等于3才认为校准完成
                    simple_data.left_calibrated = param_dict.get("L_CalibrationStatus", 0) == 3
                    simple_data.right_calibrated = param_dict.get("R_CalibrationStatus", 0) == 3
                    # 提取右手角度数据
                    simple_data.right_angles[0] = -param_dict.get("r2", 0.0)
                    simple_data.right_angles[1] = -param_dict.get("r0", 0.0)
                    simple_data.right_angles[2] = -param_dict.get("r5", 0.0)
                    simple_data.right_angles[3] = -param_dict.get("r9", 0.0)
                    simple_data.right_angles[4] = -param_dict.get("r13", 0.0)
                    simple_data.right_angles[5] = -param_dict.get("r17", 0.0)
                    
                    # 提取左手角度数据
                    simple_data.left_angles[0] = -param_dict.get("l2", 0.0)
                    simple_data.left_angles[1] = -param_dict.get("l0", 0.0)
                    simple_data.left_angles[2] = -param_dict.get("l5", 0.0)
                    simple_data.left_angles[3] = -param_dict.get("l9", 0.0)
                    simple_data.left_angles[4] = -param_dict.get("l13", 0.0)
                    simple_data.left_angles[5] = -param_dict.get("l17", 0.0)
                
                simple_glove_data_list.append(simple_data)
                
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
        except Exception as e:
            print(f"解析数据错误: {e}")
        
        return simple_glove_data_list


def vector_to_map(param_list):
    """
    将参数列表转换为字典
    :param param_list: 参数列表
    :return: 参数字典
    """
    result = {}
    for param in param_list:
        result[param.name] = param.value
    return result
