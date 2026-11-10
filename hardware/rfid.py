"""MỘT Arduino nối HAI đầu đọc RFID (cổng vào + cổng ra) qua MỘT cổng Serial.

Giao thức (9600 baud, mỗi dòng kết thúc bằng \\n; xem arduino/dual_rfid/dual_rfid.ino):

    IN:AB1992CA            quẹt thẻ ở đầu đọc CỔNG VÀO   (UID dạng HEX)
    OUT:DB2B11CA           quẹt thẻ ở đầu đọc CỔNG RA
    STATUS:IN=1,OUT=0      tình trạng từng đầu đọc (1 = hoạt động, 0 = Arduino không nói chuyện được
                           với module RFID). Arduino gửi lúc khởi động và định kỳ (~2 giây).
    PASS:IN                xe đã đi qua hẳn thanh chắn CỔNG VÀO (PASS:OUT: cổng ra); Arduino đã hạ thanh chắn
    NOPASS:OUT             hết giờ mở thanh chắn mà xe CHƯA đi qua (NOPASS:IN: cổng vào); thanh chắn đã hạ
    # ...                  dòng chú thích / log, bị bỏ qua

Chiều NGƯỢC LẠI (máy tính -> Arduino), chỉ để hiển thị lên hai màn LCD 1602 I2C (một ở mỗi cổng):
    LCDIN:dòng 1|dòng 2    hiển thị lên LCD CỔNG VÀO
    LCDOUT:dòng 1|dòng 2   hiển thị lên LCD CỔNG RA
    LCD:dòng 1|dòng 2      lệnh cũ, Arduino coi như LCDIN (giữ lại cho tương thích)
                           Mỗi dòng tối đa 16 ký tự ASCII không dấu (xem lcd_text). Arduino không có LCD
                           tương ứng hoặc còn firmware cũ thì bỏ qua dòng này, không ảnh hưởng gì.

Chiều NGƯỢC LẠI thứ hai: mở thanh chắn (servo) của từng cổng khi quẹt thẻ thành công:
    SERVOIN:OPEN           mở servo CỔNG VÀO (Arduino tự đóng lại sau thời gian mặc định trong firmware)
    SERVOOUT:OPEN:3000     mở servo CỔNG RA và giữ 3000 ms rồi Arduino tự đóng lại
    SERVOIN:CLOSE          đóng servo ngay (dự phòng)
    SERVOIN:ANGLE:0:90     đặt góc đóng (vị trí ban đầu) và góc mở của servo CỔNG VÀO (SERVOOUT:ANGLE:... cho cổng ra);
                           gửi mỗi khi Arduino khởi động (xem init_commands)
                           Arduino tự đóng, nên dù máy tính treo thì thanh chắn cũng không kẹt ở trạng thái mở.
    BUZZER:TONE:2000:120   đặt âm thanh còi: tần số (Hz) rồi độ dài một tiếng bíp (ms); gửi mỗi khi Arduino khởi động
    BUZZER:BEEP            kêu thử một tiếng bíp (để chỉnh âm thanh)
    STUCK:10000            ngưỡng cảnh báo xe dừng quá lâu (ms; 0 = tắt): đã quẹt thẻ mà xe đứng yên ở cảm biến trước / sau quá
                           ngưỡng này thì còi kêu lặp tới khi xe nhúc nhích hoặc thanh chắn đóng; gửi mỗi khi Arduino khởi động

Lớp đọc báo ba loại sự kiện để giao diện hiển thị:
    on_card(gate, uid)                  có thẻ quẹt ở cổng `gate` ("in" | "out")
    on_status(connected, message)       tình trạng Arduino: mất cổng COM, không phản hồi, sai định dạng...
    on_reader_status(gate, ok)          tình trạng đầu đọc của cổng: True / False / None (chưa rõ,
                                        VD khi Arduino đang mất kết nối)
    on_barrier(gate, passed)            kết quả của một lần mở thanh chắn (cảm biến hồng ngoại): True = xe đã qua,
                                        False = hết giờ mà xe chưa qua
LƯU Ý: các callback chạy ở luồng nền, KHÔNG được đụng trực tiếp vào widget Tkinter.
"""
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field

import serial  # pip install pyserial

GATE_CODES = {"IN": "in", "OUT": "out"}      # tiền tố trong giao thức -> mã cổng trong chương trình
BARRIER_HEADS = {"PASS": True, "NOPASS": False}   # tiền tố báo kết quả thanh chắn -> xe đã qua?
_UID_RE = re.compile(r"^[0-9A-Z]{4,32}$")
LCD_WIDTH = 16                                # LCD 1602: 16 cột x 2 dòng


# ---------------------------------------------------------------- màn LCD (hàm thuần)
def lcd_text(text, width=LCD_WIDTH):
    """Đổi chuỗi sang dạng LCD 1602 hiển thị được: ASCII không dấu, không ký tự điều khiển, tối đa `width` ký tự.

    LCD 1602 không có chữ có dấu tiếng Việt: 'BIỂN SỐ' -> 'BIEN SO'. Ký tự '|' là dấu ngăn hai dòng trong
    giao thức nên bị thay bằng '/'."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("|", "/")
    text = "".join(ch if 0x20 <= ord(ch) <= 0x7E else "?" for ch in text if ch.isprintable() or ch == " ")
    return text[:width]


LCD_PREFIX = {"in": "LCDIN", "out": "LCDOUT"}     # mã cổng -> tiền tố lệnh


def format_lcd_command(line1, line2="", gate="in"):
    """Một dòng lệnh gửi Arduino, VD 'LCDOUT:XE RA OK|TIEN 5.000 D\\n'. gate: 'in' (cổng vào) hoặc 'out' (cổng ra)."""
    try:
        prefix = LCD_PREFIX[gate]
    except KeyError:
        raise ValueError(f"cổng không hợp lệ: {gate!r} (chỉ nhận 'in' hoặc 'out')") from None
    return f"{prefix}:{lcd_text(line1)}|{lcd_text(line2)}\n"


BOOT_BANNER = "# dual_rfid"      # dòng chú thích Arduino in ra khi khởi động xong (setup)
SERVO_PREFIX = {"in": "SERVOIN", "out": "SERVOOUT"}   # mã cổng -> tiền tố lệnh servo
SERVO_ACTIONS = ("OPEN", "CLOSE")


def format_servo_command(gate, action="OPEN", hold_seconds=None, pass_seconds=None):
    """Một dòng lệnh servo gửi Arduino, VD 'SERVOOUT:OPEN:3000\\n' hoặc 'SERVOIN:OPEN:3000:3000\\n'.

    hold_seconds: giữ mở bao lâu (giây) rồi Arduino tự đóng; None = dùng thời gian mặc định trong firmware.
    pass_seconds: ân hạn khi xe rời đi: cảm biến trước mất tín hiệu quá ngần này giây mà cảm biến sau chưa thấy xe thì
    Arduino hủy (hạ thanh chắn + NOPASS); cảm biến trước còn tín hiệu thì không hủy; None = dùng mặc định trong firmware. Cần kèm hold_seconds.
    Chỉ có ý nghĩa với OPEN."""
    try:
        prefix = SERVO_PREFIX[gate]
    except KeyError:
        raise ValueError(f"cổng không hợp lệ: {gate!r} (chỉ nhận 'in' hoặc 'out')") from None
    action = (action or "").upper()
    if action not in SERVO_ACTIONS:
        raise ValueError(f"lệnh servo không hợp lệ: {action!r} (chỉ nhận {SERVO_ACTIONS})")
    if action == "OPEN" and hold_seconds is not None:
        if hold_seconds <= 0:
            raise ValueError("hold_seconds phải > 0")
        line = f"{prefix}:OPEN:{int(round(hold_seconds * 1000))}"
        if pass_seconds is not None:
            if pass_seconds <= 0:
                raise ValueError("pass_seconds phải > 0")
            line += f":{int(round(pass_seconds * 1000))}"
        return line + "\n"
    if action == "OPEN" and pass_seconds is not None:
        raise ValueError("pass_seconds cần đi kèm hold_seconds")
    return f"{prefix}:{action}\n"


SERVO_MAX_ANGLE = 180


def format_servo_angle_command(gate, closed_angle, open_angle):
    """Lệnh đặt góc servo, VD 'SERVOIN:ANGLE:0:90\\n': góc đóng (vị trí ban đầu) rồi góc mở, mỗi góc 0..180 độ."""
    try:
        prefix = SERVO_PREFIX[gate]
    except KeyError:
        raise ValueError(f"cổng không hợp lệ: {gate!r} (chỉ nhận 'in' hoặc 'out')") from None
    for angle in (closed_angle, open_angle):
        if isinstance(angle, bool) or not isinstance(angle, int) or not 0 <= angle <= SERVO_MAX_ANGLE:
            raise ValueError(f"góc servo phải là số nguyên 0..{SERVO_MAX_ANGLE}, đang là {angle!r}")
    return f"{prefix}:ANGLE:{closed_angle}:{open_angle}\n"


def servo_init_commands(*cfgs):
    """Các lệnh đặt góc servo (init_commands của ArduinoRfidReader) cho những cổng có cấu hình `cfgs`.
    Cổng tắt servo (SERVO_ENABLED=0) thì không gửi gì."""
    return [format_servo_angle_command(c.gate, c.servo_closed_angle, c.servo_open_angle)
            for c in cfgs if getattr(c, "servo_enabled", True)]


BUZZER_FREQ_RANGE = (100, 8000)      # Hz, khớp firmware (BUZZER_FREQ_MIN_HZ..MAX_HZ)
BUZZER_BEEP_RANGE = (20, 2000)       # ms, khớp firmware (BUZZER_BEEP_MIN_MS..MAX_MS)


def format_buzzer_command(freq_hz, beep_ms):
    """Lệnh đặt âm thanh còi, VD 'BUZZER:TONE:2000:120\\n': tần số (Hz) rồi độ dài một tiếng bíp (ms)."""
    for name, value, (lo, hi) in (("tần số còi", freq_hz, BUZZER_FREQ_RANGE), ("độ dài tiếng bíp", beep_ms, BUZZER_BEEP_RANGE)):
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise ValueError(f"{name} phải là số nguyên {lo}..{hi}, đang là {value!r}")
    return f"BUZZER:TONE:{freq_hz}:{beep_ms}\n"


STUCK_WARN_RANGE = (1, 600)         # giây (0 = tắt), khớp firmware (STUCK_WARN_MIN_MS..MAX_MS)


def format_stuck_command(seconds):
    """Lệnh đặt ngưỡng cảnh báo xe dừng quá lâu, VD 'STUCK:10000\\n' (giây -> ms). 0 = tắt cảnh báo."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise ValueError(f"ngưỡng cảnh báo phải là số giây, đang là {seconds!r}")
    lo, hi = STUCK_WARN_RANGE
    if seconds != 0 and not lo <= seconds <= hi:
        raise ValueError(f"ngưỡng cảnh báo phải là 0 (tắt) hoặc {lo}..{hi} giây, đang là {seconds!r}")
    return f"STUCK:{int(round(seconds * 1000))}\n"


def stuck_init_commands(cfg):
    """Lệnh đặt ngưỡng cảnh báo xe dừng quá lâu (init_commands của ArduinoRfidReader). Còi dùng chung nên chỉ một lệnh."""
    return [format_stuck_command(cfg.stuck_warn_seconds)]


def buzzer_init_commands(cfg):
    """Lệnh đặt âm thanh còi (init_commands của ArduinoRfidReader). Còi dùng chung cho cả hai cổng nên chỉ cần một lệnh."""
    return [format_buzzer_command(cfg.buzzer_freq_hz, cfg.buzzer_beep_ms)]


# ---------------------------------------------------------------- phân tích một dòng (hàm thuần)
@dataclass(frozen=True)
class CardSwipe:
    gate: str
    uid: str


@dataclass(frozen=True)
class ReaderStatus:
    readers: dict = field(default_factory=dict)     # {"in": True, "out": False}; có thể chỉ có một cổng


@dataclass(frozen=True)
class BarrierEvent:
    gate: str
    passed: bool            # True: PASS (xe đã qua hẳn); False: NOPASS (hết giờ mở mà chưa qua)


@dataclass(frozen=True)
class BadLine:
    text: str


def parse_line(raw):
    """Một dòng từ Arduino -> CardSwipe | ReaderStatus | BarrierEvent | BadLine; dòng trống hoặc chú thích -> None."""
    text = raw.strip()
    if not text or text.startswith("#"):
        return None
    head, sep, body = text.partition(":")
    head = head.strip().upper()
    if sep and head in GATE_CODES:
        uid = re.sub(r"[\s:\-]", "", body.upper())
        if _UID_RE.match(uid):
            return CardSwipe(GATE_CODES[head], uid)
    elif sep and head == "STATUS":
        readers = {}
        for part in body.split(","):
            key, _, value = part.partition("=")
            key, value = key.strip().upper(), value.strip()
            if key in GATE_CODES and value in ("0", "1"):
                readers[GATE_CODES[key]] = value == "1"
        if readers:
            return ReaderStatus(readers)
    elif sep and head in BARRIER_HEADS:
        gate = GATE_CODES.get(body.strip().upper())
        if gate:
            return BarrierEvent(gate, BARRIER_HEADS[head])
    return BadLine(text)


# ---------------------------------------------------------------- luồng đọc Serial
class ArduinoRfidReader(threading.Thread):
    RECONNECT_DELAY = 3.0
    BAD_LINES_BEFORE_ALERT = 3      # vài dòng rác lúc Arduino vừa khởi động là bình thường

    def __init__(self, port, baudrate, on_card, on_status=None, on_reader_status=None,
                 debounce=2.0, heartbeat_timeout=8.0, on_barrier=None, init_commands=(),
                 serial_factory=serial.Serial, clock=time.monotonic, sleep=time.sleep):
        super().__init__(daemon=True)
        self.port, self.baudrate = port, baudrate
        self.on_card = on_card
        self.on_status = on_status or (lambda connected, msg: None)
        self.on_reader_status = on_reader_status or (lambda gate, ok: None)
        self.on_barrier = on_barrier or (lambda gate, passed: None)
        self.debounce = debounce
        self.heartbeat_timeout = heartbeat_timeout
        # Các dòng lệnh (đã có \\n) gửi cho Arduino mỗi khi nó khởi động, VD góc servo ban đầu. Arduino Uno tự reset
        # khi mở cổng COM nên không gửi ngay lúc kết nối được: chờ dòng STATUS đầu tiên (Arduino đã sẵn sàng).
        self.init_commands = tuple(init_commands)
        self._init_pending = True
        self._serial_factory, self._clock, self._sleep = serial_factory, clock, sleep
        self._running = True
        self._last_swipe = {}           # (cổng, uid) -> thời điểm quẹt gần nhất, để chống quẹt trùng
        self._last_rx = 0.0
        self._silent = False            # đang báo "Arduino không phản hồi"
        self._bad_streak = 0
        self._format_alert = False      # đang báo "sai định dạng"
        self._ser = None                # cổng Serial đang mở (None = đang mất kết nối)
        self._write_lock = threading.Lock()

    def stop(self):
        self._running = False

    # ---------- vòng lặp chính ----------
    def run(self):
        while self._running:
            try:
                with self._serial_factory(self.port, self.baudrate, timeout=1) as ser:
                    self._reset_state()
                    self._ser = ser
                    try:
                        self.on_status(True, self._connected_text())
                        while self._running:
                            data = ser.readline()
                            if data:
                                self._on_data(data.decode(errors="ignore"))
                            self._check_silence()
                    finally:
                        self._ser = None
            except (serial.SerialException, OSError) as e:
                self.on_status(False, f"Arduino: MẤT KẾT NỐI {self.port} ({e}). "
                                      "Kiểm tra cáp USB, đóng Serial Monitor / Arduino IDE. Đang thử lại...")
                self._set_all_readers(None)
                self._sleep(self.RECONNECT_DELAY)

    # ---------- gửi lệnh xuống Arduino ----------
    def send_lcd(self, line1, line2="", gate="in"):
        """Hiển thị hai dòng lên LCD của cổng `gate` ('in' / 'out') trên Arduino. Gọi được từ luồng bất kỳ.

        Trả về True nếu đã ghi ra cổng COM; False nếu đang mất kết nối hoặc ghi lỗi (không ném ngoại lệ:
        LCD chỉ là phần phụ, không được làm hỏng việc xử lý thẻ. Nếu cổng COM hỏng thật thì vòng đọc
        sẽ tự báo MẤT KẾT NỐI và kết nối lại)."""
        return self._write_line(format_lcd_command(line1, line2, gate))   # gate sai là lỗi lập trình: ném ra

    def send_servo(self, gate, action="OPEN", hold_seconds=None, pass_seconds=None):
        """Mở / đóng servo (thanh chắn) của cổng `gate` ('in' / 'out'). Gọi được từ luồng bất kỳ.

        Trả về True nếu đã ghi ra cổng COM; False nếu đang mất kết nối hoặc ghi lỗi (không ném ngoại lệ)."""
        return self._write_line(format_servo_command(gate, action, hold_seconds, pass_seconds))

    def send_servo_angles(self, gate, closed_angle, open_angle):
        """Đặt góc đóng (vị trí ban đầu) và góc mở cho servo của cổng `gate`. Trả về True nếu đã ghi ra cổng COM."""
        return self._write_line(format_servo_angle_command(gate, closed_angle, open_angle))

    def send_buzzer_tone(self, freq_hz, beep_ms):
        """Đặt tần số (Hz) và độ dài (ms) tiếng bíp của còi. Trả về True nếu đã ghi ra cổng COM."""
        return self._write_line(format_buzzer_command(freq_hz, beep_ms))

    def send_stuck_warn(self, seconds):
        """Đặt ngưỡng (giây) cảnh báo xe dừng quá lâu, 0 = tắt. Trả về True nếu đã ghi ra cổng COM."""
        return self._write_line(format_stuck_command(seconds))

    def send_buzzer_beep(self):
        """Kêu thử một tiếng bíp với âm thanh hiện tại của Arduino. Trả về True nếu đã ghi ra cổng COM."""
        return self._write_line("BUZZER:BEEP\n")

    def _send_init_commands(self):
        """Gửi các lệnh khởi tạo; chưa gửi hết (mất kết nối giữa chừng) thì thử lại ở dòng STATUS kế tiếp (~2 giây)."""
        try:
            if all([self._write_line(line) for line in self.init_commands]):
                self._init_pending = False
        except Exception:
            pass        # chạy trong luồng đọc thẻ: servo chỉ là phần phụ, không được làm chết việc đọc RFID

    def _write_line(self, line):
        data = line.encode("ascii")
        ser = self._ser
        if ser is None:
            return False
        try:
            with self._write_lock:
                ser.write(data)
            return True
        except (serial.SerialException, OSError, ValueError):
            return False

    def _reset_state(self):
        self._last_rx = self._clock()
        self._silent = False
        self._bad_streak = 0
        self._format_alert = False
        self._init_pending = True

    def _connected_text(self):
        return f"Arduino: đã kết nối {self.port}"

    # ---------- xử lý dữ liệu ----------
    def _on_data(self, raw):
        self._last_rx = self._clock()
        if self._silent:
            self._silent = False
            self.on_status(True, self._connected_text())

        if raw.lstrip().startswith(BOOT_BANNER):
            self._init_pending = True       # Arduino vừa (khởi động lại): servo về góc mặc định, cần cài lại góc
        msg = parse_line(raw)
        if isinstance(msg, BadLine):
            self._bad_streak += 1
            if self._bad_streak >= self.BAD_LINES_BEFORE_ALERT and not self._format_alert:
                self._format_alert = True
                self.on_status(False, f"Arduino: {self.port} gửi dữ liệu sai định dạng ('{msg.text[:30]}'). "
                                      "Cần nạp firmware dual_rfid (dòng phải có dạng IN:<UID> hoặc OUT:<UID>)")
            return
        if msg is None:
            return                      # chú thích / dòng trống: Arduino còn sống nhưng không có gì để xử lý
        self._bad_streak = 0
        if self._format_alert:
            self._format_alert = False
            self.on_status(True, self._connected_text())

        if isinstance(msg, ReaderStatus):
            if self._init_pending:
                self._send_init_commands()
            for gate, ok in msg.readers.items():
                self.on_reader_status(gate, ok)
        elif isinstance(msg, BarrierEvent):
            self.on_barrier(msg.gate, msg.passed)      # không chống trùng: mỗi lần mở thanh chắn chỉ có một kết quả
        else:
            self._emit_card(msg.gate, msg.uid)

    def _emit_card(self, gate, uid):
        now = self._clock()
        key = (gate, uid)
        last = self._last_swipe.get(key)
        if last is not None and now - last < self.debounce:
            return
        self._last_swipe[key] = now
        self.on_card(gate, uid)

    def _check_silence(self):
        """Cổng COM vẫn mở nhưng Arduino im lặng (treo, mất nguồn, rút dây phía sau hub...)."""
        if self.heartbeat_timeout <= 0 or self._silent:
            return
        if self._clock() - self._last_rx > self.heartbeat_timeout:
            self._silent = True
            self.on_status(False, f"Arduino: {self.port} KHÔNG PHẢN HỒI "
                                  f"(quá {self.heartbeat_timeout:g} giây không có dữ liệu)")
            self._set_all_readers(None)

    def _set_all_readers(self, ok):
        for gate in GATE_CODES.values():
            self.on_reader_status(gate, ok)
