"""Các lỗi nghiệp vụ của tầng lưu trữ (tách riêng để test không cần pyodbc)."""


class AlreadyInside(Exception):
    """Thẻ này đã có một lượt vào chưa đóng (xe còn trong bãi)."""


class SessionAlreadyClosed(Exception):
    """Lượt gửi xe không còn mở (đã được đóng, hoặc không tồn tại)."""
