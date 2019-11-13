
#define USE_BLYNK 0

#if USE_BLYNK
  /* Comment this out to disable prints and save space */
  #define BLYNK_PRINT Serial
  #define BLYNK_USE_DIRECT_CONNECT
  #include <BlynkSimpleEsp32_BLE.h>
  #include <BLEDevice.h>
  #include <BLEServer.h>
  #include "secret.h"
  //char auth[] = "*****";
#endif

#include <HardwareSerial.h>
#include <M5StickC.h>
#include <Arduino.h>
#include <Wire.h>
#include <Wiimote.h>

Wiimote wiimote;
signed char _ctrl_throttle      =   0;
signed char _ctrl_steering      =   0;
signed char _ctrl_throttle_rate = 100;
signed char _ctrl_steering_rate = 100;
signed char _pwm_width_ms       =  25;

unsigned long _lastSentToV = 0;
unsigned long _ctrl_sec    = 0;
unsigned long _ms          = 0;
unsigned long _sec         = 0;
unsigned long _counter     = 0;

int _car_l                 = 1;
int _car_r                 = 1;
int _output_left           = 0;
int _output_right          = 0;

unsigned long _auto_ms     = 0;
int _auto_left             = 0; // -100..100
int _auto_right            = 0; // -100..100
int _auto_throttle         = 0; // -100..100
int _auto_steering         = 0; // -100..100

HardwareSerial serial_ext(2); // Serial from/to V via GROVE

double _c_vbat = 0;
double _v_vbat = 0;
double _c_vusb = 0;

uint8_t wiimote_reporting = 0xFF;
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
bool wiimote_button_C     = false;
bool wiimote_button_Z     = false;
uint8_t wiimote_SX        = 0xFF;
uint8_t wiimote_SY        = 0xFF;
uint8_t wiimote_SX_offset = 0xFF;
uint8_t wiimote_SY_offset = 0xFF;

void setup()
{
  M5.begin();
  //Serial.begin(115200);
  Serial.setTimeout(1);

#if USE_BLYNK
  Blynk.setDeviceName("BeetleC-AutoDrive");
  Blynk.begin(auth);
#endif
  wiimote.init(wiimote_callback);

  // M5StickV
  int baud = 1500000; // 115200 1500000 3000000 4500000
  serial_ext.begin(baud, SERIAL_8N1, 32, 33);
  serial_ext.setTimeout(1);

  // LCD
  M5.Axp.ScreenBreath(8);
  M5.Lcd.setRotation(0);
  M5.Lcd.setTextFont(1);
  M5.Lcd.setTextSize(1);

  // Control BeetleC Motor,LED
  Wire.begin(0, 26);

  leftwheel(0);
  rightwheel(0);
  led(7, 0);

  led_ready();
}

void loop()
{
  _ms = millis();
  _sec = _ms / 1000;

  debugLoopCount();
#if USE_BLYNK
  Blynk.run();
#endif
  wiimote.handle();

  sendToCar();
  heartbeat();

  String s;
  s = readLineFromV();
  if (0 < s.length()) {
    bool loop = strncmp(s.c_str(), "loop ", 5)==0;
    if(loop){
      uint8_t buf[512];
      size_t size = sprintf((char*)buf, "ctrl c_ms=%ld throttle=%d steering=%d left=%d right=%d V=[%s]\n", _ms, _ctrl_throttle, _ctrl_steering, _output_left, _output_right, s.c_str());
      sendToV(buf, size);
    }
    if(!loop){
      Serial.printf("V: %s\n", s.c_str());
    }

    if(strncmp(s.c_str(), "hb_v ", 5)==0){
      _v_vbat = 0.0;
      char* c0 = strstr(s.c_str(), "v_vbat=");
      if(c0 != NULL){
        c0 += 7;
        char* c1 = strstr(c0, " ");
        if(c1 != NULL){
          char buf[16];
          strncpy(buf, c0, c1-c0);
          buf[c1-c0] = 0;
          _v_vbat = atof(buf);
        }
      }
    }

    if(strncmp(s.c_str(), "auto ", 5)==0){
      _auto_ms = _ms;
      String throttle = extract_value(s, "throttle");
      if(1 <= throttle.length()){
        _auto_throttle = atoi(extract_value(s, "throttle").c_str());
        _auto_steering = atoi(extract_value(s, "steering").c_str());
        _auto_left     = 0;
        _auto_right    = 0;
        Serial.printf("auto_throttle=%2d auto_steering=%2d\n", _auto_throttle, _auto_steering);
        if(_auto_throttle != 0){ _ctrl_sec = _sec; }
      }else{
        _auto_left     = atoi(extract_value(s, "left").c_str());
        _auto_right    = atoi(extract_value(s, "right").c_str());
        _auto_throttle = 0;
        _auto_steering = 0;
        Serial.printf("auto_left=%2d auto_right=%2d\n", _auto_left, _auto_right);
        if(_auto_left != 0 || _auto_right != 0){ _ctrl_sec = _sec; }
      }
    }
  }

  s = readLineFromDebug();
  if (0 < s.length()) {
    Serial.printf("D: %s\n", s.c_str());
  }

  wiimote_control();
  update_screen();
  update_status();
}


String extract_value(String s, char* key)
{
  char* c0 = strstr(s.c_str(), (String(key)+"=").c_str());
  if(c0 != NULL){
    c0 += String(key).length()+1;
    char* c1 = strstr(c0, " ");
    if(c1 != NULL){
      char buf[16];
      strncpy(buf, c0, c1-c0);
      buf[c1-c0] = 0;
      return String(buf);
    }
  }
  return String("");
}

void heartbeat(void)
{
  #define HEARTBEAT_TO_V_MS (1000*5)
  if (_lastSentToV + HEARTBEAT_TO_V_MS < _ms) {
    double c_vbat  = M5.Axp.GetVbatData() * 1.1;
    _c_vbat = c_vbat;
    double c_temp = -144.7 + M5.Axp.GetTempData() * 0.1;
    double c_ichg  = M5.Axp.GetIchargeData() * 0.5;
    double c_idchg = M5.Axp.GetIdischargeData() * 0.5;
    double c_vusb  = M5.Axp.GetVusbinData() * 1.7;
    _c_vusb = c_vusb;
    double c_iusb  = M5.Axp.GetIusbinData() * 0.375;
    double c_vaps  = M5.Axp.GetVapsData() *1.4;
    double c_vex   = M5.Axp.GetVinData() * 1.7;
    double c_iex   = M5.Axp.GetIinData() * 0.625;
    uint8_t c_warn = M5.Axp.GetWarningLeve();

    uint8_t buf[256];
    size_t size = sprintf((char*)buf, "hb_c c_ms=%ld rtc=%s c_vbat=%.1f c_temp=%.1f c_ichg=%.1f c_idchg=%.1f c_vusb=%.1f c_iusb=%.1f c_vaps=%.1f c_vex=%.1f c_iex=%.1f c_warn=%d throttle_rate=%d steering_rate=%d pwm_width_ms=%d\n",
      _ms,
      readRTC().c_str(),
      c_vbat,
      c_temp,
      c_ichg,
      c_idchg,
      c_vusb,
      c_iusb,
      c_vaps,
      c_vex,
      c_iex,
      c_warn,
      _ctrl_throttle_rate,
      _ctrl_steering_rate,
      _pwm_width_ms
    );
    sendToV(buf, size);
    Serial.printf("%s", buf);
    _lastSentToV = _ms;
  }
}

void wiimote_control(void)
{
  static unsigned long last_tick = 0;
  unsigned long tick = (_ms / 20);
  if(last_tick < tick){
    if(wiimote_button_2){
      _ctrl_throttle += 1;
    }
    if(wiimote_button_1){
      _ctrl_throttle -= 1;
    }
    if((!wiimote_button_2) && (!wiimote_button_1)){
      _ctrl_throttle *= 0.90;
    }

    if(wiimote_button_left){
      _ctrl_steering -= 1;
    }
    if(wiimote_button_right){
      _ctrl_steering += 1;
    }
    if((!wiimote_button_left) && (!wiimote_button_right)){
      _ctrl_steering *= 0.90;
    }

    if(wiimote_reporting==0x32){
      if(wiimote_SX_offset==0xFF){ wiimote_SX_offset = wiimote_SX; }
      if(wiimote_SY_offset==0xFF){ wiimote_SY_offset = wiimote_SY; }
      _ctrl_throttle = (wiimote_SY - wiimote_SY_offset) / 2 / 5 * 5;
      _ctrl_steering = (wiimote_SX - wiimote_SX_offset)     / 5 * 5;
    }else{
      wiimote_SX_offset = 0xFF;
      wiimote_SY_offset = 0xFF;
    }

    #define WIIMOTE_THROTTLE_MAX 35
    #define WIIMOTE_STEERING_MAX 100
    if(_ctrl_throttle < -WIIMOTE_THROTTLE_MAX){ _ctrl_throttle = -WIIMOTE_THROTTLE_MAX; }
    if(WIIMOTE_THROTTLE_MAX  < _ctrl_throttle){ _ctrl_throttle =  WIIMOTE_THROTTLE_MAX; }
    if(_ctrl_steering < -WIIMOTE_STEERING_MAX){ _ctrl_steering = -WIIMOTE_STEERING_MAX; }
    if(WIIMOTE_STEERING_MAX  < _ctrl_steering){ _ctrl_steering =  WIIMOTE_STEERING_MAX; }

    last_tick = tick;
  }
}

void wiimote_callback(wiimote_event_type_t event_type, uint16_t handle, uint8_t *data, size_t len) {
  if(event_type == WIIMOTE_EVENT_DATA){
    wiimote_data(data, len);
  }else if(event_type == WIIMOTE_EVENT_INITIALIZE){
    wiimote.scan(true);
  }else if(event_type == WIIMOTE_EVENT_CONNECT){
    wiimote.scan(false);
    wiimote.set_led(handle, 0b0001);
  }
}

void wiimote_data(uint8_t* data, size_t len) {
//  Serial.printf("wiimote number=%d len=%d ", number, len);
//  for (int i = 0; i < len; i++) {
//    Serial.printf("%02X ", data[i]);
//  }
//  Serial.print("\n");

  wiimote_reporting    = data[1];
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
  if(wiimote_reporting==0x32){
    // Nunchuck : TODO check ext controller code.
    uint8_t* ext = data+4;
    wiimote_SX         = ext[0];
    wiimote_SY         = ext[1];
    wiimote_button_C   = 0==(ext[5]&0x02);
    wiimote_button_Z   = 0==(ext[5]&0x01);
  }else{
    wiimote_SX         = 0xFF;
    wiimote_SY         = 0xFF;
    wiimote_button_C   = false;
    wiimote_button_Z   = false;
  }

  if(wiimote_button_2 && wiimote_button_1){
    led(3, 0x010001);
  }else if(wiimote_button_2){
    led(3, 0x000001);
  }else if(wiimote_button_1){
    led(3, 0x010000);
  }else{
    led(3, 0x000000);
  }
  if(wiimote_button_right){
    led(2, 0x030100);
  }else{
    led(2, 0x000000);
  }
  if(wiimote_button_left){
    led(4, 0x030100);
  }else{
    led(4, 0x000000);
  }

  _ctrl_sec = _sec;
}

#if USE_BLYNK
BLYNK_WRITE(V0) // throttle(-100..+100)
{
  _throttle = param[0].asInt();
}

BLYNK_WRITE(V1) // steering(-100..+100)
{
  _steering = param[0].asInt();
}

BLYNK_WRITE(V11) // throttle_rate(0..100)
{
  _throttle_rate = param[0].asInt();
  Serial.printf("D: _throttle_rate=%d\n", _throttle_rate);
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
#endif

void sendToCar()
{
  int left  = 0; // -100 .. 100
  int right = 0; // -100 .. 100

  if((_auto_left != 0 || _auto_right != 0) && (_ms - _auto_ms < 100)){
    left  = _auto_left;
    right = _auto_right;
  }else{
    int throttle = 0; // -100 .. 100
    int steering = 0; // -100 .. 100

    if((_auto_throttle != 0 || _auto_steering != 0) && (_ms - _auto_ms < 100)){
      throttle = _auto_throttle;
      steering = _auto_steering;
    }else{
      throttle = _ctrl_throttle * _ctrl_throttle_rate / 100; // -100 .. 100
      steering = _ctrl_steering * _ctrl_steering_rate / 100; // -100 .. 100
    }

    if(1){
      left  = throttle;
      right = throttle;
      if(steering < 0){
        left  = throttle * (100 + steering) / 100;
        //right = throttle * (100 - steering) / 100;
      }else if(0 < steering){
        //left  = throttle * (100 + steering) / 100;
        right = throttle * (100 - steering) / 100;
      }
    }
    //  if(0){
    //    int left  = throttle - steering;
    //    int right = throttle + steering;
    //  }
  }

  _output_left  = left;
  _output_right = right;

  int l = left;
  int r = right;
  if(true){ // DYI PWM
    #define PWM_ON 127
    #define PWM_WIDTH_US (_pwm_width_ms*1000) // 100 50 25
    long n = 100 * (micros() % PWM_WIDTH_US) / PWM_WIDTH_US; // 0 <= t < 100
    if(0<l){
      if(n < l ){ l =  PWM_ON; }else{ l = 0; }
    }else{
      if(l < -n){ l = -PWM_ON; }else{ l = 0; }
    }
    if(0<r){
      if(n < r ){ r =  PWM_ON; }else{ r = 0; }
    }else{
      if(r < -n){ r = -PWM_ON; }else{ r = 0; }
    }
  }

  if (_car_l != l) {
    leftwheel((uint8_t)l);
    _car_l = l;
  }
  if (_car_r != r) {
    rightwheel((uint8_t)r);
    _car_r = r;
  }
}

size_t sendToV(uint8_t *buffer, size_t size)
{
  size_t wsize = serial_ext.write(buffer, size);
  //delay(1);
  return wsize;
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

void update_screen(){
  static unsigned long _prev_ms = 0;
  if(1000 < _ms - _prev_ms || _prev_ms == 0){
    // ok
  }else{
    return;
  }

  M5.Lcd.fillScreen(BLACK);

  M5.Lcd.setCursor(5, 130);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.printf("%02d:%02d:%02d", _sec/3600, _sec/60%60, _sec%60);

  M5.Lcd.setCursor(5, 140);
  M5.Lcd.setTextColor(ORANGE, BLACK);
  M5.Lcd.printf("%.2f", _c_vbat/1000);

  //M5.Lcd.setCursor(50, 140);
  M5.Lcd.setTextColor(CYAN, BLACK);
  M5.Lcd.printf(" %.2f", _v_vbat/1000);

//  String s = " ";
//  if(wiimote_button_left ){ s += "< "; }else{ s += "  "; }
//  if(wiimote_button_right){ s += "> "; }else{ s += "  "; }
//  if(wiimote_button_1    ){ s += "1 "; }else{ s += "  "; }
//  if(wiimote_button_2    ){ s += "2 "; }else{ s += "  "; }
//  M5.Lcd.setCursor(5, 150);
//  M5.Lcd.setTextColor(BLACK, WHITE);
//  M5.Lcd.printf("%s", s.c_str());

  _prev_ms = _ms;
}

void update_status()
{
  static unsigned long _prev_ms = 0;
  if(1000 < _ms - _prev_ms || _prev_ms == 0){
    // ok
  }else{
    return;
  }

  static int _prev_status = 0;

  if(4000.0 <= _c_vusb || 5 < (_sec - _ctrl_sec)){
    if(_sec % 2 == 0){
      if(4100 < _c_vbat){
        led(3, 0x000001); // blue
      }else if(3950 < _c_vbat){
        led(3, 0x000100); // green
      }else if(3800 < _c_vbat){
        led(3, 0x010100); // yellow
      }else if(3650 < _c_vbat){
        led(3, 0x020100); // orange
      }else{
        led(3, 0x020000); // red
      }
      if(4100 < _v_vbat){
        led(0, 0x000001); // blue
      }else if(3950 < _v_vbat){
        led(0, 0x000100); // green
      }else if(3800 < _v_vbat){
        led(0, 0x010100); // yellow
      }else if(3650 < _v_vbat){
        led(0, 0x020100); // orange
      }else{
        led(0, 0x020000); // red
      }
    }else{
      led(7, 0x000000); // off
    }
  }else{
    led(7, 0x000000); // off
  }

  if(4000.0 <= _c_vusb){
    _ctrl_sec = _sec;
  }

  int status = 0;
  if(60 < (_sec - _ctrl_sec)){
    status = 1;
  }
  if(120 < (_sec - _ctrl_sec)){
    status = 2;
  }
  if(M5.Axp.GetWarningLeve()){
    status = 2;
  }
  if(_prev_status != status){
    switch(status){
    case 0:
      M5.Axp.ScreenBreath(8);
      led(7, 0);
      break;
    case 1:
      M5.Axp.ScreenBreath(7);
      led(7, 0x010000); // red
      break;
    case 2:
      led(7, 0x000000); // LED off
      M5.Axp.DeepSleep();
      break;
    }
  }
  _prev_status = status;
}

void debugLoopCount()
{
  static unsigned long _prev_ms      = 0;
  static unsigned long _prev_counter = 0;
  if(10000 < _ms - _prev_ms || _prev_ms == 0){
    if (0 < _prev_ms) {
      Serial.printf("counter=%d: loop=%d/sec.\n", _counter, 1000 * (_counter - _prev_counter) / (_ms - _prev_ms));
    }
    _prev_ms      = _ms;
    _prev_counter = _counter;
  }
  _counter += 1;
}

void led_ready(void)
{
  led(7, 0);
  for(int i=0; i<3; i++){
    led(7, 0);
    led(0, 0x0f0f0f);
    m5stickc_led(false);
    delay(50);

    led(7, 0);
    led(1, 0x0f0000);
    m5stickc_led(true);
    delay(50);

    led(7, 0);
    led(2, 0x0f0f00);
    m5stickc_led(false);
    delay(50);

    led(7, 0);
    led(3, 0x000f00);
    m5stickc_led(true);
    delay(50);

    led(7, 0);
    led(4, 0x000f0f);
    m5stickc_led(false);
    delay(50);

    led(7, 0);
    led(5, 0x00000f);
    m5stickc_led(true);
    delay(50);

    led(7, 0);
    led(6, 0x0f000f);
    m5stickc_led(false);
    delay(50);
  }
  led(7, 0);
  m5stickc_led(false);
}

void m5stickc_led(bool on)
{
  static bool init = false;
  if(!init){ pinMode(GPIO_NUM_10, OUTPUT); init = true; }
  digitalWrite(GPIO_NUM_10, on ? LOW : HIGH);
}
