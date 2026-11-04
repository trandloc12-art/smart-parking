"""Các lỗi nghiệp vụ của tầng lưu trữ (tách riêng để test không cần pyodbc)."""


class AlreadyInside(Exception):
    """Thẻ này đã có một lượt vào chưa đóng (xe còn trong bãi)."""


class ParkingFull(Exception):
    """Bãi đã đủ số chỗ (PARKING_CAPACITY): không nhận thêm xe vào."""


class SessionAlreadyClosed(Exception):
    """Lượt gửi xe không còn mở (đã được đóng, hoặc không tồn tại)."""
