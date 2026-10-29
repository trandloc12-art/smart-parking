"""Mô hình dữ liệu (thuần Python, không phụ thuộc pyodbc)."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AccessEvent:
    """Một lượt gửi xe. Các trường "ra" là rỗng/None cho đến khi xe ra."""
    id: int
    card_uid: str
    plate_number: str          # 5 số lúc vào
    plate_full: str
    image_in: str
    time_in: datetime
    time_out: datetime | None = None
    fee: int | None = None
    plate_out: str = ""        # 5 số lúc ra
    image_out: str = ""
    match_status: str = ""     # MATCH / APPROVED_CLOSE / APPROVED_MISMATCH
    override_note: str = ""
    gate_in: str = ""
    gate_out: str = ""
