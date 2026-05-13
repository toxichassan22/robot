"""Quick test to see why the web server fails to bind."""
import os
import sys
import traceback

# Don't redirect stderr
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "3"

sys.path.insert(0, os.path.dirname(__file__))

try:
    from brain.pi5.web_ui_backend.main import app
    print(f"[OK] FastAPI app loaded: {app}")
except Exception as e:
    print(f"[FAIL] Could not import FastAPI app: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    import uvicorn
    print(f"[OK] uvicorn version: {uvicorn.__version__}")
except Exception as e:
    print(f"[FAIL] uvicorn import: {e}")
    sys.exit(1)

print("[INFO] Attempting to start server on 0.0.0.0:8000...")
try:
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
except Exception as e:
    print(f"[FAIL] Server crashed: {e}")
    traceback.print_exc()
    sys.exit(1)
