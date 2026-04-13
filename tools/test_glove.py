"""Quick UDP glove listener test."""

from udp_receiver import UDPReceiver


def glove_data_callback(glove_data_list):
    for simple_glove_data in glove_data_list:
        print(f"Device: {simple_glove_data.device_name}")
        print(f"Left calibrated: {'yes' if simple_glove_data.left_calibrated else 'no'}")
        print(f"Right calibrated: {'yes' if simple_glove_data.right_calibrated else 'no'}")
        right_angles_str = ",".join(f"{angle:.2f}" for angle in simple_glove_data.right_angles)
        left_angles_str = ",".join(f"{angle:.2f}" for angle in simple_glove_data.left_angles)
        print(f"Right angles: {right_angles_str}")
        print(f"Left angles: {left_angles_str}")
        print("-" * 50)


def main():
    udp_receiver = UDPReceiver(host="127.0.0.1", port=7777, buffer_size=4096)
    udp_receiver.set_callback(glove_data_callback)
    udp_receiver.start()

    try:
        print("Glove receiver started. Press Ctrl+C to stop.")
        while True:
            pass
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        udp_receiver.stop()


if __name__ == "__main__":
    main()
