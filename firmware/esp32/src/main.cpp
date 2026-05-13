```robot new version\esp_muscles\firmware\src\main.cpp#L1-260
#include <Arduino.h>
#include <ArduinoJson.h>

// Minimal ESP32 firmware skeleton
// - Offline friendly
// - JSON Lines protocol over Serial
// - Implements: ping, stop_all (stubs)
// - Adds: basic comms timeout failsafe (calls stop_all)
//
// This is intentionally minimal so you can bring up hardware safely.
// Extend later with real motor/servo drivers.
//
// Protocol reference: ../../protocol.md

#ifndef ROBOT_FW_VERSION
#define ROBOT_FW_VERSION "0.0.0"
#endif

// Serial settings
static constexpr uint32_t SERIAL_BAUD = 115200;
static constexpr size_t RX_LINE_MAX = 512; // keep small for safety on embedded

// Safety: if no valid command arrives in time, stop all outputs
static constexpr uint32_t CMD_TIMEOUT_MS = 750;

// Telemetry (optional, can be disabled by setting to 0)
static constexpr uint32_t TELEMETRY_PERIOD_MS = 0;

// RX buffer
static char g_rxLine[RX_LINE_MAX];
static size_t g_rxLen = 0;

// Timing
static uint32_t g_lastValidCmdMs = 0;
static uint32_t g_lastTelemetryMs = 0;

// Forward declarations
static void stopAllOutputs();
static void sendRespOk(int id, const char* name, JsonObjectConst data = JsonObjectConst());
static void sendRespErr(int id, const char* name, const char* error, const char* message = nullptr);
static void sendTelemetry();
static bool handleJsonLine(const char* line, size_t len);
static int readIdOrMinus1(JsonObjectConst obj);

// -------------------- Safety / Actuator Stubs --------------------

static void stopAllOutputs() {
  // TODO: Replace with real motor/servo stop logic.
  // Keep this safe even if called repeatedly.
  //
  // Examples (later):
  // - set motor PWMs to 0
  // - set direction pins low
  // - disable motor driver EN pin
  // - detach servos or hold safe position
}

// -------------------- JSON Send Helpers --------------------

static void writeJsonLine(JsonDocument& doc) {
  serializeJson(doc, Serial);
  Serial.print('\n');
}

static void sendRespOk(int id, const char* name, JsonObjectConst data) {
  StaticJsonDocument<256> doc;
  doc["type"] = "resp";
  doc["ok"] = true;
  doc["name"] = name ? name : "";
  if (id >= 0) doc["id"] = id;

  if (!data.isNull()) {
    // Copy selected data into response
    JsonObject out = doc.createNestedObject("data");
    for (JsonPairConst kv : data) out[kv.key()] = kv.value();
  }

  writeJsonLine(doc);
}

static void sendRespErr(int id, const char* name, const char* error, const char* message) {
  StaticJsonDocument<256> doc;
  doc["type"] = "resp";
  doc["ok"] = false;
  if (name && name[0]) doc["name"] = name;
  if (id >= 0) doc["id"] = id;
  doc["error"] = error ? error : "internal_error";
  if (message && message[0]) doc["message"] = message;

  writeJsonLine(doc);
}

static void sendTelemetry() {
  if (TELEMETRY_PERIOD_MS == 0) return;

  StaticJsonDocument<256> doc;
  doc["type"] = "telemetry";
  doc["ts_ms"] = millis();

  JsonObject data = doc.createNestedObject("data");
  data["uptime_ms"] = millis();

  uint32_t now = millis();
  data["last_cmd_age_ms"] = (g_lastValidCmdMs == 0) ? nullptr : (now - g_lastValidCmdMs);

  writeJsonLine(doc);
}

// -------------------- JSON Receive / Handler --------------------

static int readIdOrMinus1(JsonObjectConst obj) {
  if (!obj.containsKey("id")) return -1;
  JsonVariantConst v = obj["id"];
  if (v.is<int>()) return v.as<int>();
  if (v.is<long>()) return (int)v.as<long>();
  return -1;
}

static bool handleJsonLine(const char* line, size_t len) {
  // Parse JSON object
  StaticJsonDocument<512> doc; // must hold typical commands <= 512 bytes
  DeserializationError err = deserializeJson(doc, line, len);

  if (err) {
    // Best-effort parse error response
    sendRespErr(-1, "", "parse_error", err.c_str());
    return false;
  }

  JsonObjectConst obj = doc.as<JsonObjectConst>();
  if (obj.isNull()) {
    sendRespErr(-1, "", "parse_error", "root is not an object");
    return false;
  }

  const char* type = obj["type"] | "";
  if (strcmp(type, "cmd") != 0) {
    // Ignore non-command messages for now
    // (You can add config/other message types later)
    return false;
  }

  const char* name = obj["name"] | "";
  const int id = readIdOrMinus1(obj);

  if (name[0] == '\0') {
    sendRespErr(id, "", "invalid_cmd", "missing cmd name");
    return false;
  }

  // Mark as valid command received (only after basic validation)
  g_lastValidCmdMs = millis();

  // Dispatch commands
  if (strcmp(name, "ping") == 0) {
    StaticJsonDocument<128> dataDoc;
    JsonObject data = dataDoc.to<JsonObject>();
    data["fw"] = ROBOT_FW_VERSION;
    data["uptime_ms"] = millis();

    sendRespOk(id, "ping", data);
    return true;
  }

  if (strcmp(name, "stop_all") == 0) {
    stopAllOutputs();
    sendRespOk(id, "stop_all");
    return true;
  }

  // Unknown command
  sendRespErr(id, name, "invalid_cmd", "unknown command");
  return false;
}

// Serial line accumulator (JSON Lines)
static void pollSerial() {
  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;

    // Handle CRLF or LF
    if (c == '\r') continue;

    if (c == '\n') {
      if (g_rxLen > 0) {
        // Null-terminate for safety; deserializeJson also uses len.
        if (g_rxLen >= RX_LINE_MAX) g_rxLen = RX_LINE_MAX - 1;
        g_rxLine[g_rxLen] = '\0';

        (void)handleJsonLine(g_rxLine, g_rxLen);
      }
      // Reset line buffer
      g_rxLen = 0;
      continue;
    }

    // Accumulate bytes until max
    if (g_rxLen < (RX_LINE_MAX - 1)) {
      g_rxLine[g_rxLen++] = (char)c;
    } else {
      // Line too long: drop it safely, reset at next newline
      // We keep reading until newline to resync.
    }
  }
}

// -------------------- Arduino Entry Points --------------------

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(100);

  // Set initial safe state
  stopAllOutputs();

  g_lastValidCmdMs = millis();
  g_lastTelemetryMs = millis();

  // Optional boot message (telemetry-like)
  {
    StaticJsonDocument<256> doc;
    doc["type"] = "telemetry";
    doc["ts_ms"] = millis();
    JsonObject data = doc.createNestedObject("data");
    data["event"] = "boot";
    data["fw"] = ROBOT_FW_VERSION;
    writeJsonLine(doc);
  }
}

void loop() {
  const uint32_t now = millis();

  pollSerial();

  // Failsafe: comms timeout => stop all outputs
  if (g_lastValidCmdMs != 0 && (now - g_lastValidCmdMs) > CMD_TIMEOUT_MS) {
    stopAllOutputs();
    // Prevent repeated stop spam: bump timer so it triggers at most once per timeout interval
    g_lastValidCmdMs = now;
    // You can also emit a telemetry event here if you want.
  }

  // Optional telemetry stream
  if (TELEMETRY_PERIOD_MS > 0 && (now - g_lastTelemetryMs) >= TELEMETRY_PERIOD_MS) {
    g_lastTelemetryMs = now;
    sendTelemetry();
  }

  // Keep loop responsive
  delay(2);
}
