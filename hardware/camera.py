"""Bao gói camera OpenCV."""
import sys

import cv2


class Camera:
    def __init__(self):
        self._cap = None

    def open(self, index):
        """Mở camera số `index`. Trả về True nếu thành công."""
        self.release()
        # CAP_DSHOW ổn định hơn trên Windows
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" \
            else cv2.VideoCapture(index)
        if cap.isOpened():
            self._cap = cap
            return True
        cap.release()
        return False

    def read(self):
        """Trả về khung hình mới nhất (BGR) hoặc None."""
        if self._cap is None:
            return None
        ok, frame = self._cap.read()
        return frame if ok else None

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
