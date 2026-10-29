"""Bỏ phiếu giữa nhiều lần đọc biển số (hàm thuần, không phụ thuộc OCR/camera)."""
from collections import Counter
from dataclasses import dataclass

NUMBER_LEN = 5


@dataclass(frozen=True)
class VoteResult:
    winner: str = ""            # 5 số thắng cuộc, "" nếu chưa chốt được
    decided: bool = False       # True: đủ phiếu và dẫn đầu rõ ràng -> có thể tự động chấp nhận
    votes: int = 0              # số phiếu của số dẫn đầu
    runner_up: int = 0          # số phiếu của số đứng thứ hai
    tally: tuple = ()           # ((số, phiếu), ...) từ nhiều đến ít phiếu
    suggestion: str = ""        # gợi ý cho nhân viên: số dẫn đầu, hoặc số dài nhất nếu chưa có số nào đủ 5

    def is_settled(self, remaining):
        """True nếu dù `remaining` lần đọc còn lại có ra gì cũng không lật được kết quả."""
        return self.decided and self.votes - self.runner_up > remaining

    def tally_text(self):
        return ",".join(f"{n}:{c}" for n, c in self.tally)


def tally_votes(numbers, min_votes=2, length=NUMBER_LEN):
    """numbers: các chuỗi số đọc được (có thể thiếu số hoặc rỗng). Chỉ chuỗi ĐỦ `length` chữ số mới có phiếu.

    Thắng cuộc khi: có ít nhất `min_votes` phiếu VÀ nhiều phiếu hơn số đứng thứ hai (hòa thì không chốt).
    """
    full = [n for n in numbers if len(n) == length and n.isdigit()]
    counts = Counter(full)
    # most_common giữ thứ tự xuất hiện đầu tiên khi bằng phiếu -> kết quả ổn định
    ranked = tuple(counts.most_common())

    if ranked:
        top, top_votes = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0
        decided = top_votes >= min_votes and top_votes > second
        return VoteResult(top if decided else "", decided, top_votes, second, ranked, top)

    partial = [n for n in numbers if n and n.isdigit()]
    suggestion = max(partial, key=len) if partial else ""   # max giữ phần tử đầu khi bằng độ dài
    return VoteResult(suggestion=suggestion)
