"""Đầu đọc RFID. Lớp cơ sở + bản cài đặt qua cổng Serial (Arduino/ESP32/UART...)."""
import re
import threading
import time

import serial  # pip install pyserial

_UID_RE = re.compile(r"^[0-9A-Z]{4,32}$")


class RfidReader(threading.Thread):
    """Luồng nền đọc thẻ. Lớp con chỉ cần cài `run()` và gọi `self._emit(raw)`.

    on_card(uid)                 : gọi mỗi khi có thẻ hợp lệ (đã chống quẹt trùng)
    on_status(connected, message): gọi khi trạng thái kết nối thay đổi
    LƯU Ý: các callback chạy ở luồng nền, KHÔNG được đụng trực tiếp vào widget Tkinter.
    """

    def __init__(self, on_card, on_status=None, debounce=2.0):
        super().__init__(daemon=True)
        self.on_card = on_card
        self.on_status = on_status or (lambda connected, msg: None)
        self.debounce = debounce
        self._running = True
        self._last = ("", 0.0)

    def stop(self):
        self._running = False

    def _emit(self, raw):
        uid = re.sub(r"[\s:\-]", "", raw.upper())
        if not _UID_RE.match(uid):
            return
        now = time.time()
        if uid == self._last[0] and now - self._last[1] < self.debounce:
            return
        self._last = (uid, now)
        self.on_card(uid)


class SerialRfidReader(RfidReader):
    RECONNECT_DELAY = 3.0

    def __init__(self, port, baudrate, on_card, on_status=None, debounce=2.0):
        super().__init__(on_card, on_status, debounce)
        self.port = port
        self.baudrate = baudrate

    def run(self):
        while self._running:
            try:
                with serial.Serial(self.port, self.baudrate, timeout=1) as ser:
                    self.on_status(True, f"RFID: đã kết nối {self.port}")
                    while self._running:
                        self._emit(ser.readline().decode(errors="ignore"))
            except serial.SerialException as e:
                self.on_status(False, f"RFID: mất kết nối {self.port} ({e}). Đang thử lại...")
                time.sleep(self.RECONNECT_DELAY)
