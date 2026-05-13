import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock
import numpy as np

from brain.vision.qwen_expert_pool import QwenExpertPool, QwenAnalysis

class MockCamera:
    def get_latest_frame(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)

class MockVLMClient:
    def __init__(self, delay=1.0):
        self.delay = delay
        self.call_count = 0

    async def analyze_image_async(self, model, image_bytes, prompt, device):
        self.call_count += 1
        await asyncio.sleep(self.delay)
        return f"Analysis result {self.call_count}"

@pytest.mark.anyio
async def test_qwen_pool_staggering():
    vlm = MockVLMClient(delay=0.5)
    cam = MockCamera()
    pool = QwenExpertPool(vlm, cam, pool_size=2, cadence_s=0.2)
    
    await pool.start()
    await pool.wake()
    
    # Wait for some results
    await asyncio.sleep(1.0)
    
    queue = pool.analysis_stream()
    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    
    assert len(results) >= 2
    # Verify worker IDs are present
    worker_ids = {r.worker_id for r in results}
    assert 0 in worker_ids
    assert 1 in worker_ids
    
    await pool.stop()

@pytest.mark.asyncio
async def test_qwen_pool_backpressure():
    # Long delay to fill queue
    vlm = MockVLMClient(delay=0.1)
    cam = MockCamera()
    # Queue size is 5
    pool = QwenExpertPool(vlm, cam, pool_size=1, cadence_s=0.1)
    
    await pool.start()
    await pool.wake()
    
    # Let it produce more than 5 results
    await asyncio.sleep(1.0)
    
    queue = pool.analysis_stream()
    assert queue.qsize() == 5
    
    results = []
    while not queue.empty():
        results.append(queue.get_nowait())
    
    # Check if they are the latest ones (timestamp should be increasing)
    for i in range(len(results) - 1):
        assert results[i].timestamp_ms <= results[i+1].timestamp_ms
        
    await pool.stop()

@pytest.mark.asyncio
async def test_qwen_pool_wake_sleep():
    vlm = MockVLMClient(delay=0.1)
    cam = MockCamera()
    pool = QwenExpertPool(vlm, cam, pool_size=1, cadence_s=0.1)
    
    await pool.start()
    
    # Should be empty initially
    assert pool.analysis_stream().empty()
    
    await pool.wake()
    await asyncio.sleep(0.3)
    assert not pool.analysis_stream().empty()
    
    # Clear queue
    while not pool.analysis_stream().empty():
        pool.analysis_stream().get_nowait()
        
    await pool.sleep()
    await asyncio.sleep(0.5)
    
    # Should still be empty (or at most 1 if it was in flight)
    assert pool.analysis_stream().qsize() <= 1
    
    await pool.stop()

if __name__ == "__main__":
    asyncio.run(test_qwen_pool_staggering())
    asyncio.run(test_qwen_pool_backpressure())
    asyncio.run(test_qwen_pool_wake_sleep())
