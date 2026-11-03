"""Bao gói camera OpenCV.

Mỗi camera có một luồng nền liên tục đọc khung hình. Nhờ vậy giao diện không bị đứng chờ camera,
kể cả khi hai camera chạy cùng lúc trong một cửa sổ (mỗi lần cap.read() có thể chờ cả một khung hình)."""
import sys
import threading
import time

import cv2

# Kết quả của Camera.status()
CLOSED = "closed"           # chưa mở được (sai số camera, đang bị ứng dụng khác dùng, đã rút)
STARTING = "starting"       # vừa mở, chưa có khung hình nào
OK = "ok"                   # đang có hình
NO_SIGNAL = "no_signal"     # đã mở nhưng không còn nhận được hình (rút dây, treo)


class Camera:
    STALE_AFTER = 3.0       # giây không có khung hình mới thì coi là mất tín hiệu

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._opened_at = None
        self._last_ok = None
        self._cap = None
        self._thread = None
        self._stop = None
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0       # số thứ tự khung mới nhất do luồng nền đọc được
        self._seen = 0      # số thứ tự khung read() đã trả cho người gọi

    def open(self, index):
        """Mở camera số `index`. Trả về True nếu thành công."""
        self.release()
        # CAP_DSHOW ổn định hơn trên Windows
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" \
            else cv2.VideoCapture(index)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        self._frame, self._seq, self._seen = None, 0, 0
        self._opened_at, self._last_ok = self._clock(), None
        self._stop = threading.Event()      # mỗi lần mở một Event mới: luồng cũ không thể "sống lại"
        self._thread = threading.Thread(target=self._grab, args=(cap, self._stop), daemon=True)
        self._thread.start()
        return True

    def _grab(self, cap, stop):
        while not stop.is_set():
            ok, frame = cap.read()
            if not ok:
                stop.wait(0.05)             # camera chưa có hình / vừa rút: đừng quay vòng 100% CPU
                continue
            with self._lock:
                self._frame = frame
                self._seq += 1
                self._last_ok = self._clock()

    def read(self):
        """Trả về khung hình MỚI (BGR) từ lần đọc trước, hoặc None nếu chưa có khung mới."""
        with self._lock:
            if self._frame is None or self._seq == self._seen:
                return None
            self._seen = self._seq
            return self._frame

    def status(self):
        """CLOSED | STARTING | OK | NO_SIGNAL, để giao diện báo camera nào đang có vấn đề."""
        with self._lock:
            if self._cap is None:
                return CLOSED
            last_ok, opened_at = self._last_ok, self._opened_at
        silent_for = self._clock() - (last_ok if last_ok is not None else opened_at)
        if silent_for > self.STALE_AFTER:
            return NO_SIGNAL
        return OK if last_ok is not None else STARTING

    def release(self):
        stop, thread, cap = self._stop, self._thread, self._cap
        self._stop = self._thread = self._cap = None
        if stop is not None:
            stop.set()
        if thread is not None:
            thread.join(timeout=2)          # chờ luồng đọc dừng rồi mới nhả camera
        if cap is not None:
            cap.release()
        with self._lock:
            self._frame = None
            self._opened_at = self._last_ok = None
