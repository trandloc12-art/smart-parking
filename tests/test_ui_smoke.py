"""Chạy thật hai màn hình Tkinter (camera/OCR/DB giả). Tự bỏ qua nếu không có màn hình (DISPLAY)."""
import time
import tkinter as tk

import pytest

import config
from helpers import FakeCamera, FakeDb, ScriptedRecognizer
from services.entry_service import EntryService
from services.exit_service import ExitService
from ui.device_status import ARDUINO, DB, DeviceStatusBar, camera_key, reader_key
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


def test_entry_position_offset_warning(root, tmp_path, monkeypatch):
    db, rec = FakeDb(), ScriptedRecognizer([""])
    app = EntryApp(root, EntryService(rec, db, str(tmp_path), sleep=lambda s: None),
                   FakeCamera(), settings("in", tmp_path, monkeypatch))
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    assert not app.offset_lbl.winfo_ismapped()

    # không đọc được số nào -> hiện cảnh báo lệch vị trí, chưa cho lưu
    swipe(app, "CARD1")
    root.update()
    assert app.pending is not None and app.offset_lbl.winfo_ismapped()
    assert "LỆCH VỊ TRÍ" in app.offset_lbl.cget("text")
    assert str(app.save_btn.cget("state")) == "disabled"

    # hủy -> cảnh báo biến mất
    app.cancel_pending()
    root.update()
    assert not app.offset_lbl.winfo_ismapped()

    # lần sau đọc đủ 5 số -> tự lưu, không có cảnh báo
    rec.set_script(["25888"])
    swipe(app, "CARD1")
    assert "XE VÀO" in app.status_lbl.cget("text") and not app.offset_lbl.winfo_ismapped()


class LcdSpy:
    """Giả bộ đọc RFID: chỉ ghi lại các lần gửi lên LCD dưới dạng (cổng, dòng 1, dòng 2)."""

    def __init__(self):
        self.sent = []
        self.servos = []        # (cổng, lệnh, giây giữ mở)

    def send_lcd(self, line1, line2="", gate="in"):
        self.sent.append((gate, line1, line2))
        return True

    def send_servo(self, gate, action="OPEN", hold_seconds=None):
        self.servos.append((gate, action, hold_seconds))
        return True

    def stop(self):
        pass


def make_entry(root, tmp_path, monkeypatch, script):
    db, rec = FakeDb(), ScriptedRecognizer(script)
    app = EntryApp(root, EntryService(rec, db, str(tmp_path), sleep=lambda s: None),
                   FakeCamera(), settings("in", tmp_path, monkeypatch))
    lcd = app.rfid = LcdSpy()
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    return app, db, rec, lcd


def test_entry_lcd_messages(root, tmp_path, monkeypatch):
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, [""])

    app.on_model_ready(None)
    assert lcd.sent[-1] == ("in", "CONG VAO", "MOI QUET THE")

    swipe(app, "NOPE")                                       # thẻ chưa đăng ký
    assert lcd.sent[-2:] == [("in", "DANG KIEM TRA", "VUI LONG CHO"),
                             ("in", "THE CHUA DANG KY", "KHONG CHO VAO")]

    lcd.sent.clear()
    swipe(app, "CARD1")                                      # không đọc được số nào -> lệch vị trí
    assert lcd.sent == [("in", "DANG KIEM TRA", "VUI LONG CHO"), ("in", "XE LECH VI TRI", "HAY CHINH XE")]

    app.cancel_pending()
    assert lcd.sent[-1] == ("in", "CONG VAO", "MOI QUET THE")

    rec.set_script(["2588"])                                 # đọc thiếu số -> cũng là lệch vị trí
    swipe(app, "CARD1")
    assert lcd.sent[-1] == ("in", "XE LECH VI TRI", "HAY CHINH XE")
    app.plate_var.set("25881")                               # nhân viên nhập đủ rồi lưu
    app.save_entry()
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert lcd.sent[-1] == ("in", "XE VAO OK", "BIEN SO 25881")

    rec.set_script(["25888"])
    swipe(app, "CARD1")                                      # thẻ đang ở trong bãi
    assert lcd.sent[-1] == ("in", "THE DA VAO BAI", "KHONG CHO VAO")
    rec.set_script(["25888"])
    swipe(app, "CARD2")                                      # đọc đủ, tự lưu
    assert lcd.sent[-1] == ("in", "XE VAO OK", "BIEN SO 25888")
    assert {g for g, _, _ in lcd.sent} == {"in"}             # cổng vào chỉ nói chuyện với LCD cổng vào


def test_entry_lcd_conflicting_candidates_asks_staff(root, tmp_path, monkeypatch):
    # 5 ảnh: 25888, 25883, 25888, 25883, (không đọc được) -> hòa 2:2, đủ 5 số nhưng chưa chốt được
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, ["25888", "25883", "25888", "25883", ""])
    swipe(app, "CARD1")
    assert app.pending is not None and not app.pending.scan.decided and app.pending.scan.tally
    assert lcd.sent[-1] == ("in", "CHO NHAN VIEN", "XAC NHAN BIEN SO")      # không phải 'lệch vị trí'
    assert not app.offset_lbl.winfo_ismapped()


def make_exit(root, tmp_path, monkeypatch, script, inside=("CARD1", "CARD2")):
    db = FakeDb()
    entry_svc = EntryService(ScriptedRecognizer(["25888"]), db, str(tmp_path), sleep=lambda s: None)
    for uid in inside:                                       # các xe đã vào bãi (biển 25888)
        entry_svc.handle_card(uid, lambda: FakeCamera().read())
    rec = ScriptedRecognizer(script)
    app = ExitApp(root, ExitService(rec, db, str(tmp_path), sleep=lambda s: None), FakeCamera(),
                  settings("out", tmp_path, monkeypatch))
    lcd = app.rfid = LcdSpy()
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    return app, db, rec, lcd


def test_exit_lcd_messages(root, tmp_path, monkeypatch):
    app, db, rec, lcd = make_exit(root, tmp_path, monkeypatch, ["25888"])

    app.on_model_ready(None)
    assert lcd.sent[-1] == ("out", "CONG RA", "MOI QUET THE")

    swipe(app, "NOPE")                                       # thẻ chưa đăng ký
    assert lcd.sent[-2:] == [("out", "DANG KIEM TRA", "VUI LONG CHO"),
                             ("out", "THE CHUA DANG KY", "KHONG CHO RA")]

    swipe(app, "CARD1")                                      # khớp -> ra luôn, hiện tiền (tối thiểu 1 khối = 5.000 đ)
    assert lcd.sent[-1] == ("out", "XE RA OK", "TIEN 5.000 D")

    swipe(app, "CARD1")                                      # đã ra rồi, chưa có lượt vào mới
    assert lcd.sent[-1] == ("out", "THE CHUA VAO BAI", "KHONG CHO RA")

    rec.set_script(["11111"])                                # biển khác hẳn
    swipe(app, "CARD2")
    assert lcd.sent[-1] == ("out", "BIEN KHONG KHOP", "GOI NHAN VIEN")
    app.cancel_pending()                                     # nhân viên từ chối: LCD giữ thông báo, không về "chờ"
    assert lcd.sent[-1] == ("out", "XE CHUA DUOC RA", "GOI NHAN VIEN")
    assert db.find_open_session("CARD2") is not None

    rec.set_script(["25889"])                                # lệch đúng 1 số
    swipe(app, "CARD2")
    assert lcd.sent[-1] == ("out", "BIEN LECH 1 SO", "CHO NHAN VIEN")
    app.note_var.set("Chu xe co giay to")
    app.confirm_exit()                                       # nhân viên duyệt cho ra
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert lcd.sent[-1] == ("out", "XE RA OK", "TIEN 5.000 D")
    assert {g for g, _, _ in lcd.sent} == {"out"}            # cổng ra chỉ nói chuyện với LCD cổng ra


def test_exit_lcd_position_offset_and_tie(root, tmp_path, monkeypatch):
    app, db, rec, lcd = make_exit(root, tmp_path, monkeypatch, [""], inside=("CARD1",))
    swipe(app, "CARD1")                                      # không đọc được số nào -> lệch vị trí
    assert lcd.sent[-1] == ("out", "XE LECH VI TRI", "HAY CHINH XE")
    app.cancel_pending()

    rec.set_script(["25888", "25883", "25888", "25883", ""])     # hòa 2:2 -> nhân viên kiểm tra
    swipe(app, "CARD1")
    assert app.pending is not None and app.pending.scan.tally and not app.pending.scan.decided
    assert lcd.sent[-1] == ("out", "CHO NHAN VIEN", "KIEM TRA BIEN SO")


def test_lcd_exit_ok_formats_money_within_16_columns():
    from ui.exit_app import lcd_exit_ok
    assert lcd_exit_ok(5000) == ("XE RA OK", "TIEN 5.000 D")
    assert lcd_exit_ok(120000) == ("XE RA OK", "TIEN 120.000 D")
    assert lcd_exit_ok(1250000) == ("XE RA OK", "TIEN 1.250.000 D")
    assert lcd_exit_ok(10000000) == ("XE RA OK", "TIEN 10.000.000")        # quá dài thì bỏ chữ D
    assert lcd_exit_ok(99999999999999) == ("XE RA OK", "XEM TREN MAY")      # không cắt cụt thành số sai
    assert lcd_exit_ok(None) == ("XE RA OK", "TIEN ? D")
    for fee in (0, 5000, 10**7, 10**10, 10**15, None):
        assert all(len(line) <= 16 for line in lcd_exit_ok(fee))


def test_dual_lcd_each_gate_drives_its_own_screen(root, tmp_path, monkeypatch):
    app, db, rec = make_dual(root, tmp_path, monkeypatch)
    lcd = app.entry.rfid = app.exit.rfid = LcdSpy()           # MỘT Arduino dùng chung, hai màn LCD
    swipe(app.entry, "CARD1")
    assert lcd.sent[-1] == ("in", "XE VAO OK", "BIEN SO 25888")
    swipe(app.exit, "CARD1")
    assert lcd.sent[-1] == ("out", "XE RA OK", "TIEN 5.000 D")
    by_gate = {"in": [m for g, *m in lcd.sent if g == "in"], "out": [m for g, *m in lcd.sent if g == "out"]}
    assert ["XE RA OK", "TIEN 5.000 D"] not in by_gate["in"] and ["XE VAO OK", "BIEN SO 25888"] not in by_gate["out"]


def test_entry_works_without_lcd(root, tmp_path, monkeypatch):
    """Arduino cũ / không có LCD / chưa gắn RFID: mọi thứ vẫn chạy như trước."""
    db, rec = FakeDb(), ScriptedRecognizer(["25888"])
    app = EntryApp(root, EntryService(rec, db, str(tmp_path), sleep=lambda s: None),
                   FakeCamera(), settings("in", tmp_path, monkeypatch))
    assert app.rfid is None
    assert pump(root, lambda: idle(app) and app.last_frame is not None)
    swipe(app, "CARD1")
    assert len(db.rows) == 1 and "XE VÀO" in app.status_lbl.cget("text")


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


class BrokenCamera(FakeCamera):
    """Camera không mở được (CLOSED) hoặc mất tín hiệu (NO_SIGNAL), chỉnh được trong lúc chạy."""

    def __init__(self, state="closed"):
        self.state = state

    def open(self, index):
        return self.state not in ("closed",)

    def status(self):
        return self.state

    def read(self):
        return None


def make_dual(root, tmp_path, monkeypatch, entry_script=("25888",), exit_script=("25888",),
              exit_camera=None, wait=True):
    monkeypatch.setenv("IMG_DIR", str(tmp_path))
    db = FakeDb()
    cfg_in, cfg_out = config.load_settings("in", {"IMG_DIR": str(tmp_path)}), \
        config.load_settings("out", {"IMG_DIR": str(tmp_path)})
    rec = ScriptedRecognizer(entry_script)            # MỘT bộ nhận diện dùng chung cho cả hai cổng
    entry_svc = EntryService(rec, db, str(tmp_path), sleep=lambda s: None)
    exit_svc = ExitService(rec, db, str(tmp_path), sleep=lambda s: None)
    app = DualGateApp(root, entry_svc, exit_svc, SpyCamera(), exit_camera or SpyCamera(), cfg_in, cfg_out)
    if wait:
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


# ---------------------------------------------------------------- tình trạng thiết bị
def test_device_bar_alerts_only_on_real_problems(root):
    bar = DeviceStatusBar(root, [("in", "CỔNG VÀO"), ("out", "CỔNG RA")], "COM3")
    root.update()
    assert bar.problems() == [] and bar.alert.winfo_manager() == ""       # chưa có lỗi: không có dải đỏ

    bar.set(ARDUINO, False, "Arduino: MẤT KẾT NỐI COM3")
    bar.set(reader_key("in"), None, "Đầu đọc CỔNG VÀO: chưa rõ")           # "chưa rõ" không phải lỗi
    root.update()
    assert bar.problems() == ["Arduino (COM3)"]
    assert bar.alert.winfo_manager() == "pack" and "Arduino (COM3)" in bar.alert.cget("text")
    assert "Đầu đọc" not in bar.alert.cget("text")

    bar.set(camera_key("out"), False, "Camera CỔNG RA: KHÔNG MỞ ĐƯỢC")
    assert bar.problems() == ["Arduino (COM3)", "Camera CỔNG RA"]
    assert "Camera CỔNG RA" in bar.alert.cget("text")

    bar.set(ARDUINO, True, "Arduino: đã kết nối COM3")
    bar.set(camera_key("out"), True, "Camera CỔNG RA: có hình")
    root.update()
    assert bar.problems() == [] and bar.alert.winfo_manager() == ""       # hết lỗi: dải đỏ tự ẩn


def test_single_gate_window_has_its_own_device_bar(root, tmp_path, monkeypatch):
    app = EntryApp(root, EntryService(ScriptedRecognizer(["25888"]), FakeDb(), str(tmp_path), sleep=lambda s: None),
                   FakeCamera(), settings("in", tmp_path, monkeypatch))
    assert set(app.devices.titles) == {ARDUINO, reader_key("in"), camera_key("in"), DB}   # không có thiết bị cổng kia
    assert pump(root, lambda: app.devices.state[camera_key("in")][0] is True)
    app.handle_reader_status(False)
    assert pump(root, lambda: app.devices.problems() == ["Đầu đọc CỔNG VÀO"])


def test_dual_window_shows_one_shared_device_bar(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    assert app.entry.devices is app.exit.devices is app.devices
    assert set(app.devices.titles) == {ARDUINO, DB, reader_key("in"), reader_key("out"),
                                       camera_key("in"), camera_key("out")}
    assert app.devices.frame.winfo_manager() == "grid"
    assert app.devices.state[camera_key("in")][0] is True and app.devices.state[camera_key("out")][0] is True


def test_dual_names_the_camera_that_is_not_connected(root, tmp_path, monkeypatch):
    broken = BrokenCamera("closed")
    app, _, _ = make_dual(root, tmp_path, monkeypatch, exit_camera=broken, wait=False)
    root.update()
    assert app.devices.problems() == ["Camera CỔNG RA"]
    assert "KHÔNG MỞ ĐƯỢC" in app.devices.state[camera_key("out")][1]
    assert app.devices.state[camera_key("in")][0] is True                 # camera cổng vào vẫn tốt

    broken.state = "no_signal"                                            # cắm lại nhưng không có hình
    app.exit.update_camera_status()
    assert "MẤT TÍN HIỆU" in app.devices.state[camera_key("out")][1]
    broken.state = "ok"
    app.exit.update_camera_status()
    assert app.devices.problems() == []


def test_dual_reports_sql_server_down_and_up(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    app.entry.on_history_error(RuntimeError("không kết nối được"))
    assert app.devices.problems() == ["SQL Server"]
    app.entry.apply_history([])
    assert app.devices.problems() == []


class LiveSerial:
    """Cổng Serial giả cho luồng đọc thật: phát các dòng rồi im lặng (như Arduino đang chờ thẻ)."""

    def __init__(self, lines):
        self.lines = [line.encode() for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        time.sleep(0.02)
        return b""


def test_one_arduino_feeds_both_gates_and_shows_reader_fault(root, tmp_path, monkeypatch):
    """Đường đi thật: Arduino -> luồng đọc -> đúng cổng -> giao diện. Đầu đọc RA hỏng chỉ bị báo ở cổng RA."""
    import main
    app, db, _ = make_dual(root, tmp_path, monkeypatch)
    lines = ["# san sang\n", "STATUS:IN=1,OUT=0\n", "IN:CARD1\n"]
    reader = main._make_rfid(config.load_settings("in", {}), {"in": app.entry, "out": app.exit},
                             serial_factory=lambda port, baud, timeout: LiveSerial(lines))
    app.set_rfid(reader)                                       # MỘT bộ đọc, khởi động đúng một lần
    assert app.entry.rfid is app.exit.rfid is reader

    assert pump(root, lambda: "XE VÀO" in app.entry.status_lbl.cget("text")), \
        "thẻ gửi từ Arduino với tiền tố IN: phải vào cổng VÀO"
    assert len(db.rows) == 1 and db.rows[0].card_uid == "CARD1" and db.rows[0].gate_in == "in"
    assert app.exit.pending is None and app.exit.status_lbl.cget("text") != app.entry.status_lbl.cget("text")

    assert pump(root, lambda: app.devices.problems() == ["Đầu đọc CỔNG RA"])
    assert app.devices.state[ARDUINO][0] is True and app.devices.state[reader_key("in")][0] is True
    app.on_close()
    assert reader._running is False


class LiveSerialW(LiveSerial):
    """LiveSerial có write(): ghi lại byte gửi xuống Arduino."""

    def __init__(self, lines):
        super().__init__(lines)
        self.sent = []

    def write(self, data):
        self.sent.append(data)


def test_real_reader_sends_lcd_and_servo_commands_to_the_right_gate(root, tmp_path, monkeypatch):
    """Đường đi thật: quẹt thẻ -> giao diện -> ArduinoRfidReader.send_lcd / send_servo -> byte gửi xuống cổng COM."""
    import main
    app, db, _ = make_dual(root, tmp_path, monkeypatch)
    ser = LiveSerialW(["STATUS:IN=1,OUT=1\n", "IN:CARD1\n"])
    reader = main._make_rfid(config.load_settings("in", {}), {"in": app.entry, "out": app.exit},
                             serial_factory=lambda port, baud, timeout: ser)
    app.set_rfid(reader)
    assert pump(root, lambda: "XE VÀO" in app.entry.status_lbl.cget("text"))
    assert pump(root, lambda: b"LCDIN:XE VAO OK|BIEN SO 25888\n" in ser.sent)
    assert pump(root, lambda: b"SERVOIN:OPEN:3000\n" in ser.sent)       # xe vào -> mở servo CỔNG VÀO
    assert b"SERVOOUT:OPEN:3000\n" not in ser.sent                       # servo cổng ra chưa động đậy

    ser.lines.append(b"OUT:CARD1\n")                               # cùng thẻ quẹt ở cổng ra
    assert pump(root, lambda: "XE RA" in app.exit.status_lbl.cget("text"))
    assert pump(root, lambda: b"LCDOUT:XE RA OK|TIEN 5.000 D\n" in ser.sent)
    assert pump(root, lambda: b"SERVOOUT:OPEN:3000\n" in ser.sent)      # xe ra -> mở servo CỔNG RA
    assert ser.sent.count(b"SERVOIN:OPEN:3000\n") == 1                  # servo cổng vào không bị mở lại
    assert all(m.startswith((b"LCDIN:", b"LCDOUT:", b"SERVOIN:", b"SERVOOUT:")) and m.endswith(b"\n")
               for m in ser.sent)
    app.on_close()


def test_arduino_unplugged_is_shown_and_readers_are_not_blamed(root, tmp_path, monkeypatch):
    app, _, _ = make_dual(root, tmp_path, monkeypatch)
    app.entry.handle_reader_status(True)
    app.exit.handle_reader_status(True)
    app.entry.handle_rfid_status(False, "Arduino: MẤT KẾT NỐI COM3")
    app.entry.handle_reader_status(None)
    app.exit.handle_reader_status(None)
    assert pump(root, lambda: app.devices.problems() == ["Arduino (COM3)"])
    assert "MẤT KẾT NỐI" in app.devices.state[ARDUINO][1]
    assert app.devices.state[reader_key("in")][0] is None and app.devices.state[reader_key("out")][0] is None


# ---------------------------------------------------------------- LCD tự quay về "MOI QUET THE"
def lcd_idle_after(root, lcd, gate, line1, timeout=3.0):
    return pump(root, lambda: lcd.sent[-1] == (gate, line1, "MOI QUET THE"), timeout)


def test_entry_lcd_returns_to_idle_after_done(root, tmp_path, monkeypatch):
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0.3")
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, ["25888"])
    swipe(app, "CARD1")
    assert lcd.sent[-1] == ("in", "XE VAO OK", "BIEN SO 25888")
    assert lcd_idle_after(root, lcd, "in", "CONG VAO"), "LCD cổng vào không tự quay về"

    swipe(app, "NOPE")                                       # thẻ bị từ chối cũng tự quay về
    assert lcd.sent[-1] == ("in", "THE CHUA DANG KY", "KHONG CHO VAO")
    assert lcd_idle_after(root, lcd, "in", "CONG VAO")


def test_exit_lcd_returns_to_idle_after_done(root, tmp_path, monkeypatch):
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0.3")
    app, db, rec, lcd = make_exit(root, tmp_path, monkeypatch, ["25888"])
    swipe(app, "CARD1")
    assert lcd.sent[-1] == ("out", "XE RA OK", "TIEN 5.000 D")
    assert lcd_idle_after(root, lcd, "out", "CONG RA"), "LCD cổng ra không tự quay về"


def test_lcd_keeps_messages_that_need_staff(root, tmp_path, monkeypatch):
    """Thông báo chờ nhân viên / từ chối KHÔNG được tự biến mất."""
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0.2")
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, [""])
    swipe(app, "CARD1")                                      # lệch vị trí, đang chờ nhân viên
    assert lcd.sent[-1] == ("in", "XE LECH VI TRI", "HAY CHINH XE")
    pump(root, lambda: False, timeout=0.8)                   # chờ gấp 4 lần thời gian quay về
    assert lcd.sent[-1] == ("in", "XE LECH VI TRI", "HAY CHINH XE")

    app2, db2, rec2, lcd2 = make_exit(root, tmp_path, monkeypatch, ["25883"])
    swipe(app2, "CARD1")                                     # lệch 1 số
    app2.cancel_pending()                                    # nhân viên từ chối
    assert lcd2.sent[-1] == ("out", "XE CHUA DUOC RA", "GOI NHAN VIEN")
    pump(root, lambda: False, timeout=0.8)
    assert lcd2.sent[-1] == ("out", "XE CHUA DUOC RA", "GOI NHAN VIEN")


def test_lcd_idle_timer_is_cancelled_by_a_new_swipe(root, tmp_path, monkeypatch):
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0.5")
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, ["25888"])
    swipe(app, "CARD1")                                      # hẹn giờ quay về sau 0,5 giây
    rec.set_script([""])
    swipe(app, "CARD2")                                      # quẹt thẻ mới -> hủy hẹn giờ cũ, đang chờ nhân viên
    assert lcd.sent[-1] == ("in", "XE LECH VI TRI", "HAY CHINH XE")
    pump(root, lambda: False, timeout=1.0)
    assert ("in", "CONG VAO", "MOI QUET THE") not in lcd.sent[-2:]
    assert lcd.sent[-1] == ("in", "XE LECH VI TRI", "HAY CHINH XE")


def test_lcd_idle_seconds_zero_disables_revert(root, tmp_path, monkeypatch):
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0")
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, ["25888"])
    swipe(app, "CARD1")
    pump(root, lambda: False, timeout=0.6)
    assert lcd.sent[-1] == ("in", "XE VAO OK", "BIEN SO 25888")


def test_swipe_that_cannot_run_is_shown_on_the_lcd(root, tmp_path, monkeypatch):
    """Quẹt thẻ khi chưa có hình camera / OCR chưa nạp xong: trước đây LCD im lặng, giờ có báo."""
    app, db, rec, lcd = make_entry(root, tmp_path, monkeypatch, ["25888"])
    app.last_frame = None
    app.on_card("CARD1")
    assert lcd.sent[-1] == ("in", "LOI CAMERA", "GOI NHAN VIEN")

    app, db, rec, lcd = make_exit(root, tmp_path, monkeypatch, ["25888"])
    app.service.recognizer.ready = False
    app.on_card("CARD1")
    assert lcd.sent[-1] == ("out", "DANG KHOI DONG", "VUI LONG CHO")


# ---------------------------------------------------------------- servo thanh chắn: chỉ mở khi quẹt thẻ THÀNH CÔNG
def test_entry_servo_opens_only_when_entry_is_accepted(root, tmp_path, monkeypatch):
    app, db, rec, rfid = make_entry(root, tmp_path, monkeypatch, [""])

    swipe(app, "NOPE")                                       # thẻ chưa đăng ký
    assert rfid.servos == []

    swipe(app, "CARD1")                                      # không đọc được số nào -> chờ nhân viên, CHƯA mở
    assert app.pending is not None and rfid.servos == []
    app.cancel_pending()
    assert rfid.servos == []

    rec.set_script(["2588"])
    swipe(app, "CARD1")
    app.plate_var.set("25881")
    app.save_entry()                                         # nhân viên xác nhận -> mở
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert rfid.servos == [("in", "OPEN", 3.0)]

    rec.set_script(["25888"])
    swipe(app, "CARD1")                                      # thẻ đang trong bãi -> không mở thêm
    assert rfid.servos == [("in", "OPEN", 3.0)]

    swipe(app, "CARD2")                                      # đọc đủ, tự lưu -> mở
    assert rfid.servos == [("in", "OPEN", 3.0)] * 2


def test_exit_servo_opens_only_when_exit_is_accepted(root, tmp_path, monkeypatch):
    app, db, rec, rfid = make_exit(root, tmp_path, monkeypatch, ["25888"])

    swipe(app, "NOPE")                                       # thẻ chưa đăng ký
    assert rfid.servos == []

    swipe(app, "CARD1")                                      # biển khớp -> ra luôn, mở
    assert rfid.servos == [("out", "OPEN", 3.0)]

    swipe(app, "CARD1")                                      # chưa có lượt vào -> không mở
    assert rfid.servos == [("out", "OPEN", 3.0)]

    rec.set_script(["11111"])                                # biển không khớp -> giữ xe, không mở
    swipe(app, "CARD2")
    assert app.pending is not None and len(rfid.servos) == 1
    app.cancel_pending()                                     # nhân viên từ chối -> vẫn không mở
    assert len(rfid.servos) == 1

    rec.set_script(["25889"])                                # lệch 1 số, nhân viên duyệt -> mở
    swipe(app, "CARD2")
    assert len(rfid.servos) == 1
    app.note_var.set("Chu xe co giay to")
    app.confirm_exit()
    assert pump(root, lambda: app.pending is None and not app.busy)
    assert rfid.servos == [("out", "OPEN", 3.0)] * 2
    assert {g for g, _, _ in rfid.servos} == {"out"}         # cổng ra chỉ điều khiển servo cổng ra


def test_dual_each_gate_drives_its_own_servo(root, tmp_path, monkeypatch):
    app, db, rec = make_dual(root, tmp_path, monkeypatch)
    rfid = app.entry.rfid = app.exit.rfid = LcdSpy()          # MỘT Arduino dùng chung, hai servo
    swipe(app.entry, "CARD1")
    assert rfid.servos == [("in", "OPEN", 3.0)]
    swipe(app.exit, "CARD1")
    assert rfid.servos == [("in", "OPEN", 3.0), ("out", "OPEN", 3.0)]


def test_servo_uses_configured_hold_time_and_can_be_disabled(root, tmp_path, monkeypatch):
    monkeypatch.setenv("SERVO_OPEN_SECONDS", "6")
    app, db, rec, rfid = make_entry(root, tmp_path, monkeypatch, ["25888"])
    swipe(app, "CARD1")
    assert rfid.servos == [("in", "OPEN", 6.0)]

    monkeypatch.setenv("SERVO_ENABLED", "0")                  # chưa gắn servo -> không gửi lệnh nào
    app2, db2, rec2, rfid2 = make_entry(root, tmp_path, monkeypatch, ["25888"])
    swipe(app2, "CARD1")
    assert len(db2.rows) == 1 and rfid2.servos == []


def test_open_barrier_never_breaks_card_handling(root, tmp_path, monkeypatch):
    app, db, rec, rfid = make_entry(root, tmp_path, monkeypatch, ["25888"])

    app.rfid = None                                           # chưa có Arduino
    assert app.open_barrier() is False

    app.rfid = object()                                       # firmware/bộ đọc cũ không có send_servo
    assert app.open_barrier() is False

    class Broken:
        def send_servo(self, *a, **k):
            raise RuntimeError("cổng COM hỏng")

    app.rfid = Broken()
    swipe(app, "CARD1")                                       # servo lỗi nhưng xe vẫn được ghi nhận
    assert len(db.rows) == 1 and "XE VÀO" in app.status_lbl.cget("text")
