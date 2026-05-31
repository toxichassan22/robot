# Aria Robot - Code Issues Report

تاريخ التقرير: 2026-05-31

---

## Critical Issues (ممكن تسبب كراش أو سلوك غلط)

### 1. Circular Import Risk في models.py
**الملف:** `brain/models.py` (سطر 106-108)
**المشكلة:** الـ module بيعمل import من `brain.pi5.web_ui_backend.routers.api_keys` في الـ module level. لو الـ web backend مش متثبت أو فيه circular dependency، أي استيراد لـ `brain.models` هيفشل والكل هيتوقف.

```python
# السطر 106-108
from brain.pi5.web_ui_backend.routers.api_keys import _get_key_manager
from brain.llm.huggingface_client import HuggingFaceClient
hf_client = HuggingFaceClient(default_model="moonshotai/kimi-k2.6:free", key_manager=_get_key_manager())
```

**الحل:** نقل الـ initialization جوه lazy function أو class method بدل module level.

---

### 2. Model Instantiation at Module Level
**الملف:** `brain/models.py` (سطر 108-119)
**المشكلة:** كل الـ 5 موديلات بتتعمل instantiate على طول لما الـ module بيتأسترد. لو في مشكلة في الاتصال أو الـ API key، أي import لـ `brain.models` هيفشل.

```python
# السطر 111-119
deepseek = HuggingFaceLLMWrapper("Kimi", "moonshotai/kimi-k2.6:free", hf_client)
minimax = LLMWrapper("Minimax", OLLAMA_URL, "minimax-m2.7:cloud", timeout=None)
qwen = LLMWrapper("Qwen", OLLAMA_URL, "qwen3.5:397b-cloud", timeout=None)
nemotron = LLMWrapper("Nemotron", OLLAMA_URL, "nemotron-3-super:cloud", timeout=None)
glm = LLMWrapper("GLM", OLLAMA_URL, "glm-4.7:cloud", timeout=None)
ALL_MODELS = [deepseek, minimax, qwen, nemotron, glm]
```

**الحل:** استخدام lazy loading أو factory pattern.

---

### 3. `del vision_context` بيمسح الـ parameter
**الملف:** `brain/debate_engine.py` (سطر 105)
**المشكلة:** `run_round_0_search` بتاخد `vision_context` parameter وبتمسحه فوراً. لو حد حاول يستخدمه بعدين هياخد `NameError`.

```python
async def run_round_0_search(self, query: str, vision_context: str) -> Dict[str, str]:
    del vision_context  # <-- المشكلة هنا
```

**الحل:** استخدم `_` بدل الـ parameter name لو مش محتاجه.

---

### 4. `_parse_int` يسمح بـ `min_v=0`
**الملف:** `brain/config.py` (سطر 239)
**المشكلة:** `perf_frame_skip` بيسمح بقيمة 0. ده معناه "skip every frame" وده غلط.

```python
perf_frame_skip=BrainConfig._parse_int("PERF_FRAME_SKIP", 1, min_v=0, max_v=10)
```

**الحل:** تغيير `min_v=1`.

---

### 5. Debate Rounds Inconsistency
**الملف:** `brain/debate_engine.py`
**المشكلة:** التناقض بين اللي مكتوب واللي بيحصل فعلاً:

| المصدر | عدد الجولات |
|--------|-------------|
| `self.rounds = 5` (سطر 71) | 5 |
| `for round_num in range(2, 3)` (سطر 333) | 1 round بس |
| README.md | 7 جولات |

**الحالي فعلياً:** Round 0 (search) + Round 1 (independent) + Round 2 (review) + Round 3 (synthesis) = **4 جولات**

**الحل:** تحديث `self.rounds` والـ loop عشان يبقى consistent.

---

## Architecture/Design Issues

### 6. Coupling to Private Method
**الملف:** `brain/runtime.py` (سطر 357)
**المشكلة:** `_is_complex_query` بينادي على `self.chat_archiver._run_llm` - ده private method من class تاني. لو الـ ChatArchiver غيّر الـ method ده، الـ runtime هيتكسر.

```python
result = await self.chat_archiver._run_llm(system, user_text)
```

**الحل:** إضافة public method في ChatArchiver أو استخدام LLM client مباشرة.

---

### 7. Hardcoded Model in Debate Synthesis
**الملف:** `brain/debate_engine.py` (سطر 281)
**المشكلة:** `run_synthesis` بيعمل hardcode لـ `deepseek` model. ده بيكسر الـ abstraction بتاعة إن الـ engine بيشتغل مع أي models.

```python
from brain.models import deepseek
result = await deepseek.generate("Synthesize the final response.", system_prompt)
```

**الحل:** استخدام أول model من الـ list أو parameter مخصص للـ synthesizer.

---

### 8. Sensor Polling Disabled
**الملف:** `brain/runtime.py` (سطر 857-859)
**المشكلة:** الـ sensor polling من ESP32 مكتوب بس الـ actual call مcommented out. الروبوت مش بيقرأ sensors من الـ hardware.

```python
# sensors = await self.esp32.poll_sensors(timeout_s=0.1)
pass
```

**الحل:** تفعيل الـ sensor polling مع timeout مناسب.

---

### 9. Visual Question Keywords Too Broad
**الملف:** `brain/runtime.py` (سطر 287-290)
**المشكلة:** كلمات زي `"دي"`, `"ده"`, `"كده"`, `"كدا"` بترجع `True` لأي جملة فيها الكلمات دي. ده بيفعّل الـ vision unnecessarily.

```python
visual_kws = [
    "شايف", "لابس", "اقرا", "اقرأ", "مكتوب", "قدامك", "ولد ولا بنت", "بنت ولا ولد", "شكلي",
    "روشتة", "روشته", "ورقة", "ورقه", "معايا إيه", "معايا ايه", "إيه ده", "ايه ده", "كده", "كدا", "دي", "ده"
]
```

**الحل:** إزالة الكلمات العامة زي "دي", "ده", "كده" أو استخدام NLP بدل keyword matching.

---

### 10. Question Cache Not Actually O(1)
**الملف:** `brain/memory/question_cache.py` (سطر 131)
**المشكلة:** الـ docstring بيقول O(1) بس الـ `lookup` بيلف على كل الـ topic folders. لو في topics كتير، الـ lookup بطيء.

```python
def lookup(self, question: str) -> Optional[str]:
    fname = _sanitize_filename(question) + ".json"
    for folder in self.cache_dir.iterdir():  # <-- مش O(1)
        if not folder.is_dir():
            continue
        fpath = folder / fname
        if fpath.exists():
            ...
```

**الحل:** استخدام SQLite index بدل filesystem scan.

---

## Test Issues

### 11. Missing Mock for build_stt
**الملف:** `brain/tests/test_runtime_integration.py` (سطر 18-26)
**المشكلة:** الـ patch مش بيلتقط `build_stt` بشكل صحيح. في الـ runtime، `build_stt` بيتأسترد من `brain.speech.stt` مش من `brain.runtime`.

```python
with patch('brain.runtime.VoskSTT'),  # <-- مش كافي
```

**الحل:** إضافة `patch('brain.runtime.build_stt')`.

---

### 12. Tests Assume Specific Patching
**الملف:** `brain/tests/test_runtime_integration.py`
**المشكلة:** الـ tests بتعمل patch لـ names مش موجودة في الـ runtime module. مثلاً `brain.runtime.VoskSTT` بس الـ runtime بيعمل `from brain.speech.stt import VoskSTT, build_stt`.

---

## Security Issues

### 13. Safety Event Logging Timeout Too Low
**الملف:** `brain/runtime.py` (سطر 372)
**المشكلة:** الـ timeout ثانية واحدة بس. لو الـ web server مش شغال، الـ safety events هتت丢失 silently.

```python
async with httpx.AsyncClient(timeout=1.0) as client:
```

**الحل:** زيادة الـ timeout أو استخدام retry mechanism.

---

### 14. API Keys File in Repository
**الملف:** `api_keys.txt` (root directory)
**المشكلة:** ملف API keys موجود في الـ repository. لو الـ `.gitignore` مش بيغطيه، المفاتيح ممكن تتعرض.

**الحل:** إضافة `api_keys.txt` في `.gitignore` ومسحه من git history.

---

## Performance Issues

### 15. Perception Loop CPU Overload
**الملف:** `brain/runtime.py` (سطر 889)
**المشكلة:** الـ loop بيشتغل كل 10ms وده overload شديد على الـ CPU خصوصاً مع الـ camera processing.

```python
await asyncio.sleep(0.01)  # 10ms = 100 iterations/second
```

**الحل:** تغيير لـ `0.05` (50ms) أو `0.1` (100ms) حسب الـ camera FPS.

---

### 16. Duplicate `import sys`
**الملف:** `brain/runtime.py` (سطر 8 و 36)
**المشكلة:** `import sys` مكرر مرتين. مش بيسبب crash بس ده code smell.

---

### 17. Fuzzy Cache Jaccard Similarity Threshold
**الملف:** `brain/memory/question_cache.py` (سطر 180)
**المشكلة:** الـ threshold `0.6` ممكن يكون عالي أوي للأسئلة العربية. كلمتين مشتركتين من أصل 4 = 0.5 مش هيعدي.

```python
if similarity > 0.6 and similarity > best_overlap:
```

**الحل:** خفض الـ threshold لـ `0.4` أو استخدام better similarity metric.

---

## ملخص

| Severity | Count | الأرقام |
|----------|-------|---------|
| Critical | 5 | 1, 2, 3, 4, 5 |
| Architecture | 5 | 6, 7, 8, 9, 10 |
| Test | 2 | 11, 12 |
| Security | 2 | 13, 14 |
| Performance | 3 | 15, 16, 17 |
| **الإجمالي** | **17** | |
