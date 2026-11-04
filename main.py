"""Điểm khởi chạy: tạo các thành phần rồi nối chúng lại với nhau.

Cài đặt:  python -m pip install -r requirements.txt   (+ ODBC Driver for SQL Server)
Chạy:     python main.py                (mặc định = --gate both) MỘT cửa sổ chứa cả cổng vào và cổng ra
          python main.py --gate in      chỉ cổng vào  (thẻ quẹt ở đầu đọc cổng ra bị bỏ qua)
          python main.py --gate out     chỉ cổng ra   (thẻ quẹt ở đầu đọc cổng vào bị bỏ qua)
Phần cứng: MỘT Arduino (một cổng COM) nối hai đầu đọc RFID, nên cùng lúc chỉ chạy được MỘT tiến trình.
"""
import argparse
import tkinter as tk
from tkinter import messagebox

import config

BOTH = "both"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Bãi đỗ xe thông minh: RFID + nhận diện biển số")
    p.add_argument("--gate", default=BOTH, choices=sorted(config.GATES) + [BOTH],
                   help="in = chỉ cổng vào, out = chỉ cổng ra, both = cả hai trong một cửa sổ (mặc định)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.gate == BOTH:
        run_both()
    else:
        run_single(args.gate)


def _service_args(cfg):
    return dict(scan_frames=cfg.scan_frames, scan_interval=cfg.scan_interval, vote_min=cfg.vote_min)


def _make_db(cfg):
    from storage.database import Database
    return Database(cfg.db_server, cfg.db_name, cfg.db_user, cfg.db_password, cfg.db_driver)


def _make_rfid(cfg, apps, **reader_kwargs):
    """MỘT bộ đọc cho cả Arduino. apps: {mã cổng: giao diện của cổng đó}.

    Thẻ / tình trạng đầu đọc được chuyển đúng cổng; cổng nào không có giao diện (chạy một cổng) thì bỏ qua.
    Tình trạng Arduino (cổng COM) gửi cho mọi cổng vì chung một thiết bị."""
    from hardware.rfid import ArduinoRfidReader

    def on_card(gate, uid):
        if gate in apps:
            apps[gate].handle_card(uid)

    def on_status(connected, message):
        for app in apps.values():
            app.handle_rfid_status(connected, message)

    def on_reader_status(gate, ok):
        if gate in apps:
            apps[gate].handle_reader_status(ok)

    def on_barrier(gate, passed):
        if gate in apps:
            apps[gate].handle_barrier(passed)

    return ArduinoRfidReader(cfg.rfid_port, cfg.rfid_baud, on_card=on_card, on_status=on_status,
                             on_reader_status=on_reader_status, on_barrier=on_barrier,
                             debounce=cfg.rfid_debounce,
                             heartbeat_timeout=cfg.rfid_heartbeat, **reader_kwargs)


def _make_entry_service(recognizer, db, cfg):
    from services.entry_service import EntryService
    return EntryService(recognizer, db, cfg.image_dir, auto_save=cfg.auto_save, **_service_args(cfg))


def _make_exit_service(recognizer, db, cfg):
    from services.exit_service import ExitService
    return ExitService(recognizer, db, cfg.image_dir, price_per_block=cfg.price_per_block,
                       block_minutes=cfg.block_minutes, **_service_args(cfg))


def _init_db(root, db, cfg):
    """Tạo database + bảng. Lỗi thì báo bằng hộp thoại và trả về False."""
    try:
        db.init_schema()
        return True
    except Exception as e:
        messagebox.showerror("Lỗi SQL Server",
                             f"Không kết nối được SQL Server ({cfg.db_server}).\n\n{e}")
        root.destroy()
        return False


# ---------------------------------------------------------------- một cổng, một cửa sổ
def run_single(gate):
    # File riêng cổng được nạp trước nên thắng file chung; biến môi trường có sẵn thắng cả hai.
    env, has_gate_file = config.gate_env(gate)
    cfg = config.load_settings(gate, env)
    print(f"[{cfg.label}] Arduino {cfg.rfid_port} | camera {cfg.camera_index} | SQL {cfg.db_server}/{cfg.db_name}")
    if not has_gate_file:
        print(f"CẢNH BÁO: không thấy .env.{gate}. Số camera lấy từ .env hoặc mặc định; "
              f"nếu hai cổng trùng camera chúng sẽ tranh nhau. Hãy copy .env.{gate}.example "
              f"thành .env.{gate}.")

    # Import muộn để lỗi cấu hình hiện ra trước khi nạp các thư viện nặng (EasyOCR, OpenCV...)
    from core.recognizer import PlateRecognizer
    from hardware.camera import Camera

    root = tk.Tk()
    db = _make_db(cfg)
    if not _init_db(root, db, cfg):
        return

    recognizer = PlateRecognizer()
    if cfg.gate == "in":
        from ui.entry_app import EntryApp
        app = EntryApp(root, _make_entry_service(recognizer, db, cfg), Camera(), cfg)
    else:
        from ui.exit_app import ExitApp
        app = ExitApp(root, _make_exit_service(recognizer, db, cfg), Camera(), cfg)

    app.set_rfid(_make_rfid(cfg, {cfg.gate: app}))
    root.mainloop()


# ---------------------------------------------------------------- cả hai cổng, một cửa sổ
def run_both():
    envs = {g: config.gate_env(g) for g in config.GATES}
    cfg_in = config.load_settings("in", envs["in"][0])
    cfg_out = config.load_settings("out", envs["out"][0])
    print(f"Arduino {cfg_in.rfid_port}")
    for g, cfg in (("in", cfg_in), ("out", cfg_out)):
        print(f"[{cfg.label}] camera {cfg.camera_index}")
        if not envs[g][1]:
            print(f"CẢNH BÁO: không thấy .env.{g}, dùng camera mặc định ({cfg.camera_index}). "
                  f"Nên copy .env.{g}.example thành .env.{g}.")
    print(f"SQL {cfg_in.db_server}/{cfg_in.db_name}")

    root = tk.Tk()
    try:
        config.check_dual(cfg_in, cfg_out)
    except ValueError as e:
        messagebox.showerror("Cấu hình hai cổng", str(e))
        root.destroy()
        return

    from core.recognizer import PlateRecognizer
    from hardware.camera import Camera
    from ui.dual_app import DualGateApp

    db = _make_db(cfg_in)
    if not _init_db(root, db, cfg_in):
        return

    cfg_in, cfg_out = config.fit_views(root.winfo_screenwidth(), cfg_in, cfg_out)
    recognizer = PlateRecognizer()      # dùng chung: chỉ nạp EasyOCR một lần
    app = DualGateApp(root,
                      _make_entry_service(recognizer, db, cfg_in),
                      _make_exit_service(recognizer, db, cfg_out),
                      Camera(), Camera(), cfg_in, cfg_out)
    app.set_rfid(_make_rfid(cfg_in, {"in": app.entry, "out": app.exit}))
    root.mainloop()


if __name__ == "__main__":
    main()
