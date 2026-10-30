"""MỘT cửa sổ chứa cả hai cổng: CỔNG VÀO (trái) | CỔNG RA (phải), bảng lịch sử dùng chung ở dưới.

Mỗi cổng vẫn là một EntryApp / ExitApp nguyên vẹn (camera, RFID, nghiệp vụ riêng), chỉ khác là được
dựng vào một khung con thay vì một cửa sổ riêng. Hai cổng dùng chung:
  - một PlateRecognizer (nạp EasyOCR một lần; hai cổng quét cùng lúc thì lần lượt),
  - một Database,
  - một bảng lịch sử.
"""
import tkinter as tk
from tkinter import ttk

from ui.base_gate_app import HistoryTable
from ui.entry_app import EntryApp
from ui.exit_app import ExitApp

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

        left = ttk.Frame(root)
        right = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="n")
        right.grid(row=0, column=1, sticky="n")
        # đường kẻ phân cách giữa hai cổng
        tk.Frame(root, width=2, bg="#999").grid(row=0, column=0, sticky="nse")

        self.history = HistoryTable(root)
        self.history.frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=6)
        root.rowconfigure(1, weight=1)

        self.entry = EntryApp(root, entry_service, entry_camera, cfg_in,
                              container=left, history=self.history)
        self.exit = ExitApp(root, exit_service, exit_camera, cfg_out,
                            container=right, history=self.history)

    @property
    def gates(self):
        return (self.entry, self.exit)

    def on_close(self):
        for gate in self.gates:
            gate.shutdown()
        self.root.destroy()
