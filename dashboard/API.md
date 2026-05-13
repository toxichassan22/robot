# Web UI API

## Canonical Backend

- Python import path: `pi_5.web_ui_backend`
- Deprecated temporary shims:
  - `pi5.web_ui.backend.main`
  - `web_ui.backend.main`

## Auth Contract

استخدم هذه الصيغة داخل أي route جديدة:

```python
from fastapi import Depends
from pi_5.web_ui_backend import core

@app.post("/api/example")
async def example(_auth: str = Depends(core.get_auth_dependency())):
    return {"ok": True}
```

القواعد:

- `get_auth_dependency()` هو الـ public dependency المعتمد للـ routes.
- `require_robot_auth(...)` دالة low-level داخلية للمصادقة نفسها.
- `require_robot_auth_dependency(...)` alias مؤقت ومهجور، موجود فقط لفترة انتقالية واحدة.

## Endpoints

### Settings

- `POST /api/settings/auth`
- `GET /api/settings/check-auth`
- `GET /api/settings`
- `POST /api/settings`
- `GET /api/robot-settings`
- `PUT /api/robot-settings`
- `POST /api/admin/pin`

### Motion

- `POST /api/motion/move`

```json
{ "direction": "forward", "speed": 0.4, "durationMs": 600 }
```

- `POST /api/motion/servo`

```json
{ "servoId": 1, "angle": 90 }
```

- `POST /api/motion/stop`

```json
{}
```

### Feedback

- `POST /api/feedback`

```json
{
  "interactionId": "string",
  "rating": 1,
  "correction": "string",
  "context": {}
}
```

### Runtime

- `GET /api/status`
- `GET /api/mode`
- `POST /api/mode`
- `GET /api/safety-events`
- `POST /api/safety-events`
- `POST /api/llm/generate`
- `GET /api/health`
- `GET /v1/health`
- `GET /v1/status`
- `POST /v1/commands`
- `POST /v1/stop`
