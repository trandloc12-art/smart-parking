"""Bao gói camera OpenCV.

Mỗi camera có một luồng nền liên tục đọc khung hình. Nhờ vậy giao diện không bị đứng chờ camera,
kể cả khi hai camera chạy cùng lúc trong một cửa sổ (mỗi lần cap.read() có thể chờ cả một khung hình)."""
import sys
import threading

import cv2


class Camera:
    def __init__(self):
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

    def read(self):
        """Trả về khung hình MỚI (BGR) từ lần đọc trước, hoặc None nếu chưa có khung mới."""
        with self._lock:
            if self._frame is None or self._seq == self._seen:
                return None
            self._seen = self._seq
            return self._frame

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
