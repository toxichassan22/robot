import asyncio
import os
import sys
import io
from pathlib import Path

# Force stdout/stderr to use UTF-8 to handle Arabic text and emojis on Windows consoles
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load dotenv to configure API keys
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "config" / ".env", override=True)

async def test_kimi():
    print("[INFO] Starting test for Kimi 2.6 via OpenRouter...")
    try:
        from brain.models import deepseek
        
        print("Model wrapper details:")
        print(f" - Name: {deepseek.name}")
        print(f" - Model ID: {deepseek.model_name}")
        
        prompt = "ما هي عاصمة مصر؟ أجب باختصار في كلمة واحدة."
        print(f"\n[PROMPT] Sending prompt: '{prompt}'")
        
        response = await deepseek.generate(prompt, "You are a helpful AI assistant.")
        print(f"\n[RESPONSE] Response received from Kimi 2.6:")
        print("----------------------------------------")
        print(response)
        print("----------------------------------------")
        print("[SUCCESS] Test Succeeded!")
        
    except Exception as e:
        print(f"\n[ERROR] Test Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_kimi())
