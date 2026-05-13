# 🤖 Robot AI System — Aria

## قواعد العمل الإلزامية

- قبل أي شغل، لازم يتم قراءة الملف `d:\robot new version\.agent\verrrrry_important_file.md`
- أي ملفات تشغيل/كود/بيانات جديدة لازم تكون فقط داخل `brain/`, `firmware/`, `dashboard/`, `config/`, `scratch/`
- الموجود في الجذر مثل `README.md`, `.agent/`, `.vscode/`, `.gitignore` يعتبر ملفات Workspace/Guidance وليس مكانًا لوضع كود أو بيانات تشغيل

## هيكل المشروع

المشروع مقسم إلى **5 فولدرات رئيسية**، مع بقاء ملفات Workspace الإرشادية في الجذر فقط:

```
robot/
├── 🧠 brain/              ← عقل الروبوت (AI + Speech + Vision + Debate + Memory + Live Audio)
├── ⚡ firmware/           ← كود الهاردوير (ESP32 + Arduino)
├── �️ dashboard/         ← واجهة التحكم ولوحة المراقبة
├── 📦 config/            ← الإعدادات والموارد والملفات المرجعية
├── scratch/              ← مساحة الاختبارات والملفات المؤقتة
└── README.md             ← وثيقة المشروع الأساسية
```

---

## 🧠 brain/ — عقل الروبوت
> **المكان:** `brain/`  
> **بيشتغل على:** Mini PC  
> **اللغة:** Python

كل كود الذكاء الاصطناعي والتحكم في الروبوت:

| المجلد | الوظيفة |
|--------|---------|
| `brain/cognition/` | التفكير والقرارات (Planner, Safety Rules, Motion Planner) |
| `brain/llm/` | الاتصال بنماذج اللغة (Ollama, OpenAI, Gemini, HuggingFace) |
| `brain/speech/` | الكلام: STT (Vosk/Google) + TTS (Edge/Gemini/XTTS/Piper/Chatterbox) + Audio FSM |
| `brain/perception/` | الرؤية (كاميرا + إيماءات + VLM + GovernedPerceiver) |
| `brain/vision/` | VLM Client (نماذج الرؤية — Qwen VL) |
| `brain/memory/` | الذاكرة (SQLite + Feedback + **Topic Memory**) |
| `brain/transport/` | الاتصال بالهاردوير (Serial/TCP → ESP32) |
| `brain/state/` | حالة الروبوت (State Manager) |
| `brain/heartbeat/` | مراقبة نبض الاتصال |
| `brain/thermal/` | مراقبة الحرارة |
| `brain/pi5/` | كود خاص بالـ Raspberry Pi 5 + Web UI Backend (FastAPI) |
| `brain/libs/` | مكتبات محلية (مشكال للتشكيل العربي) |
| `brain/tests/` | التيستات |
| `brain/shared/` | إعدادات مشتركة (Docker, Legacy) |

**ملفات رئيسية في brain/:**

| الملف | الوظيفة |
|-------|---------|
| `brain/runtime.py` | المحرك الرئيسي — بيشغل كل الأنظمة مع بعض |
| `brain/debate_engine.py` | 🏛️ محرك النقاش بين 5 موديلات AI (6 جولات) |
| `brain/models.py` | تعريف الموديلات الخمسة (DeepSeek, Minimax, Qwen, Nemotron, GLM) |
| `brain/config.py` | إعدادات النظام الشاملة |
| `brain/main.py` | مدخل التشغيل القديم المبني على Gemini Live + vision context |
| `brain/live_aria.py` | تجربة الصوت المباشر مع Gemini Live |
| `brain/ears_mouth.py` | واجهة Gemini Live Audio routing |
| `brain/web_server.py` | سيرفر FastAPI للداشبورد |
| `brain/chat_with_robot.py` | شات تفاعلي مع الروبوت |
| `brain/quick_chat.py` | شات سريع (Ollama + XTTS) |
| `brain/start_robot.bat` | تشغيل النظام كامل |

---

## 🏛️ نظام النقاش بين الموديلات (Multi-Agent Debate)

النظام بيشغّل **5 موديلات AI** في نقاش من **7 جولات** (Round 0-6):

```
┌─────────────────────────────────────────────────────┐
│          Round 0: Agentic RAG Search (NEW!) 🆕       │
│  كل موديل بيدور على الويب بشكل واسع                │
│  DeepSeek → web + research                          │
│  Minimax → web + long-form sources                  │
│  Qwen → web + Arabic coverage                       │
│  Nemotron → web + technical sources                 │
│  GLM → broad multilingual web                       │
├─────────────────────────────────────────────────────┤
│                  Round 1: Independent Thinking        │
│  DeepSeek ─ Minimax ─ Qwen ─ Nemotron ─ GLM         │
│  كل موديل بيفكر لوحده باستخدام نتائج البحث         │
├─────────────────────────────────────────────────────┤
│                  Rounds 2-5: Cross Review             │
│  كل موديل بيقرأ ردود الباقي ويعدّل موقفه            │
│  ✓ اتفاق  ✗ خلاف  ⚠️ نقط ناقصة                    │
├─────────────────────────────────────────────────────┤
│                  Round 6: Final Synthesis              │
│  DeepSeek بيجمع كل الآراء في رد واحد نهائي          │
└─────────────────────────────────────────────────────┘
```

**الموديلات (كلها Cloud عبر Ollama Proxy):**
- 🔵 **DeepSeek** v3.1:671b — التفكير العميق والتحليل
- 🟢 **Minimax** M2.7 — الإبداع والمحادثة
- 🟡 **Qwen** 3.5:397b — المعرفة الواسعة
- 🔴 **Nemotron** 3 Super — السرعة والدقة
- 🟣 **GLM** 5 — التحليل المتعدد اللغات

---

## 💾 نظام الذاكرة (Topic-Based Memory)

النظام بيحفظ المحادثات تلقائياً حسب الموضوع:

```
config/data/topics/
├── programming.json    ← محادثات البرمجة
├── robot.json          ← محادثات الروبوت
├── science.json        ← محادثات العلوم
├── personal.json       ← معلومات شخصية
└── general_chat.json   ← محادثات عامة
```

- **تلقائي**: كل محادثة بتتصنف وتتحفظ
- **استرجاع**: لما ترجع تسأل في نفس الموضوع، النظام بيحمّل المحادثات القديمة
- **بحث**: تقدر تدور في كل المواضيع

---

## 👂 الصوت الحي داخل `brain/`

| الملف | الوظيفة |
|-------|---------|
| `brain/ears_mouth.py` | Gemini Live API — سمع + نطق + توجيه الاستعلامات |

---

## 💾 ذاكرة السياق داخل `brain/memory/`

| الملف | الوظيفة |
|-------|---------|
| `brain/memory/context_manager.py` | Sliding-window memory للرؤية (5 لقطات أخيرة) |

---

## ⚡ firmware/ — كود الهاردوير
> **المكان:** `firmware/`  
> **بيشتغل على:** ESP32 / Arduino  
> **اللغة:** C++ (PlatformIO)

| المجلد | الوظيفة |
|--------|---------|
| `firmware/esp32/` | كود ESP32 الحالي (PlatformIO) |
| `firmware/arduino_legacy/` | كود Arduino القديم |
| `firmware/protocol.md` | بروتوكول الاتصال بين Mini PC والهاردوير |

---

## 🖥️ dashboard/ — واجهة التحكم
> **المكان:** `dashboard/`  
> **بيشتغل على:** Browser (hosted on Mini PC)  
> **اللغة:** TypeScript + HTML/CSS

| المجلد | الوظيفة |
|--------|---------|
| `dashboard/frontend/` | الواجهة الأمامية |
| `dashboard/backend/` | السيرفر الخلفي |
| `dashboard/dist/` | البناء الجاهز للنشر |
| `dashboard/scripts/` | سكريبتات مساعدة |
| `dashboard/live.html` | لوحة المراقبة الحية القديمة |

---

## 📦 config/ — الإعدادات والموارد
> **المكان:** `config/`  
> **بيشتغل على:** Mini PC

| المجلد/الملف | الوظيفة |
|-------------|---------|
| `config/.env` | متغيرات البيئة (API keys, ports, providers) |
| `config/.env.example` | نسخة مرجعية من .env |
| `config/config.yaml` | إعدادات Chatterbox TTS Server |
| `config/modelfile.txt` | ملف مرجعي لنموذج Ollama |
| `config/data/` | بيانات التشغيل (SQLite DB, settings JSON, cache) |
| `config/data/topics/` | **ملفات الذاكرة الطويلة** (topic-based memory) |
| `config/models/` | الموديلات (Vosk STT, Piper TTS, XTTS) |
| `config/scripts/` | سكريبتات التثبيت والصيانة |
| `config/tools/` | أدوات (ffmpeg, Python portable) |

---

## 🚀 التشغيل السريع

```bash
# 1. ثبت المتطلبات
pip install -r brain/requirements.txt

# 2. عدل الإعدادات
# حرر config/.env وعدل المتغيرات حسب جهازك

# 3. شغل الروبوت (النظام الكامل مع Debate Engine)
cd brain
python -m brain.runtime
# أو
start_robot.bat

# 4. شغل أريا اللايف (صوت مباشر فقط)
python -m brain.live_aria

# 5. افتح لوحة المراقبة الحية
# افتح dashboard/live.html في المتصفح
```

## 📋 نقل المشروع للـ Mini PC

```bash
# انقل الفولدرات دي بس:
brain/          → /home/pi/robot/brain/
config/         → /home/pi/robot/config/
dashboard/      → /home/pi/robot/dashboard/
scratch/        → /home/pi/robot/scratch/

# فلش الـ ESP32:
firmware/esp32/ → افتحه في PlatformIO وارفعه على البورد
```
