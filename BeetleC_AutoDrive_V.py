import uos

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

def initRamdisk(path):
    blkdev = RAMFlashDev()
    vfs = uos.VfsSpiffs(blkdev)
    vfs.mkfs(vfs)
    uos.mount(vfs, path)

def nextSeqFileName(format):
    maxnum_filename = format % (0) + ".max"
    try:
        with open(maxnum_filename) as f:
            maxnum = int(f.read().strip())
    except:
        maxnum = 0

    for n in range(maxnum+1, 999999):
        filename = format % (n)
        try:
            stat = uos.stat(filename)
        except OSError as e:
            with open(maxnum_filename, "w") as f:
                f.write("%d" % (n))
            return filename
    return None

# ------------------------------------------------------
import sensor, time, pmu

class TestApp:
    def setup(self):
        sensor.reset()
        sensor.set_pixformat(sensor.RGB565)
        sensor.set_framesize(sensor.QVGA)
        sensor.run(1)

        ramdisk_path = "/ramdisk"
        try:
            stat = uos.stat(ramdisk_path)
            # print("ramdisk_path=", ramdisk_path, " stat=", stat)
        except OSError as e:
            initRamdisk(ramdisk_path)

    def run(self):
        seq = 0
        for x in range(100):
            filename = nextSeqFileName("/sd/recorder_example%06d.bin")
            print("filename=", filename)
            rec = Recorder(filename+".working")
            clock = time.clock()
            for i in range(100):
                clock.tick()
                rec.write_number("seq", seq, 4)
                seq += 1
                img = sensor.snapshot()
                rec.write_jpeg_image(img)
                print("i=", i, " fps=", clock.fps())
            rec.close()
            uos.rename(filename+".working", filename)
            print(filename, uos.stat(filename))

#app = TestApp()
#app.setup()
#app.run()

#***************************************************************************************************

import sensor, image, time, pmu, ure, uos, lcd
#import recorder
from fpioa_manager import fm
from machine import UART

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
            #lcd.clear(lcd.BLACK)
            #lcd.draw_string(10, 10, "BeetleC_AutoDrive_V", lcd.RED, lcd.BLACK)

    def setup(self):
        self._rec               = None
        self._record_count      = 0
        self._loop_counter      = 0
        self._last_100ms_cnt    = 0
        self._next_loop_cmd_ms  = 0
        self._last_active_ms    = 0
        self._lcd_brightness    = None
        self._charge_mode       = None

        self._axp192 = pmu.axp192()
        self._axp192.enableADCs(True)
        self._axp192.enableCoulombCounter(False)
        self.set_lcd_brightness(9)

        fm.register(35, fm.fpioa.UART2_TX, force=True)
        fm.register(34, fm.fpioa.UART2_RX, force=True)
        baud = 1500000 # 115200 1500000 3000000 4500000
        self.uart = UART(UART.UART2, baud, 8, 0, 0, timeout=1000, read_buf_len=4096)

        sensor.reset()
        sensor.set_pixformat(sensor.RGB565)
        sensor.set_framesize(sensor.QVGA)
        sensor.run(1)

        self._randisk_mount_point = "/ramdisk"
        try:
            stat = uos.stat(self._randisk_mount_point)
            uos.umount(self._randisk_mount_point)
            # print("mount_point=", mount_point, " stat=", stat)
        except OSError as e:
            pass
        initRamdisk(self._randisk_mount_point)

        lcd.init(freq=40000000)
        lcd.direction(lcd.YX_RLDU)
        lcd.clear(lcd.BLACK)
        lcd.draw_string(10, 10, "BeetleC_AutoDrive_V", lcd.CYAN, lcd.BLACK)

    def loop(self):
        self.open_recorder()

        if self._next_loop_cmd_ms <= time.ticks_ms():
            loop_cmd = "loop v_ms=%d v_records=%d v_loop=%d" % (time.ticks_ms(), self._record_count, self._loop_counter)
            self.sendToC(loop_cmd + "\n")
            self._next_loop_cmd_ms = time.ticks_ms() + 1000

        line = self.readLineFromC()
        tag = None
        if line:
            tag = line[0:line.find(" ")]
            if (tag == "hb_c") or (tag == "ctrl"):
                s = "v_ms=%d" % (time.ticks_ms())
                s += " C=[%s]" % (line)
                print("record:" + s)
                self._rec.write_string(tag, s)
            else:
                #print("ignore:" + line)
                pass

        if tag == "ctrl":
            m = ure.search("power=(-?\d+) steering=(-?\d+) left=(-?\d+) right=(-?\d+)", line)
            if m and (int(m.group(1)) != 0 or int(m.group(2)) != 0 or int(m.group(3)) != 0 or int(m.group(4)) != 0):
                self._last_active_ms = time.ticks_ms()
            if (time.ticks_ms() - self._last_active_ms) < 3000:
                self.record()
                self._next_loop_cmd_ms = 0
            else:
                self._next_loop_cmd_ms = time.ticks_ms() + 1000

        self.sometimes_do()
        self._loop_counter += 1

    def cleanup(self):
        self.close_recorder()
        uos.umount(self._randisk_mount_point)

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

            if 1 <= self._rec._write_jpeg_count and 20000 < (time.ticks_ms() - self._last_active_ms):
                self.close_recorder()

        if cnt % 20 == 0: # every 2sec. heartbeat
            s = ("hb_v v_ms=%d v_records=%d v_loop=%d " % (time.ticks_ms(), self._record_count, self._loop_counter)) + self.system_status_string()
            self.sendToC(s + "\n")
            print("V: " + s)
            self._last_heartbeat_ms = time.ticks_ms()


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
        #time.sleep(0.001) # シリアルコンソールが文字化けする場合の対策sleep

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
        s = "rec=%d fps=%.2f" % (self._record_count, self._fps)
        lcd.draw_string(10, 50, ure.sub("(.+)/", "", self._rec.filename), lcd.WHITE, lcd.BLACK)
        lcd.draw_string(10, 70, s, lcd.WHITE, lcd.BLACK)

        self._rec.write_number("v_ms", time.ticks_ms(), 4)
        img = sensor.snapshot()
        self._rec.write_jpeg_image(img)
        self._record_count += 1

    def open_recorder(self):
        if hasattr(self, '_rec') and self._rec != None:
            return
        filename = nextSeqFileName("/sd/m5stickv-record-%06d.bin")
        print("Open", filename)
        self._rec = Recorder(filename+".writing")

    def close_recorder(self):
        if not hasattr(self, '_rec') or self._rec == None:
            return
        filename = ure.sub("\.writing$", "", self._rec.filename)
        uos.rename(self._rec.filename, filename)
        self._rec.close()
        self._rec = None
        stat = uos.stat(filename)
        print("Close", filename, stat[6], stat)

    def system_status_string(self):
        svfs = uos.statvfs("/sd/")
        return "v_vbat=%.1f v_temp=%.1f v_ichg=%.1f v_idcg=%.1f v_vusb=%.1f v_iusb=%.1f v_vaps=%.1f v_vex=%.1f v_iex=%.1f v_wbat=%.1f v_warn=%d v_blocks=%d v_bfree=%d" % (
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

App().main()
