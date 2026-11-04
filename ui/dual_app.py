"""MỘT cửa sổ chứa cả hai cổng: CỔNG VÀO (trái) | CỔNG RA (phải), bảng lịch sử dùng chung ở dưới.

Mỗi cổng vẫn là một EntryApp / ExitApp nguyên vẹn (camera, RFID, nghiệp vụ riêng), chỉ khác là được
dựng vào một khung con thay vì một cửa sổ riêng. Hai cổng dùng chung:
  - một PlateRecognizer (nạp EasyOCR một lần; hai cổng quét cùng lúc thì lần lượt),
  - một Database,
  - một bảng lịch sử,
  - MỘT Arduino (một cổng COM, hai đầu đọc): xem set_rfid,
  - một thanh tình trạng thiết bị ở trên cùng: thiết bị nào mất kết nối thì hiện cảnh báo đỏ ở đó,
  - một bộ đếm chỗ trống của bãi (xe vào ở cổng vào, xe ra ở cổng ra: cả hai LCD cùng thấy số mới ngay).
"""
import tkinter as tk
from tkinter import ttk

from ui.base_gate_app import HistoryTable
from ui.device_status import DeviceStatusBar
from ui.entry_app import EntryApp
from ui.exit_app import ExitApp
from ui.slots import SlotCounter

TITLE = "Bãi đỗ xe RFID + nhận diện biển số — CỔNG VÀO | CỔNG RA"


class DualGateApp:
    def __init__(self, root, entry_service, exit_service, entry_camera, exit_camera,
                 cfg_in, cfg_out):
        self.root = root
        root.title(TITLE)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.geometry("+0+0")       # sát góc trái trên để hai panel (~1800 px) không bị tràn màn hình
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)

        self.devices = DeviceStatusBar(root, [(cfg_in.gate, cfg_in.label), (cfg_out.gate, cfg_out.label)],
                                       cfg_in.rfid_port)
        self.devices.frame.grid(row=0, column=0, columnspan=2, sticky="ew")

        left = ttk.Frame(root)
        right = ttk.Frame(root)
        left.grid(row=1, column=0, sticky="n")
        right.grid(row=1, column=1, sticky="n")
        # đường kẻ phân cách giữa hai cổng
        tk.Frame(root, width=2, bg="#999").grid(row=1, column=0, sticky="nse")

        self.history = HistoryTable(root)
        self.history.frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=6)
        root.rowconfigure(2, weight=1)

        self.slots = SlotCounter(entry_service.capacity)
        self.entry = EntryApp(root, entry_service, entry_camera, cfg_in,
                              container=left, history=self.history, devices=self.devices, slots=self.slots)
        self.exit = ExitApp(root, exit_service, exit_camera, cfg_out,
                            container=right, history=self.history, devices=self.devices, slots=self.slots)

    @property
    def gates(self):
        return (self.entry, self.exit)

    def set_rfid(self, reader):
        """Gắn MỘT bộ đọc RFID (một Arduino) dùng chung cho cả hai cổng rồi khởi động nó đúng một lần."""
        for gate in self.gates:
            gate.set_rfid(reader, start=False)
        reader.start()

    def on_close(self):
        for gate in self.gates:
            gate.shutdown()
        self.root.destroy()
