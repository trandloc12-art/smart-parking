"""Giao diện CỔNG VÀO."""
import tkinter as tk
from tkinter import ttk

from core.plate_voting import NUMBER_LEN
from services.gate_service import Outcome
from storage.errors import AlreadyInside, ParkingFull, PlateAlreadyInside
from ui.base_gate_app import (   # noqa: F401  (plate_position_offset được import lại để nơi khác dùng qua ui.entry_app)
    COLOR_ERR, COLOR_OK, COLOR_WARN, LCD_FULL, BaseGateApp, PassTicket, fmt_time, plate_position_offset,
)


class EntryApp(BaseGateApp):
    BANNER_COLOR = "#1a7f37"
    RESULT_TITLE = "Ảnh lúc vào"

    # Nội dung màn LCD ở CỔNG VÀO: (dòng 1, dòng 2), mỗi dòng tối đa 16 ký tự
    LCD_IDLE = ("CONG VAO", "MOI QUET THE")
    LCD_UNREGISTERED = ("THE CHUA DANG KY", "KHONG CHO VAO")
    LCD_ALREADY_INSIDE = ("THE DA VAO BAI", "KHONG CHO VAO")
    LCD_NEED_STAFF = ("CHO NHAN VIEN", "XAC NHAN BIEN SO")
    LCD_WAIT_PASS = ("MOI XE VAO", "QUA THANH CHAN")
    LCD_PASS_CANCELLED = ("XE CHUA VAO BAI", "HAY QUET LAI THE")
    LCD_PLATE_DUPLICATE = ("BIEN SO DA VAO", "GOI NHAN VIEN")     # giữ nguyên tới khi xe trùng rời cảm biến (không tự về màn hình chờ)

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

    # ---------- Bãi đầy ----------
    def lcd_idle_with_slots(self, free, capacity):
        """Còn chỗ: 'CONG VAO' / 'CON TRONG: 2/3'. Hết chỗ: 'BAI DA DAY' / 'HET CHO'."""
        if free <= 0:
            return LCD_FULL
        return super().lcd_idle_with_slots(free, capacity)

    def reject_swipe(self, uid):
        """Bãi đã đủ chỗ (theo số đếm đang giữ): không nhận quẹt thẻ, không quét ảnh, không mở thanh chắn."""
        if not self.slots.full:
            return False
        self.show_lot_full(uid)
        return True

    def show_lot_full(self, uid):
        capacity = self.slots.capacity
        self.set_card(uid)
        self.show_idle()                # khi đầy, màn hình chờ chính là "BAI DA DAY / HET CHO"
        self.set_status(f"BÃI ĐÃ ĐẦY ({capacity}/{capacity} chỗ). Không nhận thẻ {uid} cho đến khi có xe ra.",
                        COLOR_ERR)

    def reset_view(self):
        self.show_offset_warning(False)

    def can_rescan(self, uid):
        """Không đọc đủ 5 số (không có số nào, hoặc chỉ 1..4 số: xe thường đứng lệch vị trí) -> chưa có gì để nhân
        viên xác nhận, cho CHÍNH thẻ đó quẹt lại để quét lại, không cần bấm Hủy trên máy. Có ứng viên đủ 5 số
        (hòa phiếu, hoặc AUTO_SAVE=0 chờ xác nhận) thì vẫn phải do nhân viên xử lý."""
        o = self.pending
        return (o is not None and o.kind is Outcome.ENTRY_PENDING and o.card_uid == uid
                and plate_position_offset(o.scan))

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
        if outcome.kind is Outcome.LOT_FULL:        # số đếm đang giữ chưa biết bãi đầy, SQL Server thì biết rồi
            self.slots.force(0)
            self.show_lot_full(outcome.card_uid)
            return
        scan, uid = outcome.scan, outcome.card_uid
        self.show_image(scan.image if scan.image is not None else self.last_frame)

        if outcome.kind is Outcome.PLATE_DUPLICATE:    # biển đã có xe khác trong bãi: nghi biển giả, từ chối cứng
            self.show_plate_duplicate(uid, scan.winner, outcome.event)
            return

        if outcome.kind is Outcome.ENTRY_SAVED:        # chưa có cảm biến / servo: lưu ngay như cũ
            self.pending = None
            self.plate_var.set(scan.winner)
            self.plate_entry.configure(fg=COLOR_OK)
            self.on_saved(outcome.event, scan=scan)
            return

        if outcome.kind is Outcome.ENTRY_READY:        # đã chốt 5 số nhưng CHƯA lưu: chờ xe đi qua thanh chắn
            self.show_offset_warning(False)
            self.pending = None
            self.plate_var.set(scan.winner)
            self.plate_entry.configure(fg=COLOR_OK)
            swiped_at = outcome.swiped_at
            self.wait_for_pass(PassTicket(
                uid, scan.winner,
                commit=lambda: self.service.save_entry(uid, scan.winner, scan, swiped_at),
                on_committed=lambda e: self.on_saved(e, open_barrier=False, scan=scan)))
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
        commit = lambda: self.service.save_entry(o.card_uid, number, o.scan, o.swiped_at)  # noqa: E731
        if self.pass_gated():           # nhân viên đã xác nhận: kiểm tra biển trùng, rồi mở thanh chắn, xe đi qua rồi mới lưu
            def open_and_wait(_):
                self.pending = None
                self.show_offset_warning(False)
                self.wait_for_pass(PassTicket(o.card_uid, number, commit=commit,
                                              on_committed=lambda e: self.on_saved(e, open_barrier=False)))
                self.update_action_buttons()
            self.set_status("Đang kiểm tra biển số...", COLOR_WARN)
            self._bg(lambda: self.service.check_plate_free(o.card_uid, number), open_and_wait)
            return
        self.set_status("Đang lưu...", COLOR_WARN)
        self._bg(commit, self.on_saved)

    def on_saved(self, event, open_barrier=True, scan=None):
        """Đã lưu xong lượt vào. open_barrier=False khi thanh chắn đã mở từ trước (đã chờ cảm biến xác nhận xe qua)."""
        self.pending = None
        self.show_offset_warning(False)
        self.lcd_saved(event.plate_number)
        if open_barrier:
            self.open_barrier()         # chưa có cảm biến: lưu xong thì mở thanh chắn cổng vào
        self.slots.adjust(-1)           # sau lcd_saved: màn "XE VAO OK" không bị đè, lần về màn hình chờ sau dùng số mới
        self.upsert_row(event)
        self.update_action_buttons()
        extra = (f" ({scan.votes}/{scan.scanned} ảnh) | biển {scan.plate_full or '?'}" if scan is not None else "")
        self.set_status(f"XE VÀO | thẻ {event.card_uid} | {NUMBER_LEN} số {event.plate_number}{extra} | "
                        f"{fmt_time(event.time_in)}", COLOR_OK)

    def on_pass_cancelled(self, ticket):
        self.show_offset_warning(False)

    def cancel_pending(self):
        self.pending = None
        self.show_offset_warning(False)
        self.show_idle()
        self.plate_var.set("")
        self.set_card(None)
        self.update_action_buttons()
        self.set_status("Đã hủy. Sẵn sàng cho xe tiếp theo.", COLOR_OK)

    def show_plate_duplicate(self, uid, number, existing=None):
        """Biển `number` đang có xe khác (thẻ `existing.card_uid`) ở trong bãi: KHÔNG cho vào, KHÔNG mở thanh chắn, KHÔNG lưu.
        LCD báo và còi kêu lặp (Arduino tự làm) tới khi xe rời cảm biến trước; LCD giữ thông báo tới lúc đó."""
        self.pending = None
        self.show_offset_warning(False)
        self.set_card(uid)
        self.plate_var.set(number)
        self.plate_entry.configure(fg=COLOR_ERR)
        self.lcd(self.LCD_PLATE_DUPLICATE)          # không revert: giữ tới khi xe trùng rời đi
        alarm = self.start_alarm()
        who = (f"thẻ {existing.card_uid}, vào lúc {fmt_time(existing.time_in)}" if existing is not None else "một xe khác")
        tail = ("Còi báo liên tục tới khi xe rời khỏi cảm biến." if alarm
                else "(Không bật được còi: Arduino chưa kết nối.)")
        self.set_status(f"BIỂN SỐ {number} TRÙNG: đang có {who} ở trong bãi (nghi biển giả). "
                        f"Không cho thẻ {uid} vào, không mở thanh chắn, không lưu. {tail}", COLOR_ERR)
        self.update_action_buttons()

    def handle_error(self, exc):
        if isinstance(exc, PlateAlreadyInside):     # nhân viên nhập / xác nhận số trùng, hoặc hai bên ghi cùng lúc
            uid = self.pending.card_uid if self.pending is not None else ""
            self.show_plate_duplicate(uid, self.plate_var.get(), exc.session)
        elif isinstance(exc, AlreadyInside):
            self.pending = None
            self.show_offset_warning(False)
            self.lcd(self.LCD_ALREADY_INSIDE, revert=True)
            self.update_action_buttons()
            self.set_status("Thẻ này vừa có lượt vào khác (xe đã ở trong bãi). Không lưu thêm.",
                            COLOR_ERR)
        elif isinstance(exc, ParkingFull):      # nhân viên bấm Lưu nhưng trong lúc chờ bãi đã đầy
            uid = self.pending.card_uid if self.pending is not None else ""
            self.pending = None
            self.show_offset_warning(False)
            self.update_action_buttons()
            self.slots.force(0)
            self.show_lot_full(uid)
        elif isinstance(exc, ValueError):
            self.set_status(str(exc), COLOR_WARN)
        else:
            super().handle_error(exc)          # đã hiện "LOI HE THONG" lên LCD
