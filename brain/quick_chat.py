"""
quick_chat.py — شات سريع (Standard Ollama + XTTS)
"""
import sys, os, time
from ollama import chat

# === Path Setup ===
BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)
sys.path.insert(0, PROJECT_ROOT)

# ── Load .env from config/ ───────────────────────────────────
env_path = os.path.join(PROJECT_ROOT, 'config', '.env')
if os.path.exists(env_path):
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

from brain.speech.tts import XttsTTS

# ── Config ──────────────────────────────────────────
MODEL = os.getenv("OLLAMA_MODEL", "gemini-3-flash-preview")

SYSTEM_PROMPT = (
    "أنت مساعد ذكي اسمك آريا. أنت روبوت بتتكلم عربي عامي مصري.\n"
    "القواعد:\n"
    "1. رد على السؤال بالظبط ومباشرة.\n"
    "2. اتكلم بطريقة طبيعية وبسيطة، زي ما الناس بتتكلم في العادي بدون تكلف.\n"
    "3. ردودك لازم تكون قصيرة وواضحة (جملة أو اتنين بالكتير).\n"
    "4. خليك ودود ومحترم بس طبيعي."
)

CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")

tts_engine = XttsTTS(
    base_dir=os.getenv("XTTS_BASE_DIR", os.path.join(CONFIG_DIR, "models", "xtts", "XTTS_v2_base")),
    checkpoint_path=os.getenv("XTTS_CHECKPOINT", os.path.join(CONFIG_DIR, "models", "xtts", "xtts_ft", "checkpoint_epoch_25.pth")),
    speaker_wav=os.getenv("XTTS_SPEAKER", os.path.join(CONFIG_DIR, "models", "xtts", "source_audio", "egyptian_voice.wav")),
    language="ar",
    cache_dir=os.getenv("XTTS_CACHE_DIR", os.path.join(CONFIG_DIR, "data", "tts_cache"))
)

# ── LLM Chat ────────────────────────────────────────
def ask(messages: list[dict]) -> str:
    """Call Ollama directly (Local/Proxy)"""
    try:
        response = chat(model=MODEL, messages=messages)
        return response.message.content.strip()
    except Exception as e:
        return f"Error (Ollama): {e}\n(Make sure 'ollama serve' is running and supports '{MODEL}')"

def main():
    print(f"Model: {MODEL} (via Ollama Library)")
    print("Loading XTTS voice (background)...")
    tts_engine.start()

    print(f"\n{'='*50}")
    print(f"Chat with Aria (type 'exit' to quit)")
    print(f"{'='*50}")

    # Wait briefly for TTS model to start loading so we can show readiness
    while tts_engine.model is None and tts_engine._running:
        time.sleep(0.5)
        
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in ("exit", "quit"):
            break

        history.append({"role": "user", "content": text})
        print("Thinking...", end=" ", flush=True)
        t0 = time.time()

        try:
            reply = ask(history)
            dt = time.time() - t0
            print(f"({dt:.1f}s)")
            print(f"Aria: {reply}")
            history.append({"role": "assistant", "content": reply})

            # Play audio non-blocking through XttsTTS
            tts_engine.say(reply)

        except Exception as e:
            print(f"\nError: {e}")

    tts_engine.stop()
    print("Bye!")

if __name__ == "__main__":
    main()