```robot new version\esp_muscles\protocol.md#L1-220
# ESP32 Command Protocol (JSON Lines) — v1

This file defines the **offline** command protocol between:

- **Pi 5 (brain)**: high-level logic + safety + UI
- **ESP32 (muscles)**: real-time motor/servo/IO control

Transport is intentionally flexible:
- **Preferred initially**: USB Serial
- Later (optional): WiFi TCP/UDP

The message format is the same across transports.

---

## 1) Framing and Encoding

### 1.1 Encoding
- UTF-8 text

### 1.2 Framing (JSON Lines)
- Each message is **one JSON object per line**, terminated by `\n`.
- The receiver must buffer until newline, then parse JSON.
- Maximum line length (recommendation): **<= 512 bytes** for early firmware simplicity.

### 1.3 Example
{"id":1,"type":"cmd","name":"ping"}\n

---

## 2) Message Types

### 2.1 Command (Pi -> ESP32)
Required fields:
- `type`: `"cmd"`
- `name`: command name (string)
Optional fields:
- `id`: integer request id (recommended; echoed back in response)
- `args`: object with command-specific arguments

Example:
{"id":10,"type":"cmd","name":"set_motor","args":{"channel":0,"speed":0.35}}

### 2.2 Response / Acknowledgement (ESP32 -> Pi)
Required fields:
- `type`: `"resp"`
- `ok`: boolean
Optional fields:
- `id`: request id being responded to (if provided)
- `name`: command name (echo)
- `error`: string error code (if `ok=false`)
- `message`: human-readable explanation (optional)
- `data`: object with response data (optional)

Example success:
{"id":10,"type":"resp","ok":true,"name":"set_motor"}

Example error:
{"id":10,"type":"resp","ok":false,"name":"set_motor","error":"invalid_arg","message":"speed out of range"}

### 2.3 Telemetry / Status (ESP32 -> Pi)
ESP32 may stream status periodically.

Required fields:
- `type`: `"telemetry"`
Optional fields:
- `ts_ms`: ESP32 uptime in milliseconds
- `data`: object containing telemetry values

Example:
{"type":"telemetry","ts_ms":123456,"data":{"vbat":7.92,"temp_c":41.3,"cmd_age_ms":120}}

---

## 3) General Rules

### 3.1 Safety-first
- ESP32 must implement a **comms timeout failsafe**:
  - If no valid command received for `T` ms, it must execute `stop_all`.
  - Recommended default: `T = 500ms` for motors, `T = 1000ms` for servos (tune per robot).
- ESP32 must clamp or reject out-of-range values (see below).

### 3.2 Idempotency
- `stop_all` should be safe to call repeatedly.
- `ping` should always be safe.

### 3.3 Unknown fields
- Receivers should ignore unknown fields (forward compatibility).

### 3.4 Parsing failures
If JSON parse fails or message is malformed:
- ESP32 should reply (best-effort) with:
  - `type:"resp"`, `ok:false`, `error:"parse_error"`
- If no `id` is available, omit it.

Example:
{"type":"resp","ok":false,"error":"parse_error","message":"invalid JSON"}

---

## 4) Command Set (v1)

### 4.1 `ping`
Purpose: health check / latency measurement.

Command:
{"id":1,"type":"cmd","name":"ping"}

Response data (recommended):
- `ms`: processing time or roundtrip estimate (optional)
- `fw`: firmware version string (optional)

Response:
{"id":1,"type":"resp","ok":true,"name":"ping","data":{"fw":"0.1.0","uptime_ms":12345}}

---

### 4.2 `stop_all`
Purpose: immediate safe stop of all motion outputs.

Command:
{"id":2,"type":"cmd","name":"stop_all"}

Response:
{"id":2,"type":"resp","ok":true,"name":"stop_all"}

Notes:
- Should stop all motors (PWM=0, brake/coast as configured).
- Should stop/disable servos if your design supports it (or hold last position safely).
- Should also clear any queued motions.

---

### 4.3 `set_motor`
Purpose: set speed for a motor channel (DC motor driver / ESC abstraction).

Command args:
- `channel` (int, required): 0..N-1
- `speed` (number, required): range **-1.0 .. +1.0**
  - negative = reverse
  - positive = forward
- `mode` (string, optional): `"coast"` | `"brake"`
- `ramp_ms` (int, optional): simple smoothing (0 = immediate)

Example:
{"id":3,"type":"cmd","name":"set_motor","args":{"channel":0,"speed":0.5,"mode":"brake","ramp_ms":100}}

Response:
{"id":3,"type":"resp","ok":true,"name":"set_motor"}

Errors:
- `invalid_arg` (missing/invalid channel or speed)
- `out_of_range` (speed outside -1..1)
- `not_supported` (motor not configured)

---

### 4.4 `set_servo`
Purpose: set servo angle or pulse width.

Command args (choose one control style; angle recommended):
- `channel` (int, required): 0..N-1
- `angle_deg` (number, optional): recommended **0..180**
- `pulse_us` (int, optional): e.g. 500..2500 (depends on servo)
- `speed` (number, optional): 0..1 (if you implement easing)
- `ramp_ms` (int, optional)

Examples:
{"id":4,"type":"cmd","name":"set_servo","args":{"channel":1,"angle_deg":90}}
{"id":5,"type":"cmd","name":"set_servo","args":{"channel":1,"pulse_us":1500}}

Response:
{"id":4,"type":"resp","ok":true,"name":"set_servo"}

Errors:
- `invalid_arg`
- `out_of_range`
- `not_supported`

Notes:
- ESP32 should clamp angles/pulses to configured min/max per channel.

---

### 4.5 `set_digital_out`
Purpose: set a GPIO output (LED, relay enable, etc.)

Command args:
- `pin` (int, required): GPIO number
- `value` (0|1|true|false, required)

Example:
{"id":6,"type":"cmd","name":"set_digital_out","args":{"pin":2,"value":1}}

Response:
{"id":6,"type":"resp","ok":true,"name":"set_digital_out"}

Errors:
- `invalid_arg`
- `not_supported` (pin not allowed)

Security/safety note:
- In production, do not allow arbitrary pins unless you whitelist.

---

### 4.6 `get_status`
Purpose: request a one-shot status snapshot.

Command:
{"id":7,"type":"cmd","name":"get_status"}

Response data (example fields):
- `uptime_ms`
- `last_cmd_age_ms`
- `motors`: array of current motor outputs
- `servos`: array of current servo targets
- `errors`: array (optional)

Example response:
{"id":7,"type":"resp","ok":true,"name":"get_status","data":{"uptime_ms":54321,"last_cmd_age_ms":20,"motors":[0.5,0.0],"servos":[90],"errors":[]}}

---

### 4.7 `set_config` (optional, guarded)
Purpose: set runtime config values (timeouts, limits). Recommended to restrict or disable unless needed.

Command args (examples):
- `cmd_timeout_ms` (int)
- `telemetry_period_ms` (int)

Example:
{"id":8,"type":"cmd","name":"set_config","args":{"cmd_timeout_ms":500,"telemetry_period_ms":200}}

Response:
{"id":8,"type":"resp","ok":true,"name":"set_config"}

Errors:
- `not_supported`
- `invalid_arg`

---

## 5) Error Codes (suggested)

- `parse_error` — invalid JSON / cannot parse
- `invalid_cmd` — `name` not recognized
- `invalid_arg` — missing required arg / wrong type
- `out_of_range` — arg value outside allowed range
- `not_supported` — feature not compiled/configured
- `busy` — temporarily unable to execute
- `internal_error` — unexpected failure

---

## 6) Versioning and Compatibility

- This is **protocol v1**.
- Add new commands by introducing new `name` values.
- Adding new fields to `args` or `data` should not break older code if unknown fields are ignored.

Recommended:
- `get_status` should include `protocol_version: 1` so the Pi can verify compatibility.

---

## 7) Minimal Required Implementation (for first hardware test)

To bring up the system quickly, ESP32 firmware MUST implement:
- `ping`
- `stop_all`
- comms timeout failsafe (calls `stop_all` automatically)

Then add:
- `set_motor`
- `set_servo`
- `get_status`

---

## 8) Transport Notes

### 8.1 USB Serial
- Baud: **115200** (default)
- Line endings: `\n` required
- Pi should open the port with a read timeout and retry reconnect if unplugged.

### 8.2 WiFi (later)
- Keep the same JSON line protocol over TCP.
- If using UDP, include `id` always and consider message loss/reordering.
