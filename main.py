"""Điểm khởi chạy: tạo các thành phần rồi nối chúng lại với nhau.

Cài đặt:  python -m pip install -r requirements.txt   (+ ODBC Driver for SQL Server)
Chạy:     python main.py
"""
import tkinter as tk
from tkinter import messagebox

import config
from core.recognizer import PlateRecognizer
from hardware.camera import Camera
from hardware.rfid import SerialRfidReader
from services.access_service import AccessService
from storage.database import Database
from ui.app import App


def main():
    root = tk.Tk()

    db = Database(config.DB_SERVER, config.DB_NAME, config.DB_USER,
                  config.DB_PASSWORD, config.DB_DRIVER)
    try:
        db.init_schema()
    except Exception as e:
        messagebox.showerror("Lỗi SQL Server",
                             f"Không kết nối được SQL Server ({config.DB_SERVER}).\n\n{e}")
        root.destroy()
        return

    service = AccessService(PlateRecognizer(), db, config.IMG_DIR, config.AUTO_SAVE,
                            config.PRICE_PER_BLOCK, config.BLOCK_MINUTES)
    app = App(root, service, Camera(), config.CAMERA_INDEX)

    app.set_rfid(SerialRfidReader(
        config.RFID_PORT, config.RFID_BAUD,
        on_card=app.handle_card,
        on_status=app.handle_rfid_status,
        debounce=config.RFID_DEBOUNCE,
    ))
    root.mainloop()


if __name__ == "__main__":
    main()
