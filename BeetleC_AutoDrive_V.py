# Untitled - By: takeru - 日 9月 1 2019

import sensor, image, time
from fpioa_manager import fm
from machine import UART



class App():
    def main(self):
        self.setup()
        while True:
            self.loop()

    def setup(self):
        fm.register(35, fm.fpioa.UART2_TX, force=True)
        fm.register(34, fm.fpioa.UART2_RX, force=True)
        baud = 4500000 # 115200
        self.uart = UART(UART.UART2, baud, 8, 0, 0, timeout=1000, read_buf_len=4096)
        self._lastSent = 0

    def loop(self):
        line = self.readLineFromC()
        if line:
            print(line)

        if self._lastSent + 1000 < time.ticks_ms():
            s = "ticks_ms=%d" % time.ticks_ms()
            #print(s)
            self.sendToC(s + "\n")
            self._lastSent = time.ticks_ms()

    def sendToC(self, data):
        # data = bytearray([0x00,0x00,0x00,0x00,0x00])
        self.uart.write(data)

    def readFromC(self, num):
        return self.uart.read(num)

    def readLineFromC(self):
        return self.uart.readline()

App().main()
