# Web UI

واجهة React/Vite مع backend FastAPI معبأ داخل `pi_5.web_ui_backend`.

## تشغيل

```powershell
npm install
npm run dev
```

الواجهة الأمامية تعمل عبر Vite، و`server:dev` يشغل:

```powershell
python -m pi_5.web_ui_backend.main
```

## Routes

- `/` صفحة ترحيب
- `/console` لوحة التشغيل
- `/motion`
- `/test`
- `/settings`

## Landing Model

- ملفات المصدر: `D:\robot new version\robot_follow_cursor_for_landing_page.glb` و `D:\robot new version\robot_follow_cursor_for_landing_page.gltf`
- أصل التشغيل المحلي: `pi5/web_ui/frontend/public/assets/models/robot_follow_cursor_for_landing_page.glb`

الصفحة الترحيبية تحاول تحميل الموديل المحلي على الأجهزة المكتبية، وتعرض fallback تلقائيًا على الأجهزة الخفيفة أو عند فشل التحميل.
