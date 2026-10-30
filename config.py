"""Cấu hình tập trung. Đọc từ biến môi trường (có thể nạp từ file .env, xem load_env_file).

Có hai cách chạy:
  - `python main.py`            (hoặc `--gate both`): MỘT cửa sổ chứa cả cổng vào và cổng ra.
  - `python main.py --gate in|out`: mỗi cổng một tiến trình riêng.
Cổng nào cũng đọc `.env.<gate>` (riêng cổng: camera, cổng COM...) rồi `.env` (chung: SQL Server, giá tiền...).
Thứ tự ưu tiên: biến môi trường có sẵn > `.env.<gate>` > `.env` > mặc định.
"""
import os
from dataclasses import dataclass, replace

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


def read_env_file(path):
    """Đọc file KEY=VALUE thành dict (không đụng os.environ). Trả về None nếu không có file."""
    if not os.path.isfile(path):
        return None
    values = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = _parse_value(value)
    return values


def load_env_file(path):
    """Nạp file KEY=VALUE vào os.environ. Biến đã tồn tại KHÔNG bị ghi đè. Trả về True nếu có file."""
    values = read_env_file(path)
    if values is None:
        return False
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return True


def gate_env(gate, base_dir=BASE_DIR, environ=None):
    """Cấu hình đã gộp cho MỘT cổng, không đụng os.environ (nên đọc được cả hai cổng trong một tiến trình).

    Ưu tiên: biến môi trường có sẵn > .env.<gate> > .env. Trả về (dict, có_file_riêng_cổng)."""
    environ = os.environ if environ is None else environ
    gate_file = read_env_file(os.path.join(base_dir, f".env.{gate}"))
    common = read_env_file(os.path.join(base_dir, ".env"))
    return {**(common or {}), **(gate_file or {}), **environ}, gate_file is not None


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


def load_settings(gate, env=None):
    """Đọc cấu hình cho một cổng.

    env=None: lấy từ os.environ (gọi SAU khi đã nạp các file .env bằng load_env_file).
    env=dict: lấy từ dict đó (xem gate_env), dùng khi chạy cả hai cổng trong một tiến trình."""
    if gate not in GATES:
        raise ValueError(f"Cổng phải là một trong {sorted(GATES)}, không phải '{gate}'")
    g = GATES[gate]
    source = os.environ if env is None else env

    def _env(name, default):
        return source.get(name, default)

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


def check_dual(cfg_in, cfg_out):
    """Chạy cả hai cổng trong một cửa sổ: hai cổng KHÔNG được dùng chung cổng COM hay camera."""
    problems = []
    if cfg_in.rfid_port.strip().upper() == cfg_out.rfid_port.strip().upper():
        problems.append(f"hai cổng cùng dùng đầu đọc RFID {cfg_in.rfid_port}")
    if cfg_in.camera_index == cfg_out.camera_index:
        problems.append(f"hai cổng cùng dùng camera số {cfg_in.camera_index}")
    if problems:
        raise ValueError("Cấu hình sai: " + "; ".join(problems)
                         + ". Sửa RFID_PORT / CAMERA_INDEX trong .env.in và .env.out.")


MIN_VIEW_W = 240
_PANEL_EXTRA_W = 70     # lề + khung chữ quanh mỗi panel (ước lượng)


def fit_views(screen_w, *cfgs):
    """Thu nhỏ khung camera cho vừa chiều ngang màn hình khi xếp các cổng cạnh nhau.

    Mỗi panel rộng ~ 2*VIEW_W (camera + ảnh kết quả) + lề. Giữ tỉ lệ khung hiện tại."""
    n = len(cfgs)
    widest = max(c.view_w for c in cfgs)
    avail = (screen_w - 40) // n - _PANEL_EXTRA_W       # chiều ngang còn cho 2 khung ảnh của một panel
    max_view_w = max(MIN_VIEW_W, avail // 2)
    if widest <= max_view_w:
        return cfgs
    out = []
    for c in cfgs:
        w = min(c.view_w, max_view_w)
        h = max(1, round(c.view_h * w / c.view_w))
        out.append(replace(c, view_w=w, view_h=h))
    return tuple(out)
