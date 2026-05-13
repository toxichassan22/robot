#if __has_include(<Arduino.h>)
#include <Arduino.h>

#include <ArduinoJson.h>
#if __has_include(<ESP32Servo.h>)
#include <ESP32Servo.h>
#else
#include <Servo.h>
#endif
#include <WiFi.h>

HardwareSerial& io = Serial;

static const char* wifiSsid = "";
static const char* wifiPass = "";
static WiFiServer server(8765);
static WiFiClient client;

// Safety & Heartbeat Globals
static const unsigned long HEARTBEAT_TIMEOUT_MS = 2000;
static unsigned long lastHeartbeatMs = 0;
// Modes: 0=IDLE, 1=NAV, 2=EMERGENCY (Must match Python RobotMode enum if possible, or string map)
// For simplicity: IDLE=0, NAV=1, EMERGENCY=2
static int currentMode = 0; 
static float currentSpeedLimit = 0.0f;


static const int LEFT_PWM_CH = 0;
static const int RIGHT_PWM_CH = 1;

static const int motorLeftPwmPin = 25;
static const int motorLeftDirPin = 26;
static const int motorRightPwmPin = 27;
static const int motorRightDirPin = 14;

static const int trigPin = 32;
static const int echoPin = 33;

static const int servo1Pin = 13;
static const int servo2Pin = 12;

static Servo servo1;
static Servo servo2;

static Servo* servoById(int servoId) {
  if (servoId == 1) return &servo1;
  if (servoId == 2) return &servo2;
  return nullptr;
}

static void setMotor(int pwmChannel, int dirPin, float speed, bool forward) {
  speed = speed < 0 ? 0 : (speed > 1 ? 1 : speed);
  int duty = (int)(speed * 255.0f);
  digitalWrite(dirPin, forward ? HIGH : LOW);
  ledcWrite(pwmChannel, duty);
}

static void stopMotors() {
  ledcWrite(LEFT_PWM_CH, 0);
  ledcWrite(RIGHT_PWM_CH, 0);
}

static float readUltrasonicCm() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  long duration = pulseIn(echoPin, HIGH, 30000);
  if (duration <= 0) return -1.0f;
  return (float)duration * 0.0343f / 2.0f;
}

static void writeJson(Stream& out, const JsonDocument& doc) {
  serializeJson(doc, out);
  out.print('\n');
}

static void handleMotion(JsonObject motion) {
  const char* dir = motion["direction"] | "stop";
  float speed = motion["speed"] | 0.0f;
  int durationMs = motion["duration_ms"] | 0;

  // Safety Checks
  if (currentMode == 0 || currentMode == 2) { 
      // IDLE or EMERGENCY: Refuse motion
      stopMotors();
      return; 
  }
  // Clamp speed
  if (speed > currentSpeedLimit) {
      speed = currentSpeedLimit;
  }

  String d(dir);
  d.toLowerCase();
  if (d == "stop") {
    stopMotors();
    return;
  }

  bool forward = (d == "forward");
  bool backward = (d == "backward");
  bool left = (d == "left");
  bool right = (d == "right");

  if (forward || backward) {
    setMotor(LEFT_PWM_CH, motorLeftDirPin, speed, forward);
    setMotor(RIGHT_PWM_CH, motorRightDirPin, speed, forward);
  } else if (left) {
    setMotor(LEFT_PWM_CH, motorLeftDirPin, speed, false);
    setMotor(RIGHT_PWM_CH, motorRightDirPin, speed, true);
  } else if (right) {
    setMotor(LEFT_PWM_CH, motorLeftDirPin, speed, true);
    setMotor(RIGHT_PWM_CH, motorRightDirPin, speed, false);
  } else {
    stopMotors();
    return;
  }

  if (durationMs > 0) {
    delay(durationMs);
    stopMotors();
  }
}

static void handleServo(JsonObject servo) {
  int servoId = servo["servo_id"] | 0;
  float angle = servo["angle"] | 90.0f;
  if (angle < 0.0f) angle = 0.0f;
  if (angle > 180.0f) angle = 180.0f;
  Servo* s = servoById(servoId);
  if (!s) return;
  s->write((int)angle);
}

static void handlePollSensors(Stream& out) {
  StaticJsonDocument<256> msg;
  msg["type"] = "sensors";
  JsonObject vals = msg.createNestedObject("values");
  float cm = readUltrasonicCm();
  if (cm > 0) vals["obstacle_distance_cm"] = cm;
  writeJson(out, msg);
}

static void handleGetObstacleDistance(Stream& out) {
  StaticJsonDocument<128> msg;
  msg["type"] = "obstacle_distance";
  float cm = readUltrasonicCm();
  if (cm > 0) msg["cm"] = cm;
  writeJson(out, msg);
}

static void handleHeartbeat(JsonObject hb, Stream& out) {
  // Parse payload
  const char* modeStr = hb["mode"] | "IDLE";
  float speedLimit = hb["speed_limit"] | 0.0f;
  // float tempC = hb["temp_c"]; // We might use this for display or local logic, but mainly Brain drives thermal logic

  // Update globals
  String m(modeStr);
  m.toUpperCase();
  if (m == "NAV") currentMode = 1;
  else if (m == "EMERGENCY") currentMode = 2;
  else currentMode = 0; // IDLE

  currentSpeedLimit = speedLimit;
  lastHeartbeatMs = millis();

  // Send ACK
  StaticJsonDocument<128> ack;
  ack["type"] = "heartbeat_ack";
  ack["ts_ms"] = millis(); // or echo back
  writeJson(out, ack);
}

static void handleLine(const String& line, Stream& out) {
  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    StaticJsonDocument<128> msg;
    msg["type"] = "error";
    msg["error"] = "invalid_json";
    writeJson(out, msg);
    return;
  }
  const char* type = doc["type"] | "";
  String t(type);
  t.toLowerCase();
  if (t == "motion") {
    handleMotion(doc["motion"].as<JsonObject>());
    return;
  }
  if (t == "heartbeat") {
    handleHeartbeat(doc, out);
    return;
  }
  if (t == "servo") {
    handleServo(doc["servo"].as<JsonObject>());
    return;
  }
  if (t == "poll_sensors") {
    handlePollSensors(out);
    return;
  }
  if (t == "get_obstacle_distance") {
    handleGetObstacleDistance(out);
    return;
  }
  if (t == "action") {
    return;
  }
}

static String buf;
static String tcpBuf;

void setup() {
  io.begin(115200);

  pinMode(motorLeftDirPin, OUTPUT);
  pinMode(motorRightDirPin, OUTPUT);
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  ledcSetup(LEFT_PWM_CH, 20000, 8);
  ledcSetup(RIGHT_PWM_CH, 20000, 8);
  ledcAttachPin(motorLeftPwmPin, LEFT_PWM_CH);
  ledcAttachPin(motorRightPwmPin, RIGHT_PWM_CH);

  pinMode(servo1Pin, OUTPUT);
  pinMode(servo2Pin, OUTPUT);
  servo1.attach(servo1Pin);
  servo2.attach(servo2Pin);

  stopMotors();

  if (wifiSsid[0] != '\0') {
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSsid, wifiPass);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
      delay(100);
    }
    if (WiFi.status() == WL_CONNECTED) {
      server.begin();
    }
  }
}
void loop() {
  // Safety Watchdog
  if (millis() - lastHeartbeatMs > HEARTBEAT_TIMEOUT_MS) {
    if (currentMode != 2) { // checks if not already EMERGENCY
        currentMode = 2; // Force EMERGENCY
        stopMotors();
    }
  }

  while (io.available() > 0) {
    char c = (char)io.read();
    if (c == '\n') {
      String line = buf;
      buf = "";
      line.trim();
      if (line.length() > 0) handleLine(line, io);
    } else {
      if (buf.length() < 1024) buf += c;
    }
  }

  if (!client || !client.connected()) {
    client = server.available();
    tcpBuf = "";
  }
  if (client && client.connected()) {
    while (client.available() > 0) {
      char c = (char)client.read();
      if (c == '\n') {
        String line = tcpBuf;
        tcpBuf = "";
        line.trim();
        if (line.length() > 0) handleLine(line, client);
      } else {
        if (tcpBuf.length() < 1024) tcpBuf += c;
      }
    }
  }
}
#else
int main() { return 0; }
#endif