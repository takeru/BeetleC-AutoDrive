# M5StickVの電源管理方法
# https://github.com/sipeed/MaixPy/blob/master/components/boards/m5stick/src/m5stick.c
# https://github.com/sipeed/MaixPy/blob/master/projects/maixpy_m5stickv/builtin_py/pmu.py
# https://pdf1.alldatasheet.com/datasheet-pdf/view/757469/ETC2/AXP192.html

# 参考: M5StickC https://github.com/m5stack/M5StickC/blob/master/src/AXP192.cpp

import lcd
import pmu

class App():
    def main(self):
        self.setup()
        while(True):
            self.loop()

    def setup(self):
        lcd.init(freq=40000000)
        #lcd.direction(lcd.YX_LRUD)
        lcd.direction(lcd.YX_RLDU)

        self.counter = 0
        self.axp192 = pmu.axp192()

        self.axp192.enableADCs(True)
        self.axp192.enableCoulombCounter(True)

        self.printRegs()

        # LCDの明るさ
        self.axp192.__writeReg(0x91, 0x70) # 上位4bit 7から15
        # self.axp192.setScreenBrightness(7) # <- 0x28じゃなくて0x91が正しい https://github.com/sipeed/MaixPy/pull/153

        # バッテリ充電ON/OFF https://twitter.com/michan06/status/1168104180445106180
        reg0x33 = self.axp192.__readReg(0x33)
        reg0x33 |= (1<<7) # ON
        #reg0x33 &= ~(1<<7) # OFF
        self.axp192.__writeReg(0x33, reg0x33)



        # REG 33H：充電制御1
        # デフォルト：C8H
        #
        # bit7    充電機能により、内部および外部チャネルを含む制御ビットが可能 0：オフ、1：オン
        # bit6:5  充電目標電圧設定
        #           00：4.1V;
        #           01：4.15V;
        #           10：4.2V;
        #           11：4.36V
        # bit4    充電終了電流設定
        #           0：充電電流が設定値の10％未満になったら充電を終了
        #           1：充電電流が設定値の15％未満になったら充電を終了します
        # bit3-0  内部パス充電電流設定 default=1000(780mA)
        #           0000： 100 mA;  0001： 190 mA;  0010： 280 mA;  0011： 360 mA;
        #           0100： 450 mA;  0101： 550 mA;  0110： 630 mA;  0111： 700 mA;
        #           1000： 780 mA;  1001： 880 mA;  1010： 960 mA;  1011：1000 mA;
        #           1100：1080 mA;  1101：1160 mA;  1110：1240 mA;  1111：1320 mA;

        # 0xC0(0b11000000) なら「充電オン、充電目標電圧=4.2V、充電終了電流=10%、充電電流=100mA」
        reg0x33 = self.axp192.__readReg(0x33)
        reg0x33 = (reg0x33 & 0xF0) | 0x01 # 200mA
        self.axp192.__writeReg(0x33, reg0x33)

        # REG 34H：充電制御2
        # デフォルト：41H
        #  7    プリチャージタイムアウト設定Bit1
        #         00：30分; 01：40分;
        #         10：50分; 11：60分
        #  6    プリチャージタイムアウト設定Bit0
        #  5-3  外部パス充電電流設定範囲300-1000mA、100mA /ステップ、デフォルト300mA
        #  2    充電中の外部パスイネーブル設定0：オフ; 1：オープン
        #  1    定電流モードでのタイムアウト設定Bit1   00：7時間; 01：8時間;  10：9時間;   11：10時間RW0
        #  0    定電流モードでのタイムアウト設定Bit0


        # REG 01H：電源装置の動作モードと充電状態の表示
        # 0x70なら「温度超過なし、充電中、バッテリーあり、バッテリーアクティベーションモードに入っていない、実際の充電電流は予想電流と等しい、モードA」
        #
        # bit7    AXP192が過熱しているかどうかを示します    0：温度超過なし; 1：温度超過
        # bit6    充電表示    0：充電していない、または充電が完了している、   1：充電中
        # bit5    バッテリーの存在表示   0：バッテリーはAXP192に接続されていません;    1：バッテリーはAXP192に接続されていま
        # bit4    予約済み、変更不可
        # bit3    バッテリーがアクティブモードかどうかを示します   0：バッテリーアクティベーションモードに入っていない;    1：バッテリーアクティベーションモードに入っている
        # bit2    充電電流が目的の電流よりも小さいかどうかを示します   0：実際の充電電流は予想電流と等しい;    1：実際の充電電流は予想電流よりも小さい
        # bit1    AXP192スイッチモード表示   0：モードA; 1：モードB
        # bit0    予約済み、変更不可

        # self.axp192.setK210Vcore(0.8)

    def loop(self):
        self.printRegs()

        self.counter += 1
        print("counter=%04d vbat=%6.1fmV USB=%6.1fmV,%5.1fmA EX=%6.1fmV,%5.1fmA Bat=+%5.1fmA,-%5.1fmA,%5.1fmW %4.1fC" % (
            self.counter,
            self.axp192.getVbatVoltage(),
            self.axp192.getUSBVoltage(),
            self.axp192.getUSBInputCurrent(),
            self.axp192.getConnextVoltage(),
            self.axp192.getConnextInputCurrent(),
            self.axp192.getBatteryChargeCurrent(),
            self.axp192.getBatteryDischargeCurrent(),
            self.axp192.getBatteryInstantWatts(),
            self.axp192.getTemperature()
        ))

        lcd.clear(lcd.BLACK)
        lcd.draw_string(2,  5, "hello maixpy %d" % (self.counter), lcd.WHITE, lcd.RED)
        lcd.draw_string(2, 20, "vbat=%.1fmV" % (self.axp192.getVbatVoltage()), lcd.WHITE, lcd.BLUE)
        lcd.draw_string(2, 35, "USB=%.1fmV,%.1fmA" % (self.axp192.getUSBVoltage(), self.axp192.getUSBInputCurrent()), lcd.GREEN, lcd.BLACK)
        lcd.draw_string(2, 50, "EX=%.1fmV,%.1fmA" % (self.axp192.getConnextVoltage(), self.axp192.getConnextInputCurrent()), lcd.WHITE, lcd.BLACK)
        lcd.draw_string(2, 65, "Bat=+%.1fmA,-%.1fmA,%.1fmW" % (
            self.axp192.getBatteryChargeCurrent(),
            self.axp192.getBatteryDischargeCurrent(),
            self.axp192.getBatteryInstantWatts()),
            lcd.BLACK, lcd.YELLOW)
        lcd.draw_string(2, 80, "%.1fC" % (self.axp192.getTemperature()), lcd.RED, lcd.WHITE)
        time.sleep(5)

        if self.counter % 5 == 0 and self.axp192.getBatteryChargeCurrent() < 15.0:
            self.resetCharge()

        # VBatの計算あってる？
        #reg0x78 = self.axp192.__readReg(0x78)
        #reg0x79 = self.axp192.__readReg(0x79)
        #print("reg0x78=%02X reg0x79=%02X" % (reg0x78, reg0x79))
        #vbat = (reg0x78 << 4) + reg0x79
        #print(vbat, vbat*1.1)

    def printRegs(self):
        s = ""
        for addr in [0x28, 0x12, 0x91, 0x33, 0x34, 0x01]:
          value = self.axp192.__readReg(addr)
          s += 'REG{:02X}H=0x{:02X} ({:08b}) '.format(addr, value, value)
        print(s)

    def resetCharge(self):
        print("*** resetCharge ***")
        reg0x33 = self.axp192.__readReg(0x33)
        reg0x33 = (reg0x33 & 0xF0) | 0x01 # 200mA
        reg0x33 &= ~(1<<7) # OFF
        self.axp192.__writeReg(0x33, reg0x33)

        reg0x33 = self.axp192.__readReg(0x33)
        print("reg0x33=%02X" % (reg0x33))

        time.sleep(1)

        reg0x33 = self.axp192.__readReg(0x33)
        reg0x33 |= (1<<7) # ON
        self.axp192.__writeReg(0x33, reg0x33)

        reg0x33 = self.axp192.__readReg(0x33)
        print("reg0x33=%02X" % (reg0x33))

App().main()
