# Portable Windows Bundle

لإنشاء حزمة Windows محمولة لا تحتاج تثبيت Node أو Python على جهاز التشغيل:

```powershell
python .\pi5\web_ui\scripts\build_windows_portable.py
```

الناتج سيظهر هنا:

- `D:\robot new version\output\portable-windows\RobotControlHost`
- `D:\robot new version\output\portable-windows\RobotControlHost.zip`

التشغيل على الجهاز الهدف:

```powershell
.\start_robot_full_stack.bat
```

أو:

```powershell
.\start_robot_full_stack.ps1
```

الموقع سيفتح على:

- محليًا: `http://127.0.0.1:8000`
- من الموبايل على نفس الشبكة: `http://<host-ip>:8000`

السكربتات المرفقة داخل الحزمة:

- `start_robot_full_stack.bat` أو `start_robot_full_stack.ps1`: تشغيل `Ollama` و`Chatterbox` المحلي إذا كان مضبوطًا، ثم تشغيل الهوست بضغطة واحدة
- `start_robot_host.bat` أو `start_robot_host.ps1`: تشغيل الهوست
- `stop_robot_full_stack.bat` أو `stop_robot_full_stack.ps1`: إيقاف الهوست وإيقاف `Ollama` إذا كان هذا اللانشر هو الذي شغّله
- `stop_robot_host.bat` أو `stop_robot_host.ps1`: إيقاف الهوست
- `check_robot_host.bat` أو `check_robot_host.ps1`: فحص سريع لـ `/api/health`
- `allow_mobile_access.bat` أو `allow_mobile_access.ps1`: فتح المنفذ `8000` في Windows Firewall

ملاحظات:

- الحزمة تضبط `ROBOT_HOST_MODE=auto` افتراضيًا، لذلك تعمل بنفس السلوك على اللابتوب أو الميني بي سي.
- الحزمة تشمل Python والاعتمادات الخاصة بالباك اند والواجهة المبنية مسبقًا.
- `start_robot_full_stack` يحاول تشغيل `Ollama` تلقائيًا إذا كانت الإعدادات تشير إلى `127.0.0.1` أو `localhost`.
- إذا كان `ttsProvider = chatterbox` فسيحاول أيضًا تشغيل Chatterbox من `chatterboxInstallDir` المحفوظ في الإعدادات.
- `Ollama` نفسها ليست مضمّنة؛ إذا كنت تريد LLM/VLM محليًا على الجهاز الهدف فيجب أن تكون `Ollama` مثبتة عليه.
- `Chatterbox` أيضًا ليست مضمّنة داخل الحزمة المحمولة؛ يجب تثبيتها محليًا على الجهاز الهدف إذا أردت TTS أوفلاين بالكامل.
