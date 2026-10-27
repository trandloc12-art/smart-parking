"""Tính tiền gửi xe (hàm thuần, dễ kiểm thử)."""
import math


def calculate_fee(time_in, time_out, price_per_block=5000, block_minutes=60):
    """Làm tròn LÊN theo khối thời gian, tối thiểu 1 khối. Trả về số tiền (VND, số nguyên)."""
    minutes = max(0.0, (time_out - time_in).total_seconds() / 60)
    blocks = max(1, math.ceil(minutes / block_minutes))
    return blocks * price_per_block
