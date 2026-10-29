"""Giao diện Tkinter dùng chung cho cổng vào và cổng ra.

Lớp này lo: camera trực tiếp, nhận thẻ RFID, chạy việc nặng ở luồng nền, ô 5 số, bảng lịch sử.
Phần riêng của mỗi cổng nằm ở entry_app.py / exit_app.py (override các hook build_*, on_gate_outcome...).
"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.plate_voting import NUMBER_LEN
from services.gate_service import Outcome

COLOR_OK = "#1a7f37"
COLOR_WARN = "#b35900"
COLOR_ERR = "#c62828"
HISTORY_REFRESH_MS = 5000       # làm mới lịch sử để thấy cả lượt do cổng kia ghi

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


class BaseGateApp:
    BANNER_COLOR = "#1a7f37"
    RESULT_TITLE = "Ảnh đã chụp"
    NUMBER_HINT = f"{NUMBER_LEN} số ở dòng dưới biển số (bắt buộc đủ {NUMBER_LEN} số):"

    def __init__(self, root, service, camera, cfg):
        self.root = root
        self.service = service
        self.camera = camera
        self.cfg = cfg
        self.view_w, self.view_h = cfg.view_w, cfg.view_h
        self.rfid = None

        root.title(f"{cfg.label} - Bãi đỗ xe RFID + nhận diện biển số")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if cfg.window_pos:
            root.geometry(cfg.window_pos)

        self.q = queue.Queue()      # luồng nền -> luồng GUI
        self.busy = False
        self.pending = None         # CardOutcome đang chờ nhân viên xử lý
        self.last_frame = None
        self.rows = {}              # id lượt gửi xe -> dòng trong bảng lịch sử
        self._hist_sig = None
        self._history_loading = False
        self._closing = False

        self.build_ui()
        self.open_camera(cfg.camera_index)
        self.update_loop()

        self.set_status("Đang tải mô hình OCR (lần đầu cần Internet, hơi lâu)...", COLOR_WARN)
        self._bg(self.service.load_model, self.on_model_ready)
        self.refresh_history()

    # ---------- Kết nối thành phần ngoài ----------
    def set_rfid(self, reader):
        """Gắn đầu đọc RFID (đã tạo với on_card=app.handle_card, on_status=app.handle_rfid_status)."""
        self.rfid = reader
        reader.start()

    def handle_card(self, uid):
        """Gọi được từ luồng nền: chuyển sang luồng GUI."""
        self.q.put(lambda: self.on_card(uid))

    def handle_rfid_status(self, connected, message):
        self.q.put(lambda: self.rfid_lbl.configure(
            text=message, foreground=COLOR_OK if connected else "red"))

    # ---------- Giao diện ----------
    def build_ui(self):
        tk.Label(self.root, text=self.cfg.label, bg=self.BANNER_COLOR, fg="white",
                 font=("Segoe UI", 16, "bold")).pack(fill="x")
        main = ttk.Frame(self.root, padding=8)
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

        # Hàng 1: camera + RFID | thẻ + 5 số
        cam_box = ttk.Frame(main)
        cam_box.grid(row=1, column=0, pady=5, sticky="n")
        row = ttk.Frame(cam_box)
        row.pack()
        ttk.Label(row, text="Camera số:").pack(side="left")
        self.cam_var = tk.StringVar(value=str(self.cfg.camera_index))
        tk.Spinbox(row, from_=0, to=5, width=3, textvariable=self.cam_var).pack(side="left", padx=4)
        ttk.Button(row, text="Mở camera", command=self.change_camera).pack(side="left")
        self.rfid_lbl = ttk.Label(cam_box, text=f"RFID ({self.cfg.rfid_port}): chưa kết nối",
                                  foreground="gray")
        self.rfid_lbl.pack(pady=(4, 0))
        self.db_lbl = ttk.Label(cam_box, text="SQL Server: đang kiểm tra...", foreground="gray")
        self.db_lbl.pack()

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
        self.capture_btn = ttk.Button(btns, text="📷 Thử nhận diện (Space)",
                                      command=self.capture, state="disabled")
        self.capture_btn.pack(side="left", padx=5)
        self.open_btn = ttk.Button(btns, text="📁 Thử với ảnh từ máy",
                                   command=self.open_image, state="disabled")
        self.open_btn.pack(side="left", padx=5)

        # Hàng 3: lịch sử
        hist = ttk.LabelFrame(main, text="Lịch sử gửi xe (từ SQL Server, cả hai cổng)", padding=5)
        hist.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        cols = (("time_in", "Giờ vào", 135), ("card", "Mã thẻ", 85), ("plate", "5 số vào", 75),
                ("time_out", "Giờ ra", 135), ("plate_out", "5 số ra", 70), ("fee", "Tiền", 80),
                ("match", "Đối chiếu", 120), ("note", "Lý do", 160))
        self.tree = ttk.Treeview(hist, columns=[c[0] for c in cols], show="headings", height=6)
        for col, text, width in cols:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.root.bind("<space>", self.on_space)

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
        self.set_status(f"Lỗi: {exc}", COLOR_ERR)

    # --- Tiện ích hiển thị ---
    def on_space(self, _event):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)):
            return
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
        can_trial = self.service.ready and not self.busy and self.pending is None
        for b in (self.capture_btn, self.open_btn):
            b.configure(state="normal" if can_trial else "disabled")
        self.update_action_buttons()

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
        if not self.camera.open(index):
            self.preview_lbl.configure(image="", text=f"Không mở được camera {index}")
            self.last_frame = None

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

    def get_frame(self):
        """Khung hình mới nhất. Được gọi từ luồng nền: chỉ đọc tham chiếu, không đụng camera."""
        return self.last_frame

    def on_card(self, uid):
        if not self.service.ready:
            self.set_status(f"Thẻ {uid}: mô hình OCR chưa sẵn sàng, quẹt lại sau.", COLOR_WARN)
            return
        if self.busy:
            self.set_status(f"Thẻ {uid}: đang xử lý, quẹt lại sau.", COLOR_WARN)
            return
        if self.pending is not None:
            self.set_status(f"Còn thẻ {self.pending.card_uid} chờ xác nhận. "
                            "Hãy xử lý hoặc Hủy trước khi quẹt thẻ mới.", COLOR_WARN)
            return
        if self.last_frame is None:
            self.set_status(f"Thẻ {uid}: chưa có hình từ camera.", COLOR_ERR)
            return

        self.reset_view()
        self.plate_var.set("")
        self.set_card(uid)
        self.set_status(f"Thẻ {uid}: đang kiểm tra...", COLOR_WARN)

        def progress(done, total):
            self.q.put(lambda: self.set_status(
                f"Thẻ {uid}: đang quét ảnh {done}/{total}...", COLOR_WARN))

        self._bg(lambda: self.service.handle_card(uid, self.get_frame, progress),
                 self.on_card_outcome)

    def on_card_outcome(self, outcome):
        uid, event, kind = outcome.card_uid, outcome.event, outcome.kind
        if kind is Outcome.UNREGISTERED:
            self.set_status(f"THẺ {uid} CHƯA ĐĂNG KÝ. Không nhận diện, không lưu.", COLOR_ERR)
        elif kind is Outcome.ALREADY_INSIDE:
            where = (f" (vào {fmt_time(event.time_in)}, biển {event.plate_number})" if event else "")
            self.set_status(f"THẺ {uid} ĐANG Ở TRONG BÃI{where}. Không cho vào lần nữa.", COLOR_ERR)
        elif kind is Outcome.NOT_INSIDE:
            self.set_status(f"THẺ {uid} CHƯA CÓ LƯỢT VÀO. Xe chưa vào bãi nên không thể ra.", COLOR_ERR)
        else:
            self.on_gate_outcome(outcome)

    # ---------- Chế độ thử (không có thẻ -> không lưu) ----------
    def capture(self):
        if self.busy or not self.service.ready or self.pending is not None:
            return
        if self.last_frame is None:
            self.set_status("Chưa có hình từ camera.", COLOR_ERR)
            return
        self.run_trial(self.last_frame.copy())

    def open_image(self):
        if self.busy or not self.service.ready or self.pending is not None:
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
    @staticmethod
    def _row(e):
        return (fmt_time(e.time_in), e.card_uid, e.plate_number, fmt_time(e.time_out),
                e.plate_out, fmt_money(e.fee), MATCH_TEXT.get(e.match_status, ""), e.override_note)

    def upsert_row(self, event):
        """Thêm dòng mới (xe vào) hoặc cập nhật dòng có sẵn (xe ra)."""
        iid = self.rows.get(event.id)
        if iid is not None:
            self.tree.item(iid, values=self._row(event))
        else:
            self.rows[event.id] = self.tree.insert("", 0, values=self._row(event))

    def refresh_history(self):
        if self._closing:
            return
        if not self._history_loading:
            self._history_loading = True
            self._bg(lambda: self.service.recent_events(100), self.apply_history,
                     busy=False, on_error=self.on_history_error)
        self.root.after(HISTORY_REFRESH_MS, self.refresh_history)

    def apply_history(self, events):
        self._history_loading = False
        self.db_lbl.configure(text="SQL Server: kết nối tốt", foreground=COLOR_OK)
        sig = tuple((e.id, e.time_out, e.match_status) for e in events)
        if sig == self._hist_sig:
            return
        self._hist_sig = sig
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        for e in events:                     # recent() trả về mới nhất trước
            self.rows[e.id] = self.tree.insert("", "end", values=self._row(e))

    def on_history_error(self, exc):
        self._history_loading = False
        self.db_lbl.configure(text=f"SQL Server: LỖI ({str(exc)[:60]})", foreground="red")

    def on_close(self):
        self._closing = True
        if self.rfid is not None:
            self.rfid.stop()
        self.camera.release()
        self.root.destroy()
