"""Nghiệp vụ CỔNG VÀO.

Quẹt thẻ:
  - Thẻ chưa đăng ký          -> từ chối.
  - Thẻ đang ở trong bãi      -> từ chối (không cho vào lần nữa).
  - Còn lại                   -> quét nhiều khung, bỏ phiếu 5 số.
        chốt được + AUTO_SAVE -> lưu luôn.
        chưa chốt được        -> chờ nhân viên nhập/xác nhận ĐÚNG 5 số rồi mới lưu.
"""
from core.plate_voting import NUMBER_LEN
from services.gate_service import (
    CardOutcome, GateService, Outcome, is_valid_number, now, votes_note,
)
from storage.errors import AlreadyInside


class CardNotRegistered(Exception):
    pass


class EntryService(GateService):
    gate_code = "in"

    def __init__(self, *args, auto_save=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_save = auto_save

    def handle_card(self, card_uid, get_frame, on_progress=None):
        swiped_at = now()
        if not self.db.is_card_registered(card_uid):
            return CardOutcome(Outcome.UNREGISTERED, card_uid)

        session = self.db.find_open_session(card_uid)
        if session is not None:
            return CardOutcome(Outcome.ALREADY_INSIDE, card_uid, event=session)

        scan = self.scan(get_frame, on_progress)
        if self.auto_save and scan.decided:
            try:
                event = self.save_entry(card_uid, scan.winner, scan, swiped_at)
            except AlreadyInside:
                return CardOutcome(Outcome.ALREADY_INSIDE, card_uid,
                                   event=self.db.find_open_session(card_uid))
            return CardOutcome(Outcome.ENTRY_SAVED, card_uid, scan, event, swiped_at=swiped_at)
        return CardOutcome(Outcome.ENTRY_PENDING, card_uid, scan, swiped_at=swiped_at)

    def save_entry(self, card_uid, number, scan, swiped_at=None):
        """Lưu lượt VÀO. Bắt buộc đúng 5 chữ số và thẻ đã đăng ký."""
        if not is_valid_number(number):
            raise ValueError(f"Biển số phải đủ {NUMBER_LEN} chữ số (đang là '{number}')")
        if not self.db.is_card_registered(card_uid):
            raise CardNotRegistered(f"Thẻ {card_uid} chưa đăng ký")

        image_name = self.save_image(scan.image if scan else None, card_uid)
        plate_full = scan.plate_full if scan and number == scan.number else ""
        try:
            return self.db.add_entry(card_uid, number, plate_full, image_name,
                                     swiped_at or now(), votes_note(scan, number), self.gate_code)
        except Exception:
            self.delete_image(image_name)   # không để lại ảnh mồ côi nếu không ghi được DB
            raise
