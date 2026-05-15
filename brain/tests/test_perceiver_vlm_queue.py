import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from brain.config import BrainConfig
from brain.perception.frame_buffer import FrameRingBuffer, now_ms
from brain.perception.perceiver import UnifiedPerceiver


class BufferedMockCamera:
    def __init__(self):
        self.buffer = FrameRingBuffer(max_frames=10)
        self.index = 0

    def push(self, frame, ts_ms):
        self.index += 1
        self.buffer.append(frame, ts_ms=ts_ms, frame_index=self.index)

    def get_latest_frame_info(self):
        return self.buffer.latest()

    def get_latest_frame(self):
        record = self.buffer.latest()
        return record.frame if record is not None else None

    def get_keyframes_around(self, ts_ms, before_ms=700, after_ms=0, max_frames=3):
        return self.buffer.window_around(
            ts_ms,
            before_ms=before_ms,
            after_ms=after_ms,
            max_frames=max_frames,
        )


class MockVLM:
    def analyze_image(self, model, image_bytes, prompt, device):
        return "fresh visual description"


def _perceiver_without_worker() -> UnifiedPerceiver:
    cfg = BrainConfig(
        gesture_detection_enabled=False,
        perf_mediapipe_schedule=("idle",),
        perf_vlm_queue_size=5,
        perf_vlm_max_frame_age_ms=10_000,
    )
    perceiver = UnifiedPerceiver(cfg)
    perceiver.vlm = MockVLM()
    perceiver._ensure_vlm_worker = lambda: None
    return perceiver


def test_perceiver_queues_motion_burst_with_original_frame_timestamps():
    perceiver = _perceiver_without_worker()
    camera = BufferedMockCamera()
    perceiver.camera = camera
    base = now_ms()

    first = np.zeros((80, 80, 3), dtype=np.uint8)
    second = first.copy()
    second[10:55, 10:55] = 255

    camera.push(first, base)
    perceiver.perceive(run_vision=True, run_gesture=False, run_vlm=False)

    camera.push(second, base + 500)
    state = perceiver.perceive(run_vision=True, run_gesture=False, run_vlm=True)

    queued = perceiver._vlm_queue.snapshot()
    events = {item.event_type: item.frame_ts_ms for item in queued}
    assert state.motion_detected is True
    assert events["motion_pre"] == base
    assert events["motion_start"] == base + 500
    assert state.vlm_queue and state.vlm_queue["size"] >= 2


def test_vlm_result_metadata_uses_original_frame_timestamp():
    perceiver = _perceiver_without_worker()
    frame_ts = now_ms() - 250

    desc = perceiver._run_vlm_request(
        b"jpeg",
        "prompt",
        blocking=True,
        frame_ts_ms=frame_ts,
        event_type="motion_start",
        priority=95,
    )
    state = perceiver.perceive(run_vision=False, run_gesture=False, run_vlm=True)

    assert desc == "fresh visual description"
    assert state.vision_desc == "fresh visual description"
    assert state.vision_desc_ts_ms == frame_ts
    assert state.vision_desc_event == "motion_start"
    assert state.vision_desc_latency_ms is not None
    assert state.vision_desc_age_ms is not None
