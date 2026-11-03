/*
  dual_rfid: MỘT Arduino đọc HAI module RFID RC522 (cổng VÀO + cổng RA), gửi lên máy tính qua Serial.

  Giao thức (9600 baud, mỗi dòng kết thúc bằng \n) — phải khớp hardware/rfid.py bên Python:
    IN:AB1992CA          thẻ quẹt ở đầu đọc CỔNG VÀO (UID dạng HEX viết hoa, không dấu cách)
    OUT:DB2B11CA         thẻ quẹt ở đầu đọc CỔNG RA
    STATUS:IN=1,OUT=0    tình trạng từng đầu đọc (1 = nói chuyện được với module, 0 = không), gửi lúc
                         khởi động và mỗi 2 giây. Chương trình Python dùng dòng này để báo "đầu đọc nào mất
                         kết nối" và coi Arduino là "không phản hồi" nếu quá RFID_HEARTBEAT_TIMEOUT giây
                         không nhận được dòng nào.
    # ...                dòng chú thích, Python bỏ qua

  Đấu dây (Arduino Uno/Nano; đổi chân trong 3 hằng số bên dưới nếu cần):
    Dùng chung cho cả hai module:  SCK -> D13,  MOSI -> D11,  MISO -> D12,  RST -> D9,  3.3V,  GND
    Chân SDA (SS) riêng từng module:  CỔNG VÀO -> D10,  CỔNG RA -> D8
    LƯU Ý: RC522 chạy 3.3V (không cấp 5V).

  Thư viện: "MFRC522" của GithubCommunity (cài trong Arduino IDE: Tools > Manage Libraries).
*/
#include <SPI.h>
#include <MFRC522.h>

const unsigned long BAUD_RATE = 9600;          // phải trùng RFID_BAUD trong .env
const uint8_t PIN_RST = 9;
const uint8_t PIN_SS_IN = 10;
const uint8_t PIN_SS_OUT = 8;
const unsigned long STATUS_INTERVAL_MS = 2000;

MFRC522 readerIn(PIN_SS_IN, PIN_RST);
MFRC522 readerOut(PIN_SS_OUT, PIN_RST);

bool inOk = false;
bool outOk = false;
unsigned long lastStatus = 0;

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

void setup() {
  Serial.begin(BAUD_RATE);
  SPI.begin();
  readerIn.PCD_Init();
  readerOut.PCD_Init();
  Serial.println(F("# dual_rfid san sang"));
  sendStatus();
  lastStatus = millis();
}

void loop() {
  pollReader(readerIn, inOk, F("IN"));
  pollReader(readerOut, outOk, F("OUT"));

  if (millis() - lastStatus >= STATUS_INTERVAL_MS) {
    lastStatus = millis();
    sendStatus();
  }
}
