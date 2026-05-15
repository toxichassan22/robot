from brain.perception.frame_buffer import (
    FrameRingBuffer,
    PriorityFrameQueue,
    VLMFrameCandidate,
    now_ms,
)


def test_frame_ring_buffer_returns_keyframes_around_timestamp():
    buffer = FrameRingBuffer(max_frames=5)
    for i in range(5):
        buffer.append(f"frame-{i}", ts_ms=1_000 + i * 100, frame_index=i)

    frames = buffer.window_around(1_300, before_ms=250, after_ms=0, max_frames=2)

    assert [f.frame for f in frames] == ["frame-1", "frame-3"]
    assert [f.ts_ms for f in frames] == [1_100, 1_300]


def test_priority_frame_queue_drops_lowest_priority_when_full():
    base = now_ms()
    queue = PriorityFrameQueue(maxsize=2, max_age_ms=10_000)
    low = VLMFrameCandidate(10, base, b"low", "p", "idle")
    mid = VLMFrameCandidate(50, base + 1, b"mid", "p", "gesture")
    high = VLMFrameCandidate(90, base + 2, b"high", "p", "motion_start")

    assert queue.push(low)
    assert queue.push(mid)
    assert queue.push(high)

    items = queue.snapshot()
    assert [item.event_type for item in items] == ["motion_start", "gesture"]
    assert queue.stats()["dropped"] == 1


def test_priority_frame_queue_discards_stale_frames():
    queue = PriorityFrameQueue(maxsize=3, max_age_ms=100)
    old = VLMFrameCandidate(100, now_ms() - 1_000, b"old", "p", "motion_start")

    assert queue.push(old)

    assert queue.pop() is None
    assert queue.stats()["dropped_stale"] >= 1
