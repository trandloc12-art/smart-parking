"""Giao diện CỔNG VÀO."""
from tkinter import ttk

from core.plate_voting import NUMBER_LEN
from services.gate_service import Outcome
from storage.errors import AlreadyInside
from ui.base_gate_app import COLOR_ERR, COLOR_OK, COLOR_WARN, BaseGateApp, fmt_time


class EntryApp(BaseGateApp):
    BANNER_COLOR = "#1a7f37"
    RESULT_TITLE = "Ảnh lúc vào"

    def build_buttons(self, parent):
        self.save_btn = ttk.Button(parent, text="💾 Lưu xe vào", command=self.save_entry,
                                   state="disabled")
        self.save_btn.pack(side="left", padx=5)
        self.cancel_btn = ttk.Button(parent, text="✖ Hủy", command=self.cancel_pending,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=5)

    def update_action_buttons(self):
        waiting = self.pending is not None and not self.busy
        complete = len(self.plate_var.get()) == NUMBER_LEN
        self.save_btn.configure(state="normal" if waiting and complete else "disabled")
        self.cancel_btn.configure(state="normal" if waiting else "disabled")

    # ---------- Kết quả quẹt thẻ ----------
    def on_gate_outcome(self, outcome):
        scan, uid = outcome.scan, outcome.card_uid
        self.show_image(scan.image if scan.image is not None else self.last_frame)

        if outcome.kind is Outcome.ENTRY_SAVED:
            e = outcome.event
            self.pending = None
            self.plate_var.set(scan.winner)
            self.plate_entry.configure(fg=COLOR_OK)
            self.upsert_row(e)
            self.set_status(f"XE VÀO | thẻ {uid} | {NUMBER_LEN} số {scan.winner} "
                            f"({scan.votes}/{scan.scanned} ảnh) | biển {scan.plate_full or '?'} | "
                            f"{fmt_time(e.time_in)}", COLOR_OK)
            return

        # ENTRY_PENDING: chưa chốt được -> nhân viên nhập/xác nhận
        self.pending = outcome
        self.plate_var.set(scan.number)
        if scan.decided:    # AUTO_SAVE đang tắt
            msg = f"Đọc được {scan.winner} ({scan.votes}/{scan.scanned} ảnh). Bấm Lưu xe vào để xác nhận."
        elif scan.tally:
            msg = (f"Chưa chốt được {NUMBER_LEN} số (ứng viên: {scan.votes_text()}). "
                   "Kiểm tra ảnh, sửa nếu cần rồi bấm Lưu xe vào.")
        elif scan.suggestion:
            msg = (f"Chỉ đọc được {len(scan.suggestion)} chữ số (cần {NUMBER_LEN}). "
                   f"Hãy nhập đủ {NUMBER_LEN} số rồi bấm Lưu xe vào.")
        else:
            msg = (f"Không đọc được số ở dòng dưới biển. Nhập tay {NUMBER_LEN} số rồi Lưu, "
                   "hoặc Hủy và quẹt lại.")
        self.set_status(msg, COLOR_WARN)

    # ---------- Lưu / hủy ----------
    def save_entry(self):
        o = self.pending
        number = self.plate_var.get()
        if o is None or len(number) != NUMBER_LEN:
            return
        self.set_status("Đang lưu...", COLOR_WARN)
        self._bg(lambda: self.service.save_entry(o.card_uid, number, o.scan, o.swiped_at),
                 self.on_saved)

    def on_saved(self, event):
        self.pending = None
        self.upsert_row(event)
        self.update_action_buttons()
        self.set_status(f"XE VÀO | thẻ {event.card_uid} | {NUMBER_LEN} số {event.plate_number} | "
                        f"{fmt_time(event.time_in)}", COLOR_OK)

    def cancel_pending(self):
        self.pending = None
        self.plate_var.set("")
        self.set_card(None)
        self.update_action_buttons()
        self.set_status("Đã hủy. Sẵn sàng cho xe tiếp theo.", COLOR_OK)

    def handle_error(self, exc):
        if isinstance(exc, AlreadyInside):
            self.pending = None
            self.update_action_buttons()
            self.set_status("Thẻ này vừa có lượt vào khác (xe đã ở trong bãi). Không lưu thêm.",
                            COLOR_ERR)
        elif isinstance(exc, ValueError):
            self.set_status(str(exc), COLOR_WARN)
        else:
            super().handle_error(exc)
