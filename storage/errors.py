"""Các lỗi nghiệp vụ của tầng lưu trữ (tách riêng để test không cần pyodbc)."""


class AlreadyInside(Exception):
    """Thẻ này đã có một lượt vào chưa đóng (xe còn trong bãi)."""


class PlateAlreadyInside(Exception):
    """Biển số (5 số) này đang có một lượt vào chưa đóng của thẻ khác: nghi dùng biển giả / trùng biển, không cho vào.

    session: lượt đang mở giữ biển đó (AccessEvent) nếu biết; None nếu chỉ do chỉ mục DB chặn (hai bên ghi cùng lúc)."""

    def __init__(self, message="", session=None):
        super().__init__(message)
        self.session = session


class ParkingFull(Exception):
    """Bãi đã đủ số chỗ (PARKING_CAPACITY): không nhận thêm xe vào."""


class SessionAlreadyClosed(Exception):
    """Lượt gửi xe không còn mở (đã được đóng, hoặc không tồn tại)."""
