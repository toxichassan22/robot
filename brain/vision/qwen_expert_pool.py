from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import cv2
import numpy as np

from brain.vision.vlm_client import VLMClient

logger = logging.getLogger(__name__)

@dataclass
class QwenAnalysis:
    worker_id: int
    timestamp_ms: int
    text: str
    latency_ms: int
    completed_ts_ms: int | None = None
    frame_age_ms: int | None = None
    error: str | None = None

class QwenExpertPool:
    """
    A pool of Qwen workers that perform deep visual analysis on frames.
    Workers are staggered to provide a steady stream of analysis.
    """
    def __init__(
        self,
        vlm_client: VLMClient,
        camera: Any,
        model: str = "qwen3-vl:8b",
        pool_size: int = 4,
        cadence_s: float = 0.75,
        device: str = "gpu",
        prompt: str = "Describe this image in detail.",
    ):
        self.vlm_client = vlm_client
        self.camera = camera
        self.model = model
        self.pool_size = pool_size
        self.cadence_s = cadence_s
        self.device = device
        self.prompt = prompt

        self._tasks: list[asyncio.Task] = []
        self._wake_event = asyncio.Event()
        self._queue: asyncio.Queue[QwenAnalysis] = asyncio.Queue(maxsize=5)
        self._is_running = False

    @property
    def is_active(self) -> bool:
        return self._wake_event.is_set()

    def analysis_stream(self) -> asyncio.Queue[QwenAnalysis]:
        return self._queue

    async def start(self):
        """Starts the worker tasks. They will wait for the wake event."""
        if self._is_running:
            return
        
        self._is_running = True
        for i in range(self.pool_size):
            task = asyncio.create_task(self._worker_loop(i))
            self._tasks.append(task)
        logger.info(f"Qwen Pool: Started with {self.pool_size} workers.")

    async def stop(self):
        """Stops all worker tasks."""
        self._is_running = False
        self._wake_event.clear()
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        logger.info("Qwen Pool: Stopped.")

    async def wake(self):
        """Wakes up the workers to start staggered analysis."""
        if not self._wake_event.is_set():
            self._wake_event.set()
            logger.info(f"Qwen Pool: woke (size={self.pool_size}, cadence={self.cadence_s}s)")

    async def sleep(self):
        """Tells workers to sleep after finishing their current analysis."""
        if self._wake_event.is_set():
            self._wake_event.clear()
            logger.info("Qwen Pool: sleeping...")

    async def _worker_loop(self, worker_id: int):
        """Main loop for a single Qwen worker."""
        try:
            while self._is_running:
                # Wait for the pool to be active
                await self._wake_event.wait()

                # Staggered start: wait for offset on first run after wake
                # To handle subsequent runs in the same wake session, 
                # we don't sleep here unless we want to maintain the cadence relative to wake.
                # The ticket says: "Each worker i waits i * cadence_s seconds before first capture"
                await asyncio.sleep(worker_id * self.cadence_s)

                while self._wake_event.is_set() and self._is_running:
                    # 1. Capture frame with its original camera timestamp when available.
                    frame_ts_ms = int(time.time() * 1000)
                    get_info = getattr(self.camera, "get_latest_frame_info", None)
                    if callable(get_info):
                        record = get_info()
                        frame = getattr(record, "frame", None) if record is not None else None
                        frame_ts_ms = int(getattr(record, "ts_ms", frame_ts_ms)) if record is not None else frame_ts_ms
                    else:
                        frame = self.camera.get_latest_frame()
                    if frame is None:
                        await asyncio.sleep(0.1)
                        continue

                    # 2. Encode to JPEG
                    jpeg_bytes = self._encode_frame(frame)
                    if not jpeg_bytes:
                        await asyncio.sleep(0.1)
                        continue

                    # 3. Analyze
                    start_time = time.monotonic()
                    try:
                        analysis_text = await self.vlm_client.analyze_image_async(
                            model=self.model,
                            image_bytes=jpeg_bytes,
                            prompt=self.prompt,
                            device=self.device,
                        )
                        latency_ms = int((time.monotonic() - start_time) * 1000)
                        
                        analysis = QwenAnalysis(
                            worker_id=worker_id,
                            timestamp_ms=frame_ts_ms,
                            text=analysis_text,
                            latency_ms=latency_ms,
                            completed_ts_ms=int(time.time() * 1000),
                            frame_age_ms=max(0, int(time.time() * 1000) - frame_ts_ms),
                        )
                        logger.info(f"Worker {worker_id}: analysis ready in {latency_ms}ms")
                        
                        # 4. Push to queue with "drop oldest" backpressure
                        self._push_to_queue(analysis)

                    except Exception as e:
                        logger.error(f"Worker {worker_id}: analysis failed: {e}")
                        # Push error analysis if needed, or just continue
                    
                    # Small sleep to yield
                    await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Worker {worker_id} crashed: {e}")

    def _encode_frame(self, bgr_frame: np.ndarray, quality: int = 75, max_dim: int = 720) -> bytes | None:
        """Encodes a BGR frame to JPEG format, similar to gemini_live_vision."""
        try:
            h, w = bgr_frame.shape[:2]
            if max(h, w) > max_dim:
                scale = max_dim / max(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                bgr_frame = cv2.resize(bgr_frame, (new_w, new_h))
            
            success, jpeg_bytes = cv2.imencode(".jpg", bgr_frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if success:
                return jpeg_bytes.tobytes()
        except Exception as e:
            logger.error(f"Failed to encode frame to JPEG: {e}")
        return None

    def _push_to_queue(self, analysis: QwenAnalysis):
        """Pushes analysis to queue, dropping oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
        
        try:
            self._queue.put_nowait(analysis)
        except asyncio.QueueFull:
            # Should not happen given the get_nowait above, but for safety:
            pass
