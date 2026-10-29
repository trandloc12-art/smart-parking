import os

import pytest

from helpers import FakeDb, ScriptedRecognizer, make_frame
from services.entry_service import CardNotRegistered, EntryService
from services.gate_service import Outcome
from storage.errors import AlreadyInside


def make(tmp_path, numbers, **kw):
    db, rec = FakeDb(), ScriptedRecognizer(numbers)
    svc = EntryService(rec, db, str(tmp_path), sleep=lambda s: None, **kw)
    return svc, db, rec


def frame():
    return make_frame(7)


def test_unregistered_card_rejected_without_scanning(tmp_path):
    svc, db, rec = make(tmp_path, ["25888"])
    o = svc.handle_card("LA", frame)
    assert o.kind is Outcome.UNREGISTERED and rec.calls == 0 and db.rows == []


def test_auto_saves_when_vote_decided(tmp_path):
    svc, db, rec = make(tmp_path, ["25888"] * 5)
    o = svc.handle_card("CARD1", frame)
    assert o.kind is Outcome.ENTRY_SAVED
    assert o.scan.scanned == 3                      # dừng sớm
    e = db.rows[0]
    assert (e.plate_number, e.card_uid, e.gate_in) == ("25888", "CARD1", "in")
    assert os.path.isfile(tmp_path / e.image_in)    # ảnh đã được lưu
    assert db.votes[e.id] == "25888:3"


def test_tie_goes_to_pending_and_saves_nothing(tmp_path):
    svc, db, _ = make(tmp_path, ["25888", "25883", "25888", "25883", "99999"])
    o = svc.handle_card("CARD1", frame)
    assert o.kind is Outcome.ENTRY_PENDING and o.scan.suggestion == "25888"
    assert db.rows == [] and os.listdir(tmp_path) == []


def test_partial_digits_never_auto_saved(tmp_path):
    svc, db, _ = make(tmp_path, ["2588"] * 5)
    o = svc.handle_card("CARD1", frame)
    assert o.kind is Outcome.ENTRY_PENDING and o.scan.suggestion == "2588" and db.rows == []


def test_auto_save_off_requires_confirmation(tmp_path):
    svc, db, _ = make(tmp_path, ["25888"] * 5, auto_save=False)
    o = svc.handle_card("CARD1", frame)
    assert o.kind is Outcome.ENTRY_PENDING and o.scan.decided and db.rows == []


def test_already_inside_is_rejected_without_scanning(tmp_path):
    svc, db, rec = make(tmp_path, ["25888"] * 5)
    svc.handle_card("CARD1", frame)
    rec.calls = 0
    o = svc.handle_card("CARD1", frame)
    assert o.kind is Outcome.ALREADY_INSIDE and o.event.plate_number == "25888"
    assert rec.calls == 0 and len(db.rows) == 1


def test_confirm_requires_exactly_five_digits(tmp_path):
    svc, db, _ = make(tmp_path, ["2588"] * 5)
    o = svc.handle_card("CARD1", frame)
    for bad in ("2588", "", "258888", "2588a"):
        with pytest.raises(ValueError):
            svc.save_entry("CARD1", bad, o.scan, o.swiped_at)
    e = svc.save_entry("CARD1", "25888", o.scan, o.swiped_at)
    assert e.plate_number == "25888" and e.plate_full == ""        # số do nhân viên nhập: không giữ biển OCR
    assert "nhân viên" in db.votes[e.id]


def test_save_entry_unregistered_card(tmp_path):
    svc, db, _ = make(tmp_path, ["25888"])
    with pytest.raises(CardNotRegistered):
        svc.save_entry("LA", "25888", None)
    assert db.rows == []


def test_duplicate_open_session_blocked_and_no_orphan_image(tmp_path):
    svc, db, _ = make(tmp_path, ["25888"] * 5)
    o = svc.handle_card("CARD1", frame)
    files_before = set(os.listdir(tmp_path))
    with pytest.raises(AlreadyInside):
        svc.save_entry("CARD1", "25888", o.scan)
    assert set(os.listdir(tmp_path)) == files_before and len(db.rows) == 1
