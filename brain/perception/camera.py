import threading
import time
import logging

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV not found. Camera will be disabled.")

class Camera:
    def __init__(self, index=0, width=640, height=480, fps=90):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap = None
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        
        if not CV2_AVAILABLE:
            logging.info("Camera started (Mock mode - No OpenCV).")
            self.running = True
            return

        logging.info(f"Opening camera {self.index} ({self.width}x{self.height} @ {self.fps}fps)...")
        self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            logging.error(f"Failed to open camera {self.index}")
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logging.info("Camera started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        logging.info("Camera stopped.")

    def _capture_loop(self):
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self.frame_lock:
                    self.last_frame = frame
            else:
                logging.warning("Failed to read frame from camera.")
                time.sleep(1) # Wait a bit before retrying or maybe break?
                # For robustness, we'll just wait.
            
            time.sleep(0.01) # Small sleep to yield

    def get_latest_frame(self):
        with self.frame_lock:
            if self.last_frame is not None:
                return self.last_frame.copy()
            return None
