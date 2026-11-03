"""MỘT Arduino nối HAI đầu đọc RFID (cổng vào + cổng ra) qua MỘT cổng Serial.

Giao thức (9600 baud, mỗi dòng kết thúc bằng \\n; xem arduino/dual_rfid/dual_rfid.ino):

    IN:AB1992CA            quẹt thẻ ở đầu đọc CỔNG VÀO   (UID dạng HEX)
    OUT:DB2B11CA           quẹt thẻ ở đầu đọc CỔNG RA
    STATUS:IN=1,OUT=0      tình trạng từng đầu đọc (1 = hoạt động, 0 = Arduino không nói chuyện được
                           với module RFID). Arduino gửi lúc khởi động và định kỳ (~2 giây).
    # ...                  dòng chú thích / log, bị bỏ qua

Lớp đọc báo ba loại sự kiện để giao diện hiển thị:
    on_card(gate, uid)                  có thẻ quẹt ở cổng `gate` ("in" | "out")
    on_status(connected, message)       tình trạng Arduino: mất cổng COM, không phản hồi, sai định dạng...
    on_reader_status(gate, ok)          tình trạng đầu đọc của cổng: True / False / None (chưa rõ,
                                        VD khi Arduino đang mất kết nối)
LƯU Ý: các callback chạy ở luồng nền, KHÔNG được đụng trực tiếp vào widget Tkinter.
"""
import re
import threading
import time
from dataclasses import dataclass, field

import serial  # pip install pyserial

GATE_CODES = {"IN": "in", "OUT": "out"}      # tiền tố trong giao thức -> mã cổng trong chương trình
_UID_RE = re.compile(r"^[0-9A-Z]{4,32}$")


# ---------------------------------------------------------------- phân tích một dòng (hàm thuần)
@dataclass(frozen=True)
class CardSwipe:
    gate: str
    uid: str


@dataclass(frozen=True)
class ReaderStatus:
    readers: dict = field(default_factory=dict)     # {"in": True, "out": False}; có thể chỉ có một cổng


@dataclass(frozen=True)
class BadLine:
    text: str


def parse_line(raw):
    """Một dòng từ Arduino -> CardSwipe | ReaderStatus | BadLine; dòng trống hoặc chú thích -> None."""
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
    return BadLine(text)


# ---------------------------------------------------------------- luồng đọc Serial
class ArduinoRfidReader(threading.Thread):
    RECONNECT_DELAY = 3.0
    BAD_LINES_BEFORE_ALERT = 3      # vài dòng rác lúc Arduino vừa khởi động là bình thường

    def __init__(self, port, baudrate, on_card, on_status=None, on_reader_status=None,
                 debounce=2.0, heartbeat_timeout=8.0,
                 serial_factory=serial.Serial, clock=time.monotonic, sleep=time.sleep):
        super().__init__(daemon=True)
        self.port, self.baudrate = port, baudrate
        self.on_card = on_card
        self.on_status = on_status or (lambda connected, msg: None)
        self.on_reader_status = on_reader_status or (lambda gate, ok: None)
        self.debounce = debounce
        self.heartbeat_timeout = heartbeat_timeout
        self._serial_factory, self._clock, self._sleep = serial_factory, clock, sleep
        self._running = True
        self._last_swipe = {}           # (cổng, uid) -> thời điểm quẹt gần nhất, để chống quẹt trùng
        self._last_rx = 0.0
        self._silent = False            # đang báo "Arduino không phản hồi"
        self._bad_streak = 0
        self._format_alert = False      # đang báo "sai định dạng"

    def stop(self):
        self._running = False

    # ---------- vòng lặp chính ----------
    def run(self):
        while self._running:
            try:
                with self._serial_factory(self.port, self.baudrate, timeout=1) as ser:
                    self._reset_state()
                    self.on_status(True, self._connected_text())
                    while self._running:
                        data = ser.readline()
                        if data:
                            self._on_data(data.decode(errors="ignore"))
                        self._check_silence()
            except (serial.SerialException, OSError) as e:
                self.on_status(False, f"Arduino: MẤT KẾT NỐI {self.port} ({e}). "
                                      "Kiểm tra cáp USB, đóng Serial Monitor / Arduino IDE. Đang thử lại...")
                self._set_all_readers(None)
                self._sleep(self.RECONNECT_DELAY)

    def _reset_state(self):
        self._last_rx = self._clock()
        self._silent = False
        self._bad_streak = 0
        self._format_alert = False

    def _connected_text(self):
        return f"Arduino: đã kết nối {self.port}"

    # ---------- xử lý dữ liệu ----------
    def _on_data(self, raw):
        self._last_rx = self._clock()
        if self._silent:
            self._silent = False
            self.on_status(True, self._connected_text())

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
            for gate, ok in msg.readers.items():
                self.on_reader_status(gate, ok)
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
