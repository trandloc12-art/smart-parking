"""Giao diện CỔNG RA: đặt ảnh lúc vào cạnh ảnh lúc ra, đối chiếu 5 số, tính tiền."""
import tkinter as tk
from tkinter import ttk

from core.plate_match import MatchLevel, compare_numbers
from core.plate_voting import NUMBER_LEN
from services.exit_service import MIN_NOTE_LEN
from services.gate_service import NoteRequired, Outcome, ReviewReason
from storage.errors import SessionAlreadyClosed
from ui.base_gate_app import (
    COLOR_ERR, COLOR_OK, COLOR_WARN, BaseGateApp, fmt_duration, fmt_money, fmt_time, to_photo,
)


class ExitApp(BaseGateApp):
    BANNER_COLOR = "#1565c0"
    RESULT_TITLE = "Đối chiếu ảnh lúc vào / lúc ra"
    NUMBER_HINT = f"{NUMBER_LEN} số lúc RA (sửa nếu đọc sai):"

    # ---------- Bố cục ----------
    def build_result_panel(self, parent):
        half_h = max(self.view_h // 2 - 8, 80)
        self._half_h = half_h
        self.entry_lbl = self._image_box(parent, "Ảnh lúc vào", half_h)
        self.result_lbl = self._image_box(parent, "Ảnh lúc ra", half_h)

    def _image_box(self, parent, caption, height):
        ttk.Label(parent, text=caption).pack(anchor="w")
        f = tk.Frame(parent, width=self.view_w, height=height, bg="#222")
        f.pack_propagate(False)
        f.pack(pady=(0, 3))
        lbl = tk.Label(f, bg="#222", fg="white", text="—")
        lbl.pack(fill="both", expand=True)
        return lbl

    def show_image(self, bgr):
        """Ảnh lúc RA."""
        photo = to_photo(bgr, self.view_w, self._half_h)
        self.result_lbl.configure(image=photo, text="")
        self.result_lbl.image = photo

    def show_entry_image(self, bgr):
        if bgr is None:
            self.entry_lbl.configure(image="", text="(không có ảnh lúc vào)")
            self.entry_lbl.image = None
            return
        photo = to_photo(bgr, self.view_w, self._half_h)
        self.entry_lbl.configure(image=photo, text="")
        self.entry_lbl.image = photo

    def build_extra(self, parent):
        self.match_lbl = tk.Label(parent, text="", font=("Segoe UI", 12, "bold"))
        self.match_lbl.pack()
        ttk.Label(parent, text="Lý do cho xe ra (bắt buộc nếu biển không khớp hoàn toàn):").pack()
        self.note_var = tk.StringVar()
        self.note_var.trace_add("write", lambda *_: self.update_action_buttons())
        self.note_entry = ttk.Entry(parent, textvariable=self.note_var, width=44, state="disabled")
        self.note_entry.pack(pady=2)

    def build_buttons(self, parent):
        self.confirm_btn = ttk.Button(parent, text="✔ Cho xe ra", command=self.confirm_exit,
                                      state="disabled")
        self.confirm_btn.pack(side="left", padx=5)
        self.deny_btn = ttk.Button(parent, text="✖ Từ chối / Hủy", command=self.cancel_pending,
                                   state="disabled")
        self.deny_btn.pack(side="left", padx=5)

    def reset_view(self):
        self.entry_lbl.configure(image="", text="—")
        self.entry_lbl.image = None
        self.note_var.set("")
        self.match_lbl.configure(text="")

    # ---------- Đối chiếu trực tiếp khi nhân viên sửa số ----------
    def current_match(self):
        number = self.plate_var.get()
        if self.pending is None or len(number) != NUMBER_LEN:
            return None
        return compare_numbers(self.pending.event.plate_number, number)

    def on_number_changed(self):
        """Màu ô số theo kết quả đối chiếu (không chỉ theo việc đã đủ 5 số hay chưa)."""
        match = self.current_match()
        if self.pending is not None:
            if match is None:
                color = COLOR_WARN
            else:
                color = {MatchLevel.EXACT: COLOR_OK, MatchLevel.CLOSE: COLOR_WARN,
                         MatchLevel.MISMATCH: COLOR_ERR}[match.level]
            self.plate_entry.configure(fg=color)
        self.update_action_buttons()

    def update_action_buttons(self):
        waiting = self.pending is not None and not self.busy
        self.note_entry.configure(state="normal" if self.pending is not None else "disabled")
        if self.pending is None:
            self.confirm_btn.configure(state="disabled")
            self.deny_btn.configure(state="disabled")
            return

        match = self.current_match()
        plate_in = self.pending.event.plate_number
        if match is None:
            self.match_lbl.configure(text=f"Nhập đủ {NUMBER_LEN} số để đối chiếu (lúc vào: {plate_in})",
                                     fg=COLOR_WARN)
        elif match.level is MatchLevel.EXACT:
            self.match_lbl.configure(text=f"KHỚP biển lúc vào ({plate_in})", fg=COLOR_OK)
        elif match.level is MatchLevel.CLOSE:
            self.match_lbl.configure(text=f"LỆCH {match.distance} SỐ so với lúc vào ({plate_in})",
                                     fg=COLOR_WARN)
        else:
            self.match_lbl.configure(text=f"KHÔNG KHỚP biển lúc vào ({plate_in})", fg=COLOR_ERR)

        note_ok = len(self.note_var.get().strip()) >= MIN_NOTE_LEN
        can_confirm = waiting and match is not None and (match.level is MatchLevel.EXACT or note_ok)
        self.confirm_btn.configure(state="normal" if can_confirm else "disabled")
        self.deny_btn.configure(state="normal" if waiting else "disabled")

    # ---------- Kết quả quẹt thẻ ----------
    def on_gate_outcome(self, outcome):
        scan, uid, session = outcome.scan, outcome.card_uid, outcome.event
        self.show_image(scan.image if scan.image is not None else self.last_frame)
        self.show_entry_image(self.service.load_image(session.image_in))

        if outcome.kind is Outcome.EXIT_DONE:
            self.pending = None
            self.plate_var.set(scan.winner)
            self.plate_entry.configure(fg=COLOR_OK)
            self.match_lbl.configure(text=f"KHỚP biển lúc vào ({session.plate_number})", fg=COLOR_OK)
            self.upsert_row(session)
            self.set_status(self._exit_text("XE RA", session), COLOR_OK)
            return

        # EXIT_REVIEW
        self.pending = outcome
        self.note_var.set("")
        self.plate_var.set(scan.number)
        self.update_action_buttons()
        plate_in = session.plate_number
        if outcome.reason is ReviewReason.NEED_NUMBER:
            msg = (f"Không chốt được {NUMBER_LEN} số lúc ra"
                   + (f" (ứng viên: {scan.votes_text()})" if scan.tally else "")
                   + f". Nhập {NUMBER_LEN} số rồi bấm Cho xe ra. Lúc vào: {plate_in}.")
            color = COLOR_WARN
        elif outcome.reason is ReviewReason.CLOSE:
            msg = (f"Lệch 1 số: lúc vào {plate_in}, lúc ra {scan.winner}. "
                   "So ảnh, nhập lý do rồi bấm Cho xe ra.")
            color = COLOR_WARN
        else:
            msg = (f"BIỂN KHÔNG KHỚP: lúc vào {plate_in}, lúc ra {scan.winner}. "
                   "Giữ xe lại. Chỉ cho ra khi đã kiểm tra và có lý do.")
            color = COLOR_ERR
        self.set_status(msg, color)

    # ---------- Nhân viên chốt / từ chối ----------
    def confirm_exit(self):
        o = self.pending
        number = self.plate_var.get()
        if o is None or len(number) != NUMBER_LEN:
            return
        self.set_status("Đang ghi giờ ra...", COLOR_WARN)
        note = self.note_var.get()
        self._bg(lambda: self.service.confirm_exit(o.card_uid, number, o.scan, o.swiped_at, note),
                 self.on_exit_confirmed)

    def on_exit_confirmed(self, event):
        self.pending = None
        self.upsert_row(event)
        self.update_action_buttons()
        exact = event.match_status == "MATCH"
        self.match_lbl.configure(
            text="KHỚP biển lúc vào" if exact else "ĐÃ DUYỆT CHO RA (biển không khớp hoàn toàn)",
            fg=COLOR_OK if exact else COLOR_WARN)
        self.set_status(self._exit_text("XE RA (nhân viên xác nhận)", event),
                        COLOR_OK if exact else COLOR_WARN)

    def cancel_pending(self):
        self.pending = None
        self.plate_var.set("")
        self.note_var.set("")
        self.match_lbl.configure(text="")
        self.set_card(None)
        self.update_action_buttons()
        self.set_status("Đã từ chối. Lượt gửi xe vẫn mở, xe chưa được ra.", COLOR_WARN)

    @staticmethod
    def _exit_text(title, e):
        return (f"{title} | thẻ {e.card_uid} | vào {fmt_time(e.time_in)} | ra {fmt_time(e.time_out)} "
                f"({fmt_duration(e.time_out - e.time_in)}) | TIỀN: {fmt_money(e.fee)}")

    def handle_error(self, exc):
        if isinstance(exc, NoteRequired):
            self.set_status(str(exc), COLOR_WARN)
        elif isinstance(exc, SessionAlreadyClosed):
            self.pending = None
            self.update_action_buttons()
            self.set_status(f"{exc}. Làm mới lịch sử để xem trạng thái.", COLOR_ERR)
        elif isinstance(exc, ValueError):
            self.set_status(str(exc), COLOR_WARN)
        else:
            super().handle_error(exc)
