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

    def setup(self):
        self._axp192 = pmu.axp192()
        self.set_lcd_brightness(7)

        fm.register(35, fm.fpioa.UART2_TX, force=True)
        fm.register(34, fm.fpioa.UART2_RX, force=True)
        baud = 115200 # 1500000
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
        lcd.draw_string(20, 50, "BeetleC_AutoDrive_V", lcd.CYAN, lcd.BLACK)

        self._rec               = None
        self._record_count      = 0
        self._loop_counter      = 0
        self._last_heartbeat_ms = 0
        self._next_loop_cmd_ms  = 0
        self._last_active_ms    = 0

    def loop(self):
        self.heartbeat()

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
            if line.find("power=0 steering=0 left=0 right=0") == -1:
                self._last_active_ms = time.ticks_ms()
            is_active = (time.ticks_ms() - self._last_active_ms) < 5000
            if is_active:
                self.record()
            else:
                time.sleep(2.0)
            self._next_loop_cmd_ms = 0

        if 500 <= self._rec._write_jpeg_count:
            self.close_recorder()

        self._loop_counter += 1

    def cleanup(self):
        self.close_recorder()
        uos.umount(self._randisk_mount_point)

    def heartbeat(self):
        if 2000 < time.ticks_ms() - self._last_heartbeat_ms:
            s = ("hb_v v_ms=%d v_records=%d v_loop=%d " % (time.ticks_ms(), self._record_count, self._loop_counter)) + self.system_status_string()
            self.sendToC(s + "\n")
            print("V: " + s)
            self._last_heartbeat_ms = time.ticks_ms()

    def set_lcd_brightness(self, brightness): # 0...15
        #self._axp192.setScreenBrightness(brightness)
        self._axp192.__writeReg(0x91, brightness << 4)

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
        s = "%d %f" % (self._record_count, self._fps)
        lcd.draw_string(2, 2, ure.sub("(.+)/", "", self._rec.filename), lcd.WHITE, lcd.RED)
        lcd.draw_string(2, 20, s, lcd.WHITE, lcd.RED)

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

App().main()
