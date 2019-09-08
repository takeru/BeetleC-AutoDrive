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
#include <Wiimote.h>


#include "secret.h"
//char auth[] = "*****";

signed char _power         =  0;
signed char _steering      =  0;
signed char _power_rate    = 40;
signed char _steering_rate = 40;
signed char _pwm_width_ms  = 25;

bool _controlUpdated = false;

unsigned long _lastSentToV = 0;
unsigned long _ms = 0;
unsigned long _counter = 0;
uint8_t _car_left  = 1;
uint8_t _car_right = 1;
HardwareSerial serial_ext(2); // Serial from/to V via GROVE

bool wiimote_button_down  = false;
bool wiimote_button_up    = false;
bool wiimote_button_right = false;
bool wiimote_button_left  = false;
bool wiimote_button_plus  = false;
bool wiimote_button_2     = false;
bool wiimote_button_1     = false;
bool wiimote_button_B     = false;
bool wiimote_button_A     = false;
bool wiimote_button_minus = false;
bool wiimote_button_home  = false;

void setup()
{
  M5.begin();

  Serial.begin(115200);
  Serial.println("Waiting for connections...");
  Blynk.setDeviceName("BeetleC-AutoDrive");
  Blynk.begin(auth);
  Wiimote::init();
  Wiimote::register_callback(1, wiimote_callback);

  // M5StickV
  int baud = 4500000; // 115200 1500000 3000000 4500000
  serial_ext.begin(baud, SERIAL_8N1, 32, 33);

  // LCD
  M5.Axp.ScreenBreath(0);

  // Control BeetleC Motor,LED
  Wire.begin(0, 26);

  leftwheel(0);
  rightwheel(0);
}

void loop()
{
  _ms = millis();

  debugLoopCount();
  Blynk.run();
  Wiimote::handle();

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

  static unsigned long last_tick = 0;
  unsigned long tick = (_ms / 50);
  if(last_tick < tick){
    if(wiimote_button_2){
      _power += 2;
    }
    if(wiimote_button_1){
      _power -= 2;
    }
    if((!wiimote_button_2) && (!wiimote_button_1)){
      _power *= 0.90;
    }

    if(wiimote_button_left){
      _steering += 5;
    }
    if(wiimote_button_right){
      _steering -= 5;
    }
    if((!wiimote_button_left) && (!wiimote_button_right)){
      _steering *= 0.80;
    }

    if(_power    < -100     ){ _power    = -100; }
    if(100       < _power   ){ _power    =  100; }
    if(_steering < -100     ){ _steering = -100; }
    if(100       < _steering){ _steering =  100; }

    last_tick = tick;
  }
}

void wiimote_callback(uint8_t number, uint8_t* data, size_t len) {
  Serial.printf("wiimote number=%d len=%d ", number, len);
  for (int i = 0; i < len; i++) {
    Serial.printf("%02X ", data[i]);
  }
  Serial.print("\n");

  wiimote_button_down  = (data[2] & 0x01) != 0;
  wiimote_button_up    = (data[2] & 0x02) != 0;
  wiimote_button_right = (data[2] & 0x04) != 0;
  wiimote_button_left  = (data[2] & 0x08) != 0;
  wiimote_button_plus  = (data[2] & 0x10) != 0;
  wiimote_button_2     = (data[3] & 0x01) != 0;
  wiimote_button_1     = (data[3] & 0x02) != 0;
  wiimote_button_B     = (data[3] & 0x04) != 0;
  wiimote_button_A     = (data[3] & 0x08) != 0;
  wiimote_button_minus = (data[3] & 0x10) != 0;
  wiimote_button_home  = (data[3] & 0x80) != 0;
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

BLYNK_WRITE(V11) // power_rate(0..100)
{
  _power_rate = param[0].asInt();
  Serial.printf("D: _power_rate=%d\n", _power_rate);
}

BLYNK_WRITE(V12) // steering_rate(0..100)
{
  _steering_rate = param[0].asInt();
  Serial.printf("D: _steering_rate=%d\n", _steering_rate);
}

BLYNK_WRITE(V13) // pwm_width_ms(1..500)
{
  _pwm_width_ms = param[0].asInt();
  Serial.printf("D: _pwm_width_ms=%d\n", _pwm_width_ms);
}

void sendToCar()
{
  // steer by rate
  //signed int power = _power    * 0.3;
  //signed int steer = _steering * 0.7;
  //signed int left  = power * (100 - steer) / 100;
  //signed int right = power * (100 + steer) / 100;

  // steer by abs
  signed int power = _power    * _power_rate    / 100;
  signed int steer = _steering * _steering_rate / 100;
  signed int left  = power - steer;
  signed int right = power + steer;

  if(true){ // DYI PWM
    #define PWM_ON 127
    #define PWM_WIDTH_US (_pwm_width_ms*1000) // 100 50 25
    long n = 100 * (micros() % PWM_WIDTH_US) / PWM_WIDTH_US; // 0 <= t < 100
    if(0<left){
      if(n     < left ){ left =  PWM_ON; }else{ left  = 0; }
    }else{
      if(left  < -n   ){ left = -PWM_ON; }else{ left  = 0; }
    }
    if(0<right){
      if(n     < right){ right =  PWM_ON; }else{ right = 0; }
    }else{
      if(right < -n   ){ right = -PWM_ON; }else{ right = 0; }
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
