import threading
import time
import logging

from brain.perception.frame_buffer import FrameRingBuffer, now_ms

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logging.warning("OpenCV not found. Camera will be disabled.")

class Camera:
    def __init__(
        self,
        index=0,
        width=640,
        height=480,
        fps=90,
        buffer_seconds=5.0,
        max_buffer_frames=300,
    ):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.buffer_seconds = buffer_seconds
        self.max_buffer_frames = max_buffer_frames
        self.cap = None
        self.last_frame = None
        self.last_frame_ts_ms = 0
        self.frame_index = 0
        buffer_frames = min(max(1, int(float(fps) * float(buffer_seconds))), int(max_buffer_frames))
        self.frame_buffer = FrameRingBuffer(max_frames=buffer_frames)
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
                    self.frame_index += 1
                    self.last_frame_ts_ms = now_ms()
                    self.last_frame = frame
                    self.frame_buffer.append(
                        frame,
                        ts_ms=self.last_frame_ts_ms,
                        frame_index=self.frame_index,
                    )
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

    def get_latest_frame_info(self):
        with self.frame_lock:
            latest = self.frame_buffer.latest()
            if latest is not None:
                return latest
            if self.last_frame is not None:
                self.frame_index += 1
                self.last_frame_ts_ms = now_ms()
                return self.frame_buffer.append(
                    self.last_frame,
                    ts_ms=self.last_frame_ts_ms,
                    frame_index=self.frame_index,
                ).copied()
            return None

    def get_frame_history(self):
        with self.frame_lock:
            return self.frame_buffer.snapshot()

    def get_keyframes_around(self, ts_ms, before_ms=700, after_ms=0, max_frames=3):
        with self.frame_lock:
            return self.frame_buffer.window_around(
                int(ts_ms),
                before_ms=int(before_ms),
                after_ms=int(after_ms),
                max_frames=int(max_frames),
            )
