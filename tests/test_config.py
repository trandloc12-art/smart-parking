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
