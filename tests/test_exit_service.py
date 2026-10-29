import os
from datetime import timedelta

import pytest

from helpers import FakeDb, ScriptedRecognizer, make_frame
from services.entry_service import EntryService
from services.exit_service import ExitService
from services.gate_service import NoteRequired, Outcome, ReviewReason, now
from storage.errors import SessionAlreadyClosed


def frame():
    return make_frame(9)


class Lot:
    """Một bãi giả: cổng vào + cổng ra dùng chung DB và thư mục ảnh."""

    def __init__(self, tmp_path):
        self.db = FakeDb()
        self.rec_in = ScriptedRecognizer(["25888"])
        self.rec_out = ScriptedRecognizer(["25888"])
        self.tmp = tmp_path
        self.entry = EntryService(self.rec_in, self.db, str(tmp_path), sleep=lambda s: None)
        self.exit = ExitService(self.rec_out, self.db, str(tmp_path), sleep=lambda s: None)

    def park(self, uid="CARD1", plate="25888", minutes_ago=90):
        self.rec_in.set_script([plate])
        o = self.entry.handle_card(uid, frame)
        assert o.kind is Outcome.ENTRY_SAVED
        # lùi giờ vào để kiểm tra tiền
        e = self.db.rows[-1]
        e.time_in = now() - timedelta(minutes=minutes_ago)
        return e


def test_unregistered_and_not_inside(tmp_path):
    lot = Lot(tmp_path)
    assert lot.exit.handle_card("LA", frame).kind is Outcome.UNREGISTERED
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.NOT_INSIDE and lot.rec_out.calls == 0     # chưa vào -> không quét


def test_matching_exit_closes_and_charges(tmp_path):
    lot = Lot(tmp_path)
    lot.park(minutes_ago=90)
    lot.rec_out.set_script(["25888"])
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.EXIT_DONE
    e = lot.db.rows[0]
    assert e.time_out is not None and e.fee == 10000          # 90 phút -> 2 khối
    assert (e.plate_out, e.match_status, e.gate_out) == ("25888", "MATCH", "out")
    assert os.path.isfile(tmp_path / e.image_out) and e.image_out != e.image_in


def test_after_exit_card_can_enter_again_but_not_exit_twice(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.exit.handle_card("CARD1", frame)
    assert lot.exit.handle_card("CARD1", frame).kind is Outcome.NOT_INSIDE
    lot.rec_in.set_script(["11111"])
    assert lot.entry.handle_card("CARD1", frame).kind is Outcome.ENTRY_SAVED


def test_one_digit_off_needs_staff_and_reason(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script(["25883"])
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.EXIT_REVIEW and o.reason is ReviewReason.CLOSE
    assert lot.db.rows[0].time_out is None                         # chưa đóng lượt
    with pytest.raises(NoteRequired):
        lot.exit.confirm_exit("CARD1", "25883", o.scan, o.swiped_at, note="")
    with pytest.raises(NoteRequired):
        lot.exit.confirm_exit("CARD1", "25883", o.scan, o.swiped_at, note="ok")   # quá ngắn
    e = lot.exit.confirm_exit("CARD1", "25883", o.scan, o.swiped_at,
                              note="Chủ xe xuất trình cà vẹt")
    assert e.match_status == "APPROVED_CLOSE" and "cà vẹt" in lot.db.rows[0].override_note


def test_big_mismatch_blocked_until_reason(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script(["11111"])
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.EXIT_REVIEW and o.reason is ReviewReason.MISMATCH
    with pytest.raises(NoteRequired):
        lot.exit.confirm_exit("CARD1", "11111", o.scan, o.swiped_at)
    e = lot.exit.confirm_exit("CARD1", "11111", o.scan, o.swiped_at, note="Xe đã đổi biển")
    assert e.match_status == "APPROVED_MISMATCH"


def test_staff_retypes_correct_number_needs_no_reason(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script(["11111"])               # OCR đọc sai hẳn
    o = lot.exit.handle_card("CARD1", frame)
    e = lot.exit.confirm_exit("CARD1", "25888", o.scan, o.swiped_at)
    assert e.match_status == "MATCH" and e.plate_out == "25888"
    assert "nhân viên" in lot.db.votes_out[e.id]                   # ghi nhận số cuối do nhân viên chốt


def test_unreadable_exit_needs_number(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script([""])
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.EXIT_REVIEW and o.reason is ReviewReason.NEED_NUMBER
    assert o.match is None and o.event.plate_number == "25888"


def test_tie_at_exit_goes_to_review(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script(["25888", "25883", "25888", "25883", "99999"])
    o = lot.exit.handle_card("CARD1", frame)
    assert o.kind is Outcome.EXIT_REVIEW and o.reason is ReviewReason.NEED_NUMBER
    assert o.scan.suggestion == "25888" and o.match is not None    # có gợi ý -> đã so khớp thử


def test_confirm_needs_five_digits(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    for bad in ("2588", "", "x5888"):
        with pytest.raises(ValueError):
            lot.exit.confirm_exit("CARD1", bad, None, now(), note="lý do hợp lệ")


def test_confirm_after_session_closed(tmp_path):
    lot = Lot(tmp_path)
    lot.park()
    lot.rec_out.set_script(["25883"])
    o = lot.exit.handle_card("CARD1", frame)
    lot.exit.confirm_exit("CARD1", "25883", o.scan, o.swiped_at, note="lần một")
    with pytest.raises(SessionAlreadyClosed):
        lot.exit.confirm_exit("CARD1", "25883", o.scan, o.swiped_at, note="lần hai")


def test_exit_time_is_swipe_time_not_confirm_time(tmp_path):
    lot = Lot(tmp_path)
    lot.park(minutes_ago=30)
    lot.rec_out.set_script([""])
    o = lot.exit.handle_card("CARD1", frame)
    # nhân viên xác nhận muộn (giả lập bằng cách chỉ truyền giờ quẹt thẻ): giờ ra phải là giờ QUẸT THẺ
    out = lot.exit.confirm_exit("CARD1", "25888", o.scan, o.swiped_at)
    assert out.time_out == o.swiped_at and out.fee == 5000
