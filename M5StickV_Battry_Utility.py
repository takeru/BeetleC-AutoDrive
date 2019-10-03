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
        self._axp192 = pmu.axp192()

        self._axp192.enableADCs(True)
        self._axp192.enableCoulombCounter(False)

        self.printRegs()

        # LCDの明るさ
        self._axp192.__writeReg(0x91, 0xA0) # 上位4bit 7から15
        # self._axp192.setScreenBrightness(7) # <- 0x28じゃなくて0x91が正しい https://github.com/sipeed/MaixPy/pull/153

        # バッテリ充電ON/OFF https://twitter.com/michan06/status/1168104180445106180
        reg0x33 = self._axp192.__readReg(0x33)
        reg0x33 |= (1<<7) # ON
        #reg0x33 &= ~(1<<7) # OFF
        self._axp192.__writeReg(0x33, reg0x33)


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
        reg0x33 = self._axp192.__readReg(0x33)
        reg0x33 = (reg0x33 & 0xF0) | 0x01 # 190mA
        self._axp192.__writeReg(0x33, reg0x33)

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

        self._axp192.setK210Vcore(0.8)

    def loop(self):
        self.printRegs()

        self.counter += 1
        s = "counter=%d v_vbat=%.1f v_temp=%.1f v_ichg=%.1f v_idcg=%.1f v_vusb=%.1f v_iusb=%.1f v_vaps=%.1f v_vex=%.1f v_iex=%.1f v_wbat=%.1f v_warn=%d" % (
            self.counter,
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
        )
        print(s)

        lcd.clear(lcd.BLACK)
        lcd.draw_string(2,  5, "M5StickV Battry Utility %d" % (self.counter), lcd.CYAN, lcd.BLACK)

        temp = self._axp192.getTemperature()
        if 40.0 < temp:
            colors = (lcd.YELLOW, lcd.RED, "Hot!!")
        else:
            colors = (lcd.WHITE, lcd.BLACK, "")
        lcd.draw_string(20, 27, "Temp: %.1fC %s" % (temp, colors[2]), colors[0], colors[1])

        vbat = self._axp192.getVbatVoltage()
        if vbat < 3700:
            colors = (lcd.WHITE, lcd.RED, "[*____] LOW")
        elif vbat < 3800:
            colors = (lcd.RED, lcd.BLACK, "[**___]")
        elif vbat < 3900:
            colors = (lcd.ORANGE, lcd.BLACK, "[***__]")
        elif vbat < 4000:
            colors = (lcd.YELLOW, lcd.BLACK, "[****_]")
        else:
            colors = (lcd.GREEN, lcd.BLACK, "[*****] FULL")
        lcd.draw_string(20, 45, "VBat: %.1fmV %s" % (vbat, colors[2]), colors[0], colors[1])

        ichg = self._axp192.getBatteryChargeCurrent()
        if ichg < 1:
            colors = (lcd.DARKGREY, lcd.BLACK, "[___]")
        elif ichg < 15:
            colors = (lcd.YELLOW, lcd.BLACK, "[>__]")
        elif ichg < 100:
            colors = (lcd.ORANGE, lcd.BLACK, "[>>_]")
        else:
            colors = (lcd.ORANGE, lcd.BLUE, "[>>>]")
        lcd.draw_string(20, 63, "IChg: %.1fmA %s" % (ichg, colors[2]), colors[0], colors[1])



        lcd.draw_string(20, 100, "IDcg: %.1fmA" % (self._axp192.getBatteryDischargeCurrent()), lcd.WHITE, lcd.BLACK)
        lcd.draw_string(20, 115, "USB : %.1fmV, %.1fmA" % (self._axp192.getUSBVoltage(), self._axp192.getUSBInputCurrent()), lcd.WHITE, lcd.BLACK)

        #lcd.draw_string(2, 50, "EX=%.1fmV,%.1fmA" % (self._axp192.getConnextVoltage(), self._axp192.getConnextInputCurrent()), lcd.WHITE, lcd.BLACK)
        time.sleep(5)

        if self.counter % 5 == 0 and self._axp192.getBatteryChargeCurrent() < 15.0:
            self.resetCharge()

        print("")

    def printRegs(self):
        s = "Reg: "
        for addr in [0x28, 0x12, 0x91, 0x33, 0x34, 0x00, 0x01]:
          value = self._axp192.__readReg(addr)
          s += '{:02X}H={:02X}({:08b}) '.format(addr, value, value)
        print(s)

    def resetCharge(self):
        print("*** resetCharge ***")
        reg0x33 = self._axp192.__readReg(0x33)
        reg0x33 = (reg0x33 & 0xF0) | 0x01 # 200mA
        reg0x33 &= ~(1<<7) # OFF
        self._axp192.__writeReg(0x33, reg0x33)

        reg0x33 = self._axp192.__readReg(0x33)
        #print("reg0x33=%02X" % (reg0x33))

        time.sleep(1)

        reg0x33 = self._axp192.__readReg(0x33)
        reg0x33 |= (1<<7) # ON
        self._axp192.__writeReg(0x33, reg0x33)

        reg0x33 = self._axp192.__readReg(0x33)
        #print("reg0x33=%02X" % (reg0x33))

    def _axp192_getApsVoltage(self):
        lsb = self._axp192.__readReg(0x7E)
        msb = self._axp192.__readReg(0x7F)
        return ((lsb << 4) + msb) * 1.4

    def _axp192_getWarningLeve(self):
        v = self._axp192.__readReg(0x47)
        return v & 0x01

App().main()
