"""Nhận diện biển số từ một khung hình. GUI, CLI hay service đều dùng chung lớp này."""
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from core.plate_utils import (
    NUMBER_LEN, PLATE_RE, extract_number, find_plate_candidates,
    fix_plate, format_plate, read_lines,
)


@dataclass
class RecognitionResult:
    image: np.ndarray          # ảnh đã vẽ khung biển số
    plate_full: str = ""       # biển số đầy đủ, VD "27-B1 258.88"
    number: str = ""           # chữ số ở dòng dưới, VD "25888"

    @property
    def is_complete(self):
        return len(self.number) == NUMBER_LEN


class PlateRecognizer:
    MAX_WIDTH = 1000
    GOOD_ENOUGH = 300   # điểm của kết quả "đủ 5 số + khớp dạng biển" (xem _analyze)

    def __init__(self):
        self._reader = None
        self._lock = threading.Lock()   # EasyOCR không nên chạy song song

    @property
    def ready(self):
        return self._reader is not None

    def load(self):
        """Tải mô hình OCR (chậm, lần đầu cần Internet). Gọi ở luồng nền."""
        import easyocr
        self._reader = easyocr.Reader(["en"], gpu=False)

    def recognize(self, frame):
        if not self.ready:
            raise RuntimeError("Mô hình OCR chưa sẵn sàng")

        scale = self.MAX_WIDTH / frame.shape[1]
        if scale < 1:
            frame = cv2.resize(frame, None, fx=scale, fy=scale)

        best = None  # (điểm, biển số, 5 số, box)
        with self._lock:
            for (x, y, bw, bh) in find_plate_candidates(frame):
                pad = 4
                crop = frame[max(0, y - pad): y + bh + pad, max(0, x - pad): x + bw + pad]
                if crop.size == 0:
                    continue
                plate, number, score = self._analyze(crop)
                if best is None or score > best[0]:
                    best = (score, plate, number, (x, y, bw, bh))
                if score >= self.GOOD_ENOUGH:   # đủ 5 số + đúng dạng biển -> khỏi OCR các vùng còn lại (nhanh hơn)
                    break

        annotated = frame.copy()
        if best is None or not best[2]:
            return RecognitionResult(annotated)

        _, plate, number, (x, y, bw, bh) = best
        cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (0, 255, 0), 3)
        full = format_plate(plate) if PLATE_RE.match(plate) else plate
        return RecognitionResult(annotated, full, number)

    def _analyze(self, crop):
        lines = read_lines(self._reader, crop)
        plate = fix_plate("".join(lines))
        number = extract_number(lines)
        score = ((200 if len(number) == NUMBER_LEN else 0)
                 + (100 if PLATE_RE.match(plate) else 0) + len(number))
        return plate, number, score
