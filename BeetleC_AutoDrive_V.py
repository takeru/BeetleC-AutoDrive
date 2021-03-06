import sensor, image, time, pmu, ure, uos, lcd, gc
from Maix import GPIO
from fpioa_manager import fm, board_info
from machine import UART
import KPU as kpu

class App():
    def main(self):
        try:
            self.setup()
            clock = time.clock()
            while True:
                self._fps = clock.fps()
                clock.tick()
                self.loop()
        finally:
            self.cleanup()
            self.set_lcd_brightness(7)

    def setup(self):
        print(kpu.memtest())
        self._rec               = None
        self._record_count      = 0
        self._loop_counter      = 0
        self._last_100ms_cnt    = 0
        self._next_loop_cmd_ms  = 0
        self._last_active_ms    = 0
        self._lcd_brightness    = None
        self._charge_mode       = None
        self._timestamp         = None
        self._ramdisk_mount_point = "/ramdisk"
        self._task              = None
        #self._mode              = "rec"
        self._mode              = "auto"
        self._flag_send_img_to_C = False

        self._axp192 = pmu.axp192()
        self._axp192.enableADCs(True)
        self._axp192.enableCoulombCounter(False)
        self.set_lcd_brightness(9)

        fm.register(board_info.BUTTON_A, fm.fpioa.GPIO1)
        self.button_a = GPIO(GPIO.GPIO1, GPIO.IN, GPIO.PULL_UP)
        fm.register(board_info.BUTTON_B, fm.fpioa.GPIO2)
        self.button_b = GPIO(GPIO.GPIO2, GPIO.IN, GPIO.PULL_UP)

        fm.register(35, fm.fpioa.UART2_TX, force=True)
        fm.register(34, fm.fpioa.UART2_RX, force=True)
        baud = 115200 # 115200 1500000 3000000 4500000
        self.uart = UART(UART.UART2, baud, 8, 0, 0, timeout=1000, read_buf_len=4096)

        sensor.reset()
        sensor.set_pixformat(sensor.RGB565)
        #sensor.set_pixformat(sensor.GRAYSCALE)
        #sensor.set_framesize(sensor.QVGA)
        sensor.set_framesize(sensor.QQVGA)
        #sensor.set_vflip(1)
        #sensor.set_hmirror(1) # if set 1, storange color!!!
        #sensor.set_windowing((224, 224))
        sensor.run(1)

        try:
            stat = uos.stat(self._ramdisk_mount_point)
            uos.umount(self._ramdisk_mount_point)
            # print("mount_point=", mount_point, " stat=", stat)
        except OSError as e:
            pass
        blkdev = RAMFlashDev()
        vfs = uos.VfsSpiffs(blkdev)
        vfs.mkfs(vfs)
        uos.mount(vfs, self._ramdisk_mount_point)

        lcd.init(freq=40000000)
        lcd.direction(lcd.YX_RLDU)
        lcd.clear(lcd.BLACK)
        lcd.draw_string(10, 10, "BeetleC_AutoDrive_V", lcd.CYAN, lcd.BLACK)

        if self._mode == "auto":
            #self._twoWheelSteeringThrottle = TwoWheelSteeringThrottle()
            print(kpu.memtest())
            self._task = kpu.load("/sd/model.kmodel")
            print(kpu.memtest())

    def loop(self):
        if self._mode == "auto":
            self.autopilot_loop()
            return
        if self._mode == "rec":
            self.recording_loop()
            return

    def recording_loop(self):
        self.open_recorder()

        if self._next_loop_cmd_ms <= time.ticks_ms():
            loop_cmd = "loop v_ms=%d v_records=%d v_loop=%d" % (time.ticks_ms(), self._record_count, self._loop_counter)
            self.sendToC(loop_cmd + "\n")
            self._next_loop_cmd_ms = time.ticks_ms() + 1000

        line = self.readLineFromC()
        tag = None
        if line:
            # print("C: %s" % line)
            tag = line[0:line.find(" ")]

        if tag == "ctrl":
            m = ure.search("throttle=(-?\d+) steering=(-?\d+) left=(-?\d+) right=(-?\d+)", line)
            if m and (int(m.group(1)) != 0 or int(m.group(2)) != 0 or int(m.group(3)) != 0 or int(m.group(4)) != 0):
                self._last_active_ms = time.ticks_ms()
            if (time.ticks_ms() - self._last_active_ms) < 1000:
                s = "v_ms=%d C=[%s]" % (time.ticks_ms(), line)
                if self._rec:
                    self._rec.write_string("ctrl", s)
                    print("R: " + s)
                    self.record()
                    self._next_loop_cmd_ms = 0
                else:
                    self._next_loop_cmd_ms = time.ticks_ms() + 200
            else:
                self._next_loop_cmd_ms = time.ticks_ms() + 200

        if tag == "hb_c":
            s = "v_ms=%d C=[%s]" % (time.ticks_ms(), line)
            if self._rec:
                self._rec.write_string("hb_c", s)
                print("R: " + s)
            else:
                print("_: " + s)
            m = ure.search("rtc=(\d+)-(\d+)-(\d+)_(\d+):(\d+):(\d+)", line)
            if m:
                self._timestamp = m.group(1) + m.group(2) + m.group(3) + "_" + m.group(4) + m.group(5) + m.group(6)

        if tag == "snapshot":
            self._flag_send_img_to_C = True

        self.sometimes_do()
        self._loop_counter += 1

    def autopilot_loop(self):
        img = sensor.snapshot()
        img = img.resize(224, 224)
        #img.draw_rectangle(0, 0, 224, 93, color=(0,0,0), fill=True)
        #img.draw_rectangle(0, 0, 224, 224, color=(255,0,0), fill=False)
        #img.draw_rectangle(0, 0, 112, 112, color=(0,255,0), fill=False)
        img.pix_to_ai()
        fmap = kpu.forward(self._task, img)
        plist = fmap[:]
        if True:
            # categorical model
            pmax = max(plist)
            max_index = plist.index(pmax)
            print(" ".join(["%2d" % (p*10) for p in plist]))
            print((" " * (3*max_index)) + "**")
            siz = len(plist) // 2
            steering = 45 * ((max_index - siz) / siz)
            throttle = 45
            print("throttle=", throttle, " steering=", steering)
            #left, right = self._twoWheelSteeringThrottle.run(throttle, steering)
            #left  = int(left  * 100)
            #right = int(right * 100)
            #s = "auto v_ms=%d left=%d right=%d " % (time.ticks_ms(), left, right)
            s = "auto v_ms=%d throttle=%d steering=%d " % (time.ticks_ms(), throttle, steering)
            self.sendToC(s + "\n")
            print("V: " + s)
        if False:
            # liner model
            print("plist=", plist)
            steering = plist[0] - 100
            throttle = 40
            #print("throttle=", throttle, " steering=", steering)
            s = "auto v_ms=%d throttle=%d steering=%d " % (time.ticks_ms(), throttle, steering)
            self.sendToC(s + "\n")
            print("V: " + s)

        lcd.display(img)
        img = None
        gc.collect()
        #lcd.draw_string(20, 100, "  %d    %d  " % (left, right), lcd.YELLOW, lcd.BLACK)
        #self.check_sleep_mode()

    def cleanup(self):
        self.close_recorder()
        try:
            uos.umount(self._ramdisk_mount_point)
        except OSError as e:
            print(e)
        if self._task:
            kpu.deinit(self._task)
            self._task = None

    def sometimes_do(self):
        cnt = int(time.ticks_ms() / 100)
        if cnt <= self._last_100ms_cnt:
            return
        self._last_100ms_cnt = cnt

        if cnt % 10 == 0: # every 1sec.
            if (time.ticks_ms() - self._last_active_ms) < 5000:
                self.set_lcd_brightness(9)
                self.set_charge_mode("on")
            else:
                self.set_lcd_brightness(7)

            if self._rec and 1 <= self._rec._write_jpeg_count and 10000 < (time.ticks_ms() - self._last_active_ms):
                self.close_recorder()
            self.check_send_img_to_C()
            self.check_sleep_mode()

        if cnt % 20 == 0: # every 2sec. heartbeat
            s = ("hb_v v_ms=%d v_records=%d v_loop=%d " % (time.ticks_ms(), self._record_count, self._loop_counter)) + self.system_status_string()
            self.sendToC(s + "\n")
            print("V: " + s)

        if False: # debug
            s = ""
            for addr in [0x28, 0x12, 0x91, 0x33, 0x34, 0x01, 0x7A, 0x7B]:
                value = self._axp192.__readReg(addr)
                s += 'REG{:02X}H=0x{:02X} ({:08b}) '.format(addr, value, value)
            print(s)
            r7a = self._axp192.__readReg(0x7A) # 8bit
            r7b = self._axp192.__readReg(0x7B) # 5bit
            ichg = (r7a << 5 | (r7b & 0x1F)) * 0.5
            print("ichg=%.3f" % ichg)

        if cnt % 60 == 0: # every 6sec.
            if 5000 < (time.ticks_ms() - self._last_active_ms):
                if self._axp192.getVbatVoltage() < 4100:
                    if self._charge_mode == "fast":
                        if self._axp192.getBatteryChargeCurrent() < 15:
                            self.set_charge_mode("off")
                        else:
                            self.set_charge_mode("fast")
                    else:
                        self.set_charge_mode("fast")
                else:
                    self.set_charge_mode("on")

    def set_lcd_brightness(self, brightness): # 0...15
        #self._axp192.setScreenBrightness(brightness)
        if self._lcd_brightness != brightness:
            self._axp192.__writeReg(0x91, brightness << 4)
            self._lcd_brightness = brightness

    def sendToC(self, data):
        # data = bytearray([0x00,0x00,0x00,0x00,0x00])
        self.uart.write(data)

    def readFromC(self, num):
        return self.uart.read(num)

    def readLineFromC(self):
        line = self.uart.readline()
        if line and line[0] != 0:
            try:
                line = line.decode('ascii').strip()
            except UnicodeError as e:
                line = None
        else:
            line = None
        return line

    def record(self):
        lcd.draw_string(10, 50, ure.sub("(.+)/", "", self._rec.filename), lcd.WHITE, lcd.BLACK)
        lcd.draw_string(10, 70, "%d" % (self._record_count), lcd.WHITE, lcd.BLACK)
        lcd.draw_string(10, 90, "fps=%.2f" % (self._fps), lcd.WHITE, lcd.BLACK)

        self._rec.write_number("v_ms", time.ticks_ms(), 4)
        img = sensor.snapshot()
        self._rec.write_jpeg_image(img)
        self._record_count += 1

    def open_recorder(self):
        if self._rec != None:
            return
        if self._timestamp:
            filename = "/sd/record-"+self._timestamp+".bin"
            try:
                self._rec = Recorder(filename+".writing")
                print("Open", filename)
                self._error_string = None
            except OSError as e:
                # print("Open Failed %s %s" % (filename, e))
                self._error_string = str(e)
                self._rec = None

    def close_recorder(self):
        if self._rec == None:
            return
        filename = ure.sub("\.writing$", "", self._rec.filename)
        uos.rename(self._rec.filename, filename)
        self._rec.close()
        self._rec = None
        stat = uos.stat(filename)
        print("Close", filename, stat[6], stat)

    def system_status_string(self):
        try:
            svfs = uos.statvfs("/sd/")
            self._error_string = None
        except OSError as e:
            self._error_string = str(e)
            svfs = (None,None,"ERR","ERR")

        return "v_vbat=%.1f v_temp=%.1f v_ichg=%.1f v_idcg=%.1f v_vusb=%.1f v_iusb=%.1f v_vaps=%.1f v_vex=%.1f v_iex=%.1f v_wbat=%.1f v_warn=%d v_blocks=%s v_bfree=%s" % (
            self._axp192.getVbatVoltage(),
            self._axp192.getTemperature(),
            self._axp192.getBatteryChargeCurrent(),
            self._axp192.getBatteryDischargeCurrent(),
            self._axp192.getUSBVoltage(),
            self._axp192.getUSBInputCurrent(),
            self._axp192_getApsVoltage(),
            self._axp192.getConnextVoltage(),
            self._axp192.getConnextInputCurrent(),
            self._axp192.getBatteryInstantWatts(),
            self._axp192_getWarningLeve(),
            svfs[2],
            svfs[3]
        )

    def _axp192_getApsVoltage(self):
        lsb = self._axp192.__readReg(0x7E)
        msb = self._axp192.__readReg(0x7F)
        return ((lsb << 4) + msb) * 1.4

    def _axp192_getWarningLeve(self):
        v = self._axp192.__readReg(0x47)
        return v & 0x01

    def set_charge_mode(self, mode):
        if self._charge_mode == mode:
            return
        reg0x33 = self._axp192.__readReg(0x33)
        if mode == "fast":
            reg0x33 |= (1<<7) # ON
            reg0x33 = (reg0x33 & 0xF0) | 0x01 # 190mA
        elif mode == "on":
            reg0x33 |= (1<<7) # ON
            reg0x33 = (reg0x33 & 0xF0) | 0x00 # 100mA
        elif mode == "off":
            reg0x33 &= ~(1<<7) # OFF
            reg0x33 = (reg0x33 & 0xF0) | 0x00 # 100mA
        self._axp192.__writeReg(0x33, reg0x33)
        self._charge_mode = mode
        #reg0x33 = self.axp192.__readReg(0x33)
        #print("reg0x33=%02X" % (reg0x33))

    def check_sleep_mode(self):
        if self.button_a.value() == 0:
            lcd.clear(lcd.WHITE)
            lcd.draw_string(30, 30, "Sleep...", lcd.RED, lcd.WHITE)
            time.sleep_ms(3000)
            self._axp192.setEnterSleepMode()

    def check_send_img_to_C(self):
        if self._flag_send_img_to_C:
            self.sendToC("img a=1")
            img = sensor.snapshot()
            #img = img.resize(224, 224)
            self.send_img(img)
            self._flag_send_img_to_C = False

# https://qiita.com/nnn112358/items/5efd926fea20cd6c2c43
    def send_img(self, img):
        img_buf = img.compress() # quality=70
        img_size1 = (img_buf.size()& 0xFF0000)>>16
        img_size2 = (img_buf.size()& 0x00FF00)>>8
        img_size3 = (img_buf.size()& 0x0000FF)>>0
        data_packet = bytearray([0xFF,0xD8,0xEA,0x01,img_size1,img_size2,img_size3,0x00,0x00,0x00])
        self.sendToC(data_packet)
        self.sendToC(img_buf)

#===================================================================================================
class Recorder:
    def __init__(self, filename):
        self.tmp_path = "/ramdisk/tmp.jpg"
        self.filename = filename
        self.bin_f = open(filename, "w")
        self._write_jpeg_count = 0

    def close(self):
        self.bin_f.flush()
        self.bin_f.close()

    def write_jpeg_image(self, img):
        img.save(self.tmp_path)
        stat = uos.stat(self.tmp_path)
        #print("tmp_path=", self.tmp_path, stat)
        size = stat[6]
        #print("size=", size)

        tmp_f = open(self.tmp_path, "rb")
        #r_len_sum = 0
        #w_len_sum = 0

        self.bin_f.write("jpeg\x00") # key=jpeg
        self.bin_f.write(size.to_bytes(4, 'big')) # 4 byte length
        while True:
            data = tmp_f.read(256)
            r_len = len(data)
            #print("r_len=", r_len)
            if 0 < r_len:
                #r_len_sum += r_len
                w_len = self.bin_f.write(data)
                #w_len_sum += w_len
                #print("w_len=", w_len)
            else:
                #print("r_len_sum=", r_len_sum, " w_len_sum=", w_len_sum)
                break
            data = None
        self.bin_f.flush()
        tmp_f.close()
        uos.remove(self.tmp_path)
        self._write_jpeg_count += 1

    def write_number(self, key, value, length=4):
        self.bin_f.write(key+"\x00")
        self.bin_f.write((length).to_bytes(4, 'big'))
        self.bin_f.write(value.to_bytes(length, 'big'))
        self.bin_f.flush()

    def write_string(self, key, value):
        self.bin_f.write(key+"\x00")
        self.bin_f.write((len(value)).to_bytes(4, 'big'))
        self.bin_f.write(value)
        self.bin_f.flush()

class RAMFlashDev:
    def __init__(self):
        unit = 128
        self.fs_size        = 256*unit  # 256*1024
        self.fs_data        = bytearray(self.fs_size)
        self.erase_block    =  32*unit  #  32*1024
        self.log_block_size =  64*unit  #  64*1024
        self.log_page_size  =   4*unit  #   4*1024

    def read(self,buf,size,addr):
        for i in range(len(buf)):
            buf[i] = self.fs_data[addr+i]

    def write(self,buf,size,addr):
        for i in range(len(buf)):
            self.fs_data[addr+i] = buf[i]

    def erase(self,size,addr):
        for i in range(size):
            self.fs_data[addr+i] = 0xff

class TwoWheelSteeringThrottle_xxx(object):
    def run(self, throttle, steering):
        if throttle > 1 or throttle < -1:
            raise ValueError( "throttle must be between 1(forward) and -1(reverse)")

        if steering > 1 or steering < -1:
            raise ValueError( "steering must be between 1(right) and -1(left)")

        left_motor_speed = throttle
        right_motor_speed = throttle

        if steering < 0:
            left_motor_speed  *= (1.0 - (-steering))
            right_motor_speed *= (1.0 - steering)
        elif steering > 0:
            right_motor_speed *= (1.0 - steering)
            left_motor_speed  *= (1.0 - (-steering))

        return left_motor_speed, right_motor_speed

    def inv(self, left_motor_speed, right_motor_speed):
        if left_motor_speed > 1 or left_motor_speed < -1:
            raise ValueError( "left_motor_speed must be between 1 and -1")

        if right_motor_speed > 1 or right_motor_speed < -1:
            raise ValueError( "right_motor_speed must be between 1 and -1")

        if left_motor_speed == right_motor_speed:
            throttle = left_motor_speed
            steering = 0.0
        elif abs(left_motor_speed) < abs(right_motor_speed):
            throttle = right_motor_speed
            steering = -(1.0 - ((left_motor_speed) / throttle))
        elif abs(left_motor_speed) > abs(right_motor_speed):
            throttle = left_motor_speed
            steering = 1.0 - ((right_motor_speed) / throttle)
        return throttle, steering


#===================================================================================================

App().main()
