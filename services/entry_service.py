"""Nghiệp vụ CỔNG VÀO.

Quẹt thẻ:
  - Thẻ chưa đăng ký          -> từ chối.
  - Thẻ đang ở trong bãi      -> từ chối (không cho vào lần nữa).
  - Bãi đã đủ số chỗ          -> từ chối, KHÔNG quét ảnh (không nhận quẹt thẻ cho đến khi có xe ra).
  - Biển số (5 số đã chốt) đã có xe khác đang ở trong bãi -> từ chối cứng (nghi biển giả), không mở thanh chắn, không lưu.
  - Còn lại                   -> quét nhiều khung, bỏ phiếu 5 số.
        chốt được + AUTO_SAVE -> lưu luôn (hoặc, khi defer=True: trả ENTRY_READY, chưa lưu — giao diện chỉ gọi
                                 save_entry sau khi cảm biến xác nhận xe đã đi qua thanh chắn).
        chưa chốt được        -> chờ nhân viên nhập/xác nhận ĐÚNG 5 số rồi mới lưu.
"""
from core.plate_voting import NUMBER_LEN
from services.gate_service import (
    CardOutcome, GateService, Outcome, is_valid_number, now, votes_note,
)
from storage.errors import AlreadyInside, ParkingFull, PlateAlreadyInside


class CardNotRegistered(Exception):
    pass


class EntryService(GateService):
    gate_code = "in"

    def __init__(self, *args, auto_save=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_save = auto_save

    def handle_card(self, card_uid, get_frame, on_progress=None, defer=False):
        swiped_at = now()
        if not self.db.is_card_registered(card_uid):
            return CardOutcome(Outcome.UNREGISTERED, card_uid)

        session = self.db.find_open_session(card_uid)
        if session is not None:
            return CardOutcome(Outcome.ALREADY_INSIDE, card_uid, event=session)

        if self.is_full():
            return CardOutcome(Outcome.LOT_FULL, card_uid)

        scan = self.scan(get_frame, on_progress)
        if scan.decided and is_valid_number(scan.winner):
            duplicate = self.db.find_open_session_by_plate(scan.winner)     # chặn TRƯỚC khi mở thanh chắn
            if duplicate is not None:
                return CardOutcome(Outcome.PLATE_DUPLICATE, card_uid, scan, duplicate, swiped_at=swiped_at)
        if self.auto_save and scan.decided:
            if defer:       # chờ xe đi qua thanh chắn rồi mới lưu (xe không vào thì không lưu gì cả)
                return CardOutcome(Outcome.ENTRY_READY, card_uid, scan, swiped_at=swiped_at)
            try:
                event = self.save_entry(card_uid, scan.winner, scan, swiped_at)
            except AlreadyInside:
                return CardOutcome(Outcome.ALREADY_INSIDE, card_uid,
                                   event=self.db.find_open_session(card_uid))
            except PlateAlreadyInside as e:     # xe khác vừa vào cùng biển ngay lúc này (hai bên ghi cùng lúc)
                return CardOutcome(Outcome.PLATE_DUPLICATE, card_uid, scan,
                                   e.session or self.db.find_open_session_by_plate(scan.winner), swiped_at=swiped_at)
            return CardOutcome(Outcome.ENTRY_SAVED, card_uid, scan, event, swiped_at=swiped_at)
        return CardOutcome(Outcome.ENTRY_PENDING, card_uid, scan, swiped_at=swiped_at)

    def check_plate_free(self, card_uid, number):
        """Ném PlateAlreadyInside nếu 5 số `number` đang thuộc một xe KHÁC (thẻ khác) ở trong bãi. Giao diện gọi trước khi
        mở thanh chắn cho số do nhân viên nhập / xác nhận (số do OCR tự chốt đã được kiểm tra ngay trong handle_card)."""
        duplicate = self.db.find_open_session_by_plate(number)
        if duplicate is not None and duplicate.card_uid != card_uid:
            raise PlateAlreadyInside(f"Biển số {number} đang có xe khác (thẻ {duplicate.card_uid}) ở trong bãi", duplicate)

    def save_entry(self, card_uid, number, scan, swiped_at=None):
        """Lưu lượt VÀO. Bắt buộc đúng 5 chữ số và thẻ đã đăng ký."""
        if not is_valid_number(number):
            raise ValueError(f"Biển số phải đủ {NUMBER_LEN} chữ số (đang là '{number}')")
        if not self.db.is_card_registered(card_uid):
            raise CardNotRegistered(f"Thẻ {card_uid} chưa đăng ký")
        if self.is_full():      # nhân viên bấm Lưu sau khi bãi đã đầy (VD xe khác vừa vào trong lúc chờ xác nhận)
            raise ParkingFull(f"Bãi đã đủ {self.capacity} chỗ, không nhận thêm xe")
        self.check_plate_free(card_uid, number)     # biển đang thuộc xe khác trong bãi: không lưu

        image_name = self.save_image(scan.image if scan else None, card_uid)
        plate_full = scan.plate_full if scan and number == scan.number else ""
        try:
            return self.db.add_entry(card_uid, number, plate_full, image_name,
                                     swiped_at or now(), votes_note(scan, number), self.gate_code)
        except Exception:
            self.delete_image(image_name)   # không để lại ảnh mồ côi nếu không ghi được DB
            raise
