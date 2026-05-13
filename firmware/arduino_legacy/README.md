# ESP32 Firmware

## المتطلبات

- ESP32 DevKit
- محركات DC + Driver (مثل L298N/TB6612)
- Servo واحد أو أكثر
- حساس Ultrasonic (HC-SR04) أو ما يعادله

## الرفع

- افتح `esp32/main/main.ino` داخل Arduino IDE
- ثبّت مكتبة ArduinoJson
- اختر الـBoard والـPort ثم Upload

## البروتوكول

التواصل Line-delimited JSON.

### Poll Sensors

Request:

```json
{"type":"poll_sensors","ts_ms":0}
```

Response:

```json
{"type":"sensors","values":{"obstacle_distance_cm":42.0}}
```

### Motion

```json
{"type":"motion","ts_ms":0,"motion":{"direction":"forward","speed":0.4,"duration_ms":800}}
```

### Servo

```json
{"type":"servo","ts_ms":0,"servo":{"servo_id":1,"angle":90}}
```

