"""Cấu hình tập trung. Đọc từ biến môi trường (có thể nạp từ file .env, xem load_env_file).

Mỗi cổng chạy là một tiến trình riêng: `python main.py --gate in` và `python main.py --gate out`.
Mỗi tiến trình nạp `.env.<gate>` (riêng cổng: camera, cổng COM...) rồi `.env` (chung: SQL Server, giá tiền...).
Biến môi trường có sẵn luôn được ưu tiên hơn file.
"""
import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mặc định riêng từng cổng (ghi đè bằng CAMERA_INDEX / RFID_PORT trong .env.<gate>)
GATES = {
    "in":  {"label": "CỔNG VÀO", "camera_index": 0, "rfid_port": "COM3"},
    "out": {"label": "CỔNG RA",  "camera_index": 1, "rfid_port": "COM4"},
}


def _parse_value(raw):
    """Giá trị trong file .env: bỏ dấu nháy bao quanh, và bỏ chú thích cùng dòng (` # ...`).

    VD `RFID_PORT=COM3   # đổi cho đúng` -> `COM3`. Dấu # dính liền giá trị (VD mật khẩu `ab#c`)
    được giữ nguyên; muốn mật khẩu có ` #` thì đặt trong dấu nháy."""
    value = raw.strip()
    if value[:1] in "\"'" and value[:1]:
        end = value.find(value[0], 1)
        if end != -1:
            return value[1:end]
    for i, ch in enumerate(value):
        if ch == "#" and (i == 0 or value[i - 1].isspace()):
            return value[:i].strip()
    return value


def load_env_file(path):
    """Nạp file KEY=VALUE vào os.environ. Biến đã tồn tại KHÔNG bị ghi đè. Trả về True nếu có file."""
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), _parse_value(value))
    return True


@dataclass(frozen=True)
class Settings:
    gate: str                  # "in" | "out"
    label: str
    # Camera + RFID (riêng từng cổng)
    camera_index: int
    rfid_port: str
    rfid_baud: int
    rfid_debounce: float       # giây, bỏ qua quẹt trùng cùng thẻ
    # SQL Server (chung)
    db_server: str
    db_name: str
    db_user: str               # để trống -> dùng Windows Authentication
    db_password: str
    db_driver: str
    image_dir: str             # thư mục ảnh, hai cổng dùng chung (cùng một máy)
    # Nghiệp vụ
    auto_save: bool            # cổng vào: chốt được 5 số thì lưu luôn, không chờ xác nhận
    price_per_block: int       # VND mỗi khối
    block_minutes: int         # độ dài một khối (phút)
    # Quét nhiều khung hình rồi bỏ phiếu
    scan_frames: int           # số khung quét sau mỗi lần quẹt
    scan_interval: float       # giây giữa hai khung
    vote_min: int              # số phiếu tối thiểu để tự chấp nhận
    # Giao diện
    view_w: int
    view_h: int
    window_pos: str            # VD "+0+0" hoặc "+900+0" để xếp hai cửa sổ cạnh nhau; để trống = mặc định


def _env(name, default):
    return os.getenv(name, default)


def load_settings(gate):
    """Đọc cấu hình cho một cổng (gọi SAU khi đã nạp các file .env)."""
    if gate not in GATES:
        raise ValueError(f"Cổng phải là một trong {sorted(GATES)}, không phải '{gate}'")
    g = GATES[gate]
    s = Settings(
        gate=gate,
        label=g["label"],
        camera_index=int(_env("CAMERA_INDEX", str(g["camera_index"]))),
        rfid_port=_env("RFID_PORT", g["rfid_port"]),
        rfid_baud=int(_env("RFID_BAUD", "9600")),
        rfid_debounce=float(_env("RFID_DEBOUNCE", "2.0")),
        db_server=_env("DB_SERVER", r"localhost\SQLEXPRESS"),
        db_name=_env("DB_NAME", "BienSoDB"),
        db_user=_env("DB_USER", ""),
        db_password=_env("DB_PASSWORD", ""),
        db_driver=_env("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        image_dir=_env("IMG_DIR", os.path.join(BASE_DIR, "anh_chup")),
        auto_save=_env("AUTO_SAVE", "1") == "1",
        price_per_block=int(_env("PRICE_PER_BLOCK", "5000")),
        block_minutes=int(_env("BLOCK_MINUTES", "60")),
        scan_frames=int(_env("SCAN_FRAMES", "5")),
        scan_interval=float(_env("SCAN_INTERVAL", "0.25")),
        vote_min=int(_env("VOTE_MIN", "2")),
        view_w=int(_env("VIEW_W", "420")),
        view_h=int(_env("VIEW_H", "315")),
        window_pos=_env("WINDOW_POS", ""),
    )
    if s.scan_frames < 1:
        raise ValueError("SCAN_FRAMES phải >= 1")
    if not 1 <= s.vote_min <= s.scan_frames:
        raise ValueError("VOTE_MIN phải nằm trong khoảng 1..SCAN_FRAMES")
    if s.block_minutes < 1 or s.price_per_block < 0:
        raise ValueError("BLOCK_MINUTES phải >= 1 và PRICE_PER_BLOCK phải >= 0")
    return s
