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
      PASS:IN              xe đã đi qua hẳn thanh chắn CỔNG VÀO (PASS:OUT cho cổng ra); thanh chắn đã được hạ ngay
      NOPASS:IN            hết giờ mở mà xe CHƯA đi qua (NOPASS:OUT cho cổng ra); thanh chắn đã được hạ
      # ...                dòng chú thích, Python bỏ qua
    Máy tính -> Arduino:
      LCDIN:dòng 1|dòng 2   hiển thị lên LCD CỔNG VÀO
      LCDOUT:dòng 1|dòng 2  hiển thị lên LCD CỔNG RA
      LCD:dòng 1|dòng 2     lệnh cũ, coi như LCDIN (giữ lại cho tương thích)
                            Mỗi dòng tối đa 16 ký tự ASCII không dấu; dòng 2 có thể bỏ trống.
                            VD  LCDOUT:XE RA OK|TIEN 5.000 D
                            LCD tương ứng không có thì bỏ qua lệnh đó (LCD còn lại vẫn chạy).
      SERVOIN:OPEN          mở servo (thanh chắn) CỔNG VÀO, giữ SERVO_HOLD_MS mặc định rồi TỰ đóng lại
      SERVOIN:OPEN:3000     như trên nhưng giữ 3000 ms (giới hạn SERVO_HOLD_MIN_MS..SERVO_HOLD_MAX_MS)
      SERVOOUT:OPEN[:ms]    như trên cho servo CỔNG RA
      SERVOIN:CLOSE         đóng ngay (SERVOOUT:CLOSE cho cổng ra)
      SERVOIN:ANGLE:0:90    đặt GÓC ĐÓNG (vị trí ban đầu) và GÓC MỞ của servo CỔNG VÀO, 0..180 độ (SERVOOUT:ANGLE:... cho
                            cổng ra). Servo chạy tới góc mới ngay. Máy tính gửi lệnh này mỗi khi Arduino khởi động; chưa nhận
                            được thì servo dùng SERVO_CLOSED_ANGLE / SERVO_OPEN_ANGLE bên dưới.
                            Arduino tự đóng bằng đồng hồ của chính nó nên máy tính treo cũng không kẹt thanh chắn mở.

  Đấu dây RFID (Arduino Uno/Nano; đổi chân trong 3 hằng số bên dưới nếu cần):
    Dùng chung cho cả hai module:  SCK -> D13,  MOSI -> D11,  MISO -> D12,  RST -> D9,  3.3V,  GND
    Chân SDA (SS) riêng từng module:  CỔNG VÀO -> D10,  CỔNG RA -> D8
    LƯU Ý: RC522 chạy 3.3V (không cấp 5V).

  Đấu dây HAI LCD 1602 có module I2C (PCF8574). MỖI LCD một bus I2C RIÊNG, dùng I2C PHẦN MỀM (bit-bang)
  nên cắm vào chân analog bất kỳ, không cần thư viện Wire / LiquidCrystal_I2C:
    LCD CỔNG VÀO :  SDA -> A0,  SCL -> A1,  VCC -> 5V,  GND -> GND
    LCD CỔNG RA  :  SDA -> A2,  SCL -> A3,  VCC -> 5V,  GND -> GND
  (LCD cần 5V, KHÔNG nối vào ray 3.3V của RC522.) Vì hai LCD ở hai bus khác nhau nên được TRÙNG địa chỉ
  (không cần hàn chân A0 trên module). Sketch tự dò địa chỉ 0x27 (chip PCF8574) hoặc 0x3F (PCF8574A).
  Muốn đổi chân: sửa 4 hằng số PIN_LCD_* bên dưới.

  Đấu dây HAI SERVO thanh chắn (SG90 / MG90S...): dây tín hiệu (cam/vàng) vào chân số, đỏ vào 5V, nâu/đen vào GND:
    SERVO CỔNG VÀO :  tín hiệu -> D6
    SERVO CỔNG RA  :  tín hiệu -> D7
  LƯU Ý NGUỒN: servo giật dòng lớn khi chạy (có thể > 500 mA mỗi con) nên NÊN cấp 5V riêng (pin/adapter 5V 2A)
  cho hai servo và NỐI CHUNG GND với Arduino; cấp thẳng từ chân 5V của Arduino qua cổng USB dễ làm Arduino reset,
  LCD nháy hoặc RC522 mất tín hiệu. Chân D6/D7 không trùng SPI (D8..D13), LCD (A0..A3), cảm biến (D2..D5), còi (A5) hay Serial (D0/D1).
  Góc mở/đóng chỉnh ở SERVO_*_ANGLE bên dưới cho khớp thanh chắn thật.

  Đấu dây CÒI BÍP (MỘT còi dùng chung cho cả hai cổng): chân (+) -> A5,  chân (-) -> GND.
  Mỗi lần quẹt thẻ ở BẤT KỲ cổng nào còi kêu một tiếng bíp ngắn (do Arduino tự làm ngay khi đọc được thẻ,
  không chờ máy tính). Dùng tone() nên chạy được cả còi active lẫn passive; còi nhỏ (< 20 mA) nối thẳng
  chân A5, còi công suất lớn thì qua transistor. Muốn đổi chân / tần số / độ dài: sửa PIN_BUZZER,
  BUZZER_FREQ_HZ, BUZZER_BEEP_MS bên dưới.

  Đấu dây BỐN CẢM BIẾN HỒNG NGOẠI (mỗi cổng hai cái: một ở TRƯỚC, một ở SAU thanh chắn), dùng để biết xe đã
  đi qua hẳn thanh chắn chưa. Mỗi cảm biến: VCC -> 5V, GND -> GND, ngõ ra (OUT) -> chân số:
    CỔNG VÀO :  trước -> D2,  sau -> D3
    CỔNG RA  :  trước -> D4,  sau -> D5
  Mặc định ngõ ra xuống LOW khi có vật chắn (đa số module E18-D80NK / FC-51); loại ngược lại thì đặt
  IR_ACTIVE_LOW = false. Chân dùng INPUT_PULLUP nên ngõ ra open-collector cũng chạy được.
  Cách hoạt động (sau khi thanh chắn MỞ): xe chắn cảm biến trước, rồi chắn cảm biến sau, rồi rời khỏi cả hai
  -> "đã qua": thanh chắn HẠ NGAY và Arduino gửi PASS:<cổng>. Xe lùi ra (cảm biến sau nhả khi cảm biến trước
  còn bị chắn) thì không tính là đã qua. Hết giờ giữ mở mà chưa qua thì hạ thanh chắn và gửi NOPASS:<cổng>,
  NHƯNG nếu lúc đó còn có vật chắn cảm biến (xe đang ở dưới thanh chắn) thì chờ thêm tối đa IR_EXTEND_MAX_MS
  rồi mới hạ, để thanh chắn không đóng xuống xe.

  Thư viện (Arduino IDE: Tools > Manage Libraries):
    - "MFRC522" của GithubCommunity
    - "Servo" (có sẵn trong Arduino IDE, không cần cài thêm)
*/
#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>

const unsigned long BAUD_RATE = 9600;          // phải trùng RFID_BAUD trong .env
const uint8_t PIN_RST = 9;
const uint8_t PIN_SS_IN = 10;
const uint8_t PIN_SS_OUT = 8;
const unsigned long STATUS_INTERVAL_MS = 2000;

const uint8_t LCD_COLS = 16;
const uint8_t LCD_ROWS = 2;
// Chân I2C phần mềm của từng LCD (mỗi LCD một bus riêng nên được trùng địa chỉ).
const uint8_t PIN_LCD_IN_SDA = A0;
const uint8_t PIN_LCD_IN_SCL = A1;
const uint8_t PIN_LCD_OUT_SDA = A2;
const uint8_t PIN_LCD_OUT_SCL = A3;
// Địa chỉ I2C có thể có của module (dò lần lượt, gặp địa chỉ nào trả lời thì dùng).
const uint8_t LCD_ADDRS[] = {0x27, 0x3F};
// Servo thanh chắn: mỗi cổng một servo. Góc 0..180 độ; chỉnh cho khớp cơ cấu thật (đảo hai góc nếu quay ngược).
const uint8_t PIN_SERVO_IN = 6;
const uint8_t PIN_SERVO_OUT = 7;
const uint8_t SERVO_CLOSED_ANGLE = 0;          // thanh chắn hạ (đóng) = vị trí ban đầu; máy tính ghi đè bằng SERVO_CLOSED_ANGLE trong .env
const uint8_t SERVO_OPEN_ANGLE = 90;           // thanh chắn nâng (mở); máy tính ghi đè bằng SERVO_OPEN_ANGLE trong .env
const unsigned long SERVO_HOLD_MS = 3000;      // giữ mở mặc định khi lệnh không nêu thời gian
const unsigned long SERVO_HOLD_MIN_MS = 500;   // chặn lệnh sai: tối thiểu / tối đa
const unsigned long SERVO_HOLD_MAX_MS = 30000;
// Cảm biến hồng ngoại: mỗi cổng hai cái, "trước" = phía xe đi tới, "sau" = phía bên kia thanh chắn.
const uint8_t PIN_IR_IN_BEFORE = 2;
const uint8_t PIN_IR_IN_AFTER = 3;
const uint8_t PIN_IR_OUT_BEFORE = 4;
const uint8_t PIN_IR_OUT_AFTER = 5;
const bool IR_ACTIVE_LOW = true;               // true: ngõ ra LOW khi có vật chắn; false: HIGH khi có vật chắn
const unsigned long IR_DEBOUNCE_MS = 30;       // tín hiệu phải ổn định ngần này ms mới được tin (chống nhiễu)
const unsigned long IR_EXTEND_MAX_MS = 10000;  // hết giờ mà còn vật chắn cảm biến: chờ thêm tối đa ngần này ms
// Còi bíp: một còi chung, kêu mỗi lần quẹt thẻ (cổng vào hoặc cổng ra).
const uint8_t PIN_BUZZER = A5;
const unsigned int BUZZER_FREQ_HZ = 2000;      // passive: đây là cao độ; active: vẫn kêu bình thường
const unsigned int BUZZER_BEEP_MS = 120;       // độ dài một tiếng bíp
const uint8_t RX_MAX = 48;                     // "LCDOUT:" + 16 + "|" + 16 = 40 ký tự, chừa dư

MFRC522 readerIn(PIN_SS_IN, PIN_RST);
MFRC522 readerOut(PIN_SS_OUT, PIN_RST);

// ------------------------------------------------------------------ LCD 1602 + PCF8574 qua I2C phần mềm
// Mỗi đối tượng điều khiển MỘT LCD trên cặp chân SDA/SCL riêng. SDA mô phỏng open-drain (thả = INPUT,
// kéo thấp = OUTPUT LOW; module I2C đã có điện trở kéo lên); SCL đẩy kéo vì PCF8574 không kéo giãn xung.
// Ánh xạ chân PCF8574 chuẩn: P0=RS, P1=RW, P2=EN, P3=đèn nền, P4..P7=D4..D7.
class SoftLcd {
 public:
  SoftLcd(uint8_t sda, uint8_t scl) : sda_(sda), scl_(scl) {}

  // Dò địa chỉ, khởi tạo LCD. Trả về false nếu không địa chỉ nào trả lời.
  bool begin(const uint8_t *addrs, uint8_t count) {
    digitalWrite(sda_, LOW);                   // PORT = 0: chỉ đổi INPUT/OUTPUT là có HIGH-Z / LOW
    pinMode(scl_, OUTPUT);
    sclLow();
    sdaRelease();
    addr_ = 0;
    for (uint8_t i = 0; i < count && addr_ == 0; i++) {
      if (probe(addrs[i])) addr_ = addrs[i];
    }
    if (addr_ == 0) return false;
    initLcd();
    return true;
  }

  uint8_t address() const { return addr_; }

  void setCursor(uint8_t col, uint8_t row) {
    send(0x80 | (uint8_t)(col + (row ? 0x40 : 0x00)), 0);
  }

  void print(char c) { send((uint8_t)c, RS); }

 private:
  static const uint8_t RS = 0x01, EN = 0x04, BL = 0x08;
  uint8_t sda_, scl_, addr_ = 0;

  void bitDelay() { delayMicroseconds(4); }   // ~100 kHz
  void sdaRelease() { pinMode(sda_, INPUT); }
  void sdaLow() { pinMode(sda_, OUTPUT); }    // PORT đã = 0
  void sclHigh() { digitalWrite(scl_, HIGH); }
  void sclLow() { digitalWrite(scl_, LOW); }

  void i2cStart() { sdaRelease(); sclHigh(); bitDelay(); sdaLow(); bitDelay(); sclLow(); }
  void i2cStop() { sdaLow(); bitDelay(); sclHigh(); bitDelay(); sdaRelease(); bitDelay(); }

  // Gửi một byte, trả về true nếu bên nhận ACK.
  bool i2cWrite(uint8_t b) {
    for (uint8_t i = 0; i < 8; i++) {
      if (b & 0x80) sdaRelease(); else sdaLow();
      bitDelay();
      sclHigh(); bitDelay(); sclLow();
      b <<= 1;
    }
    sdaRelease();
    bitDelay();
    sclHigh(); bitDelay();
    bool ack = (digitalRead(sda_) == LOW);
    sclLow();
    return ack;
  }

  bool probe(uint8_t addr) {
    i2cStart();
    bool ack = i2cWrite((uint8_t)(addr << 1));
    i2cStop();
    return ack;
  }

  void expanderWrite(uint8_t data) {
    i2cStart();
    if (i2cWrite((uint8_t)(addr_ << 1))) i2cWrite(data | BL);
    i2cStop();
  }

  void write4(uint8_t nibbleAndMode) {        // 4 bit cao = dữ liệu, 4 bit thấp = RS/RW/EN
    expanderWrite(nibbleAndMode);
    expanderWrite(nibbleAndMode | EN);
    delayMicroseconds(1);
    expanderWrite(nibbleAndMode & ~EN);
    delayMicroseconds(50);
  }

  void send(uint8_t value, uint8_t mode) {
    write4((value & 0xF0) | mode);
    write4(((value << 4) & 0xF0) | mode);
  }

  void initLcd() {                            // trình tự khởi tạo 4 bit của HD44780
    delay(50);
    expanderWrite(0);
    write4(0x30); delay(5);
    write4(0x30); delay(5);
    write4(0x30); delayMicroseconds(150);
    write4(0x20);                             // chuyển sang chế độ 4 bit
    send(0x28, 0);                            // 4 bit, 2 dòng, font 5x8
    send(0x0C, 0);                            // bật hiển thị, tắt con trỏ
    send(0x06, 0);                            // con trỏ chạy sang phải
    send(0x01, 0); delay(2);                  // xóa màn hình
  }
};

SoftLcd lcdInDev(PIN_LCD_IN_SDA, PIN_LCD_IN_SCL);
SoftLcd lcdOutDev(PIN_LCD_OUT_SDA, PIN_LCD_OUT_SCL);
SoftLcd *lcdIn = nullptr;                      // nullptr = không tìm thấy LCD cổng vào
SoftLcd *lcdOut = nullptr;                     // nullptr = không tìm thấy LCD cổng ra

bool inOk = false;
bool outOk = false;
unsigned long lastStatus = 0;

char rxBuf[RX_MAX + 1];                        // dòng lệnh đang nhận từ máy tính
uint8_t rxLen = 0;
bool rxOverflow = false;                       // dòng quá dài: bỏ cả dòng

// ------------------------------------------------------------------ Cảm biến hồng ngoại
// Một cảm biến có chống nhiễu: chỉ đổi trạng thái khi tín hiệu giữ ổn định IR_DEBOUNCE_MS.
class IrSensor {
 public:
  explicit IrSensor(uint8_t pin) : pin_(pin) {}

  void begin() {
    pinMode(pin_, IR_ACTIVE_LOW ? INPUT_PULLUP : INPUT);   // active-HIGH mà kéo lên thì lúc không cắm sẽ luôn "bị chắn"
    raw_ = stable_ = read();
    changedAt_ = millis();
  }

  void update() {                              // gọi mỗi vòng loop
    bool now = read();
    if (now != raw_) {
      raw_ = now;
      changedAt_ = millis();
    } else if (raw_ != stable_ && millis() - changedAt_ >= IR_DEBOUNCE_MS) {
      stable_ = raw_;
    }
  }

  bool blocked() const { return stable_; }

 private:
  bool read() const {
    bool high = (digitalRead(pin_) == HIGH);
    return IR_ACTIVE_LOW ? !high : high;
  }

  uint8_t pin_;
  bool raw_ = false, stable_ = false;
  unsigned long changedAt_ = 0;
};

// BEGIN PassDetector (không phụ thuộc Arduino: tests/ biên dịch riêng đoạn này để thử logic)
// Nhận biết "xe đã đi qua hẳn" từ hai cảm biến (trước / sau thanh chắn):
//   cảm biến trước bị chắn -> cảm biến sau bị chắn -> cảm biến sau nhả ra khi cảm biến trước cũng đã nhả.
// Nếu cảm biến sau nhả ra trong lúc cảm biến trước còn bị chắn thì xe đang lùi ra: bỏ lần chắn sau đó.
class PassDetector {
 public:
  void reset() { seenBefore_ = seenAfter_ = false; }

  // before / after: cảm biến tương ứng đang bị chắn. Trả về true đúng một lần khi xe đã qua hẳn.
  bool update(bool before, bool after) {
    if (!seenBefore_ && before) seenBefore_ = true;
    if (seenBefore_ && !seenAfter_ && after) seenAfter_ = true;
    if (seenAfter_ && !after) {
      if (!before) {
        reset();                               // báo đúng một lần
        return true;
      }
      seenAfter_ = false;                      // xe lùi ra
    }
    return false;
  }

 private:
  bool seenBefore_ = false, seenAfter_ = false;
};
// END PassDetector

// ------------------------------------------------------------------ Servo thanh chắn
// Một thanh chắn: mở theo lệnh rồi TỰ đóng khi hết thời gian giữ (đo bằng millis(), không chặn vòng loop nên
// việc quét thẻ và nhận lệnh LCD vẫn chạy bình thường trong lúc thanh chắn đang mở).
// Có hai cảm biến hồng ngoại: xe đã đi qua hẳn thì HẠ NGAY và báo PASS:<cổng>; hết giờ mà chưa qua thì hạ và báo
// NOPASS:<cổng> (còn vật chắn cảm biến thì chờ thêm tối đa IR_EXTEND_MAX_MS để không hạ xuống xe).
class Barrier {
 public:
  Barrier(uint8_t servoPin, uint8_t irBeforePin, uint8_t irAfterPin, const char *tag)
      : pin_(servoPin), before_(irBeforePin), after_(irAfterPin), tag_(tag) {}

  void begin() {
    servo_.attach(pin_);
    servo_.write(closedAngle_);                // khởi động luôn ở vị trí đóng (góc ban đầu)
    open_ = false;
    before_.begin();
    after_.begin();
  }

  // Mở (hoặc gia hạn nếu đang mở: quẹt thẻ liên tiếp thì thanh chắn không đóng giữa chừng).
  void open(unsigned long holdMs) {
    holdMs = constrain(holdMs, SERVO_HOLD_MIN_MS, SERVO_HOLD_MAX_MS);
    if (!open_) {
      servo_.write(openAngle_);
      detector_.reset();                       // lần mở mới: theo dõi xe từ đầu
    }
    open_ = true;
    openedAt_ = millis();
    holdMs_ = holdMs;
  }

  // Đóng theo lệnh (không báo PASS / NOPASS).
  void close() {
    if (open_) servo_.write(closedAngle_);
    open_ = false;
  }

  // Đặt góc đóng (vị trí ban đầu) / góc mở. Servo chạy tới góc tương ứng với trạng thái hiện tại ngay.
  void setAngles(uint8_t closedAngle, uint8_t openAngle) {
    closedAngle_ = closedAngle > 180 ? 180 : closedAngle;
    openAngle_ = openAngle > 180 ? 180 : openAngle;
    servo_.write(open_ ? openAngle_ : closedAngle_);
  }

  void update() {                              // gọi mỗi vòng loop
    before_.update();
    after_.update();
    if (!open_) return;

    if (detector_.update(before_.blocked(), after_.blocked())) {
      close();                                 // xe đã qua hẳn: hạ ngay
      report(F("PASS:"));
      return;
    }
    unsigned long elapsed = millis() - openedAt_;
    if (elapsed < holdMs_) return;
    bool occupied = before_.blocked() || after_.blocked();
    if (occupied && elapsed < holdMs_ + IR_EXTEND_MAX_MS) return;   // xe đang ở thanh chắn: chưa hạ
    close();
    report(F("NOPASS:"));                      // hết giờ mà chưa thấy xe qua
  }

 private:
  void report(const __FlashStringHelper *kind) {
    Serial.print(kind);
    Serial.println(tag_);
  }

  uint8_t pin_;
  Servo servo_;
  IrSensor before_, after_;
  PassDetector detector_;
  const char *tag_;                            // "IN" / "OUT" (chuỗi thường: F() không dùng được ở phạm vi toàn cục)
  bool open_ = false;
  uint8_t closedAngle_ = SERVO_CLOSED_ANGLE, openAngle_ = SERVO_OPEN_ANGLE;   // mặc định; máy tính ghi đè bằng ANGLE
  unsigned long openedAt_ = 0, holdMs_ = SERVO_HOLD_MS;
};

Barrier barrierIn(PIN_SERVO_IN, PIN_IR_IN_BEFORE, PIN_IR_IN_AFTER, "IN");
Barrier barrierOut(PIN_SERVO_OUT, PIN_IR_OUT_BEFORE, PIN_IR_OUT_AFTER, "OUT");

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

// Một tiếng bíp ngắn. tone() có thời lượng KHÔNG chặn vòng loop (tự tắt bằng ngắt timer).
void beep() {
  tone(PIN_BUZZER, BUZZER_FREQ_HZ, BUZZER_BEEP_MS);
}

void pollReader(MFRC522 &reader, bool ok, const __FlashStringHelper *tag) {
  if (!ok) return;
  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) return;

  beep();                                    // báo cho người quẹt biết thẻ đã được đọc
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
// Ghi đè đúng một hàng: ký tự ngoài ASCII in được thành '?', thiếu thì đệm dấu cách (khỏi phải clear() gây nháy).
void lcdPrintRow(SoftLcd *lcd, uint8_t row, const char *text) {
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
void lcdShow(SoftLcd *lcd, const char *line1, const char *line2) {
  if (lcd == nullptr) return;
  lcdPrintRow(lcd, 0, line1);
  lcdPrintRow(lcd, 1, line2);
}

// Dò + khởi tạo một LCD. Trả về con trỏ tới LCD, hoặc nullptr nếu không địa chỉ nào trả lời.
SoftLcd *findLcd(SoftLcd &dev, const __FlashStringHelper *name, const char *idleLine1,
                 const __FlashStringHelper *pins) {
  if (!dev.begin(LCD_ADDRS, sizeof(LCD_ADDRS))) {
    Serial.print(F("# LCD "));
    Serial.print(name);
    Serial.print(F(": khong tim thay (kiem tra day GND, VCC=5V, "));
    Serial.print(pins);
    Serial.println(F(" va dia chi I2C)"));
    return nullptr;
  }
  lcdShow(&dev, idleLine1, "MOI QUET THE");
  Serial.print(F("# LCD "));
  Serial.print(name);
  Serial.print(F(": dia chi 0x"));
  Serial.println(dev.address(), HEX);
  return &dev;
}

void initLcds() {
  lcdIn = findLcd(lcdInDev, F("VAO"), "CONG VAO", F("SDA=A0, SCL=A1"));
  lcdOut = findLcd(lcdOutDev, F("RA"), "CONG RA", F("SDA=A2, SCL=A3"));
}

// Nếu `cmd` bắt đầu bằng `prefix` thì trả về con trỏ tới phần sau tiền tố, ngược lại nullptr.
char *afterPrefix(char *cmd, const char *prefix) {
  size_t n = strlen(prefix);
  return strncmp(cmd, prefix, n) == 0 ? cmd + n : nullptr;
}

// Lệnh servo: `args` là phần sau "SERVOIN:" / "SERVOOUT:", dạng "OPEN", "OPEN:3000" hoặc "CLOSE".
void handleServo(Barrier &barrier, char *args) {
  if (strncmp(args, "OPEN", 4) == 0) {
    unsigned long holdMs = SERVO_HOLD_MS;
    if (args[4] == ':') {
      unsigned long v = strtoul(args + 5, nullptr, 10);
      if (v > 0) holdMs = v;                   // số hỏng / bằng 0 -> dùng thời gian mặc định
    }
    barrier.open(holdMs);
  } else if (strncmp(args, "CLOSE", 5) == 0) {
    barrier.close();
  } else if (strncmp(args, "ANGLE:", 6) == 0) {           // "ANGLE:<góc đóng>:<góc mở>", mỗi góc 0..180
    char *end = nullptr;
    long closedAngle = strtol(args + 6, &end, 10);
    if (end == args + 6 || *end != ':') return;           // sai định dạng: bỏ qua cả lệnh
    char *start = end + 1;
    long openAngle = strtol(start, &end, 10);
    if (end == start) return;
    if (closedAngle < 0 || closedAngle > 180 || openAngle < 0 || openAngle > 180) return;
    barrier.setAngles((uint8_t)closedAngle, (uint8_t)openAngle);
  }
}

// Một dòng lệnh đã nhận đủ (kết thúc bằng \n). Hiểu SERVOIN:, SERVOOUT:, LCDIN:, LCDOUT: và LCD: (cũ = LCDIN);
// lệnh khác bỏ qua.
void handleCommand(char *cmd) {
  char *args = afterPrefix(cmd, "SERVOOUT:");
  if (args != nullptr) { handleServo(barrierOut, args); return; }
  args = afterPrefix(cmd, "SERVOIN:");
  if (args != nullptr) { handleServo(barrierIn, args); return; }

  SoftLcd *target = nullptr;
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
  pinMode(PIN_BUZZER, OUTPUT);
  barrierIn.begin();
  barrierOut.begin();
  Serial.println(F("# dual_rfid san sang (servo: vao=D6, ra=D7, coi=A5, ir: vao=D2/D3, ra=D4/D5)"));
  sendStatus();
  lastStatus = millis();
}

void loop() {
  readSerialCommands();
  pollReader(readerIn, inOk, F("IN"));
  pollReader(readerOut, outOk, F("OUT"));
  barrierIn.update();
  barrierOut.update();

  if (millis() - lastStatus >= STATUS_INTERVAL_MS) {
    lastStatus = millis();
    sendStatus();
  }
}
