"""Cấu hình tập trung. Đọc từ biến môi trường (có thể nạp từ file .env, xem load_env_file).

Phần cứng: MỘT Arduino (một cổng COM) nối HAI đầu đọc RFID; Arduino gửi mỗi thẻ kèm tên cổng (xem hardware/rfid.py).
Có hai cách chạy:
  - `python main.py`            (hoặc `--gate both`): MỘT cửa sổ chứa cả cổng vào và cổng ra.
  - `python main.py --gate in|out`: chỉ một cổng (thẻ của cổng kia bị bỏ qua).
Cổng nào cũng đọc `.env.<gate>` (riêng cổng: camera...) rồi `.env` (chung: RFID_PORT, SQL Server, giá tiền...).
Thứ tự ưu tiên: biến môi trường có sẵn > `.env.<gate>` > `.env` > mặc định.
"""
import os
from dataclasses import dataclass, replace

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Mặc định riêng từng cổng (ghi đè bằng CAMERA_INDEX trong .env.<gate>)
GATES = {
    "in":  {"label": "CỔNG VÀO", "camera_index": 0},
    "out": {"label": "CỔNG RA",  "camera_index": 1},
}
DEFAULT_RFID_PORT = "COM3"      # MỘT Arduino chung cho cả hai cổng (ghi đè bằng RFID_PORT trong .env)


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


def read_env_file(path, raw=False):
    """Đọc file KEY=VALUE thành dict (không đụng os.environ). Trả về None nếu không có file.

    raw=True: giữ nguyên chữ sau dấu '=' (chưa bỏ nháy / chú thích), dùng cho gate_env."""
    if not os.path.isfile(path):
        return None
    values = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip() if raw else _parse_value(value)
    return values


def load_env_file(path):
    """Nạp file KEY=VALUE vào os.environ. Biến đã tồn tại KHÔNG bị ghi đè. Trả về True nếu có file."""
    values = read_env_file(path)
    if values is None:
        return False
    for key, value in values.items():
        os.environ.setdefault(key, value)
    return True


def _as_ide_injects(raw):
    """Giá trị VS Code (python.envFile) nạp vào môi trường từ một dòng .env: chỉ bỏ cặp nháy bao quanh,
    KHÔNG bỏ chú thích cùng dòng (`KEY=2.0   # ghi chú` thành "2.0   # ghi chú")."""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def gate_env(gate, base_dir=BASE_DIR, environ=None):
    """Cấu hình đã gộp cho MỘT cổng, không đụng os.environ (nên đọc được cả hai cổng trong một tiến trình).

    Ưu tiên: biến môi trường có sẵn > .env.<gate> > .env. Trả về (dict, có_file_riêng_cổng).

    Ngoại lệ: biến môi trường chỉ là BẢN SAO chưa bỏ chú thích của chính dòng trong file .env (VS Code
    tự nạp .env khi bấm F5 / mở terminal, và nạp cả chú thích) thì bỏ qua, dùng giá trị đã phân tích của file.
    Biến môi trường do người dùng tự đặt (khác chữ trong file) vẫn thắng như cũ."""
    environ = os.environ if environ is None else environ
    gate_path, common_path = os.path.join(base_dir, f".env.{gate}"), os.path.join(base_dir, ".env")
    gate_file, common = read_env_file(gate_path), read_env_file(common_path)

    copies = set()
    for raw_values in (read_env_file(common_path, raw=True), read_env_file(gate_path, raw=True)):
        for key, raw in (raw_values or {}).items():
            if environ.get(key) == _as_ide_injects(raw):
                copies.add(key)
    real_environ = {k: v for k, v in environ.items() if k not in copies}
    return {**(common or {}), **(gate_file or {}), **real_environ}, gate_file is not None


@dataclass(frozen=True)
class Settings:
    gate: str                  # "in" | "out"
    label: str
    # Camera (riêng từng cổng)
    camera_index: int
    # Arduino + 2 đầu đọc RFID (chung cho cả hai cổng)
    rfid_port: str
    rfid_baud: int
    rfid_debounce: float       # giây, bỏ qua quẹt trùng cùng thẻ ở cùng một cổng
    rfid_heartbeat: float      # giây không nhận được gì từ Arduino thì báo mất kết nối; 0 = không kiểm tra
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
    servo_enabled: bool = True      # False = không gửi lệnh mở thanh chắn (chưa gắn servo)
    servo_open_seconds: float = 3.0 # giây giữ thanh chắn mở sau khi quẹt thẻ thành công rồi Arduino tự đóng lại
    lcd_idle_seconds: float = 5.0   # giây: thông báo xong việc (xe vào/ra OK, thẻ bị từ chối) tự về "MOI QUET THE"; 0 = giữ đến lần quẹt sau


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

    def _num(name, default, cast=int):
        raw = _env(name, default)
        try:
            return cast(raw)
        except ValueError:
            raise ValueError(f"{name} phải là số nhưng đang là {raw!r}. Kiểm tra file .env* "
                             "(chú thích nên đặt ở dòng riêng, bắt đầu bằng #)") from None

    s = Settings(
        gate=gate,
        label=g["label"],
        camera_index=_num("CAMERA_INDEX", str(g["camera_index"])),
        rfid_port=_env("RFID_PORT", DEFAULT_RFID_PORT),
        rfid_baud=_num("RFID_BAUD", "9600"),
        rfid_debounce=_num("RFID_DEBOUNCE", "2.0", float),
        rfid_heartbeat=_num("RFID_HEARTBEAT_TIMEOUT", "8", float),
        db_server=_env("DB_SERVER", r"localhost\SQLEXPRESS"),
        db_name=_env("DB_NAME", "BienSoDB"),
        db_user=_env("DB_USER", ""),
        db_password=_env("DB_PASSWORD", ""),
        db_driver=_env("DB_DRIVER", "ODBC Driver 17 for SQL Server"),
        image_dir=_env("IMG_DIR", os.path.join(BASE_DIR, "anh_chup")),
        auto_save=_env("AUTO_SAVE", "1") == "1",
        price_per_block=_num("PRICE_PER_BLOCK", "5000"),
        block_minutes=_num("BLOCK_MINUTES", "60"),
        scan_frames=_num("SCAN_FRAMES", "5"),
        scan_interval=_num("SCAN_INTERVAL", "0.25", float),
        vote_min=_num("VOTE_MIN", "2"),
        view_w=_num("VIEW_W", "420"),
        view_h=_num("VIEW_H", "315"),
        window_pos=_env("WINDOW_POS", ""),
        lcd_idle_seconds=_num("LCD_IDLE_SECONDS", "5", float),
        servo_enabled=_env("SERVO_ENABLED", "1") == "1",
        servo_open_seconds=_num("SERVO_OPEN_SECONDS", "3", float),
    )
    if s.scan_frames < 1:
        raise ValueError("SCAN_FRAMES phải >= 1")
    if not 1 <= s.vote_min <= s.scan_frames:
        raise ValueError("VOTE_MIN phải nằm trong khoảng 1..SCAN_FRAMES")
    if s.lcd_idle_seconds < 0:
        raise ValueError("LCD_IDLE_SECONDS phải >= 0 (0 = không tự quay về)")
    if not 0.5 <= s.servo_open_seconds <= 30:
        raise ValueError("SERVO_OPEN_SECONDS phải nằm trong khoảng 0.5..30 giây")
    if s.rfid_heartbeat < 0:
        raise ValueError("RFID_HEARTBEAT_TIMEOUT phải >= 0 (0 = tắt kiểm tra)")
    if s.block_minutes < 1 or s.price_per_block < 0:
        raise ValueError("BLOCK_MINUTES phải >= 1 và PRICE_PER_BLOCK phải >= 0")
    return s


def check_dual(cfg_in, cfg_out):
    """Chạy cả hai cổng trong một cửa sổ.

    Chỉ có MỘT Arduino nên hai cổng phải dùng CÙNG một RFID_PORT (lỗi hay gặp khi còn sót
    RFID_PORT của thời hai Arduino trong .env.in / .env.out), nhưng phải dùng camera KHÁC nhau."""
    problems = []
    port_in, port_out = cfg_in.rfid_port.strip(), cfg_out.rfid_port.strip()
    if port_in.upper() != port_out.upper():
        problems.append(f"hai cổng khai báo RFID_PORT khác nhau ({port_in} / {port_out}); "
                        "chỉ có MỘT Arduino nên hãy đặt RFID_PORT trong .env và xóa khỏi .env.in / .env.out")
    if cfg_in.camera_index == cfg_out.camera_index:
        problems.append(f"hai cổng cùng dùng camera số {cfg_in.camera_index} "
                        "(sửa CAMERA_INDEX trong .env.in và .env.out)")
    if problems:
        raise ValueError("Cấu hình sai: " + "; ".join(problems) + ".")


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
