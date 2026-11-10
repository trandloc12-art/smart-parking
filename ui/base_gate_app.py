"""Giao diện Tkinter dùng chung cho cổng vào và cổng ra.

Lớp này lo: camera trực tiếp, nhận thẻ RFID, chạy việc nặng ở luồng nền, ô 5 số, bảng lịch sử.
Phần riêng của mỗi cổng nằm ở entry_app.py / exit_app.py (override các hook build_*, on_gate_outcome...).

Hai cách dùng:
  - Cửa sổ riêng: BaseGateApp(root, service, camera, cfg) tự dựng cửa sổ + bảng lịch sử + thanh tình trạng thiết bị.
  - Nhúng vào cửa sổ chung (ui/dual_app.py): truyền thêm container=<Frame>, history=<HistoryTable>,
    devices=<DeviceStatusBar> và slots=<SlotCounter> (dùng chung cho cả hai cổng).
"""
import queue
import time
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import Any, Callable
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.plate_voting import NUMBER_LEN
from hardware import camera as cam_state
from services.gate_service import Outcome
from services.gate_service import now as current_time
from ui.device_status import ARDUINO, DB, DeviceStatusBar, camera_key, reader_key
from ui.slots import SlotCounter

COLOR_OK = "#1a7f37"
COLOR_WARN = "#b35900"
COLOR_ERR = "#c62828"
HISTORY_REFRESH_MS = 5000       # làm mới lịch sử để thấy cả lượt do cổng kia ghi
CAMERA_CHECK_MS = 1000          # kiểm tra camera còn có hình không

PASS_WAIT_MARGIN_SECONDS = 15.0  # chờ thêm ngần này giây (ngoài SERVO_OPEN_SECONDS) mà Arduino vẫn im thì coi như xe KHÔNG qua
PASS_WAIT_MAX_SECONDS = 300.0    # Arduino còn kết nối (còn nhịp tim) thì xe đang đứng ở cảm biến trước được chờ tiếp, tối đa ngần này giây


@dataclass
class PassTicket:
    """Một phiên quẹt thẻ đã được chấp nhận nhưng CHƯA ghi vào SQL Server: chờ cảm biến hồng ngoại xác nhận xe đã đi
    qua thanh chắn. Xe qua -> commit() ghi vào CSDL; xe không qua -> bỏ phiên, không lưu gì."""
    card_uid: str
    number: str                         # 5 số biển (để hiển thị)
    commit: Callable[[], Any]           # chạy ở luồng nền: ghi vào SQL Server, trả về AccessEvent
    on_committed: Callable[[Any], None] # chạy ở luồng GUI sau khi ghi xong


MATCH_TEXT = {"MATCH": "Khớp", "APPROVED_CLOSE": "Lệch 1 số (đã duyệt)",
              "APPROVED_MISMATCH": "Không khớp (đã duyệt)"}


def to_photo(bgr, w, h):
    img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    img.thumbnail((w, h))
    return ImageTk.PhotoImage(img)


def fmt_time(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def fmt_money(v):
    return "" if v is None else f"{v:,}".replace(",", ".") + " đ"


def fmt_duration(td):
    h, m = divmod(int(td.total_seconds() // 60), 60)
    return f"{h} giờ {m} phút" if h else f"{m} phút"


def plate_position_offset(scan):
    """True nếu không khung hình nào đọc đủ NUMBER_LEN số -> thường do xe đứng lệch vị trí so với camera
    (biển nằm ngoài khung, quá xa/gần, nghiêng). Trường hợp có ứng viên đủ 5 số nhưng chưa đủ phiếu
    thì KHÔNG tính là lệch vị trí (đó là OCR chưa chắc chắn, nhân viên tự xác nhận)."""
    return scan is not None and not scan.decided and not scan.tally


# Nội dung màn LCD 1602 dùng chung cho cả hai cổng: (dòng 1, dòng 2), mỗi dòng tối đa 16 ký tự
# (hardware.rfid.lcd_text tự bỏ dấu tiếng Việt). Phần riêng từng cổng là thuộc tính LCD_* của EntryApp / ExitApp.
LCD_CHECKING = ("DANG KIEM TRA", "VUI LONG CHO")
LCD_ERROR = ("LOI HE THONG", "GOI NHAN VIEN")
LCD_LOADING = ("DANG KHOI DONG", "VUI LONG CHO")      # quẹt thẻ khi OCR chưa nạp xong
LCD_NO_CAMERA = ("LOI CAMERA", "GOI NHAN VIEN")        # quẹt thẻ nhưng camera chưa có hình
LCD_FULL = ("BAI DA DAY", "HET CHO")                   # cổng vào: bãi đã đủ số chỗ, không nhận quẹt thẻ


class HistoryTable:
    """Bảng lịch sử gửi xe. Một bảng có thể dùng chung cho nhiều cổng trong cùng một cửa sổ."""
    COLUMNS = (("time_in", "Giờ vào", 135), ("card", "Mã thẻ", 85), ("plate", "5 số vào", 75),
               ("time_out", "Giờ ra", 135), ("plate_out", "5 số ra", 70), ("fee", "Tiền", 80),
               ("match", "Đối chiếu", 120), ("note", "Lý do", 160))

    def __init__(self, parent, height=6):
        self.frame = ttk.LabelFrame(parent, text="Lịch sử gửi xe (từ SQL Server, cả hai cổng)",
                                    padding=5)
        self.tree = ttk.Treeview(self.frame, columns=[c[0] for c in self.COLUMNS],
                                 show="headings", height=height)
        for col, text, width in self.COLUMNS:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)
        sb = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.rows = {}              # id lượt gửi xe -> dòng trong bảng
        self._sig = None

    @staticmethod
    def _row(e):
        return (fmt_time(e.time_in), e.card_uid, e.plate_number, fmt_time(e.time_out),
                e.plate_out, fmt_money(e.fee), MATCH_TEXT.get(e.match_status, ""), e.override_note)

    def upsert(self, event):
        """Thêm dòng mới (xe vào) hoặc cập nhật dòng có sẵn (xe ra)."""
        iid = self.rows.get(event.id)
        if iid is not None:
            self.tree.item(iid, values=self._row(event))
        else:
            self.rows[event.id] = self.tree.insert("", 0, values=self._row(event))

    def apply(self, events):
        """Thay toàn bộ bảng bằng `events` (mới nhất trước). Bỏ qua nếu không có gì thay đổi."""
        sig = tuple((e.id, e.time_out, e.match_status) for e in events)
        if sig == self._sig:
            return
        self._sig = sig
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for e in events:
            self.rows[e.id] = self.tree.insert("", "end", values=self._row(e))


class BaseGateApp:
    BANNER_COLOR = "#1a7f37"
    RESULT_TITLE = "Ảnh đã chụp"
    NUMBER_HINT = f"{NUMBER_LEN} số ở dòng dưới biển số (bắt buộc đủ {NUMBER_LEN} số):"

    # Nội dung LCD của cổng này (EntryApp / ExitApp ghi đè phần riêng)
    LCD_IDLE = ("MOI QUET THE", "")
    LCD_UNREGISTERED = ("THE CHUA DANG KY", "")
    LCD_ALREADY_INSIDE = ("THE DA VAO BAI", "")
    LCD_NOT_INSIDE = ("THE CHUA VAO BAI", "")
    LCD_OFFSET = ("XE LECH VI TRI", "HAY CHINH XE")        # không đọc được số nào: xe lệch vị trí so với camera
    LCD_NEED_STAFF = ("CHO NHAN VIEN", "KIEM TRA BIEN SO")  # có ứng viên đủ 5 số nhưng chưa chốt được
    LCD_WAIT_PASS = ("MOI XE DI QUA", "THANH CHAN")         # đã mở thanh chắn, chờ cảm biến báo xe đã qua
    LCD_PASS_CANCELLED = ("XE CHUA QUA", "HAY QUET LAI THE")  # xe không đi qua: hủy phiên quẹt thẻ
    LCD_CANCEL_SECONDS = 2.0        # giây: thông báo hủy hiện ngần này rồi LCD về màn hình chờ

    def __init__(self, root, service, camera, cfg, container=None, history=None, devices=None, slots=None):
        """root: cửa sổ Tk (dùng cho after/bind). container: khung để dựng giao diện vào
        (None = dựng thẳng vào root và tự lo tiêu đề/đóng cửa sổ). history: bảng lịch sử dùng chung
        (None = tự tạo bảng riêng ở cuối giao diện). devices: thanh tình trạng thiết bị dùng chung
        (None = tự tạo thanh riêng cho cổng này). slots: bộ đếm chỗ trống dùng chung của bãi
        (None = tự tạo theo service.capacity)."""
        self.root = root
        self.embedded = container is not None
        self.container = container if self.embedded else root
        self.service = service
        self.camera = camera
        self.cfg = cfg
        self.view_w, self.view_h = cfg.view_w, cfg.view_h
        self.rfid = None

        if not self.embedded:
            root.title(f"{cfg.label} - Bãi đỗ xe RFID + nhận diện biển số")
            root.protocol("WM_DELETE_WINDOW", self.on_close)
            if cfg.window_pos:
                root.geometry(cfg.window_pos)

        self.q = queue.Queue()      # luồng nền -> luồng GUI
        self.busy = False
        self.pending = None         # CardOutcome đang chờ nhân viên xử lý
        self.last_frame = None
        self.history = history      # None -> build_ui tự tạo
        self.devices = devices      # None -> build_ui tự tạo
        self.camera_index = cfg.camera_index
        self._history_loading = False
        self._closing = False
        self._lcd_job = None        # hẹn giờ đưa LCD về "MOI QUET THE" (xem lcd)
        self._awaiting = None           # PassTicket: phiên quẹt thẻ đã mở thanh chắn, chờ cảm biến báo xe đã qua (chưa lưu)
        self._pass_job = None           # hẹn giờ dự phòng khi Arduino không báo PASS / NOPASS
        self._pass_started = None       # lúc bắt đầu chờ xe qua (time.monotonic), để giới hạn tổng thời gian chờ
        self._servo_btn_state = "normal"    # trạng thái hiện tại của nút Test servo (xem sync_servo_button)
        self.slots = slots if slots is not None else SlotCounter(getattr(service, "capacity", None))
        self.slots.subscribe(self.on_slots_changed)
        self._idle_shown = False        # LCD đang hiện màn hình chờ (để cập nhật số chỗ trống khi nó đổi)
        self._slots_loading = False

        self.build_ui()
        self.open_camera(cfg.camera_index)
        self.poll_camera()
        self.update_loop()

        self.set_status("Đang tải mô hình OCR (lần đầu cần Internet, hơi lâu)...", COLOR_WARN)
        self._bg(self.service.load_model, self.on_model_ready)
        self.refresh_history()

    # ---------- Kết nối thành phần ngoài ----------
    def set_rfid(self, reader, start=True):
        """Gắn bộ đọc RFID dùng chung (ArduinoRfidReader). start=False khi cửa sổ chung đã tự khởi động nó."""
        self.rfid = reader
        if start:
            reader.start()

    def lcd(self, message, revert=False, revert_seconds=None):
        """Hiển thị (dòng 1, dòng 2) lên màn LCD của CỔNG NÀY (cfg.gate: 'in' / 'out') qua Arduino.
        Chưa có Arduino, Arduino không có LCD hay đang mất kết nối thì bỏ qua: LCD chỉ là phần phụ,
        không bao giờ được làm hỏng việc xử lý thẻ.

        revert=True: sau cfg.lcd_idle_seconds giây tự đưa LCD về LCD_IDLE (dùng cho thông báo đã xong việc,
        VD "XE VAO OK"). Thông báo cần nhân viên xử lý thì KHÔNG revert để tài xế còn đọc được."""
        self._cancel_lcd_revert()
        self._idle_shown = False
        send = getattr(self.rfid, "send_lcd", None)
        if send is not None:
            try:
                send(message[0], message[1], gate=self.cfg.gate)
            except Exception:
                pass
        if revert:
            self._schedule_lcd_revert(revert_seconds)

    # ---------- Số chỗ (slot) còn trống ----------
    def idle_message(self):
        """Màn hình chờ của LCD. Có theo dõi số chỗ thì kèm số chỗ trống; chưa biết số chỗ thì như lúc chưa có tính năng này."""
        free, capacity = self.slots.free, self.slots.capacity
        if free is None or capacity is None:
            return self.LCD_IDLE
        return self.lcd_idle_with_slots(free, capacity)

    def lcd_idle_with_slots(self, free, capacity):
        """Màn hình chờ khi biết số chỗ: dòng 1 tên cổng, dòng 2 'CON TRONG: 2/3'. Cổng vào ghi đè khi bãi đầy."""
        return (self.LCD_IDLE[0], f"CON TRONG: {free}/{capacity}")

    def show_idle(self):
        """Đưa LCD về màn hình chờ (có số chỗ trống). Nhớ là đang ở màn hình chờ để tự cập nhật khi số chỗ đổi."""
        self.lcd(self.idle_message())
        self._idle_shown = True

    def on_slots_changed(self):
        """Số chỗ trống vừa đổi (xe vào / ra ở cổng nào cũng được). Chỉ đổi LCD khi nó đang ở màn hình chờ;
        thông báo khác (xe vào OK, chờ nhân viên...) giữ nguyên, lần về màn hình chờ sau sẽ dùng số mới."""
        if (self._idle_shown and not self._closing and not self.busy and self.pending is None
                and self._awaiting is None):
            self.show_idle()

    def refresh_slots(self):
        """Đối chiếu số chỗ trống với SQL Server ở luồng nền (số do hai cổng cộng trừ có thể lệch, VD nhân viên sửa SQL)."""
        if self._closing or self._slots_loading or not self.slots.tracking:
            return
        self._slots_loading = True
        version = self.slots.version
        self._bg(self.service.free_slots, lambda free: self._slots_loaded(free, version),
                 busy=False, on_error=self._slots_failed)

    def _slots_loaded(self, free, version):
        self._slots_loading = False
        self.slots.update(free, version)

    def _slots_failed(self, exc):
        self._slots_loading = False     # lỗi SQL Server đã được báo ở thanh tình trạng (refresh_history)

    def reject_swipe(self, uid):
        """Hook: True nếu cổng này không nhận lần quẹt thẻ này (và đã tự báo). Mặc định nhận hết; cổng vào ghi đè
        để chặn khi bãi đầy."""
        return False

    def can_rescan(self, uid):
        """Hook: True nếu lần quẹt thẻ `uid` được phép THAY ca đang chờ nhân viên (self.pending) để quét lại.
        Mặc định không cho: phải xử lý hoặc Hủy trước. Cổng ra ghi đè cho trường hợp không đọc đủ 5 số."""
        return False

    def pass_gated(self):
        """True khi việc GHI (lưu xe vào / đóng lượt ra) phải CHỜ cảm biến hồng ngoại xác nhận xe đã đi qua thanh chắn.
        Cần cảm biến bật (IR_ENABLED), servo bật (SERVO_ENABLED) và có Arduino để gửi lệnh; thiếu một trong ba thì
        giữ cách cũ: ghi ngay khi quẹt thẻ thành công."""
        return (bool(getattr(self.cfg, "ir_enabled", True)) and bool(getattr(self.cfg, "servo_enabled", True))
                and callable(getattr(self.rfid, "send_servo", None)))

    def open_barrier(self, wait_pass=False):
        """Mở thanh chắn (servo) của CỔNG NÀY khi xe được chấp nhận (quẹt thẻ thành công).
        Arduino tự đóng lại sau cfg.servo_open_seconds giây (hoặc ngay khi cảm biến thấy xe đã qua). Giống LCD:
        chưa có Arduino, mất kết nối hoặc tắt bằng SERVO_ENABLED=0 thì bỏ qua, không bao giờ làm hỏng việc xử lý thẻ.

        wait_pass=True: kèm ân hạn khi xe rời đi (cfg.ir_pass_timeout_seconds): cảm biến trước mất tín hiệu quá ngần đó
        chưa tới cảm biến sau thì Arduino hủy (hạ thanh chắn + NOPASS). Trả về True nếu đã gửi lệnh."""
        if not getattr(self.cfg, "servo_enabled", True):
            return False
        send = getattr(self.rfid, "send_servo", None)
        if send is None:
            return False
        try:
            if wait_pass:
                sent = send(self.cfg.gate, "OPEN", self.cfg.servo_open_seconds, self.cfg.ir_pass_timeout_seconds)
            else:
                sent = send(self.cfg.gate, "OPEN", self.cfg.servo_open_seconds)
        except Exception:
            return False
        return bool(sent)

    # ---------- Chờ xe đi qua thanh chắn rồi mới lưu ----------
    def wait_for_pass(self, ticket):
        """Mở thanh chắn rồi CHỜ cảm biến báo xe đã qua hẳn: PASS -> ghi vào SQL Server (ticket.commit); NOPASS (xe ở
        cảm biến trước mất tín hiệu mà cảm biến sau không thấy xe trong IR_PASS_TIMEOUT_SECONDS, hoặc hết giờ mở) -> HỦY phiên,
        không lưu gì. Không gửi được lệnh mở thanh chắn thì không có gì để chờ: ghi ngay như khi chưa có cảm biến."""
        self.lcd(self.LCD_WAIT_PASS)
        if not self.open_barrier(wait_pass=True):
            self._commit_ticket(ticket, None)
            return
        self._awaiting = ticket
        self._schedule_pass_timeout()
        self.set_status(f"Thẻ {ticket.card_uid}: biển {ticket.number}. Mời xe đi qua thanh chắn. CHƯA lưu vào hệ thống; "
                        "xe không đi qua thì phiên quẹt thẻ này sẽ bị hủy.", COLOR_WARN)
        self.refresh_buttons()

    def _schedule_pass_timeout(self, extend=False):
        self._cancel_pass_timer()
        if not extend:
            self._pass_started = time.monotonic()
        ms = int((self.cfg.servo_open_seconds + PASS_WAIT_MARGIN_SECONDS) * 1000)
        try:
            self._pass_job = self.root.after(ms, self._pass_timed_out)
        except Exception:
            self._pass_job = None

    def _cancel_pass_timer(self):
        job, self._pass_job = self._pass_job, None
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _pass_timed_out(self):
        """Đồng hồ dự phòng đã hết mà Arduino chưa báo PASS / NOPASS.

        Arduino còn kết nối (còn nhịp tim) thì không hủy: cảm biến trước còn tín hiệu (xe đang đứng chờ) nên Arduino
        chủ động chưa hạ thanh chắn (xe còn ở cảm biến trước / sau); nó sẽ tự báo PASS khi xe vào, hoặc NOPASS khi xe rời đi. Chờ tiếp, nhưng không
        quá PASS_WAIT_MAX_SECONDS để một sự cố (Arduino reset giữa chừng...) không treo cổng mãi.
        Arduino mất kết nối / không phản hồi (hoặc quá hạn tối đa): coi như xe KHÔNG qua, hủy phiên."""
        self._pass_job = None
        if self._awaiting is None or self._closing:
            return
        started = self._pass_started
        waited = (time.monotonic() - started) if started is not None else None
        arduino_alive = self.devices.state.get(ARDUINO, (None, ""))[0] is True
        if arduino_alive and waited is not None and waited < PASS_WAIT_MAX_SECONDS:
            self._schedule_pass_timeout(extend=True)
            return
        self.on_barrier_result(False, current_time())

    def _commit_ticket(self, ticket, at):
        """Ghi phiên vào SQL Server (ở luồng nền). at: lúc cảm biến báo xe qua (None = không có cảm biến để ghi)."""
        def done(event):
            ticket.on_committed(event)
            if at is not None:
                self._bg(lambda: self.service.record_pass(event.id, True, at), lambda _: None,
                         busy=False, on_error=self.on_pass_record_error)
        self._bg(ticket.commit, done)

    def _cancel_ticket(self, ticket):
        """Xe không đi qua thanh chắn: bỏ phiên quẹt thẻ, KHÔNG ghi gì (không lượt vào/ra, không biển số, không ảnh)."""
        self.lcd(self.LCD_PASS_CANCELLED, revert=True, revert_seconds=self.LCD_CANCEL_SECONDS)
        self.plate_var.set("")
        self.set_card(None)
        self.on_pass_cancelled(ticket)
        self.set_status(f"ĐÃ HỦY phiên quẹt thẻ {ticket.card_uid} (biển {ticket.number}): xe rời đi mà không vào "
                        "(cảm biến trước mất tín hiệu, cảm biến sau không thấy xe). Không lưu gì vào hệ thống. Hãy quẹt lại thẻ khi xe vào đúng vị trí.",
                        COLOR_WARN)
        self.refresh_buttons()

    def on_pass_cancelled(self, ticket):
        """Hook: dọn phần giao diện riêng của cổng khi phiên bị hủy."""

    def test_servo(self):
        """Nút "Test servo": mở thanh chắn của CỔNG NÀY để kiểm tra servo / góc quay, rồi Arduino tự đóng lại sau
        cfg.servo_open_seconds giây. Không gắn với lượt gửi xe nào nên kết quả cảm biến (PASS / NOPASS) của lần thử
        bị bỏ qua, không ghi vào SQL Server. Trả về True nếu đã gửi lệnh."""
        label = self.cfg.label
        if self.busy or self.pending is not None or self._awaiting is not None:
            return False                # đang xử lý một lần quẹt thẻ / chờ nhân viên / chờ xe qua: không mở thanh chắn lúc này
        if not getattr(self.cfg, "servo_enabled", True):
            self.set_status(f"Servo {label} đang tắt (SERVO_ENABLED=0 trong .env). Đặt thành 1 rồi chạy lại để thử.",
                            COLOR_WARN)
            return False
        send = getattr(self.rfid, "send_servo", None)
        sent = False
        if send is not None:
            try:
                sent = bool(send(self.cfg.gate, "OPEN", self.cfg.servo_open_seconds))
            except Exception:
                sent = False
        if sent:
            self.set_status(f"Test servo {label}: đã gửi lệnh mở, thanh chắn tự đóng sau "
                            f"{self.cfg.servo_open_seconds:g} giây.", COLOR_OK)
        else:
            self.set_status(f"Test servo {label}: KHÔNG gửi được lệnh (Arduino chưa kết nối). "
                            "Xem thanh tình trạng thiết bị phía trên.", COLOR_ERR)
        return sent

    def handle_barrier(self, passed):
        """Arduino báo kết quả lần mở thanh chắn của cổng này: passed=True xe đã qua hẳn, False hết giờ mà chưa qua.
        Gọi được từ luồng nền: chuyển sang luồng GUI."""
        at = current_time()
        self.q.put(lambda: self.on_barrier_result(passed, at))

    def on_barrier_result(self, passed, at):
        """Kết quả lần mở thanh chắn của phiên đang chờ: xe qua hẳn -> ghi vào SQL Server; không qua -> hủy phiên.
        Không có phiên nào đang chờ (VD nút Test servo, hoặc lệnh gõ tay) thì bỏ qua."""
        if not getattr(self.cfg, "ir_enabled", True):
            return                      # chưa gắn cảm biến hồng ngoại
        ticket, self._awaiting = self._awaiting, None
        if ticket is None:
            return
        self._cancel_pass_timer()
        if passed:
            self._commit_ticket(ticket, at)
        else:
            self._cancel_ticket(ticket)

    def on_pass_record_error(self, exc):
        self.devices.set(DB, False, f"SQL Server: LỖI ({str(exc)[:60]})")

    def _cancel_lcd_revert(self):
        job, self._lcd_job = self._lcd_job, None
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _schedule_lcd_revert(self, seconds=None):
        if seconds is None:
            seconds = self.cfg.lcd_idle_seconds
        if seconds <= 0 or self._closing:
            return
        try:
            self._lcd_job = self.root.after(int(seconds * 1000), self._lcd_back_to_idle)
        except Exception:
            self._lcd_job = None

    def _lcd_back_to_idle(self):
        self._lcd_job = None
        if self._closing or self.pending is not None or self._awaiting is not None:
            return                      # đang chờ nhân viên / chờ xe qua: màn hình phải giữ thông báo hiện tại
        if self.busy:
            self._schedule_lcd_revert() # đang xử lý việc khác: thử lại sau
            return
        self.show_idle()

    def handle_card(self, uid):
        """Gọi được từ luồng nền: chuyển sang luồng GUI."""
        self.q.put(lambda: self.on_card(uid))

    def handle_rfid_status(self, connected, message):
        """Tình trạng Arduino (cổng COM). Gọi được từ luồng nền."""
        self.q.put(lambda: self.devices.set(ARDUINO, connected, message))

    def handle_reader_status(self, ok):
        """Tình trạng đầu đọc RFID của cổng này: True / False / None (chưa rõ). Gọi được từ luồng nền."""
        label = self.cfg.label
        if ok:
            text = f"Đầu đọc {label}: hoạt động"
        elif ok is False:
            text = f"Đầu đọc {label}: KHÔNG NHẬN ĐƯỢC module RFID (kiểm tra dây nối)"
        else:
            text = f"Đầu đọc {label}: chưa rõ"
        self.q.put(lambda: self.devices.set(reader_key(self.cfg.gate), ok, text))

    # ---------- Giao diện ----------
    def build_ui(self):
        tk.Label(self.container, text=self.cfg.label, bg=self.BANNER_COLOR, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(fill="x")
        if self.devices is None:        # chạy một cổng: thanh tình trạng riêng, nằm dưới tiêu đề
            self.devices = DeviceStatusBar(self.container, [(self.cfg.gate, self.cfg.label)],
                                           self.cfg.rfid_port)
            self.devices.frame.pack(fill="x")
        main = ttk.Frame(self.container, padding=8)
        main.pack(fill="both", expand=True)

        left = ttk.LabelFrame(main, text="Camera trực tiếp", padding=5)
        left.grid(row=0, column=0, padx=5, pady=5, sticky="n")
        lf = tk.Frame(left, width=self.view_w, height=self.view_h, bg="black")
        lf.pack_propagate(False)
        lf.pack()
        self.preview_lbl = tk.Label(lf, bg="black", fg="white", text="Chưa có camera")
        self.preview_lbl.pack(fill="both", expand=True)

        right = ttk.LabelFrame(main, text=self.RESULT_TITLE, padding=5)
        right.grid(row=0, column=1, padx=5, pady=5, sticky="n")
        self.build_result_panel(right)

        # Hàng 1: camera | thẻ + 5 số
        cam_box = ttk.Frame(main)
        cam_box.grid(row=1, column=0, pady=5, sticky="n")
        row = ttk.Frame(cam_box)
        row.pack()
        ttk.Label(row, text="Camera số:").pack(side="left")
        self.cam_var = tk.StringVar(value=str(self.cfg.camera_index))
        tk.Spinbox(row, from_=0, to=5, width=3, textvariable=self.cam_var).pack(side="left", padx=4)
        ttk.Button(row, text="Mở camera", command=self.change_camera).pack(side="left")

        val_box = ttk.Frame(main)
        val_box.grid(row=1, column=1, pady=5, sticky="n")
        self.card_lbl = ttk.Label(val_box, text="Thẻ: —", font=("Consolas", 12, "bold"))
        self.card_lbl.pack()
        ttk.Label(val_box, text=self.NUMBER_HINT).pack()
        self.plate_var = tk.StringVar()
        vcmd = (self.root.register(lambda P: P == "" or (P.isdigit() and len(P) <= NUMBER_LEN)), "%P")
        self.plate_entry = tk.Entry(val_box, textvariable=self.plate_var, width=8,
                                    font=("Consolas", 28, "bold"), justify="center",
                                    validate="key", validatecommand=vcmd)
        self.plate_entry.pack(pady=3)
        self.plate_var.trace_add("write", lambda *_: self.on_number_changed())
        self.build_extra(val_box)
        self.status_lbl = ttk.Label(val_box, text="", wraplength=max(self.view_w, 360))
        self.status_lbl.pack()

        # Hàng 2: nút
        btns = ttk.Frame(main)
        btns.grid(row=2, column=0, columnspan=2, pady=8)
        self.build_buttons(btns)
        trial_text = "📷 Thử nhận diện (Space)" if not self.embedded \
            else "📷 Thử nhận diện (Space khi chuột ở đây)"
        self.capture_btn = ttk.Button(btns, text=trial_text,
                                      command=self.capture, state="disabled")
        self.capture_btn.pack(side="left", padx=5)
        self.open_btn = ttk.Button(btns, text="📁 Thử với ảnh từ máy",
                                   command=self.open_image, state="disabled")
        self.open_btn.pack(side="left", padx=5)
        self.servo_btn = ttk.Button(btns, text="🔧 Test servo", command=self.test_servo)
        self.servo_btn.pack(side="left", padx=5)

        # Hàng 3: lịch sử (cửa sổ chung thì dùng bảng do cửa sổ chung tạo)
        if self.history is None:
            self.history = HistoryTable(main)
            self.history.frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.tree = self.history.tree

        self.root.bind("<space>", self.on_space, add="+")

    # --- Hook cho lớp con ---
    def build_result_panel(self, parent):
        """Khung bên phải. Mặc định: một ảnh kết quả."""
        rf = tk.Frame(parent, width=self.view_w, height=self.view_h, bg="#222")
        rf.pack_propagate(False)
        rf.pack()
        self.result_lbl = tk.Label(rf, bg="#222", fg="white", text="Quẹt thẻ để bắt đầu")
        self.result_lbl.pack(fill="both", expand=True)

    def build_extra(self, parent):
        """Thêm widget giữa ô 5 số và dòng trạng thái."""

    def build_buttons(self, parent):
        """Nút riêng của cổng (đặt bên trái các nút thử)."""

    def update_action_buttons(self):
        """Bật/tắt nút riêng của cổng theo trạng thái hiện tại."""

    def reset_view(self):
        """Gọi khi bắt đầu xử lý một lần quẹt thẻ mới."""

    def on_gate_outcome(self, outcome):
        """Xử lý kết quả riêng của cổng (ENTRY_* hoặc EXIT_*)."""
        raise NotImplementedError

    def handle_error(self, exc):
        self.lcd(LCD_ERROR)
        self.set_status(f"Lỗi: {exc}", COLOR_ERR)

    # --- Tiện ích hiển thị ---
    def _pointer_inside(self):
        """Chuột đang nằm trong khung của cổng này? (chỉ dùng khi hai cổng chung một cửa sổ)"""
        w = self.root.winfo_containing(*self.root.winfo_pointerxy())
        while w is not None:
            if w is self.container:
                return True
            w = w.master
        return False

    def on_space(self, _event):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)):
            return
        if self.embedded and not self._pointer_inside():
            return      # hai cổng cùng nghe phím Space: chỉ cổng đang được trỏ chuột vào mới chạy
        self.capture()

    def on_number_changed(self):
        complete = len(self.plate_var.get()) == NUMBER_LEN
        if self.pending is not None:
            self.plate_entry.configure(fg=COLOR_OK if complete else COLOR_WARN)
        self.update_action_buttons()

    def set_status(self, text, color="black"):
        self.status_lbl.configure(text=text, foreground=color)

    def set_card(self, uid):
        self.card_lbl.configure(text=f"Thẻ: {uid}" if uid else "Thẻ: —")

    def show_image(self, bgr):
        """Hiện ảnh vừa chụp/nhận diện."""
        photo = to_photo(bgr, self.view_w, self.view_h)
        self.result_lbl.configure(image=photo, text="")
        self.result_lbl.image = photo

    def refresh_buttons(self):
        can_trial = self.service.ready and not self.busy and self.pending is None and self._awaiting is None
        for b in (self.capture_btn, self.open_btn):
            b.configure(state="normal" if can_trial else "disabled")
        self.sync_servo_button()
        self.update_action_buttons()

    def sync_servo_button(self):
        """Test servo không cần OCR nạp xong; chỉ khóa khi đang xử lý một lần quẹt thẻ / chờ nhân viên (khỏi mở
        thanh chắn nhầm giữa chừng và khỏi đè dòng trạng thái đang cần nhân viên đọc). `pending` đổi ở nhiều chỗ
        trong lớp con nên được gọi cả từ update_loop; chỉ đụng tới nút khi trạng thái thật sự đổi."""
        state = "normal" if not self.busy and self.pending is None and self._awaiting is None else "disabled"
        if state != self._servo_btn_state:
            self._servo_btn_state = state
            self.servo_btn.configure(state=state)

    # ---------- Chạy việc nặng ở luồng nền ----------
    def _bg(self, fn, on_ok, busy=True, on_error=None):
        if busy:
            self.busy = True
            self.refresh_buttons()

        def work():
            try:
                res = fn()
            except Exception as e:
                self.q.put(lambda e=e: self.on_fail(e, busy, on_error))
            else:
                self.q.put(lambda: self.on_done(on_ok, res, busy))

        threading.Thread(target=work, daemon=True).start()

    def on_done(self, on_ok, res, busy):
        if busy:
            self.busy = False
            self.refresh_buttons()
        on_ok(res)

    def on_fail(self, exc, busy, on_error=None):
        if busy:
            self.busy = False
            self.refresh_buttons()
        (on_error or self.handle_error)(exc)

    # ---------- Camera ----------
    def open_camera(self, index):
        self.camera_index = index
        if not self.camera.open(index):
            self.preview_lbl.configure(image="", text=f"Không mở được camera {index}")
            self.last_frame = None
        self.update_camera_status()

    def update_camera_status(self):
        """Báo lên thanh tình trạng: camera của cổng này đang có hình, mất tín hiệu hay không mở được."""
        label, state = self.cfg.label, self.camera.status()
        if state == cam_state.OK:
            ok, text = True, f"Camera {label}: có hình"
        elif state == cam_state.STARTING:
            ok, text = None, f"Camera {label}: đang khởi động..."
        elif state == cam_state.NO_SIGNAL:
            ok, text = False, (f"Camera {label}: MẤT TÍN HIỆU (số {self.camera_index}). "
                               "Kiểm tra dây, rồi bấm 'Mở camera'")
        else:
            ok, text = False, (f"Camera {label}: KHÔNG MỞ ĐƯỢC (số {self.camera_index}). "
                               "Đổi số camera rồi bấm 'Mở camera'")
        self.devices.set(camera_key(self.cfg.gate), ok, text)

    def poll_camera(self):
        if self._closing:
            return
        self.update_camera_status()
        self.root.after(CAMERA_CHECK_MS, self.poll_camera)

    def change_camera(self):
        try:
            self.open_camera(int(self.cam_var.get()))
        except ValueError:
            pass

    def update_loop(self):
        if self._closing:
            return
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                break

        self.sync_servo_button()
        frame = self.camera.read()
        if frame is not None:
            self.last_frame = frame
            photo = to_photo(frame, self.view_w, self.view_h)
            self.preview_lbl.configure(image=photo, text="")
            self.preview_lbl.image = photo
        self.root.after(30, self.update_loop)

    # ---------- Quẹt thẻ ----------
    def on_model_ready(self, _):
        self.set_status("Sẵn sàng. Quẹt thẻ.", COLOR_OK)
        self.show_idle()

    def get_frame(self):
        """Khung hình mới nhất. Được gọi từ luồng nền: chỉ đọc tham chiếu, không đụng camera."""
        return self.last_frame

    def on_card(self, uid):
        if not self.service.ready:
            self.lcd(LCD_LOADING)
            self.set_status(f"Thẻ {uid}: mô hình OCR chưa sẵn sàng, quẹt lại sau.", COLOR_WARN)
            return
        if self._awaiting is not None:
            self.set_status(f"Đang chờ xe của thẻ {self._awaiting.card_uid} đi qua thanh chắn. "
                            f"Thẻ {uid}: quẹt lại sau.", COLOR_WARN)
            return
        if self.busy:
            self.set_status(f"Thẻ {uid}: đang xử lý, quẹt lại sau.", COLOR_WARN)
            return
        if self.pending is not None:
            if not self.can_rescan(uid):
                self.set_status(f"Còn thẻ {self.pending.card_uid} chờ xác nhận. "
                                "Hãy xử lý hoặc Hủy trước khi quẹt thẻ mới.", COLOR_WARN)
                return
            self.pending = None         # chưa ghi gì vào DB nên bỏ ca cũ rồi quét lại bình thường
            self.plate_var.set("")
            self.reset_view()           # ẩn cảnh báo / xóa phần hiển thị của ca cũ (kể cả khi lần quẹt này bị từ chối ngay sau đó)
            self.update_action_buttons()
        if self.last_frame is None:
            self.lcd(LCD_NO_CAMERA)
            self.set_status(f"Thẻ {uid}: chưa có hình từ camera.", COLOR_ERR)
            return
        if self.reject_swipe(uid):
            return

        self.reset_view()
        self.lcd(LCD_CHECKING)
        self.plate_var.set("")
        self.set_card(uid)
        self.set_status(f"Thẻ {uid}: đang kiểm tra...", COLOR_WARN)

        def progress(done, total):
            self.q.put(lambda: self.set_status(
                f"Thẻ {uid}: đang quét ảnh {done}/{total}...", COLOR_WARN))

        if self.pass_gated():       # chốt được xe thì CHƯA lưu: chờ cảm biến báo xe đã đi qua thanh chắn
            run = lambda: self.service.handle_card(uid, self.get_frame, progress, defer=True)  # noqa: E731
        else:
            run = lambda: self.service.handle_card(uid, self.get_frame, progress)              # noqa: E731
        self._bg(run, self.on_card_outcome)

    def on_card_outcome(self, outcome):
        uid, event, kind = outcome.card_uid, outcome.event, outcome.kind
        if kind is Outcome.UNREGISTERED:
            self.lcd(self.LCD_UNREGISTERED, revert=True)
            self.set_status(f"THẺ {uid} CHƯA ĐĂNG KÝ. Không nhận diện, không lưu.", COLOR_ERR)
        elif kind is Outcome.ALREADY_INSIDE:
            self.lcd(self.LCD_ALREADY_INSIDE, revert=True)
            where = (f" (vào {fmt_time(event.time_in)}, biển {event.plate_number})" if event else "")
            self.set_status(f"THẺ {uid} ĐANG Ở TRONG BÃI{where}. Không cho vào lần nữa.", COLOR_ERR)
        elif kind is Outcome.NOT_INSIDE:
            self.lcd(self.LCD_NOT_INSIDE, revert=True)
            self.set_status(f"THẺ {uid} CHƯA CÓ LƯỢT VÀO. Xe chưa vào bãi nên không thể ra.", COLOR_ERR)
        else:
            self.on_gate_outcome(outcome)

    # ---------- Chế độ thử (không có thẻ -> không lưu) ----------
    def capture(self):
        if self.busy or not self.service.ready or self.pending is not None or self._awaiting is not None:
            return
        if self.last_frame is None:
            self.set_status("Chưa có hình từ camera.", COLOR_ERR)
            return
        self.run_trial(self.last_frame.copy())

    def open_image(self):
        if self.busy or not self.service.ready or self.pending is not None or self._awaiting is not None:
            return
        path = filedialog.askopenfilename(
            title="Chọn ảnh xe",
            filetypes=[("Ảnh", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Tất cả", "*.*")])
        if not path:
            return
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            messagebox.showerror("Lỗi", "Không đọc được file ảnh này.")
            return
        self.run_trial(img)

    def run_trial(self, frame):
        self.set_card(None)
        self.set_status("Đang nhận diện (chế độ thử, 1 ảnh)...", COLOR_WARN)
        self._bg(lambda: self.service.identify(frame), self.on_trial_result)

    def on_trial_result(self, result):
        self.show_image(result.image)
        self.plate_var.set(result.number)
        self.plate_entry.configure(fg=COLOR_OK if result.is_complete else COLOR_WARN)
        self.set_status(f"[THỬ - KHÔNG LƯU] Biển: {result.plate_full or '?'} | "
                        f"{NUMBER_LEN} số: {result.number or '?'}. Chỉ lưu khi quẹt thẻ đã đăng ký.",
                        COLOR_WARN)

    # ---------- Lịch sử ----------
    def upsert_row(self, event):
        """Thêm dòng mới (xe vào) hoặc cập nhật dòng có sẵn (xe ra)."""
        self.history.upsert(event)

    def refresh_history(self):
        if self._closing:
            return
        if not self._history_loading:
            self._history_loading = True
            self._bg(lambda: self.service.recent_events(100), self.apply_history,
                     busy=False, on_error=self.on_history_error)
        self.refresh_slots()
        self.root.after(HISTORY_REFRESH_MS, self.refresh_history)

    def apply_history(self, events):
        self._history_loading = False
        self.devices.set(DB, True, "SQL Server: kết nối tốt")
        self.history.apply(events)

    def on_history_error(self, exc):
        self._history_loading = False
        self.devices.set(DB, False, f"SQL Server: LỖI ({str(exc)[:60]})")

    def shutdown(self):
        """Dừng RFID + camera của cổng này (không đóng cửa sổ)."""
        self._closing = True
        self._cancel_lcd_revert()
        self._cancel_pass_timer()
        if self.rfid is not None:
            self.rfid.stop()
        self.camera.release()

    def on_close(self):
        self.shutdown()
        self.root.destroy()
