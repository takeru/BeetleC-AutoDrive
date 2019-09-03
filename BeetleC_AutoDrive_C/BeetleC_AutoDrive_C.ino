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

signed char _v0 = 0;
signed char _v1 = 0;
unsigned long _lastSent = 0;
unsigned long _ms = 0;

HardwareSerial serial_ext(2);

void setup()
{
  M5.begin();

  Serial.begin(115200);
  Serial.println("Waiting for connections...");
  Blynk.setDeviceName("BeetleC");
  Blynk.begin(auth);
  int baud = 4500000; // 115200 1500000 3000000 4500000
  serial_ext.begin(baud, SERIAL_8N1, 32, 33);

  // LCD
  M5.Axp.ScreenBreath(0);

  // BeetleC
  Wire.begin(0, 26);

}

void loop()
{
  _ms = millis();

  Blynk.run();

  if (_lastSent + 1000 < _ms) {
    sendToCar();
    sendToM5StickV();
    _lastSent = _ms;
  }

  String s = readLineFromV();
  if (0 < s.length()) {
    Serial.printf("%s\n", s.c_str());
  }
}

BLYNK_WRITE(V0)
{
  _v0 = param[0].asInt();
  _lastSent = 0;
}

BLYNK_WRITE(V1)
{
  _v1 = param[0].asInt();
  _lastSent = 0;
}

void sendToCar()
{
  signed char left  = _v0 / 2;
  signed char right = _v1 / 2;
  #define POWER_MIN 10
  #define POWER_MAX 40
  if(-POWER_MIN < left  && left  < POWER_MIN){ left  = 0; }
  if(-POWER_MIN < right && right < POWER_MIN){ right = 0; }
  if(POWER_MAX < left){  left  = POWER_MAX; }
  if(POWER_MAX < right){ right = POWER_MAX; }
  if(left  < -POWER_MAX){ left  = -POWER_MAX; }
  if(right < -POWER_MAX){ right = -POWER_MAX; }

  leftwheel((uint8_t)left);
  rightwheel((uint8_t)right);

  uint8_t buf[256];
  size_t size = sprintf((char*)buf, "left=%d right=%d\n", left, right);
  
  Serial.printf("%s", buf);
}

void sendToM5StickV()                 
{
  uint8_t buf[256];
  size_t size = sprintf((char*)buf, "V0=%d V1=%d ms=%ld rtc=%s\n", _v0, _v1, _ms, readRTC().c_str());
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
