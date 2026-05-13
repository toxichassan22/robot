from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio

from .. import core

app = core.app

async def frame_generator():
    # We need to access the perceiver from the runtime. 
    # Since core.py doesn't have a direct link to perceiver, we might need to get it from state_manager 
    # Or we can just use the global app state if we inject it.
    
    while True:
        perceiver = getattr(app.state, "perceiver", None)
        if perceiver:
            try:
                # get snapshot_jpeg
                jpg = perceiver.snapshot_jpeg()
                if jpg:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
            except Exception:
                pass
        await asyncio.sleep(0.1)

@app.get("/api/camera/stream")
async def video_stream():
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
