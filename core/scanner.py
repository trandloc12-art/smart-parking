"""Quét nhiều khung hình sau mỗi lần quẹt thẻ rồi bỏ phiếu lấy 5 số xuất hiện nhiều nhất.

Không phụ thuộc OCR hay camera cụ thể: nhận vào hàm `recognize(frame)` và hàm `get_frame()`.
"""
import time
from dataclasses import dataclass

from core.plate_voting import tally_votes


@dataclass
class ScanResult:
    image: object = None        # khung hình (đã vẽ khung biển) cho ra số thắng; None nếu không có khung nào
    plate_full: str = ""        # biển đầy đủ của khung đó (chỉ để tham khảo)
    winner: str = ""            # 5 số đã chốt ("" nếu chưa chốt được)
    suggestion: str = ""        # gợi ý điền sẵn cho nhân viên khi chưa chốt được
    decided: bool = False       # đủ phiếu, dẫn đầu rõ -> có thể tự động chấp nhận
    votes: int = 0
    scanned: int = 0            # số khung đã quét
    tally: tuple = ()

    @property
    def number(self):
        """Số để hiển thị/điền sẵn: số đã chốt, nếu chưa thì gợi ý."""
        return self.winner or self.suggestion

    def votes_text(self):
        return ",".join(f"{n}:{c}" for n, c in self.tally)


def scan_best_of(recognize, get_frame, frames=5, interval=0.25, min_votes=2,
                 on_progress=None, sleep=time.sleep):
    """Lấy `frames` khung hình cách nhau `interval` giây, OCR từng khung, bỏ phiếu.

    Dừng sớm khi kết quả không thể bị lật nữa (VD 3 khung đầu cùng ra một số trong 5 khung).
    on_progress(đã_quét, tổng) được gọi sau mỗi khung (chạy ở luồng gọi hàm này).
    """
    results, numbers = [], []
    vote = tally_votes([], min_votes)

    for i in range(frames):
        if i:
            sleep(interval)             # chờ để khung hình sau khác khung trước, bỏ phiếu mới có ý nghĩa
        frame = get_frame()
        if frame is None:
            results.append(None)
            numbers.append("")
        else:
            res = recognize(frame)
            results.append(res)
            numbers.append(res.number)
        if on_progress:
            on_progress(i + 1, frames)

        vote = tally_votes(numbers, min_votes)
        if vote.is_settled(frames - (i + 1)):
            break

    scanned = len(numbers)
    chosen = _pick_result(results, vote.winner or vote.suggestion)
    return ScanResult(
        image=chosen.image if chosen else None,
        plate_full=chosen.plate_full if chosen else "",
        winner=vote.winner, suggestion=vote.suggestion, decided=vote.decided,
        votes=vote.votes, scanned=scanned, tally=vote.tally)


def _pick_result(results, number):
    """Khung đầu tiên cho ra đúng `number`; không có thì khung cuối cùng có ảnh."""
    real = [r for r in results if r is not None]
    if number:
        for r in real:
            if r.number == number:
                return r
    return real[-1] if real else None
