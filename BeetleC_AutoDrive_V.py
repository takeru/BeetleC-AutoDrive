import uos

class Recorder:
    def __init__(self, filename):
        self.tmp_path = "/ramdisk/tmp.jpg"
        self.filename = filename
        self.bin_f = open(filename, "w")

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
        baud = 1500000 # 115200
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
        lcd.clear(lcd.BLUE)
        lcd.draw_string(20, 50, "BeetleC_AutoDrive_V", lcd.YELLOW, lcd.BLUE)

        self._rec          = None
        self._record_count = 0
        self._loop_counter = 0

    def loop(self):
        self.open_recorder()
        while True:
            line = self.readLineFromC()
            if line and line[0] != 0:
                line = line.decode('ascii').strip()
                s = "v_loop=%d v_ms=%d" % (self._loop_counter, time.ticks_ms())
                if line[0:2] == "hb":
                    s += " " + self.axp192_status_line()

                s += " C=[%s]" % (line)
                print(s)
                time.sleep(0.001)
                if self._rec:
                    self._rec.write_string("s", s)
            else:
                break

        self.record()
        if self._loop_counter % 100 == 99:
            self.close_recorder()
        self.sendToC("v_loop=%d v_ms=%d\n" % (self._loop_counter, time.ticks_ms()))
        self._loop_counter += 1

    def cleanup(self):
        self.close_recorder()
        uos.umount(self._randisk_mount_point)

    def set_lcd_brightness(self, brightness): # 0...15
        #self._axp192.setScreenBrightness(brightness)
        self._axp192.__writeReg(0x91, brightness << 4)

    def sendToC(self, data):
        # data = bytearray([0x00,0x00,0x00,0x00,0x00])
        self.uart.write(data)

    def readFromC(self, num):
        return self.uart.read(num)

    def readLineFromC(self):
        return self.uart.readline()

    def record(self):
        s = "%d %d %f" % (self._loop_counter, self._record_count, self._fps)
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
        self._record_count = 0

    def close_recorder(self):
        if not hasattr(self, '_rec') or self._rec == None:
            return
        filename = ure.sub("\.writing$", "", self._rec.filename)
        uos.rename(self._rec.filename, filename)
        self._rec.close()
        self._rec = None
        stat = uos.stat(filename)
        print("Close", filename, stat[6], stat)

    def axp192_status_line(self):
        return "v_vbat=%.1f v_vusb=%.1f v_iusb=%.1f v_vex=%.1f v_iex=%.1f v_ichg=%.1f v_idcg=%.1f v_wbat=%.1f v_temp=%.1f" % (
            self._axp192.getVbatVoltage(),
            self._axp192.getUSBVoltage(),
            self._axp192.getUSBInputCurrent(),
            self._axp192.getConnextVoltage(),
            self._axp192.getConnextInputCurrent(),
            self._axp192.getBatteryChargeCurrent(),
            self._axp192.getBatteryDischargeCurrent(),
            self._axp192.getBatteryInstantWatts(),
            self._axp192.getTemperature()
        )

App().main()
