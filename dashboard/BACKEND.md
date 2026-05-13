# Backend Notes

## Canonical Import Path

استخدم دائمًا:

```python
from pi_5.web_ui_backend.main import app
from pi_5.web_ui_backend import core
```

## Deprecated Temporary Paths

المسارات التالية ما زالت تعمل مؤقتًا فقط وتصدر `DeprecationWarning`:

- `pi5.web_ui.backend.main`
- `web_ui.backend.main`

لا تضف أي اعتماد جديد عليها.

## Auth Usage

داخل الـ routes:

```python
from fastapi import Depends
from pi_5.web_ui_backend import core

@app.post("/api/example")
async def example(_auth: str = Depends(core.get_auth_dependency())):
    return {"ok": True}
```

لا تستخدم مباشرة:

- `Depends(core.require_robot_auth)`
- `Depends(core.require_robot_auth_dependency)`

## Route Ownership

- `/` صفحة الترحيب فقط.
- `/console` لوحة التشغيل فقط.
- `AppShell` يخص صفحات التشغيل، وليس صفحة الترحيب.

## Landing Asset Workflow

التدفق المعتمد:

1. حدّث أصل المصدر `robot_follow_cursor_for_landing_page.glb` أو `robot_follow_cursor_for_landing_page.gltf`.
2. استخدم نسخة `glb` كأصل تشغيل للويب.
3. ضع الملف تحت `pi5/web_ui/frontend/public/assets/models/`.
4. صفحة الترحيب تحمل الأصل المحلي من `/assets/models/...`.

إذا فشل التحميل أو كان الجهاز منخفض القدرة، الواجهة تعرض fallback ثابت بدل كسر الصفحة.
