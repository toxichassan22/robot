```robot new version\esp_muscles\README.md#L1-200
# ESP32 Muscles — Motor/Servo/Sensor Control (Offline)

This folder is for the **ESP32 firmware** that directly drives hardware (motors, servos, LEDs, simple sensors). Think of the ESP32 as the robot’s **muscles**: it executes low-level commands quickly and predictably.

The Raspberry Pi 5 is the “brain” (LLM + web + high-level logic). The Pi sends **safe, validated** commands to the ESP32. The ESP32 should *never* need internet.

---

## Design goals

- **Deterministic control loop** (fast, reliable).
- **Simple command protocol** (easy to debug).
- **Failsafe behavior** (stop motors if comms lost).
- Start with **USB Serial**, optionally add **WiFi** later.

---

## Folder layout

- `protocol.md`
  - Defines the command/response messages between Pi and ESP32.
- `firmware/`
  - PlatformIO-based ESP32 firmware project
  - `src/main.cpp` is the entry point

---

## Recommended bring-up plan (what you do first)

### Step 1 — Flash a minimal firmware
Goal: prove flashing + serial comms is working.

Firmware should:
- start serial at `115200`
- respond to `{"cmd":"ping"}` with `{"ok":true,...}`
- implement `{"cmd":"stop_all"}` safely (even if no motors are attached yet)

### Step 2 — Add real actuators incrementally
Do one subsystem at a time:
1. LED / status GPIO
2. One servo
3. One motor driver channel
4. Add sensors (limit switch, IMU, etc.)

### Step 3 — Add failsafe
Minimum failsafe behavior:
- If no valid command received for *N* ms → **stop_all**
- If malformed JSON/unknown cmd → ignore + respond with error (don’t crash)

---

## Communication options (offline)

### Option A (recommended first): USB Serial
Pros:
- simplest, fastest to debug
- no WiFi complexity
- reliable in noisy environments (usually)

How it connects:
- Pi 5 ↔ USB cable ↔ ESP32
- Pi opens `/dev/ttyUSB0` (or similar)

### Option B (later): WiFi (TCP/UDP)
Pros:
- fewer cables
Cons:
- more failure modes (network dropouts)
- needs careful timeouts + reconnect logic

If you add WiFi, keep the same JSON protocol so the Pi logic doesn’t change much.

---

## Safety responsibilities (ESP32 side)

Even if the Pi sends bad commands, the ESP32 should protect hardware:

- Clamp motor speeds and servo angles to safe ranges
- Require explicit enable/arm before motion (optional but recommended)
- Immediately stop on:
  - comms timeout
  - brownout / low voltage condition (if measured)
  - emergency-stop pin (if you wire one)

---

## Tooling / Build system

This firmware is intended for **PlatformIO**.

Typical workflow:
- Open `esp_muscles/firmware/` in VS Code with PlatformIO
- Select your ESP32 board (configured in `platformio.ini`)
- Build + Upload
- Open Serial Monitor at `115200`

---

## Hardware notes (fill in as you choose parts)

You’ll want to document:
- motor driver type (TB6612FNG, BTS7960, ESC, etc.)
- servo power source (don’t power servos from ESP32 5V pin)
- shared ground between ESP32 and motor/servo power
- pin mappings (GPIOs) and limits

A good next file to add later:
- `pinout.md` (GPIO mapping and wiring diagram notes)

---

## Next steps to implement in `firmware/src/main.cpp`

1. Serial JSON receive buffer (line-based)
2. Parse commands:
   - `ping`
   - `stop_all`
   - `set_motor`
   - `set_servo`
3. Actuator abstraction:
   - `MotorDriver` class
   - `ServoBank` class
4. Watchdog / comms timeout failsafe
5. Status reporting (`{"ok":true,"status":{...}}`)

If you tell me your motor driver model and whether you’re using servos, DC motors, or steppers, I can tailor the initial firmware skeleton to the exact hardware.
