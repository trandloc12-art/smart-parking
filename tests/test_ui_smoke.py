"""Chạy thật hai màn hình Tkinter (camera/OCR/DB giả). Tự bỏ qua nếu không có màn hình (DISPLAY)."""
import time
import tkinter as tk

import pytest

import config
from helpers import FakeCamera, FakeDb, ScriptedRecognizer
from services.entry_service import EntryService
from services.exit_service import ExitService
from ui.entry_app import EntryApp
from ui.exit_app import ExitApp


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("không có màn hình để chạy Tkinter")
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def pump(root, cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.01)
    return False


def settings(gate, tmp_path, monkeypatch):
    monkeypatch.setenv("IMG_DIR", str(tmp_path))
    return config.load_settings(gate)


def idle(app):
    return app.service.ready and not app.busy


def swipe(app, uid):
    """Quẹt thẻ đúng đường đi thật (luồng RFID -> hàng đợi -> GUI) rồi chờ kết quả được xử lý xong."""
    seen = []
    original = app.on_card_outcome
    app.on_card_outcome = lambda outcome: (seen.append(outcome), original(outcome))
    try:
        app.handle_card(uid)
        assert pump(app.root, lambda: seen), "không nhận được kết quả quẹt thẻ"
        assert pump(app.root, lambda: not app.busy), "xử lý quá lâu"
    finally:
        del app.on_card_outcome            # bỏ bản bọc, trả về phương thức gốc
    return seen[0]


def test_entry_app_flow(root, tmp_path, monkeypatch):
    db, rec = FakeDb(), ScriptedRecognizer(["25888"])
    svc = EntryService(rec, db, str(tmp_path), sleep=lambda s: None)
    app = EntryApp(root, svc, FakeCamera(), settings("in", tmp_path, monkeypatch))
    assert pump(root, lambda: idle(app) and app.last_frame is not None)

    swipe(app, "LA")                                           # thẻ lạ
    assert "CHƯA ĐĂNG KÝ" in app.status_lbl.cget("text") and db.rows == []

    swipe(app, "CARD1")                                        # đọc rõ -> tự lưu
    assert "XE VÀO" in app.status_lbl.cget("text") and app.plate_var.get() == "25888"
    assert len(db.rows) == 1 and app.pending is None

    swipe(app, "CARD1")                                        # quẹt lại -> đang trong bãi
    assert "ĐANG Ở TRONG BÃI" in app.status_lbl.cget("text") and len(db.rows) == 1

    # đọc thiếu số -> chờ nhân viên; nút Lưu chỉ bật khi đủ 5 số
    rec.set_script(["2588"])
    swipe(app, "CARD2")
    assert app.pending is not None and app.plate_var.get() == "2588"
    assert str(app.save_btn.cget("state")) == "disabled"
    app.plate_var.set("25881")
    root.update()
    assert str(app.save_btn.cget("state")) == "normal"
    app.save_entry()
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert [e.plate_number for e in db.rows] == ["25888", "25881"]

    # lịch sử hiển thị
    assert pump(root, lambda: len(app.tree.get_children()) == 2)


def test_entry_cancel(root, tmp_path, monkeypatch):
    db, rec = FakeDb(), ScriptedRecognizer([""])
    app = EntryApp(root, EntryService(rec, db, str(tmp_path), sleep=lambda s: None),
                   FakeCamera(), settings("in", tmp_path, monkeypatch))
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    swipe(app, "CARD1")
    assert app.pending is not None and str(app.save_btn.cget("state")) == "disabled"
    app.cancel_pending()
    assert app.pending is None and db.rows == []


def test_exit_app_flow(root, tmp_path, monkeypatch):
    db = FakeDb()
    entry_svc = EntryService(ScriptedRecognizer(["25888"]), db, str(tmp_path), sleep=lambda s: None)
    entry_svc.handle_card("CARD1", lambda: FakeCamera().read())      # xe vào trước
    entry_svc.handle_card("CARD2", lambda: FakeCamera().read())

    rec = ScriptedRecognizer(["25888"])
    app = ExitApp(root, ExitService(rec, db, str(tmp_path), sleep=lambda s: None), FakeCamera(),
                  settings("out", tmp_path, monkeypatch))
    assert pump(root, lambda: idle(app) and app.last_frame is not None)

    swipe(app, "LA")
    assert "CHƯA ĐĂNG KÝ" in app.status_lbl.cget("text")

    swipe(app, "CARD1")                                              # khớp -> ra luôn
    assert "XE RA" in app.status_lbl.cget("text") and "TIỀN" in app.status_lbl.cget("text")
    assert db.find_open_session("CARD1") is None and app.pending is None

    swipe(app, "CARD1")                                              # chưa có lượt vào nữa
    assert "CHƯA CÓ LƯỢT VÀO" in app.status_lbl.cget("text")

    rec.set_script(["11111"])                                        # CARD2 ra với biển khác hẳn
    swipe(app, "CARD2")
    assert app.pending is not None and "KHÔNG KHỚP" in app.match_lbl.cget("text")
    assert str(app.confirm_btn.cget("state")) == "disabled"          # chưa có lý do -> chặn
    app.note_var.set("Chủ xe có giấy tờ")
    root.update()
    assert str(app.confirm_btn.cget("state")) == "normal"

    app.plate_var.set("25888")                                       # nhân viên sửa đúng số -> khớp, khỏi lý do
    app.note_var.set("")
    root.update()
    assert "KHỚP" in app.match_lbl.cget("text") and str(app.confirm_btn.cget("state")) == "normal"
    app.confirm_exit()
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert db.find_open_session("CARD2") is None
    assert db.rows[1].match_status == "MATCH" and db.rows[1].plate_out == "25888"


def test_exit_deny_keeps_session_open(root, tmp_path, monkeypatch):
    db = FakeDb()
    EntryService(ScriptedRecognizer(["25888"]), db, str(tmp_path), sleep=lambda s: None) \
        .handle_card("CARD1", lambda: FakeCamera().read())
    app = ExitApp(root, ExitService(ScriptedRecognizer(["11111"]), db, str(tmp_path),
                                    sleep=lambda s: None),
                  FakeCamera(), settings("out", tmp_path, monkeypatch))
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    swipe(app, "CARD1")
    assert app.pending is not None
    app.cancel_pending()
    assert app.pending is None and db.find_open_session("CARD1") is not None
