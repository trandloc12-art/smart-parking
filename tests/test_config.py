import pytest

import config


def test_load_env_file_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env.test"
    f.write_text('# ghi chú\nT_A=1\nT_B="hai"\nT_C=localhost\\SQLEXPRESS\n\nbad line\n', encoding="utf-8")
    monkeypatch.setenv("T_A", "da-co")
    monkeypatch.delenv("T_B", raising=False)
    monkeypatch.delenv("T_C", raising=False)
    assert config.load_env_file(str(f)) is True
    import os
    assert os.environ["T_A"] == "da-co"             # biến có sẵn thắng file
    assert os.environ["T_B"] == "hai"               # bỏ dấu nháy
    assert os.environ["T_C"] == "localhost\\SQLEXPRESS"
    monkeypatch.delenv("T_B"); monkeypatch.delenv("T_C")


def test_missing_file():
    assert config.load_env_file("/không/có/file") is False


def test_gate_defaults(monkeypatch):
    for k in ("CAMERA_INDEX", "RFID_PORT", "SCAN_FRAMES", "VOTE_MIN"):
        monkeypatch.delenv(k, raising=False)
    cin, cout = config.load_settings("in"), config.load_settings("out")
    assert (cin.camera_index, cin.rfid_port, cin.label) == (0, "COM3", "CỔNG VÀO")
    assert (cout.camera_index, cout.rfid_port, cout.label) == (1, "COM4", "CỔNG RA")
    assert cin.scan_frames == 5 and cin.vote_min == 2


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("CAMERA_INDEX", "3")
    monkeypatch.setenv("RFID_PORT", "COM9")
    s = config.load_settings("out")
    assert s.camera_index == 3 and s.rfid_port == "COM9"


def test_validation(monkeypatch):
    with pytest.raises(ValueError):
        config.load_settings("sideways")
    monkeypatch.setenv("SCAN_FRAMES", "3")
    monkeypatch.setenv("VOTE_MIN", "4")
    with pytest.raises(ValueError):
        config.load_settings("in")


def test_inline_comments_like_the_real_env_example(tmp_path, monkeypatch):
    """Định dạng thật trong .env.example của repo: chú thích nằm cùng dòng với giá trị."""
    f = tmp_path / ".env.real"
    f.write_text(
        "RFID_PORT=COM3                 #đổi cổng port\n"
        "DB_SERVER=localhost\\SQLEXPRESS #cần chỉnh sửa\n"
        "DB_USER=                       # nhập sa hoặc user khác\n"
        "DB_PASSWORD=ab#c               # dấu # dính liền giá trị thì giữ\n"
        "T_QUOTED=\"pa ss #1\"  # nháy bảo vệ dấu #\n"
        "BLOCK_MINUTES=60", encoding="utf-8")                      # dòng cuối không có xuống dòng
    keys = ["RFID_PORT", "DB_SERVER", "DB_USER", "DB_PASSWORD", "T_QUOTED", "BLOCK_MINUTES"]
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    config.load_env_file(str(f))
    import os
    got = {k: os.environ.get(k) for k in keys}
    for k in keys:
        monkeypatch.delenv(k, raising=False)
    assert got == {"RFID_PORT": "COM3", "DB_SERVER": "localhost\\SQLEXPRESS", "DB_USER": "",
                   "DB_PASSWORD": "ab#c", "T_QUOTED": "pa ss #1", "BLOCK_MINUTES": "60"}


# ---------- Chạy cả hai cổng trong một tiến trình ----------
def test_read_env_file_returns_dict_without_touching_environ(tmp_path, monkeypatch):
    f = tmp_path / ".env.x"
    f.write_text("T_ONLY_FILE=abc  # chú thích\n", encoding="utf-8")
    monkeypatch.delenv("T_ONLY_FILE", raising=False)
    import os
    assert config.read_env_file(str(f)) == {"T_ONLY_FILE": "abc"}
    assert "T_ONLY_FILE" not in os.environ
    assert config.read_env_file(str(tmp_path / "khong-co")) is None


def test_gate_env_keeps_each_gate_separate(tmp_path):
    """Lỗi cũ: nạp .env.in rồi .env.out vào os.environ thì RFID_PORT của cổng ra bị cổng vào chiếm."""
    (tmp_path / ".env").write_text("DB_NAME=Chung\nRFID_PORT=COM1\nSCAN_FRAMES=4\n", encoding="utf-8")
    (tmp_path / ".env.in").write_text("RFID_PORT=COM3\nCAMERA_INDEX=0\n", encoding="utf-8")
    (tmp_path / ".env.out").write_text("RFID_PORT=COM4\nCAMERA_INDEX=1\n", encoding="utf-8")
    env_in, has_in = config.gate_env("in", str(tmp_path), environ={})
    env_out, has_out = config.gate_env("out", str(tmp_path), environ={})
    cin, cout = config.load_settings("in", env_in), config.load_settings("out", env_out)
    assert has_in and has_out
    assert (cin.rfid_port, cin.camera_index) == ("COM3", 0)
    assert (cout.rfid_port, cout.camera_index) == ("COM4", 1)
    assert cin.db_name == cout.db_name == "Chung" and cin.scan_frames == cout.scan_frames == 4


def test_gate_env_priority_and_missing_gate_file(tmp_path):
    (tmp_path / ".env").write_text("RFID_PORT=COM1\n", encoding="utf-8")
    env, has_file = config.gate_env("out", str(tmp_path), environ={})
    assert has_file is False and env["RFID_PORT"] == "COM1"      # không có .env.out -> lấy .env
    (tmp_path / ".env.out").write_text("RFID_PORT=COM4\n", encoding="utf-8")
    env, _ = config.gate_env("out", str(tmp_path), environ={})
    assert env["RFID_PORT"] == "COM4"                            # file riêng cổng thắng file chung
    env, _ = config.gate_env("out", str(tmp_path), environ={"RFID_PORT": "COM9"})
    assert env["RFID_PORT"] == "COM9"                            # biến môi trường thắng tất cả


def test_check_dual():
    cin, cout = config.load_settings("in", {}), config.load_settings("out", {})
    config.check_dual(cin, cout)                                 # mặc định COM3/0 và COM4/1: ổn
    same_port = config.load_settings("out", {"RFID_PORT": "com3"})
    with pytest.raises(ValueError, match="RFID"):
        config.check_dual(cin, same_port)
    same_cam = config.load_settings("out", {"CAMERA_INDEX": "0"})
    with pytest.raises(ValueError, match="camera"):
        config.check_dual(cin, same_cam)


def test_fit_views():
    cin, cout = config.load_settings("in", {}), config.load_settings("out", {})      # 420x315
    assert config.fit_views(1920, cin, cout) == (cin, cout)       # vừa màn 1920: giữ nguyên
    small_in, small_out = config.fit_views(1366, cin, cout)       # màn nhỏ: thu nhỏ, giữ tỉ lệ 4:3
    assert small_in.view_w < 420 and small_in.view_w == small_out.view_w
    assert small_in.view_h == round(315 * small_in.view_w / 420)
    assert 2 * (2 * small_in.view_w + 70) <= 1366
    tiny_in, _ = config.fit_views(800, cin, cout)                 # màn quá nhỏ: không nhỏ hơn mức tối thiểu
    assert tiny_in.view_w == config.MIN_VIEW_W
