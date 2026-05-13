import asyncio

from brain.runtime import BrainRuntime


def test_demo_runs():
    runtime = BrainRuntime.from_env()
    asyncio.run(runtime.demo(steps=2))

