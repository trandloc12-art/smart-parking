"""Giao diện CỔNG VÀO."""
import tkinter as tk
from tkinter import ttk

from core.plate_voting import NUMBER_LEN
from services.gate_service import Outcome
from storage.errors import AlreadyInside
from ui.base_gate_app import (   # noqa: F401  (plate_position_offset được import lại để nơi khác dùng qua ui.entry_app)
    COLOR_ERR, COLOR_OK, COLOR_WARN, BaseGateApp, fmt_time, plate_position_offset,
)


class EntryApp(BaseGateApp):
    BANNER_COLOR = "#1a7f37"
    RESULT_TITLE = "Ảnh lúc vào"

    # Nội dung màn LCD ở CỔNG VÀO: (dòng 1, dòng 2), mỗi dòng tối đa 16 ký tự
    LCD_IDLE = ("CONG VAO", "MOI QUET THE")
    LCD_UNREGISTERED = ("THE CHUA DANG KY", "KHONG CHO VAO")
    LCD_ALREADY_INSIDE = ("THE DA VAO BAI", "KHONG CHO VAO")
    LCD_NEED_STAFF = ("CHO NHAN VIEN", "XAC NHAN BIEN SO")

    OFFSET_TEXT = (f"⚠ BIỂN SỐ LỆCH VỊ TRÍ\n"
                   f"Chưa đọc đủ {NUMBER_LEN} số. Hãy chỉnh xe vào đúng vị trí trước camera rồi quẹt thẻ lại.")

    def build_extra(self, parent):
        # Dải cảnh báo lớn, mặc định ẩn; chỉ hiện khi cổng vào không đọc đủ 5 số.
        self.offset_lbl = tk.Label(parent, text=self.OFFSET_TEXT, bg=COLOR_ERR, fg="white",
                                   font=("Segoe UI", 12, "bold"), justify="center",
                                   wraplength=max(self.view_w, 360), padx=8, pady=6)

    def show_offset_warning(self, show):
        if show:
            if not self.offset_lbl.winfo_ismapped():
                self.offset_lbl.pack(before=self.status_lbl, fill="x", pady=4)
        else:
            self.offset_lbl.pack_forget()

    def lcd_saved(self, number):
        self.lcd(("XE VAO OK", f"BIEN SO {number}"), revert=True)

    def reset_view(self):
        self.show_offset_warning(False)

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
            self.show_offset_warning(False)
            e = outcome.event
            self.pending = None
            self.plate_var.set(scan.winner)
            self.plate_entry.configure(fg=COLOR_OK)
            self.upsert_row(e)
            self.lcd_saved(scan.winner)
            self.open_barrier(e.id)     # tự lưu xong -> mở thanh chắn cổng vào
            self.set_status(f"XE VÀO | thẻ {uid} | {NUMBER_LEN} số {scan.winner} "
                            f"({scan.votes}/{scan.scanned} ảnh) | biển {scan.plate_full or '?'} | "
                            f"{fmt_time(e.time_in)}", COLOR_OK)
            return

        # ENTRY_PENDING: chưa chốt được -> nhân viên nhập/xác nhận
        self.pending = outcome
        self.plate_var.set(scan.number)
        offset = plate_position_offset(scan)
        self.show_offset_warning(offset)
        self.lcd(self.LCD_OFFSET if offset else self.LCD_NEED_STAFF)
        if scan.decided:    # AUTO_SAVE đang tắt
            msg = f"Đọc được {scan.winner} ({scan.votes}/{scan.scanned} ảnh). Bấm Lưu xe vào để xác nhận."
        elif scan.tally:
            msg = (f"Chưa chốt được {NUMBER_LEN} số (ứng viên: {scan.votes_text()}). "
                   "Kiểm tra ảnh, sửa nếu cần rồi bấm Lưu xe vào.")
        elif scan.suggestion:
            msg = (f"Chỉ đọc được {len(scan.suggestion)} chữ số (cần {NUMBER_LEN}). "
                   f"Hãy nhập đủ {NUMBER_LEN} số rồi bấm Lưu xe vào.")
        else:
            msg = (f"Không đọc được số ở dòng dưới biển (xe có thể lệch vị trí). Nhập tay {NUMBER_LEN} số rồi Lưu, "
                   "hoặc Hủy, chỉnh xe rồi quẹt lại.")
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
        self.show_offset_warning(False)
        self.lcd_saved(event.plate_number)
        self.open_barrier(event.id)     # nhân viên đã xác nhận cho xe vào -> mở thanh chắn cổng vào
        self.upsert_row(event)
        self.update_action_buttons()
        self.set_status(f"XE VÀO | thẻ {event.card_uid} | {NUMBER_LEN} số {event.plate_number} | "
                        f"{fmt_time(event.time_in)}", COLOR_OK)

    def cancel_pending(self):
        self.pending = None
        self.show_offset_warning(False)
        self.lcd(self.LCD_IDLE)
        self.plate_var.set("")
        self.set_card(None)
        self.update_action_buttons()
        self.set_status("Đã hủy. Sẵn sàng cho xe tiếp theo.", COLOR_OK)

    def handle_error(self, exc):
        if isinstance(exc, AlreadyInside):
            self.pending = None
            self.show_offset_warning(False)
            self.lcd(self.LCD_ALREADY_INSIDE, revert=True)
            self.update_action_buttons()
            self.set_status("Thẻ này vừa có lượt vào khác (xe đã ở trong bãi). Không lưu thêm.",
                            COLOR_ERR)
        elif isinstance(exc, ValueError):
            self.set_status(str(exc), COLOR_WARN)
        else:
            super().handle_error(exc)          # đã hiện "LOI HE THONG" lên LCD
