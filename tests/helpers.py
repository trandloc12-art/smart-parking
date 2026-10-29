"""Đồ giả dùng cho test: CSDL trong bộ nhớ, bộ nhận diện kịch bản, camera giả."""
import dataclasses

import numpy as np

from core.recognizer import RecognitionResult
from storage.errors import AlreadyInside, SessionAlreadyClosed
from storage.models import AccessEvent


class FakeDb:
    """Cùng giao diện với storage.database.Database, lưu trong list."""

    def __init__(self, cards=("CARD1", "CARD2")):
        self.cards = set(cards)
        self.rows = []
        self.votes = {}
        self.votes_out = {}

    def is_card_registered(self, uid):
        return uid in self.cards

    def find_open_session(self, uid):
        for e in reversed(self.rows):
            if e.card_uid == uid and e.time_out is None:
                return e
        return None

    def add_entry(self, card_uid, plate_number, plate_full, image_in, time_in, votes="", gate=""):
        if self.find_open_session(card_uid):
            raise AlreadyInside(card_uid)
        e = AccessEvent(len(self.rows) + 1, card_uid, plate_number, plate_full, image_in,
                        time_in, gate_in=gate)
        self.rows.append(e)
        self.votes[e.id] = votes
        return e

    def close_session(self, session_id, time_out, fee, plate_out, image_out, match_status,
                      override_note="", votes_out="", gate=""):
        for i, e in enumerate(self.rows):
            if e.id == session_id and e.time_out is None:
                self.rows[i] = dataclasses.replace(
                    e, time_out=time_out, fee=fee, plate_out=plate_out, image_out=image_out,
                    match_status=match_status, override_note=override_note, gate_out=gate)
                self.votes_out[session_id] = votes_out
                return
        raise SessionAlreadyClosed("đã đóng")

    def recent(self, limit=100):
        return list(reversed(self.rows))[:limit]


class ScriptedRecognizer:
    """Mỗi lần recognize() trả về số kế tiếp trong kịch bản (hết thì lặp lại số cuối)."""
    ready = True

    def __init__(self, numbers):
        self.numbers = list(numbers)
        self.calls = 0

    def load(self):
        pass

    def set_script(self, numbers):
        self.numbers, self.calls = list(numbers), 0

    def recognize(self, frame):
        n = self.numbers[min(self.calls, len(self.numbers) - 1)]
        self.calls += 1
        return RecognitionResult(frame.copy(), f"fake-{n}" if n else "", n)


def make_frame(value=0):
    return np.full((60, 80, 3), value, dtype=np.uint8)


class FakeCamera:
    def open(self, index):
        return True

    def read(self):
        return make_frame(128)

    def release(self):
        pass
