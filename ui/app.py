"""Giao diện Tkinter. Chỉ lo hiển thị và điều phối; nghiệp vụ nằm ở AccessService."""
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from services.access_service import Outcome

VIEW_W, VIEW_H = 520, 390
COLOR_OK = "#1a7f37"
COLOR_WARN = "#b35900"
COLOR_ERR = "#c62828"
NUMBER_LEN = 5


def to_photo(bgr, w=VIEW_W, h=VIEW_H):
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


class App:
    def __init__(self, root, service, camera, camera_index=0):
        self.root = root
        self.service = service
        self.camera = camera
        self.camera_index = camera_index
        self.rfid = None

        root.title("Quản lý xe bằng thẻ RFID + nhận diện biển số")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.q = queue.Queue()      # luồng nền -> luồng GUI
        self.busy = False
        self.last_frame = None
        self.current_image = None
        self.current_plate_full = ""
        self.pending_card = None    # thẻ hợp lệ đang chờ người dùng xác nhận 5 số (xe vào)
        self.rows = {}              # id lượt gửi xe -> dòng trong bảng lịch sử

        self.build_ui()
        self.open_camera(camera_index)
        self.update_loop()

        self.set_status("Đang tải mô hình OCR (lần đầu cần Internet, hơi lâu)...", COLOR_WARN)
        self._bg(self.service.load_model, self.on_model_ready)
        self._bg(lambda: self.service.recent_events(100), self.fill_history, busy=False)

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
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        left = ttk.LabelFrame(main, text="Camera trực tiếp", padding=5)
        left.grid(row=0, column=0, padx=5, pady=5)
        right = ttk.LabelFrame(main, text="Ảnh đã chụp", padding=5)
        right.grid(row=0, column=1, padx=5, pady=5)

        lf = tk.Frame(left, width=VIEW_W, height=VIEW_H, bg="black")
        lf.pack_propagate(False)
        lf.pack()
        self.preview_lbl = tk.Label(lf, bg="black", fg="white", text="Chưa có camera")
        self.preview_lbl.pack(fill="both", expand=True)

        rf = tk.Frame(right, width=VIEW_W, height=VIEW_H, bg="#222")
        rf.pack_propagate(False)
        rf.pack()
        self.result_lbl = tk.Label(rf, bg="#222", fg="white",
                                   text="Quẹt thẻ để xe vào / ra\nKết quả hiện ở đây")
        self.result_lbl.pack(fill="both", expand=True)

        # Hàng 1: camera + RFID | thẻ + 5 số
        cam_box = ttk.Frame(main)
        cam_box.grid(row=1, column=0, pady=5)
        row = ttk.Frame(cam_box)
        row.pack()
        ttk.Label(row, text="Camera số:").pack(side="left")
        self.cam_var = tk.StringVar(value=str(self.camera_index))
        tk.Spinbox(row, from_=0, to=5, width=3, textvariable=self.cam_var).pack(side="left", padx=4)
        ttk.Button(row, text="Mở camera", command=self.change_camera).pack(side="left")
        self.rfid_lbl = ttk.Label(cam_box, text="RFID: chưa kết nối", foreground="gray")
        self.rfid_lbl.pack(pady=(4, 0))

        val_box = ttk.Frame(main)
        val_box.grid(row=1, column=1, pady=5)
        self.card_lbl = ttk.Label(val_box, text="Thẻ: —", font=("Consolas", 12, "bold"))
        self.card_lbl.pack()
        ttk.Label(val_box, text="5 số ở dòng dưới biển số (sửa nếu đọc sai):").pack()
        self.plate_var = tk.StringVar()
        vcmd = (self.root.register(lambda P: P == "" or (P.isdigit() and len(P) <= NUMBER_LEN)), "%P")
        self.plate_entry = tk.Entry(val_box, textvariable=self.plate_var, width=8,
                                    font=("Consolas", 32, "bold"), justify="center",
                                    validate="key", validatecommand=vcmd)
        self.plate_entry.pack(pady=3)
        self.status_lbl = ttk.Label(val_box, text="", wraplength=480)
        self.status_lbl.pack()

        # Hàng 2: nút
        btns = ttk.Frame(main)
        btns.grid(row=2, column=0, columnspan=2, pady=8)
        self.capture_btn = ttk.Button(btns, text="📷 Thử nhận diện (Space)",
                                      command=self.capture, state="disabled")
        self.capture_btn.pack(side="left", padx=5)
        self.open_btn = ttk.Button(btns, text="📁 Thử với ảnh từ máy",
                                   command=self.open_image, state="disabled")
        self.open_btn.pack(side="left", padx=5)
        self.save_btn = ttk.Button(btns, text="💾 Lưu xe vào", command=self.save_result)
        self.save_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(btns, text="✖ Hủy", command=self.cancel_pending)
        self.cancel_btn.pack(side="left", padx=5)

        # Hàng 3: lịch sử
        hist = ttk.LabelFrame(main, text="Lịch sử gửi xe (từ SQL Server)", padding=5)
        hist.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        self.tree = ttk.Treeview(hist, columns=("time_in", "card", "plate", "time_out", "fee", "file"),
                                 show="headings", height=6)
        for col, text, width in (("time_in", "Giờ vào", 150), ("card", "Mã thẻ", 100),
                                 ("plate", "5 số", 70), ("time_out", "Giờ ra", 150),
                                 ("fee", "Tiền", 100), ("file", "Ảnh", 400)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width)
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.root.bind("<space>", self.on_space)

    def on_space(self, _event):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)):
            return
        self.capture()

    def set_status(self, text, color="black"):
        self.status_lbl.configure(text=text, foreground=color)

    def set_card(self, uid):
        self.card_lbl.configure(text=f"Thẻ: {uid}" if uid else "Thẻ: —")

    def show_image(self, bgr):
        photo = to_photo(bgr)
        self.result_lbl.configure(image=photo, text="")
        self.result_lbl.image = photo

    def refresh_buttons(self):
        can_run = self.service.ready and not self.busy
        for b in (self.capture_btn, self.open_btn):
            b.configure(state="normal" if can_run else "disabled")
        self.save_btn.configure(state="disabled" if self.busy else "normal")

    # ---------- Chạy việc nặng ở luồng nền ----------
    def _bg(self, fn, on_ok, busy=True):
        if busy:
            self.busy = True
            self.refresh_buttons()

        def work():
            try:
                res = fn()
            except Exception as e:
                self.q.put(lambda e=e: self.on_fail(e, busy))
            else:
                self.q.put(lambda: self.on_done(on_ok, res, busy))

        threading.Thread(target=work, daemon=True).start()

    def on_done(self, on_ok, res, busy):
        if busy:
            self.busy = False
            self.refresh_buttons()
        on_ok(res)

    def on_fail(self, exc, busy):
        if busy:
            self.busy = False
            self.refresh_buttons()
        self.set_status(f"Lỗi: {exc}", COLOR_ERR)

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
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                break

        frame = self.camera.read()
        if frame is not None:
            self.last_frame = frame
            photo = to_photo(frame)
            self.preview_lbl.configure(image=photo, text="")
            self.preview_lbl.image = photo
        self.root.after(30, self.update_loop)

    # ---------- Quẹt thẻ ----------
    def on_model_ready(self, _):
        self.set_status("Sẵn sàng. Quẹt thẻ để xe vào / ra.", COLOR_OK)

    def on_card(self, uid):
        if not self.service.ready:
            self.set_status(f"Thẻ {uid}: mô hình OCR chưa sẵn sàng, quẹt lại sau.", COLOR_WARN)
            return
        if self.busy:
            self.set_status(f"Thẻ {uid}: đang xử lý, quẹt lại sau.", COLOR_WARN)
            return
        if self.pending_card is not None:
            self.set_status(f"Còn thẻ {self.pending_card} chờ xác nhận. Hãy Lưu hoặc Hủy trước khi quẹt thẻ mới.",
                            COLOR_WARN)
            return
        if self.last_frame is None:
            self.set_status(f"Thẻ {uid}: chưa có hình từ camera.", COLOR_ERR)
            return

        frame = self.last_frame.copy()
        self.set_card(uid)
        self.set_status(f"Thẻ {uid}: đang kiểm tra...", COLOR_WARN)
        self._bg(lambda: self.service.handle_card(uid, frame),
                 lambda outcome: self.on_card_outcome(uid, frame, outcome))

    def on_card_outcome(self, uid, frame, outcome):
        if outcome.kind is Outcome.REJECTED:
            self.pending_card = None
            self.set_status(f"THẺ {uid} CHƯA ĐĂNG KÝ. Không nhận diện, không lưu.", COLOR_ERR)
            return

        if outcome.kind is Outcome.EXIT:
            e = outcome.event
            self.pending_card = None
            self.show_image(frame)
            self.plate_var.set(e.plate_number)
            self.plate_entry.configure(fg=COLOR_OK)
            self.upsert_row(e)
            self.set_status(
                f"XE RA | thẻ {uid} | biển {e.plate_number} | vào {fmt_time(e.time_in)} | "
                f"ra {fmt_time(e.time_out)} ({fmt_duration(e.time_out - e.time_in)}) | "
                f"TIỀN: {fmt_money(e.fee)}", COLOR_OK)
            return

        # XE VÀO
        result, event = outcome.result, outcome.event
        self.current_image = result.image
        self.current_plate_full = result.plate_full
        self.show_image(result.image)
        self.plate_var.set(result.number)

        if event is not None:                       # đã tự lưu
            self.pending_card = None
            self.plate_entry.configure(fg=COLOR_OK)
            self.upsert_row(event)
            self.set_status(f"XE VÀO | thẻ {uid} | biển {result.plate_full or '?'} | 5 số {result.number} | "
                            f"{fmt_time(event.time_in)}", COLOR_OK)
            return

        self.pending_card = uid                     # cần người dùng xác nhận
        if result.number:
            self.plate_entry.configure(fg=COLOR_WARN)
            self.set_status(f"Chỉ đọc được {len(result.number)} chữ số (cần {NUMBER_LEN}). "
                            "Hãy sửa rồi bấm Lưu xe vào.", COLOR_WARN)
        else:
            self.plate_entry.configure(fg=COLOR_WARN)
            self.set_status("Không đọc được số ở dòng dưới biển. Nhập tay rồi Lưu, hoặc Hủy và quẹt lại.",
                            COLOR_WARN)

    # ---------- Chế độ thử (không có thẻ -> không lưu) ----------
    def capture(self):
        if self.busy or not self.service.ready:
            return
        if self.last_frame is None:
            self.set_status("Chưa có hình từ camera.", COLOR_ERR)
            return
        self.run_trial(self.last_frame.copy())

    def open_image(self):
        if self.busy or not self.service.ready:
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
        self.set_status("Đang nhận diện (chế độ thử)...", COLOR_WARN)
        self._bg(lambda: self.service.identify(frame), self.on_trial_result)

    def on_trial_result(self, result):
        self.show_image(result.image)
        self.plate_var.set(result.number)
        self.plate_entry.configure(fg=COLOR_OK if result.is_complete else COLOR_WARN)
        self.set_status(f"[THỬ - KHÔNG LƯU] Biển: {result.plate_full or '?'} | 5 số: {result.number or '?'}. "
                        "Chỉ lưu khi quẹt thẻ đã đăng ký.", COLOR_WARN)

    # ---------- Lưu / hủy ----------
    def save_result(self):
        if self.pending_card is None:
            messagebox.showinfo("Không có gì để lưu",
                                "Chỉ lưu được khi có thẻ đã đăng ký đang chờ xác nhận. Hãy quẹt thẻ trước.")
            return
        number = re.sub(r"\D", "", self.plate_var.get())
        if not number:
            messagebox.showwarning("Chưa có số", "Hãy nhập 5 số vào ô.")
            return
        if len(number) != NUMBER_LEN and not messagebox.askyesno(
                "Chưa đủ 5 số", f"Mới có {len(number)} chữ số ({number}). Vẫn lưu?"):
            return

        uid, image, full = self.pending_card, self.current_image, self.current_plate_full
        self.set_status("Đang lưu...", COLOR_WARN)
        self._bg(lambda: self.service.save_entry(uid, number, full, image), self.on_saved)

    def on_saved(self, event):
        self.pending_card = None
        self.upsert_row(event)
        self.set_status(f"XE VÀO | thẻ {event.card_uid} | 5 số {event.plate_number} | "
                        f"{fmt_time(event.time_in)}", COLOR_OK)

    def cancel_pending(self):
        self.pending_card = None
        self.plate_var.set("")
        self.set_card(None)
        self.set_status("Đã hủy. Sẵn sàng cho xe tiếp theo.", COLOR_OK)

    # ---------- Lịch sử ----------
    @staticmethod
    def _row(e):
        return (fmt_time(e.time_in), e.card_uid, e.plate_number,
                fmt_time(e.time_out), fmt_money(e.fee), e.image_path)

    def upsert_row(self, event):
        """Thêm dòng mới (xe vào) hoặc cập nhật dòng có sẵn (xe ra)."""
        iid = self.rows.get(event.id)
        if iid is not None:
            self.tree.item(iid, values=self._row(event))
        else:
            self.rows[event.id] = self.tree.insert("", 0, values=self._row(event))

    def fill_history(self, events):
        for e in events:                     # recent() trả về mới nhất trước
            self.rows[e.id] = self.tree.insert("", "end", values=self._row(e))

    def on_close(self):
        if self.rfid is not None:
            self.rfid.stop()
        self.camera.release()
        self.root.destroy()
