"""Điểm khởi chạy: tạo các thành phần rồi nối chúng lại với nhau.

Cài đặt:  python -m pip install -r requirements.txt   (+ ODBC Driver for SQL Server)
Chạy:     python main.py --gate in      (cổng vào)
          python main.py --gate out     (cổng ra)      -> mở hai cửa sổ terminal, mỗi cổng một tiến trình
"""
import argparse
import os
import tkinter as tk
from tkinter import messagebox

import config


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Bãi đỗ xe thông minh: RFID + nhận diện biển số")
    p.add_argument("--gate", required=True, choices=sorted(config.GATES),
                   help="in = cổng vào, out = cổng ra")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    # File riêng cổng được nạp trước nên thắng file chung; biến môi trường có sẵn thắng cả hai.
    has_gate_file = config.load_env_file(os.path.join(config.BASE_DIR, f".env.{args.gate}"))
    config.load_env_file(os.path.join(config.BASE_DIR, ".env"))
    cfg = config.load_settings(args.gate)
    print(f"[{cfg.label}] RFID {cfg.rfid_port} | camera {cfg.camera_index} | SQL {cfg.db_server}/{cfg.db_name}")
    if not has_gate_file:
        print(f"CẢNH BÁO: không thấy .env.{args.gate}. Cổng COM / camera lấy từ .env hoặc mặc định; "
              f"nếu hai cổng trùng nhau chúng sẽ tranh nhau. Hãy copy .env.{args.gate}.example "
              f"thành .env.{args.gate}.")

    # Import muộn để lỗi cấu hình hiện ra trước khi nạp các thư viện nặng (EasyOCR, OpenCV...)
    from core.recognizer import PlateRecognizer
    from hardware.camera import Camera
    from hardware.rfid import SerialRfidReader
    from storage.database import Database

    root = tk.Tk()
    db = Database(cfg.db_server, cfg.db_name, cfg.db_user, cfg.db_password, cfg.db_driver)
    try:
        db.init_schema()
    except Exception as e:
        messagebox.showerror("Lỗi SQL Server",
                             f"Không kết nối được SQL Server ({cfg.db_server}).\n\n{e}")
        root.destroy()
        return

    common = dict(scan_frames=cfg.scan_frames, scan_interval=cfg.scan_interval,
                  vote_min=cfg.vote_min)
    recognizer = PlateRecognizer()
    if cfg.gate == "in":
        from services.entry_service import EntryService
        from ui.entry_app import EntryApp
        service = EntryService(recognizer, db, cfg.image_dir, auto_save=cfg.auto_save, **common)
        app = EntryApp(root, service, Camera(), cfg)
    else:
        from services.exit_service import ExitService
        from ui.exit_app import ExitApp
        service = ExitService(recognizer, db, cfg.image_dir,
                              price_per_block=cfg.price_per_block,
                              block_minutes=cfg.block_minutes, **common)
        app = ExitApp(root, service, Camera(), cfg)

    app.set_rfid(SerialRfidReader(
        cfg.rfid_port, cfg.rfid_baud,
        on_card=app.handle_card,
        on_status=app.handle_rfid_status,
        debounce=cfg.rfid_debounce,
    ))
    root.mainloop()


if __name__ == "__main__":
    main()
