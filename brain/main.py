import os
import asyncio
import logging

# Suppress MediaPipe and TensorFlow log spam
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '3'

# Set up logging to WARNING to hide internal info spam
logging.basicConfig(
    level=logging.WARNING, 
    format='%(message)s'
)
# We will use direct print() for the 3 things the user wants
logging.getLogger("absl").setLevel(logging.ERROR)
logging.getLogger("mediapipe").setLevel(logging.ERROR)
logging.getLogger("google").setLevel(logging.ERROR)

from brain.ears_mouth import start_ears_and_mouth, perceiver as shared_perceiver
from brain.memory.context_manager import context_manager

# Real vision task using the UnifiedPerceiver from ears_mouth
async def real_vision_task():
    logger = logging.getLogger("Senses.Eyes")
    logger.info("👀 Vision system starting...")
    
    # Start the camera
    shared_perceiver.start()
    
    try:
        while True:
            # Capture a frame and process it (VLM, gestures, etc.)
            # We run it in a thread to keep the loop responsive
            state = await asyncio.to_thread(shared_perceiver.perceive, run_vlm=True)
            
            # Update the global context manager with the new description
            if state.vision_desc:
                context_manager.add_vision_state(
                    entities=state.vision.get("entities", []) if state.vision else [],
                    action=state.vision.get("action", "observing") if state.vision else "observing",
                    raw_description=state.vision_desc
                )
            
            # Small delay to prevent CPU saturation
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Vision task crashed: {e}")
    finally:
        shared_perceiver.stop()

async def main():
    print("==================================================")
    print("🤖 ARIA MULTI-AGENT DEBATE ARCHITECTURE STARTING...")
    print("==================================================")
    
    # Run the vision gathering and the Gemini Live audio/routing interface concurrently
    await asyncio.gather(
        real_vision_task(),
        start_ears_and_mouth()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 System shutdown. Goodbye!")
