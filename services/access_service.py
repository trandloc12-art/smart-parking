"""Nghiệp vụ gửi xe bằng thẻ. Không phụ thuộc Tkinter.

Quẹt thẻ:
  - Thẻ KHÔNG có trong bảng cards  -> từ chối, không nhận diện, không lưu gì.
  - Thẻ hợp lệ, chưa có lượt vào   -> XE VÀO: chụp, nhận diện biển số, lưu time_in.
  - Thẻ hợp lệ, đang có lượt vào   -> XE RA : ghi time_out và tính tiền.
"""
import os
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

import cv2

from services.pricing import calculate_fee


class Outcome(Enum):
    REJECTED = "rejected"   # thẻ chưa đăng ký
    ENTRY = "entry"         # xe vào
    EXIT = "exit"           # xe ra


class CardNotRegistered(Exception):
    pass


@dataclass
class CardOutcome:
    kind: Outcome
    result: object = None   # RecognitionResult (chỉ khi xe vào)
    event: object = None    # AccessEvent. Với xe vào: None nghĩa là chưa lưu, cần người dùng xác nhận


def _now():
    return datetime.now().replace(microsecond=0)


class AccessService:
    def __init__(self, recognizer, db, image_dir, auto_save=True,
                 price_per_block=5000, block_minutes=60):
        self.recognizer = recognizer
        self.db = db
        self.image_dir = image_dir
        self.auto_save = auto_save
        self.price_per_block = price_per_block
        self.block_minutes = block_minutes
        os.makedirs(image_dir, exist_ok=True)

    @property
    def ready(self):
        return self.recognizer.ready

    def load_model(self):
        self.recognizer.load()

    def identify(self, frame):
        """Chỉ nhận diện, không lưu (dùng cho chế độ thử). Trả về RecognitionResult."""
        return self.recognizer.recognize(frame)

    def handle_card(self, card_uid, frame):
        """Xử lý một lần quẹt thẻ. Trả về CardOutcome."""
        if not self.db.is_card_registered(card_uid):
            return CardOutcome(Outcome.REJECTED)

        open_session = self.db.find_open_session(card_uid)
        if open_session is not None:
            return CardOutcome(Outcome.EXIT, event=self._close(open_session))

        result = self.identify(frame)
        event = None
        if self.auto_save and result.is_complete:
            event = self.save_entry(card_uid, result.number, result.plate_full, result.image)
        return CardOutcome(Outcome.ENTRY, result, event)

    def save_entry(self, card_uid, number, plate_full, image):
        """Lưu lượt VÀO. Chỉ lưu nếu thẻ nằm trong danh sách đã đăng ký."""
        if not self.db.is_card_registered(card_uid):
            raise CardNotRegistered(f"Thẻ {card_uid} chưa đăng ký")
        image_name = self._save_image(image, card_uid) if image is not None else ""
        return self.db.add_entry(card_uid, number, plate_full, image_name, _now())

    def recent_events(self, limit=100):
        return self.db.recent(limit)

    def _close(self, session):
        time_out = _now()
        fee = calculate_fee(session.time_in, time_out, self.price_per_block, self.block_minutes)
        self.db.close_session(session.id, time_out, fee)
        return replace(session, time_out=time_out, fee=fee)

    def _save_image(self, image, card_uid):
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{card_uid}.jpg"
        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            return ""
        buf.tofile(os.path.join(self.image_dir, name))   # tofile: an toàn với đường dẫn có dấu
        return name
