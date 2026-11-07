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
    for k in ("CAMERA_INDEX", "RFID_PORT", "SCAN_FRAMES", "VOTE_MIN", "RFID_HEARTBEAT_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)
    cin, cout = config.load_settings("in"), config.load_settings("out")
    assert (cin.camera_index, cin.label) == (0, "CỔNG VÀO")
    assert (cout.camera_index, cout.label) == (1, "CỔNG RA")
    assert cin.rfid_port == cout.rfid_port == "COM3"        # MỘT Arduino chung cho cả hai cổng
    assert cin.rfid_heartbeat == 8
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
    """Lỗi cũ: nạp .env.in rồi .env.out vào os.environ thì CAMERA_INDEX của cổng ra bị cổng vào chiếm."""
    (tmp_path / ".env").write_text("DB_NAME=Chung\nRFID_PORT=COM7\nSCAN_FRAMES=4\n", encoding="utf-8")
    (tmp_path / ".env.in").write_text("CAMERA_INDEX=0\n", encoding="utf-8")
    (tmp_path / ".env.out").write_text("CAMERA_INDEX=1\n", encoding="utf-8")
    env_in, has_in = config.gate_env("in", str(tmp_path), environ={})
    env_out, has_out = config.gate_env("out", str(tmp_path), environ={})
    cin, cout = config.load_settings("in", env_in), config.load_settings("out", env_out)
    assert has_in and has_out
    assert (cin.camera_index, cout.camera_index) == (0, 1)
    assert cin.rfid_port == cout.rfid_port == "COM7"             # một Arduino: RFID_PORT khai báo chung ở .env
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
    config.check_dual(cin, cout)                                 # mặc định: cùng COM3, camera 0 và 1: ổn
    same_port_other_case = config.load_settings("out", {"RFID_PORT": "com3"})
    config.check_dual(cin, same_port_other_case)                 # cùng cổng COM (khác hoa/thường) vẫn ổn
    leftover = config.load_settings("out", {"RFID_PORT": "COM4"})   # sót RFID_PORT của thời hai Arduino
    with pytest.raises(ValueError, match="RFID_PORT.*MỘT Arduino"):
        config.check_dual(cin, leftover)
    same_cam = config.load_settings("out", {"CAMERA_INDEX": "0"})
    with pytest.raises(ValueError, match="camera"):
        config.check_dual(cin, same_cam)


def test_heartbeat_setting():
    assert config.load_settings("in", {"RFID_HEARTBEAT_TIMEOUT": "0"}).rfid_heartbeat == 0   # 0 = tắt
    with pytest.raises(ValueError, match="RFID_HEARTBEAT_TIMEOUT"):
        config.load_settings("in", {"RFID_HEARTBEAT_TIMEOUT": "-1"})


def test_fit_views():
    cin, cout = config.load_settings("in", {}), config.load_settings("out", {})      # 420x315
    assert config.fit_views(1920, cin, cout) == (cin, cout)       # vừa màn 1920: giữ nguyên
    small_in, small_out = config.fit_views(1366, cin, cout)       # màn nhỏ: thu nhỏ, giữ tỉ lệ 4:3
    assert small_in.view_w < 420 and small_in.view_w == small_out.view_w
    assert small_in.view_h == round(315 * small_in.view_w / 420)
    assert 2 * (2 * small_in.view_w + 70) <= 1366
    tiny_in, _ = config.fit_views(800, cin, cout)                 # màn quá nhỏ: không nhỏ hơn mức tối thiểu
    assert tiny_in.view_w == config.MIN_VIEW_W


# ---------------------------------------------------------------- VS Code tự nạp .env (kèm chú thích)
def vscode_environ(text):
    """Mô phỏng python.envFile của VS Code (parseEnvLine): chỉ bỏ cặp nháy, KHÔNG bỏ chú thích cùng dòng."""
    import re
    env = {}
    for line in text.split("\n"):
        m = re.match(r"^\s*(_*[a-zA-Z]\w*)\s*=\s*(.*?)?\s*$", line)
        if not m:
            continue
        value = m.group(2) or ""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[m.group(1)] = value
    return env


def test_vscode_injected_env_with_inline_comments_is_ignored(tmp_path):
    """Lỗi thật: bấm F5 trong VS Code -> RFID_DEBOUNCE='2.0   # giây, ...' nằm trong os.environ và thắng file."""
    import os
    example = open(os.path.join(config.BASE_DIR, ".env.example"), encoding="utf-8").read()
    (tmp_path / ".env").write_text(example, encoding="utf-8")
    injected = vscode_environ(example)
    assert "#" in injected["RFID_DEBOUNCE"]                       # đúng là VS Code mang cả chú thích vào

    env, _ = config.gate_env("in", str(tmp_path), environ=injected)
    s = config.load_settings("in", env)                           # trước đây: ValueError ở RFID_DEBOUNCE
    assert s.rfid_debounce == 2.0 and s.rfid_heartbeat == 8 and s.scan_frames == 5
    assert s.auto_save is True                                    # "1   # ..." trước đây lặng lẽ thành False
    assert s.db_server == "localhost\\SQLEXPRESS"                 # không dính chú thích vào tên server
    assert s.rfid_port == "COM3"


def test_real_environment_variable_still_wins_over_file(tmp_path):
    (tmp_path / ".env").write_text("RFID_DEBOUNCE=2.0   # giây\nRFID_PORT=COM3\n", encoding="utf-8")
    environ = {"RFID_DEBOUNCE": "5.0", "RFID_PORT": "COM3"}       # người dùng tự đặt khác chữ trong file
    env, _ = config.gate_env("in", str(tmp_path), environ=environ)
    assert env["RFID_DEBOUNCE"] == "5.0"


def test_quoted_value_injected_by_vscode_keeps_hash(tmp_path):
    (tmp_path / ".env").write_text('DB_PASSWORD="ab #c"   # mật khẩu\n', encoding="utf-8")
    env, _ = config.gate_env("in", str(tmp_path), environ=vscode_environ('DB_PASSWORD="ab #c"   # mật khẩu\n'))
    assert env["DB_PASSWORD"] == "ab #c"


def test_bad_number_error_names_the_variable():
    with pytest.raises(ValueError, match=r"RFID_DEBOUNCE phải là số nhưng đang là '2\.0 # giây'"):
        config.load_settings("in", {"RFID_DEBOUNCE": "2.0 # giây"})
    with pytest.raises(ValueError, match="SCAN_FRAMES phải là số"):
        config.load_settings("in", {"SCAN_FRAMES": "năm"})


def test_lcd_idle_seconds(monkeypatch):
    monkeypatch.delenv("LCD_IDLE_SECONDS", raising=False)
    assert config.load_settings("in").lcd_idle_seconds == 5.0
    monkeypatch.setenv("LCD_IDLE_SECONDS", "2.5")
    assert config.load_settings("out").lcd_idle_seconds == 2.5
    monkeypatch.setenv("LCD_IDLE_SECONDS", "0")
    assert config.load_settings("in").lcd_idle_seconds == 0
    monkeypatch.setenv("LCD_IDLE_SECONDS", "-1")
    with pytest.raises(ValueError):
        config.load_settings("in")


def test_servo_settings(monkeypatch):
    monkeypatch.delenv("SERVO_ENABLED", raising=False)
    monkeypatch.delenv("SERVO_OPEN_SECONDS", raising=False)
    s = config.load_settings("in")
    assert s.servo_enabled is True and s.servo_open_seconds == 3.0
    monkeypatch.setenv("SERVO_ENABLED", "0")
    monkeypatch.setenv("SERVO_OPEN_SECONDS", "5.5")
    s = config.load_settings("out")
    assert s.servo_enabled is False and s.servo_open_seconds == 5.5


@pytest.mark.parametrize("value", ["0", "0.1", "31", "-2"])
def test_servo_open_seconds_out_of_range_is_rejected(monkeypatch, value):
    monkeypatch.setenv("SERVO_OPEN_SECONDS", value)
    with pytest.raises(ValueError, match="SERVO_OPEN_SECONDS"):
        config.load_settings("in")


def test_servo_open_seconds_must_be_a_number(monkeypatch):
    monkeypatch.setenv("SERVO_OPEN_SECONDS", "ba")
    with pytest.raises(ValueError, match="SERVO_OPEN_SECONDS phải là số"):
        config.load_settings("in")


def test_ir_setting(monkeypatch):
    monkeypatch.delenv("IR_ENABLED", raising=False)
    assert config.load_settings("in").ir_enabled is True            # mặc định bật
    monkeypatch.setenv("IR_ENABLED", "0")
    assert config.load_settings("out").ir_enabled is False          # chưa gắn cảm biến thì tắt
    assert config.load_settings("in", {"IR_ENABLED": "1"}).ir_enabled is True


def test_ir_default_is_in_env_example(tmp_path):
    import os
    example = open(os.path.join(config.BASE_DIR, ".env.example"), encoding="utf-8").read()
    assert "IR_ENABLED=1" in example
    (tmp_path / ".env").write_text(example, encoding="utf-8")
    env, _ = config.gate_env("in", str(tmp_path), environ={})
    assert config.load_settings("in", env).ir_enabled is True


def test_servo_defaults_are_in_env_example(tmp_path):
    import os
    example = open(os.path.join(config.BASE_DIR, ".env.example"), encoding="utf-8").read()
    (tmp_path / ".env").write_text(example, encoding="utf-8")
    env, _ = config.gate_env("in", str(tmp_path), environ={})
    s = config.load_settings("in", env)
    assert s.servo_enabled is True and s.servo_open_seconds == 3.0
    assert (s.servo_closed_angle, s.servo_open_angle) == (0, 90)


def test_servo_angle_settings(monkeypatch):
    monkeypatch.delenv("SERVO_CLOSED_ANGLE", raising=False)
    monkeypatch.delenv("SERVO_OPEN_ANGLE", raising=False)
    s = config.load_settings("in")
    assert (s.servo_closed_angle, s.servo_open_angle) == (0, 90)          # mặc định khớp firmware
    monkeypatch.setenv("SERVO_CLOSED_ANGLE", "10")
    monkeypatch.setenv("SERVO_OPEN_ANGLE", "120")
    s = config.load_settings("out")
    assert (s.servo_closed_angle, s.servo_open_angle) == (10, 120)
    # servo quay ngược: đảo hai góc là hợp lệ
    assert config.load_settings("in", {"SERVO_CLOSED_ANGLE": "90", "SERVO_OPEN_ANGLE": "0"}).servo_closed_angle == 90


def test_servo_angles_can_differ_per_gate(tmp_path):
    (tmp_path / ".env").write_text("SERVO_OPEN_ANGLE=90\n", encoding="utf-8")
    (tmp_path / ".env.out").write_text("SERVO_OPEN_ANGLE=110\n", encoding="utf-8")
    env_in, _ = config.gate_env("in", str(tmp_path), environ={})
    env_out, _ = config.gate_env("out", str(tmp_path), environ={})
    assert config.load_settings("in", env_in).servo_open_angle == 90
    assert config.load_settings("out", env_out).servo_open_angle == 110


@pytest.mark.parametrize("name", ["SERVO_CLOSED_ANGLE", "SERVO_OPEN_ANGLE"])
@pytest.mark.parametrize("value", ["-1", "181", "360"])
def test_servo_angle_out_of_range_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        config.load_settings("in")


def test_servo_angles_must_differ_and_be_integers(monkeypatch):
    with pytest.raises(ValueError, match="không được bằng nhau"):
        config.load_settings("in", {"SERVO_CLOSED_ANGLE": "45", "SERVO_OPEN_ANGLE": "45"})
    monkeypatch.setenv("SERVO_OPEN_ANGLE", "chín mươi")
    with pytest.raises(ValueError, match="SERVO_OPEN_ANGLE phải là số"):
        config.load_settings("in")


def test_parking_capacity(monkeypatch):
    monkeypatch.delenv("PARKING_CAPACITY", raising=False)
    assert config.load_settings("in").parking_capacity == 3          # mặc định: 3 slot
    monkeypatch.setenv("PARKING_CAPACITY", "5")
    assert config.load_settings("out").parking_capacity == 5


@pytest.mark.parametrize("value", ["0", "-1"])
def test_parking_capacity_must_be_positive(monkeypatch, value):
    monkeypatch.setenv("PARKING_CAPACITY", value)
    with pytest.raises(ValueError, match="PARKING_CAPACITY"):
        config.load_settings("in")


def test_parking_capacity_must_be_a_number(monkeypatch):
    monkeypatch.setenv("PARKING_CAPACITY", "ba")
    with pytest.raises(ValueError, match="PARKING_CAPACITY phải là số"):
        config.load_settings("in")


def test_parking_capacity_default_is_in_env_example(tmp_path):
    import os
    example = open(os.path.join(config.BASE_DIR, ".env.example"), encoding="utf-8").read()
    (tmp_path / ".env").write_text(example, encoding="utf-8")
    env, _ = config.gate_env("in", str(tmp_path), environ={})
    assert env["PARKING_CAPACITY"] == "3"
    assert config.load_settings("in", env).parking_capacity == 3


def test_ir_pass_timeout_default_and_override(monkeypatch):
    monkeypatch.delenv("IR_PASS_TIMEOUT_SECONDS", raising=False)
    assert config.load_settings("in").ir_pass_timeout_seconds == 3.0        # mặc định 3 giây
    monkeypatch.setenv("IR_PASS_TIMEOUT_SECONDS", "4.5")
    assert config.load_settings("out").ir_pass_timeout_seconds == 4.5
    assert config.load_settings("in", {"IR_PASS_TIMEOUT_SECONDS": "6"}).ir_pass_timeout_seconds == 6.0


@pytest.mark.parametrize("value", ["0", "0.2", "31", "-1"])
def test_ir_pass_timeout_out_of_range_is_rejected(monkeypatch, value):
    monkeypatch.setenv("IR_PASS_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="IR_PASS_TIMEOUT_SECONDS"):
        config.load_settings("in")


def test_ir_pass_timeout_must_be_a_number(monkeypatch):
    monkeypatch.setenv("IR_PASS_TIMEOUT_SECONDS", "ba")
    with pytest.raises(ValueError, match="IR_PASS_TIMEOUT_SECONDS phải là số"):
        config.load_settings("in")


def test_ir_pass_timeout_default_is_in_env_example(tmp_path):
    import os
    example = open(os.path.join(config.BASE_DIR, ".env.example"), encoding="utf-8").read()
    assert "IR_PASS_TIMEOUT_SECONDS=3" in example
    (tmp_path / ".env").write_text(example, encoding="utf-8")
    env, _ = config.gate_env("in", str(tmp_path), environ={})
    assert config.load_settings("in", env).ir_pass_timeout_seconds == 3.0


def test_ir_pass_timeout_can_differ_per_gate(tmp_path):
    (tmp_path / ".env").write_text("IR_PASS_TIMEOUT_SECONDS=3\n", encoding="utf-8")
    (tmp_path / ".env.out").write_text("CAMERA_INDEX=1\nIR_PASS_TIMEOUT_SECONDS=5\n", encoding="utf-8")
    env_in, _ = config.gate_env("in", str(tmp_path), environ={})
    env_out, _ = config.gate_env("out", str(tmp_path), environ={})
    assert config.load_settings("in", env_in).ir_pass_timeout_seconds == 3.0
    assert config.load_settings("out", env_out).ir_pass_timeout_seconds == 5.0
