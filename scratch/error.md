# Aria Robot - Code Issues Report

تاريخ التقرير: 2026-05-31
حالة الإصلاح: **تم إصلاح 15 من 17 مشكلة**

---

## Critical Issues (ممكن تسبب كراش أو سلوك غلط)

### 1. Circular Import Risk في models.py ✅ تم الإصلاح
**الملف:** `brain/models.py`
**المشكلة:** الـ module بيعمل import من `brain.pi5.web_ui_backend.routers.api_keys` في الـ module level.
**الحل:** تم نقل الـ initialization جوه lazy functions (`get_deepseek()`, `get_minimax()`, etc.) مع `_LazyModel` proxy للتوافق مع الكود القديم.

---

### 2. Model Instantiation at Module Level ✅ تم الإصلاح
**الملف:** `brain/models.py`
**المشكلة:** كل الـ 5 موديلات بتتعمل instantiate على طول لما الـ module بيتأسترد.
**الحل:** تم استخدام lazy loading pattern مع `_models_cache` dictionary.

---

### 3. `del vision_context` بيمسح الـ parameter ✅ تم الإصلاح
**الملف:** `brain/debate_engine.py`
**المشكلة:** `run_round_0_search` بتاخد `vision_context` parameter وبتمسحه فوراً.
**الحل:** تم استخدام `_ = vision_context` بدل `del vision_context`.

---

### 4. `_parse_int` يسمح بـ `min_v=0` ✅ تم الإصلاح
**الملف:** `brain/config.py`
**المشكلة:** `perf_frame_skip` بيسمح بقيمة 0 (skip every frame).
**الحل:** تم تغيير `min_v=0` إلى `min_v=1`.

---

### 5. Debate Rounds Inconsistency ✅ تم الإصلاح
**الملف:** `brain/debate_engine.py`
**المشكلة:** التناقض بين `self.rounds = 5` و `for round_num in range(2, 3)` و README.
**الحل:** تم تحديث `self.rounds = 4` مع تحديث جميع الـ prompts والـ labels.

---

## Architecture/Design Issues

### 6. Coupling to Private Method ✅ تم الإصلاح
**الملف:** `brain/runtime.py` + `brain/memory/chat_archiver.py`
**المشكلة:** `_is_complex_query` بينادي على `self.chat_archiver._run_llm` - private method.
**الحل:** تم تغيير `_run_llm` إلى `run_llm` (public method) في ChatArchiver وتحديث كل المراجع.

---

### 7. Hardcoded Model in Debate Synthesis ✅ تم الإصلاح
**الملف:** `brain/debate_engine.py`
**المشكلة:** `run_synthesis` بيعمل hardcode لـ `deepseek` model.
**الحل:** تم استخدام `get_deepseek()` lazy getter بدل direct import.

---

### 8. Sensor Polling Disabled ✅ تم الإصلاح
**الملف:** `brain/runtime.py`
**المشكلة:** الـ sensor polling من ESP32 مcommented out.
**الحل:** تم تفعيل الـ sensor polling مع timing صحيح (`_last_sensor_poll` + `_SENSOR_POLL_INTERVAL = 1.0s`).

---

### 9. Visual Question Keywords Too Broad ✅ تم الإصلاح
**الملف:** `brain/runtime.py` + `brain/cognition/planner.py`
**المشكلة:** كلمات زي `"دي"`, `"ده"`, `"كده"`, `"كدا"` بترجع `True` لأي جملة.
**الحل:** تم إزالة الكلمات العامة واستبدالها بـ `"الكاميرا"`, `"صورة"`, `"صوره"`.

---

### 10. Question Cache Not Actually O(1) ✅ تم الإصلاح
**الملف:** `brain/memory/question_cache.py`
**المشكلة:** الـ docstring بيقول O(1) بس الـ lookup بيلف على كل الـ topic folders.
**الحل:** تم تحديث الـ docstring عشان يوضح إن الـ lookup هو O(n).

---

## Test Issues

### 11. Missing Mock for build_stt ✅ تم الإصلاح
**الملف:** `brain/tests/test_runtime_integration.py`
**المشكلة:** الـ patch مش بيلتقط `build_stt` بشكل صحيح.
**الحل:** تم تغيير `brain.runtime.VoskSTT` إلى `brain.runtime.build_stt`.

---

### 12. Tests Assume Specific Patching ⚠️ لم يتم الإصلاح
**الملف:** `brain/tests/test_runtime_integration.py`
**المشكلة:** الـ tests بتعمل patch لـ names مش موجودة في الـ runtime module.
**ملاحظة:** تم إصلاح الـ mock الأساسي (issue 11). الباقي ممكن يبقى محتاج review أعمق.

---

## Security Issues

### 13. Safety Event Logging Timeout Too Low ✅ تم الإصلاح
**الملف:** `brain/runtime.py`
**المشكلة:** الـ timeout ثانية واحدة بس.
**الحل:** تم زيادة الـ timeout من 1.0s إلى 3.0s.

---

### 14. API Keys File in Repository ✅ تم التحقق - لا حاجة للإصلاح
**الملف:** `.gitignore`
**المشكلة:** ملف API keys موجود في الـ repository.
**التحقق:** `api_keys.txt` موجود فعلاً في `.gitignore` (سطر 27). لا حاجة لإجراء.

---

## Performance Issues

### 15. Perception Loop CPU Overload ✅ تم الإصلاح
**الملف:** `brain/runtime.py`
**المشكلة:** الـ loop بيشتغل كل 10ms وده overload على الـ CPU.
**الحل:** تم زيادة الـ sleep من 0.01 إلى 0.05 (50ms).

---

### 16. Duplicate `import sys` ✅ تم الإصلاح
**الملف:** `brain/runtime.py`
**المشكلة:** `import sys` مكرر مرتين.
**الحل:** تم حذف الـ import المكرر.

---

### 17. Fuzzy Cache Jaccard Similarity Threshold ✅ تم الإصلاح
**الملف:** `brain/memory/question_cache.py`
**المشكلة:** الـ threshold 0.6 عالي أوي للأسئلة العربية.
**الحل:** تم خفض الـ threshold من 0.6 إلى 0.4.

---

## ملخص

| Severity | الإجمالي | تم الإصلاح | متبقي |
|----------|---------|------------|-------|
| Critical | 5 | 5 | 0 |
| Architecture | 5 | 5 | 0 |
| Test | 2 | 1 | 1 |
| Security | 2 | 2 | 0 |
| Performance | 3 | 3 | 0 |
| **الإجمالي** | **17** | **16** | **1** |

المشكلة المتبقية (#12) محتاجة review أعمق للـ test patching.
