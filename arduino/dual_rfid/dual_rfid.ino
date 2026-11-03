/*
  dual_rfid: MỘT Arduino đọc HAI module RFID RC522 (cổng VÀO + cổng RA), gửi lên máy tính qua Serial.
  Ngoài ra điều khiển HAI màn LCD 1602 I2C (một ở cổng vào, một ở cổng ra) theo lệnh từ máy tính.

  Giao thức (9600 baud, mỗi dòng kết thúc bằng \n) — phải khớp hardware/rfid.py bên Python:
    Arduino -> máy tính:
      IN:AB1992CA          thẻ quẹt ở đầu đọc CỔNG VÀO (UID dạng HEX viết hoa, không dấu cách)
      OUT:DB2B11CA         thẻ quẹt ở đầu đọc CỔNG RA
      STATUS:IN=1,OUT=0    tình trạng từng đầu đọc (1 = nói chuyện được với module, 0 = không), gửi lúc
                           khởi động và mỗi 2 giây. Chương trình Python dùng dòng này để báo "đầu đọc nào mất
                           kết nối" và coi Arduino là "không phản hồi" nếu quá RFID_HEARTBEAT_TIMEOUT giây
                           không nhận được dòng nào.
      # ...                dòng chú thích, Python bỏ qua
    Máy tính -> Arduino:
      LCDIN:dòng 1|dòng 2   hiển thị lên LCD CỔNG VÀO
      LCDOUT:dòng 1|dòng 2  hiển thị lên LCD CỔNG RA
      LCD:dòng 1|dòng 2     lệnh cũ, coi như LCDIN (giữ lại cho tương thích)
                            Mỗi dòng tối đa 16 ký tự ASCII không dấu; dòng 2 có thể bỏ trống.
                            VD  LCDOUT:XE RA OK|TIEN 5.000 D
                            LCD tương ứng không có thì bỏ qua lệnh đó (LCD còn lại vẫn chạy).

  Đấu dây RFID (Arduino Uno/Nano; đổi chân trong 3 hằng số bên dưới nếu cần):
    Dùng chung cho cả hai module:  SCK -> D13,  MOSI -> D11,  MISO -> D12,  RST -> D9,  3.3V,  GND
    Chân SDA (SS) riêng từng module:  CỔNG VÀO -> D10,  CỔNG RA -> D8
    LƯU Ý: RC522 chạy 3.3V (không cấp 5V).

  Đấu dây HAI LCD 1602 có module I2C (4 dây, cắm SONG SONG vào cùng 4 chân; không trùng chân nào của RFID):
    GND -> GND,  VCC -> 5V (LCD cần 5V, KHÔNG nối vào ray 3.3V của RC522),  SDA -> A4,  SCL -> A5
  Hai module I2C phải có ĐỊA CHỈ KHÁC NHAU (mặc định cả hai đều 0x27 hoặc 0x3F nên sẽ xung đột):
    hàn nối chân A0 trên mặt sau module của LCD cổng ra để đổi địa chỉ. Sketch tự dò:
      LCD cổng VÀO:  0x27 (chip PCF8574)  hoặc 0x3F (chip PCF8574A)   <- giữ nguyên, không hàn
      LCD cổng RA :  0x26 (chip PCF8574)  hoặc 0x3E (chip PCF8574A)   <- hàn nối A0

  Thư viện (Arduino IDE: Tools > Manage Libraries):
    - "MFRC522" của GithubCommunity
    - "LiquidCrystal I2C" của Frank de Brabander
*/
#include <SPI.h>
#include <MFRC522.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

const unsigned long BAUD_RATE = 9600;          // phải trùng RFID_BAUD trong .env
const uint8_t PIN_RST = 9;
const uint8_t PIN_SS_IN = 10;
const uint8_t PIN_SS_OUT = 8;
const unsigned long STATUS_INTERVAL_MS = 2000;

const uint8_t LCD_COLS = 16;
const uint8_t LCD_ROWS = 2;
// Địa chỉ I2C có thể có của từng LCD (dò lần lượt, gặp địa chỉ nào trả lời thì dùng).
const uint8_t LCD_IN_ADDRS[] = {0x27, 0x3F};
const uint8_t LCD_OUT_ADDRS[] = {0x26, 0x3E};
const uint8_t RX_MAX = 48;                     // "LCDOUT:" + 16 + "|" + 16 = 40 ký tự, chừa dư

MFRC522 readerIn(PIN_SS_IN, PIN_RST);
MFRC522 readerOut(PIN_SS_OUT, PIN_RST);
LiquidCrystal_I2C *lcdIn = nullptr;            // nullptr = không tìm thấy LCD cổng vào
LiquidCrystal_I2C *lcdOut = nullptr;           // nullptr = không tìm thấy LCD cổng ra

bool inOk = false;
bool outOk = false;
unsigned long lastStatus = 0;

char rxBuf[RX_MAX + 1];                        // dòng lệnh đang nhận từ máy tính
uint8_t rxLen = 0;
bool rxOverflow = false;                       // dòng quá dài: bỏ cả dòng

// ------------------------------------------------------------------ RFID
// Module có đang nói chuyện được không? Đọc thanh ghi phiên bản: 0x00 hoặc 0xFF = không có tín hiệu.
bool checkReader(MFRC522 &reader, bool &wasOk) {
  byte version = reader.PCD_ReadRegister(MFRC522::VersionReg);
  bool ok = (version != 0x00 && version != 0xFF);
  if (ok && !wasOk) {
    reader.PCD_Init();                         // vừa cắm lại dây: khởi tạo lại module
  }
  wasOk = ok;
  return ok;
}

void sendStatus() {
  bool a = checkReader(readerIn, inOk);
  bool b = checkReader(readerOut, outOk);
  Serial.print(F("STATUS:IN="));
  Serial.print(a ? 1 : 0);
  Serial.print(F(",OUT="));
  Serial.println(b ? 1 : 0);
}

void pollReader(MFRC522 &reader, bool ok, const __FlashStringHelper *tag) {
  if (!ok) return;
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) return;

  Serial.print(tag);
  Serial.print(':');
  for (byte i = 0; i < reader.uid.size; i++) {
    if (reader.uid.uidByte[i] < 0x10) Serial.print('0');
    Serial.print(reader.uid.uidByte[i], HEX);
  }
  Serial.println();

  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
}

// ------------------------------------------------------------------ LCD
bool i2cResponds(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// Ghi đè đúng một hàng: ký tự ngoài ASCII in được thành '?', thiếu thì đệm dấu cách (khỏi phải clear() gây nháy).
void lcdPrintRow(LiquidCrystal_I2C *lcd, uint8_t row, const char *text) {
  lcd->setCursor(0, row);
  uint8_t col = 0;
  for (; col < LCD_COLS && text[col] != '\0'; col++) {
    char c = text[col];
    lcd->print((c >= 0x20 && c <= 0x7E) ? c : '?');
  }
  for (; col < LCD_COLS; col++) {
    lcd->print(' ');
  }
}

// lcd == nullptr (không có màn này) thì bỏ qua, màn kia không bị ảnh hưởng.
void lcdShow(LiquidCrystal_I2C *lcd, const char *line1, const char *line2) {
  if (lcd == nullptr) return;
  lcdPrintRow(lcd, 0, line1);
  lcdPrintRow(lcd, 1, line2);
}

// Dò một LCD trong danh sách địa chỉ có thể có. Trả về nullptr nếu không địa chỉ nào trả lời.
LiquidCrystal_I2C *findLcd(const uint8_t *addrs, uint8_t count, const __FlashStringHelper *name,
                           const char *idleLine1) {
  uint8_t addr = 0;
  for (uint8_t i = 0; i < count && addr == 0; i++) {
    if (i2cResponds(addrs[i])) addr = addrs[i];
  }
  if (addr == 0) {
    Serial.print(F("# LCD "));
    Serial.print(name);
    Serial.println(F(": khong tim thay (kiem tra day GND, VCC=5V, SDA=A4, SCL=A5 va dia chi I2C)"));
    return nullptr;
  }
  LiquidCrystal_I2C *lcd = new LiquidCrystal_I2C(addr, LCD_COLS, LCD_ROWS);
  lcd->init();
  lcd->backlight();
  lcdShow(lcd, idleLine1, "MOI QUET THE");
  Serial.print(F("# LCD "));
  Serial.print(name);
  Serial.print(F(": dia chi 0x"));
  Serial.println(addr, HEX);
  return lcd;
}

void initLcds() {
  Wire.begin();
  lcdIn = findLcd(LCD_IN_ADDRS, sizeof(LCD_IN_ADDRS), F("VAO"), "CONG VAO");
  lcdOut = findLcd(LCD_OUT_ADDRS, sizeof(LCD_OUT_ADDRS), F("RA"), "CONG RA");
}

// Nếu `cmd` bắt đầu bằng `prefix` thì trả về con trỏ tới phần sau tiền tố, ngược lại nullptr.
char *afterPrefix(char *cmd, const char *prefix) {
  size_t n = strlen(prefix);
  return strncmp(cmd, prefix, n) == 0 ? cmd + n : nullptr;
}

// Một dòng lệnh đã nhận đủ (kết thúc bằng \n). Hiểu LCDIN:, LCDOUT: và LCD: (cũ = LCDIN); lệnh khác bỏ qua.
void handleCommand(char *cmd) {
  LiquidCrystal_I2C *target = nullptr;
  char *line1 = afterPrefix(cmd, "LCDOUT:");
  if (line1 != nullptr) {
    target = lcdOut;
  } else if ((line1 = afterPrefix(cmd, "LCDIN:")) != nullptr || (line1 = afterPrefix(cmd, "LCD:")) != nullptr) {
    target = lcdIn;
  } else {
    return;
  }
  char *sep = strchr(line1, '|');
  const char *line2 = "";
  if (sep != nullptr) {
    *sep = '\0';
    line2 = sep + 1;
  }
  lcdShow(target, line1, line2);
}

// Đọc không chặn: gom từng ký tự đến khi gặp \n. Không dùng delay nên việc quét thẻ không bị chậm.
void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (!rxOverflow) {
        rxBuf[rxLen] = '\0';
        handleCommand(rxBuf);
      }
      rxLen = 0;
      rxOverflow = false;
    } else if (rxLen < RX_MAX) {
      rxBuf[rxLen++] = c;
    } else {
      rxOverflow = true;
    }
  }
}

// ------------------------------------------------------------------ chính
void setup() {
  Serial.begin(BAUD_RATE);
  SPI.begin();
  readerIn.PCD_Init();
  readerOut.PCD_Init();
  initLcds();
  Serial.println(F("# dual_rfid san sang"));
  sendStatus();
  lastStatus = millis();
}

void loop() {
  readSerialCommands();
  pollReader(readerIn, inOk, F("IN"));
  pollReader(readerOut, outOk, F("OUT"));

  if (millis() - lastStatus >= STATUS_INTERVAL_MS) {
    lastStatus = millis();
    sendStatus();
  }
}
