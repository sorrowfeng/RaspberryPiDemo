import threading


class MotionRuntimeState:
    """Shared motion state for cycle/grasp coordination."""

    def __init__(self):
        self.running = False
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()

    def start(self) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.stop_flag.clear()
            return True

    def stop(self):
        with self.lock:
            self.running = False
            self.stop_flag.set()

    def mark_idle(self):
        with self.lock:
            self.running = False
