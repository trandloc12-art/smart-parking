"""Thanh tình trạng thiết bị: cho nhân viên biết thiết bị nào đang KHÔNG kết nối.

Gồm một dải cảnh báo đỏ (chỉ hiện khi có lỗi, liệt kê tên thiết bị lỗi) và một lưới các dòng:

    Arduino | Đầu đọc từng cổng | Camera từng cổng | SQL Server

Mỗi thiết bị có trạng thái True (tốt, xanh) / False (lỗi, đỏ) / None (đang kiểm tra hoặc chưa rõ,
xám, KHÔNG tính là lỗi). VD khi Arduino mất kết nối thì hai đầu đọc chuyển sang "chưa rõ" để dải cảnh
báo chỉ nêu đúng nguyên nhân gốc là Arduino.

Chỉ gọi set() từ luồng giao diện (luồng nền phải đi qua hàng đợi của giao diện).
"""
import tkinter as tk
from tkinter import ttk

ARDUINO = "arduino"
DB = "db"
COLOR_OK = "#1a7f37"
COLOR_ERR = "#c62828"
COLOR_UNKNOWN = "gray"
COLUMNS = 3


def reader_key(gate):
    return f"reader_{gate}"


def camera_key(gate):
    return f"cam_{gate}"


class DeviceStatusBar:
    def __init__(self, parent, gates, arduino_port=""):
        """gates: [(mã cổng, nhãn)], VD [("in", "CỔNG VÀO"), ("out", "CỔNG RA")]."""
        self.frame = ttk.Frame(parent)
        self.alert = tk.Label(self.frame, bg=COLOR_ERR, fg="white", font=("Segoe UI", 11, "bold"),
                              anchor="w", justify="left", padx=8, pady=3)
        self.grid_frame = ttk.Frame(self.frame)
        self.grid_frame.pack(fill="x", padx=8, pady=3)

        port = f" ({arduino_port})" if arduino_port else ""
        self.titles = {ARDUINO: f"Arduino{port}"}
        for gate, label in gates:
            self.titles[reader_key(gate)] = f"Đầu đọc {label}"
        for gate, label in gates:
            self.titles[camera_key(gate)] = f"Camera {label}"
        self.titles[DB] = "SQL Server"

        self.state = {}                 # khóa -> (True/False/None, nội dung đang hiển thị)
        self._labels = {}
        for i, (key, title) in enumerate(self.titles.items()):
            lbl = ttk.Label(self.grid_frame, text=f"● {title}: đang kiểm tra...", foreground=COLOR_UNKNOWN)
            lbl.grid(row=i // COLUMNS, column=i % COLUMNS, sticky="w", padx=(0, 18))
            self._labels[key] = lbl
            self.state[key] = (None, "")

    def set(self, key, ok, text):
        """ok: True / False / None. text: nội dung hiển thị (đã gồm tên thiết bị và lý do)."""
        if key not in self._labels:
            return
        self.state[key] = (ok, text)
        color = COLOR_OK if ok else COLOR_ERR if ok is False else COLOR_UNKNOWN
        self._labels[key].configure(text=f"● {text}", foreground=color)
        self._refresh_alert()

    def problems(self):
        """Tên các thiết bị đang lỗi (đúng thứ tự hiển thị)."""
        return [self.titles[k] for k in self.titles if self.state[k][0] is False]

    def _refresh_alert(self):
        problems = self.problems()
        if problems:
            self.alert.configure(text="⚠ KHÔNG KẾT NỐI ĐƯỢC: " + "  |  ".join(problems))
            self.alert.pack(fill="x", before=self.grid_frame)
        else:
            self.alert.pack_forget()
