"""Giới hạn số chỗ (slot) của bãi: đủ chỗ thì cổng vào không nhận quẹt thẻ, xe ra thì trả lại chỗ."""
import pytest

from helpers import FakeDb, ScriptedRecognizer, make_frame
from services.entry_service import EntryService
from services.exit_service import ExitService
from services.gate_service import Outcome
from storage.errors import ParkingFull

CARDS = ("C1", "C2", "C3", "C4")
PLATES = {"C1": "11111", "C2": "22222", "C3": "33333", "C4": "44444"}   # mỗi xe một biển riêng (biển trùng bị chặn)


def frame():
    return make_frame(7)


def make(tmp_path, capacity=3, script=("25888",)):
    db, rec = FakeDb(cards=CARDS), ScriptedRecognizer(script)
    entry = EntryService(rec, db, str(tmp_path), sleep=lambda s: None, capacity=capacity)
    exit_ = ExitService(rec, db, str(tmp_path), sleep=lambda s: None, capacity=capacity)
    return entry, exit_, db, rec


def swipe(svc, rec, uid):
    """Quẹt thẻ `uid`: camera thấy đúng biển của xe đó."""
    rec.set_script([PLATES[uid]])
    return svc.handle_card(uid, frame)


def fill(entry, rec, uids=("C1", "C2", "C3")):
    for uid in uids:
        assert swipe(entry, rec, uid).kind is Outcome.ENTRY_SAVED


def test_free_slots_counts_cars_inside(tmp_path):
    entry, _, _, rec = make(tmp_path)
    assert entry.free_slots() == 3
    fill(entry, rec, ("C1",))
    assert entry.free_slots() == 2
    fill(entry, rec, ("C2", "C3"))
    assert entry.free_slots() == 0


def test_full_lot_rejects_swipe_without_scanning_or_saving(tmp_path):
    entry, _, db, rec = make(tmp_path)
    fill(entry, rec)
    rec.calls = 0
    o = entry.handle_card("C4", frame)
    assert o.kind is Outcome.LOT_FULL and o.card_uid == "C4"
    assert rec.calls == 0 and len(db.rows) == 3


def test_exit_gives_a_slot_back(tmp_path):
    entry, exit_, db, rec = make(tmp_path)
    fill(entry, rec)
    assert entry.handle_card("C4", frame).kind is Outcome.LOT_FULL
    assert swipe(exit_, rec, "C1").kind is Outcome.EXIT_DONE      # xe ra: biển khớp
    assert entry.free_slots() == 1
    assert swipe(entry, rec, "C4").kind is Outcome.ENTRY_SAVED
    assert entry.free_slots() == 0


def test_exit_gate_still_works_when_lot_is_full(tmp_path):
    entry, exit_, _, rec = make(tmp_path)
    fill(entry, rec)
    assert swipe(exit_, rec, "C2").kind is Outcome.EXIT_DONE


def test_unregistered_and_already_inside_are_reported_before_full(tmp_path):
    entry, _, _, rec = make(tmp_path)
    fill(entry, rec)
    assert entry.handle_card("LA", frame).kind is Outcome.UNREGISTERED
    assert entry.handle_card("C1", frame).kind is Outcome.ALREADY_INSIDE


def test_staff_save_is_refused_when_lot_filled_up_meanwhile(tmp_path):
    entry, _, db, rec = make(tmp_path, capacity=1, script=("2588",) * 5)
    pending = entry.handle_card("C1", frame)                    # đọc thiếu số: chờ nhân viên
    assert pending.kind is Outcome.ENTRY_PENDING
    rec.set_script(["25888"])
    assert entry.handle_card("C2", frame).kind is Outcome.ENTRY_SAVED   # trong lúc chờ, xe khác vào, hết chỗ
    with pytest.raises(ParkingFull):
        entry.save_entry("C1", "25881", pending.scan)
    assert [e.card_uid for e in db.rows] == ["C2"]


def test_no_capacity_means_no_limit(tmp_path):
    entry, _, db, rec = make(tmp_path, capacity=None)
    assert entry.free_slots() is None
    fill(entry, rec, CARDS)
    assert len(db.rows) == 4
