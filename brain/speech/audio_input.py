import queue
import logging
import threading
import numpy as np

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    logging.warning("sounddevice not found. Audio input disabled.")

class AudioStream:
    def __init__(self, sample_rate=16000, block_size=4000, device=None):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self.queue = queue.Queue()
        self.stream = None
        self.running = False

    def _callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            logging.debug(f"Audio status: {status}")
        self.queue.put(bytes(indata))

    def start(self):
        if not SD_AVAILABLE:
            logging.info("AudioStream start ignored (mock mode).")
            return

        if self.running:
            return

        try:
            logging.info(f"Starting AudioStream (device={self.device}, sr={self.sample_rate})...")
            self.stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                device=self.device,
                dtype='int16',
                channels=1,
                callback=self._callback
            )
            self.stream.start()
            self.running = True
        except Exception as e:
            logging.error(f"Failed to start AudioStream: {e}")
            self.running = False


    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        logging.info("AudioStream stopped.")

    def read(self, timeout=None):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None
