"""Chạy thật hai màn hình Tkinter (camera/OCR/DB giả). Tự bỏ qua nếu không có màn hình (DISPLAY)."""
import time
import tkinter as tk

import pytest

import config
from helpers import FakeCamera, FakeDb, ScriptedRecognizer
from services.entry_service import EntryService
from services.exit_service import ExitService
from ui.dual_app import DualGateApp
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


# ---------- Một cửa sổ chứa cả hai cổng ----------
class SpyCamera(FakeCamera):
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class SpyRfid:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def make_dual(root, tmp_path, monkeypatch, entry_script=("25888",), exit_script=("25888",)):
    monkeypatch.setenv("IMG_DIR", str(tmp_path))
    db = FakeDb()
    cfg_in, cfg_out = config.load_settings("in", {"IMG_DIR": str(tmp_path)}), \
        config.load_settings("out", {"IMG_DIR": str(tmp_path)})
    rec = ScriptedRecognizer(entry_script)            # MỘT bộ nhận diện dùng chung cho cả hai cổng
    entry_svc = EntryService(rec, db, str(tmp_path), sleep=lambda s: None)
    exit_svc = ExitService(rec, db, str(tmp_path), sleep=lambda s: None)
    app = DualGateApp(root, entry_svc, exit_svc, SpyCamera(), SpyCamera(), cfg_in, cfg_out)
    assert pump(root, lambda: idle(app.entry) and idle(app.exit)
                and app.entry.last_frame is not None and app.exit.last_frame is not None)
    return app, db, rec


def test_dual_window_has_two_camera_panels_and_one_history(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    entry, exit_ = app.entry, app.exit
    assert entry.container is not exit_.container and entry.embedded and exit_.embedded
    assert entry.preview_lbl is not exit_.preview_lbl             # hai khung camera riêng
    assert entry.preview_lbl.cget("image") and exit_.preview_lbl.cget("image")   # cả hai đang có hình
    assert entry.history is exit_.history is app.history          # chỉ MỘT bảng lịch sử
    assert entry.service.recognizer is exit_.service.recognizer   # chỉ MỘT bộ OCR
    assert root.title() == "Bãi đỗ xe RFID + nhận diện biển số — CỔNG VÀO | CỔNG RA"


def test_dual_full_flow_entry_then_exit_in_one_window(root, tmp_path, monkeypatch):
    app, db, _ = make_dual(root, tmp_path, monkeypatch)

    swipe(app.entry, "CARD1")                                     # xe vào ở panel trái
    assert "XE VÀO" in app.entry.status_lbl.cget("text") and len(db.rows) == 1
    assert pump(root, lambda: len(app.history.tree.get_children()) == 1)
    assert app.exit.status_lbl.cget("text") != app.entry.status_lbl.cget("text")   # trạng thái riêng

    swipe(app.exit, "CARD1")                                      # cùng thẻ ra ở panel phải
    assert "XE RA" in app.exit.status_lbl.cget("text") and "TIỀN" in app.exit.status_lbl.cget("text")
    assert db.find_open_session("CARD1") is None
    rows = app.history.tree.get_children()
    assert len(rows) == 1                                         # cập nhật dòng cũ, không thêm dòng mới
    assert db.rows[0].gate_in == "in" and db.rows[0].gate_out == "out"
    assert "5.000" in app.history.tree.item(rows[0], "values")[5]


def test_dual_gates_are_independent(root, tmp_path, monkeypatch):
    """Cổng vào đang chờ nhân viên xác nhận thì cổng ra vẫn quẹt thẻ bình thường (và ngược lại)."""
    app, db, rec = make_dual(root, tmp_path, monkeypatch, entry_script=("25888",))
    swipe(app.entry, "CARD1")                                     # CARD1 vào bãi
    rec.set_script(["2588"])                                      # lần đọc kế tiếp thiếu số
    swipe(app.entry, "CARD2")
    assert app.entry.pending is not None and app.exit.pending is None

    rec.set_script(["25888"])
    swipe(app.exit, "CARD1")                                      # cổng ra không bị cổng vào chặn
    assert "XE RA" in app.exit.status_lbl.cget("text") and app.entry.pending is not None

    app.entry.cancel_pending()
    assert app.entry.pending is None and db.find_open_session("CARD2") is None


def test_dual_space_goes_only_to_panel_under_pointer(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    inside_entry = app.entry.preview_lbl                          # một widget nằm trong panel trái
    monkeypatch.setattr(root, "winfo_containing", lambda x, y: inside_entry)
    assert app.entry._pointer_inside() is True
    assert app.exit._pointer_inside() is False
    monkeypatch.setattr(root, "winfo_containing", lambda x, y: None)   # chuột ngoài cửa sổ
    assert app.entry._pointer_inside() is False and app.exit._pointer_inside() is False


def test_dual_close_stops_both_gates(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    rfids = SpyRfid(), SpyRfid()
    app.entry.rfid, app.exit.rfid = rfids
    app.on_close()
    assert all(r.stopped for r in rfids)
    assert app.entry.camera.released and app.exit.camera.released
    assert app.entry._closing and app.exit._closing
