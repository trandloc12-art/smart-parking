"""Nghiệp vụ CỔNG RA.

Quẹt thẻ:
  - Thẻ chưa đăng ký          -> từ chối.
  - Thẻ chưa có lượt vào      -> từ chối (xe chưa vào bãi).
  - Còn lại                   -> quét nhiều khung, bỏ phiếu 5 số, ĐỐI CHIẾU với 5 số lúc vào.
        khớp hoàn toàn        -> đóng lượt, tính tiền, cho ra.
        lệch 1 số             -> chờ nhân viên xác nhận (kèm lý do).
        lệch nhiều / không đọc được đủ 5 số -> chặn, nhân viên xử lý (nhập lại số hoặc cho qua kèm lý do).
Giờ ra tính tại thời điểm QUẸT THẺ, không phải lúc nhân viên bấm xác nhận.
"""
from dataclasses import replace

from core.plate_match import MatchLevel, compare_numbers
from core.plate_voting import NUMBER_LEN
from services.gate_service import (
    CardOutcome, GateService, NoteRequired, Outcome, ReviewReason, is_valid_number, now, votes_note,
)
from services.pricing import calculate_fee
from storage.errors import SessionAlreadyClosed

MIN_NOTE_LEN = 3

_STATUS = {
    MatchLevel.EXACT: "MATCH",
    MatchLevel.CLOSE: "APPROVED_CLOSE",
    MatchLevel.MISMATCH: "APPROVED_MISMATCH",
}


class ExitService(GateService):
    gate_code = "out"

    def __init__(self, *args, price_per_block=5000, block_minutes=60, **kwargs):
        super().__init__(*args, **kwargs)
        self.price_per_block = price_per_block
        self.block_minutes = block_minutes

    def handle_card(self, card_uid, get_frame, on_progress=None):
        swiped_at = now()
        if not self.db.is_card_registered(card_uid):
            return CardOutcome(Outcome.UNREGISTERED, card_uid)

        session = self.db.find_open_session(card_uid)
        if session is None:
            return CardOutcome(Outcome.NOT_INSIDE, card_uid)

        scan = self.scan(get_frame, on_progress)

        if not scan.decided:
            match = (compare_numbers(session.plate_number, scan.number)
                     if is_valid_number(scan.number) else None)
            return CardOutcome(Outcome.EXIT_REVIEW, card_uid, scan, session, match,
                               ReviewReason.NEED_NUMBER, swiped_at)

        match = compare_numbers(session.plate_number, scan.winner)
        if match.level is MatchLevel.EXACT:
            event = self._close(session, scan.winner, scan, swiped_at, MatchLevel.EXACT, "")
            return CardOutcome(Outcome.EXIT_DONE, card_uid, scan, event, match, swiped_at=swiped_at)

        reason = ReviewReason.CLOSE if match.level is MatchLevel.CLOSE else ReviewReason.MISMATCH
        return CardOutcome(Outcome.EXIT_REVIEW, card_uid, scan, session, match, reason, swiped_at)

    def confirm_exit(self, card_uid, number, scan, swiped_at, note=""):
        """Nhân viên chốt cho xe ra với 5 số `number` (đã nhập/sửa).

        Khớp hoàn toàn: không cần lý do. Lệch (1 số hoặc nhiều): bắt buộc có lý do (NoteRequired)."""
        if not is_valid_number(number):
            raise ValueError(f"Biển số phải đủ {NUMBER_LEN} chữ số (đang là '{number}')")
        session = self.db.find_open_session(card_uid)
        if session is None:
            raise SessionAlreadyClosed("Thẻ này không còn lượt vào nào đang mở")

        match = compare_numbers(session.plate_number, number)
        note = (note or "").strip()
        if match.level is not MatchLevel.EXACT and len(note) < MIN_NOTE_LEN:
            raise NoteRequired("Biển không khớp hoàn toàn: hãy nhập lý do cho xe ra")
        return self._close(session, number, scan, swiped_at, match.level, note)

    def _close(self, session, number, scan, swiped_at, level, note):
        time_out = swiped_at or now()
        fee = calculate_fee(session.time_in, time_out, self.price_per_block, self.block_minutes)
        image_name = self.save_image(scan.image if scan else None, session.card_uid)
        status = _STATUS[level]
        try:
            self.db.close_session(session.id, time_out, fee, number, image_name, status,
                                  note, votes_note(scan, number), self.gate_code)
        except Exception:
            self.delete_image(image_name)
            raise
        return replace(session, time_out=time_out, fee=fee, plate_out=number, image_out=image_name,
                       match_status=status, override_note=note, gate_out=self.gate_code)
