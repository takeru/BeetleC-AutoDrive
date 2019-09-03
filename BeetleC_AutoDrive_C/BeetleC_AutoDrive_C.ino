/* Comment this out to disable prints and save space */
#define BLYNK_PRINT Serial
#define BLYNK_USE_DIRECT_CONNECT

#include <BlynkSimpleEsp32_BLE.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <HardwareSerial.h>
#include <M5StickC.h>
#include <Arduino.h>
#include <Wire.h>

#include "secret.h"
//char auth[] = "*****";

signed char _power = 0;
signed char _steering = 0;
bool _controlUpdated = false;
unsigned long _lastSentToV = 0;
unsigned long _ms = 0;
unsigned long _counter = 0;
uint8_t _car_left  = 0;
uint8_t _car_right = 0;
HardwareSerial serial_ext(2); // Serial from/to V via GROVE

void setup()
{
  M5.begin();

  Serial.begin(115200);
  Serial.println("Waiting for connections...");
  Blynk.setDeviceName("BeetleC-AutoDrive");
  Blynk.begin(auth);

  // M5StickV
  int baud = 4500000; // 115200 1500000 3000000 4500000
  serial_ext.begin(baud, SERIAL_8N1, 32, 33);

  // LCD
  M5.Axp.ScreenBreath(0);

  // Control BeetleC Motor,LED
  Wire.begin(0, 26);
}

void loop()
{
  _ms = millis();

  debugLoopCount();
  Blynk.run();

  sendToCar();

  #define HEARTBEAT_TO_V_MS (1000*5)
  if (_controlUpdated || _lastSentToV + HEARTBEAT_TO_V_MS < _ms) {
    sendToM5StickV();
    _lastSentToV = _ms;
    _controlUpdated = false;
  }

  String s;
  s = readLineFromV();
  if (0 < s.length()) {
    Serial.printf("V: %s\n", s.c_str());
  }

  s = readLineFromDebug();
  if (0 < s.length()) {
    Serial.printf("D: %s\n", s.c_str());
  }
}

BLYNK_WRITE(V0) // power(-100..+100)
{
  _power = param[0].asInt();
  _controlUpdated = true;
}

BLYNK_WRITE(V1) // steering(-100..+100)
{
  _steering = param[0].asInt();
  _controlUpdated = true;
}

void sendToCar()
{
  // steer by rate
  //signed int power = _power    * 0.3;
  //signed int steer = _steering * 0.7;
  //signed int left  = power * (100 - steer) / 100;
  //signed int right = power * (100 + steer) / 100;

  // steer by abs
  signed int power = _power    * 0.3;
  signed int steer = _steering * 0.3;
  signed int left  = power - steer;
  signed int right = power + steer;

#define POWER_MIN   1
#define POWER_MAX 100
  if (-POWER_MIN < left  && left  < POWER_MIN) {
    left  = 0;
  }
  if (-POWER_MIN < right && right < POWER_MIN) {
    right = 0;
  }
  if (POWER_MAX < left) {
    left  = POWER_MAX;
  }
  if (POWER_MAX < right) {
    right = POWER_MAX;
  }
  if (left  < -POWER_MAX) {
    left  = -POWER_MAX;
  }
  if (right < -POWER_MAX) {
    right = -POWER_MAX;
  }

  if(true){ // DYI PWM
    signed int n = _ms % 100;
    if(0<left){
      if(n     < left ){ left =  POWER_MAX; }else{ left  = 0; }
    }else{
      if(left  < -n   ){ left = -POWER_MAX; }else{ left  = 0; }
    }
    if(0<right){
      if(n     < right){ right =  POWER_MAX; }else{ right = 0; }
    }else{
      if(right < -n   ){ right = -POWER_MAX; }else{ right = 0; }
    }
  }

  if (_car_left != left) {
    leftwheel((uint8_t)left);
    _car_left = left;
  }
  if (_car_right != right) {
    rightwheel((uint8_t)right);
    _car_right = right;
  }

  //uint8_t buf[256];
  //size_t size = sprintf((char*)buf, "left=%d right=%d\n", left, right);
  //Serial.printf("%s", buf);
}

void sendToM5StickV()
{
  uint8_t buf[256];
  size_t size = sprintf((char*)buf, "power=%d steering=%d ms=%ld rtc=%s\n", _power, _steering, _ms, readRTC().c_str());
  sendToV(buf, size);

  Serial.printf("%s", buf);
}

size_t sendToV(uint8_t *buffer, size_t size)
{
  return serial_ext.write(buffer, size);
}

int readFromV(uint8_t *buffer, size_t size) {
  if (serial_ext.available()) {
    return serial_ext.readBytes(buffer, size);
  } else {
    return 0;
  }
}

String readLineFromV(void) {
  if (serial_ext.available()) {
    return serial_ext.readStringUntil('\n');
  } else {
    return String("");
  }
}

String readLineFromDebug(void) {
  if (Serial.available()) {
    return Serial.readStringUntil('\n');
  } else {
    return String("");
  }
}

String readRTC(void)
{
  RTC_TimeTypeDef time;
  RTC_DateTypeDef date;
  M5.Rtc.GetTime(&time);
  M5.Rtc.GetData(&date);
  char datetime[20];
  sprintf(datetime, "%04d-%02d-%02d_%02d:%02d:%02d", date.Year, date.Month, date.Date, time.Hours, time.Minutes, time.Seconds);
  return String(datetime);
}

void leftwheel(uint8_t val) {
  Wire.beginTransmission(0x38);
  Wire.write(0x00);
  Wire.write(val);
  Wire.endTransmission();
}

void rightwheel(uint8_t val) {
  Wire.beginTransmission(0x38);
  Wire.write(0x01);
  Wire.write(val);
  Wire.endTransmission();
}

void led(uint8_t num, uint32_t val) {
  Wire.beginTransmission(0x38);
  Wire.write(0x02);
  Wire.write(num);
  Wire.write(uint8_t(val >> 16));
  Wire.write(uint8_t(val >> 8));
  Wire.write(uint8_t(val & 0x0f));
  Wire.endTransmission();
}

void debugLoopCount()
{
  static unsigned long _prevMs = 0;
  #define LOOPS 20000
  if (_counter % LOOPS == 0) {
    if (0 < _prevMs) {
      Serial.printf("counter=%d: loop=%d/sec.\n", _counter, 1000 * LOOPS / (_ms - _prevMs));
    }
    _prevMs = _ms;
  }
  _counter += 1;
}
