"""Chống biển số giả / trùng biển: biển 5 số đã có xe KHÁC (thẻ khác) đang ở trong bãi thì cổng vào từ chối cứng.

Chặn ở 3 chỗ: (1) handle_card sau khi OCR chốt số (TRƯỚC khi mở thanh chắn), (2) check_plate_free / save_entry cho số do nhân
viên nhập, (3) chỉ mục UX_access_log_open_plate của DB khi hai bên ghi cùng lúc (add_entry ném PlateAlreadyInside)."""
import os

import pytest

from helpers import FakeDb, ScriptedRecognizer, make_frame
from services.entry_service import EntryService
from services.exit_service import ExitService
from services.gate_service import Outcome
from storage.errors import PlateAlreadyInside


def frame():
    return make_frame(7)


def make(tmp_path, numbers=("25888",), cards=("CARD1", "CARD2", "CARD3"), **kw):
    db, rec = FakeDb(cards=cards), ScriptedRecognizer(numbers)
    svc = EntryService(rec, db, str(tmp_path), sleep=lambda s: None, **kw)
    return svc, db, rec


def enter(svc, rec, uid, plate):
    rec.set_script([plate])
    return svc.handle_card(uid, frame)


def test_same_plate_on_another_card_is_rejected_and_nothing_is_saved(tmp_path):
    svc, db, rec = make(tmp_path)
    assert enter(svc, rec, "CARD1", "25888").kind is Outcome.ENTRY_SAVED
    saved_files = sorted(os.listdir(tmp_path))
    o = enter(svc, rec, "CARD2", "25888")
    assert o.kind is Outcome.PLATE_DUPLICATE and o.card_uid == "CARD2"
    assert o.scan.winner == "25888"
    assert o.event is not None and o.event.card_uid == "CARD1"        # báo được xe đang giữ biển đó
    assert [e.card_uid for e in db.rows] == ["CARD1"]                 # không có lượt mới
    assert sorted(os.listdir(tmp_path)) == saved_files                # không giữ ảnh của lần bị từ chối


def test_different_plate_is_accepted(tmp_path):
    svc, db, rec = make(tmp_path)
    assert enter(svc, rec, "CARD1", "25888").kind is Outcome.ENTRY_SAVED
    assert enter(svc, rec, "CARD2", "25889").kind is Outcome.ENTRY_SAVED     # lệch 1 số vẫn là biển khác
    assert len(db.rows) == 2


def test_plate_can_be_used_again_after_the_car_left(tmp_path):
    svc, db, rec = make(tmp_path)
    exit_ = ExitService(rec, db, str(tmp_path), sleep=lambda s: None)
    assert enter(svc, rec, "CARD1", "25888").kind is Outcome.ENTRY_SAVED
    rec.set_script(["25888"])
    assert exit_.handle_card("CARD1", frame).kind is Outcome.EXIT_DONE
    assert enter(svc, rec, "CARD2", "25888").kind is Outcome.ENTRY_SAVED     # xe cũ đã ra: biển được dùng lại


def test_duplicate_is_detected_before_the_barrier_in_deferred_mode(tmp_path):
    """Chế độ chờ cảm biến (defer=True) hoãn việc lưu tới lúc xe qua thanh chắn: phải chặn TRƯỚC, không được trả ENTRY_READY."""
    svc, db, rec = make(tmp_path)
    enter(svc, rec, "CARD1", "25888")
    rec.set_script(["25888"])
    assert svc.handle_card("CARD2", frame, defer=True).kind is Outcome.PLATE_DUPLICATE


def test_duplicate_is_detected_even_when_auto_save_is_off(tmp_path):
    svc, db, rec = make(tmp_path, auto_save=False)
    db.seed_open("CARD1", "25888")
    rec.set_script(["25888"])
    assert svc.handle_card("CARD2", frame).kind is Outcome.PLATE_DUPLICATE


def test_already_inside_and_full_lot_are_reported_before_duplicate(tmp_path):
    svc, db, rec = make(tmp_path, capacity=1)
    enter(svc, rec, "CARD1", "25888")
    rec.calls = 0
    assert svc.handle_card("CARD2", frame).kind is Outcome.LOT_FULL and rec.calls == 0     # đầy: không quét
    svc2, db2, rec2 = make(tmp_path, capacity=5)
    enter(svc2, rec2, "CARD1", "25888")
    rec2.set_script(["25888"])
    assert svc2.handle_card("CARD1", frame).kind is Outcome.ALREADY_INSIDE                 # cùng thẻ: đã trong bãi


def test_partial_digits_do_not_trigger_the_duplicate_check(tmp_path):
    svc, db, rec = make(tmp_path, numbers=("2588",) * 5)
    db.seed_open("CARD1", "25888")
    o = svc.handle_card("CARD2", frame)
    assert o.kind is Outcome.ENTRY_PENDING                                  # thiếu số: để nhân viên xử lý


def test_staff_typed_duplicate_number_is_refused(tmp_path):
    svc, db, rec = make(tmp_path, numbers=("2588",) * 5)
    db.seed_open("CARD1", "25888")
    pending = svc.handle_card("CARD2", frame)
    assert pending.kind is Outcome.ENTRY_PENDING
    with pytest.raises(PlateAlreadyInside) as info:
        svc.check_plate_free("CARD2", "25888")
    assert info.value.session.card_uid == "CARD1"
    with pytest.raises(PlateAlreadyInside):
        svc.save_entry("CARD2", "25888", pending.scan)
    assert [e.card_uid for e in db.rows] == ["CARD1"] and os.listdir(tmp_path) == []   # không lưu, không để ảnh mồ côi
    svc.check_plate_free("CARD2", "25881")                                  # biển khác thì được
    assert svc.save_entry("CARD2", "25881", pending.scan).plate_number == "25881"


def test_race_two_entries_at_the_same_time_is_caught_by_the_db_index(tmp_path):
    """Lúc kiểm tra chưa có ai giữ biển, nhưng ngay trước khi ghi một xe khác vừa vào: add_entry ném PlateAlreadyInside."""
    svc, db, rec = make(tmp_path)
    real_find = db.find_open_session_by_plate
    calls = []

    def find(plate):
        calls.append(plate)
        if len(calls) == 1:         # lần kiểm tra đầu (trong handle_card): chưa có
            return None
        return real_find(plate)

    db.find_open_session_by_plate = find
    real_add = db.add_entry

    def add(*a, **k):
        db.seed_open("CARD1", "25888")          # xe khác vừa ghi xong giữa hai bước
        return real_add(*a, **k)

    db.add_entry = add
    rec.set_script(["25888"])
    o = svc.handle_card("CARD2", frame)
    assert o.kind is Outcome.PLATE_DUPLICATE and o.event.card_uid == "CARD1"
    assert [e.card_uid for e in db.rows] == ["CARD1"] and os.listdir(tmp_path) == []
