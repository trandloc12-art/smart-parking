"""So khớp 5 số biển lúc vào với lúc ra (hàm thuần)."""
from dataclasses import dataclass
from enum import Enum


class MatchLevel(Enum):
    EXACT = "exact"          # khớp hoàn toàn
    CLOSE = "close"          # lệch 1 chữ số (thường do OCR nhầm) -> cần nhân viên xác nhận
    MISMATCH = "mismatch"    # lệch nhiều -> chặn, chỉ cho qua khi có lý do


@dataclass(frozen=True)
class PlateMatch:
    level: MatchLevel
    distance: int


def compare_numbers(entry, exit_, close_distance=1):
    """Hai chuỗi phải cùng độ dài (5 số); khác độ dài hoặc rỗng -> MISMATCH."""
    a, b = (entry or "").strip(), (exit_ or "").strip()
    if not a or not b or len(a) != len(b):
        return PlateMatch(MatchLevel.MISMATCH, max(len(a), len(b), 1))
    distance = sum(x != y for x, y in zip(a, b))
    if distance == 0:
        return PlateMatch(MatchLevel.EXACT, 0)
    if distance <= close_distance:
        return PlateMatch(MatchLevel.CLOSE, distance)
    return PlateMatch(MatchLevel.MISMATCH, distance)
