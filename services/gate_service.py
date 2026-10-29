"""Phần dùng chung của cổng vào và cổng ra. Không phụ thuộc Tkinter."""
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import cv2
import numpy as np

from core.scanner import scan_best_of

NUMBER_RE = re.compile(r"^\d{5}$")


class Outcome(Enum):
    UNREGISTERED = "unregistered"     # thẻ chưa đăng ký / bị khóa
    ALREADY_INSIDE = "already_inside" # cổng vào: thẻ đang ở trong bãi
    NOT_INSIDE = "not_inside"         # cổng ra: thẻ chưa có lượt vào
    ENTRY_SAVED = "entry_saved"       # xe vào, đã lưu
    ENTRY_PENDING = "entry_pending"   # xe vào, chờ nhân viên xác nhận 5 số
    EXIT_DONE = "exit_done"           # xe ra, biển khớp, đã đóng lượt + tính tiền
    EXIT_REVIEW = "exit_review"       # xe ra, chờ nhân viên (không đọc đủ / lệch / không khớp)


class ReviewReason(Enum):
    NEED_NUMBER = "need_number"       # OCR không chốt được 5 số
    CLOSE = "close"                   # lệch 1 chữ số
    MISMATCH = "mismatch"             # lệch từ 2 chữ số


class NoteRequired(Exception):
    """Cho xe ra khi biển không khớp hoàn toàn thì bắt buộc ghi lý do."""


@dataclass
class CardOutcome:
    kind: Outcome
    card_uid: str = ""
    scan: object = None             # ScanResult (khi đã quét)
    event: object = None            # AccessEvent: lượt đã lưu/đã đóng, hoặc lượt đang mở (ALREADY_INSIDE, EXIT_REVIEW)
    match: object = None            # PlateMatch (cổng ra)
    reason: object = None           # ReviewReason (EXIT_REVIEW)
    swiped_at: object = None        # thời điểm quẹt thẻ


def now():
    return datetime.now().replace(microsecond=0)


def is_valid_number(number):
    return bool(NUMBER_RE.match(number or ""))


class GateService:
    """Lớp nền: nhận diện bằng nhiều khung hình, lưu/đọc ảnh."""
    gate_code = ""

    def __init__(self, recognizer, db, image_dir, scan_frames=5, scan_interval=0.25,
                 vote_min=2, sleep=time.sleep):
        self.recognizer = recognizer
        self.db = db
        self.image_dir = image_dir
        self.scan_frames = scan_frames
        self.scan_interval = scan_interval
        self.vote_min = vote_min
        self._sleep = sleep
        os.makedirs(image_dir, exist_ok=True)

    @property
    def ready(self):
        return self.recognizer.ready

    def load_model(self):
        self.recognizer.load()

    def identify(self, frame):
        """Nhận diện MỘT khung, không lưu (chế độ thử). Trả về RecognitionResult."""
        return self.recognizer.recognize(frame)

    def scan(self, get_frame, on_progress=None):
        """Quét nhiều khung sau khi quẹt thẻ và bỏ phiếu. Trả về ScanResult."""
        return scan_best_of(self.recognizer.recognize, get_frame, self.scan_frames,
                            self.scan_interval, self.vote_min, on_progress, self._sleep)

    def recent_events(self, limit=100):
        return self.db.recent(limit)

    # ---------- Ảnh ----------
    def save_image(self, image, card_uid):
        """Lưu ảnh, trả về tên file ("" nếu không có ảnh hoặc không mã hóa được)."""
        if image is None:
            return ""
        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            return ""
        name = f"{datetime.now():%Y%m%d_%H%M%S_%f}_{card_uid}_{self.gate_code}.jpg"
        buf.tofile(os.path.join(self.image_dir, name))   # tofile: an toàn với đường dẫn có dấu
        return name

    def delete_image(self, name):
        if name:
            try:
                os.remove(os.path.join(self.image_dir, name))
            except OSError:
                pass

    def load_image(self, name):
        """Đọc ảnh đã lưu; None nếu không có/không đọc được."""
        if not name:
            return None
        path = os.path.join(self.image_dir, name)
        if not os.path.isfile(path):
            return None
        return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def votes_note(scan, number):
    """Chuỗi ghi vào DB: kết quả bỏ phiếu + ghi chú nếu số cuối cùng do nhân viên chốt."""
    text = scan.votes_text() if scan else ""
    if scan is None or number != scan.winner:
        text = f"{text} | nhân viên nhập/xác nhận".strip(" |")
    return text[:100]
