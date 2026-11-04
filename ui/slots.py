"""Số chỗ (slot) còn trống của bãi, dùng chung cho các cổng trong cùng một cửa sổ. Không phụ thuộc Tkinter.

Nguồn sự thật là SQL Server (số lượt chưa có giờ ra), nhưng hỏi SQL Server mất thời gian nên giao diện giữ một bản
sao ở đây: xe vào / ra thì cộng trừ ngay, và cứ vài giây lại đối chiếu lại với SQL Server (xem BaseGateApp.refresh_slots).

Mọi hàm gọi ở luồng GUI. `version` tăng mỗi khi có cộng/trừ cục bộ: kết quả đối chiếu SQL Server hỏi từ TRƯỚC lúc đó
(version cũ) bị bỏ, tránh ghi đè số mới bằng số cũ.
"""


class SlotCounter:
    def __init__(self, capacity):
        self.capacity = capacity        # None = không giới hạn chỗ (không theo dõi slot)
        self.free = None                # None = chưa biết (chưa đối chiếu SQL Server lần nào)
        self.version = 0
        self._listeners = []

    @property
    def tracking(self):
        return self.capacity is not None

    @property
    def full(self):
        return self.free is not None and self.free <= 0

    def subscribe(self, listener):
        """listener() được gọi mỗi khi số chỗ trống đổi."""
        self._listeners.append(listener)

    def _set(self, free):
        if self.capacity is not None:
            free = max(0, min(self.capacity, free))
        changed = free != self.free
        self.free = free
        if changed:
            for listener in list(self._listeners):
                listener()

    def adjust(self, delta):
        """Có xe vào (-1) hoặc xe ra (+1). Chưa biết số chỗ thì bỏ qua (lần đối chiếu kế tiếp sẽ cho số đúng)."""
        if not self.tracking:
            return
        self.version += 1
        if self.free is not None:
            self._set(self.free + delta)

    def force(self, free):
        """Đặt đúng số chỗ trống đã biết chắc (VD service báo bãi đã đầy)."""
        if not self.tracking:
            return
        self.version += 1
        self._set(free)

    def update(self, free, version):
        """Kết quả đối chiếu SQL Server, hỏi lúc `version`. Trả về True nếu được áp dụng."""
        if not self.tracking or free is None or version != self.version:
            return False
        self._set(free)
        return True
