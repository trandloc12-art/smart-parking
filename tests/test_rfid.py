"""MỘT Arduino, HAI đầu đọc: giao thức một dòng và luồng đọc Serial (dùng cổng Serial giả, không cần phần cứng)."""
import pytest
import serial

from hardware.rfid import (
    ArduinoRfidReader, BadLine, BarrierEvent, CardSwipe, ReaderStatus, format_lcd_command,
    buzzer_init_commands, format_buzzer_command, format_servo_angle_command, format_servo_command, lcd_text, parse_line, servo_init_commands,
)


# ---------------------------------------------------------------- parse_line
def test_parse_card_swipes():
    assert parse_line("IN:AB1992CA\r\n") == CardSwipe("in", "AB1992CA")
    assert parse_line("OUT:DB2B11CA\n") == CardSwipe("out", "DB2B11CA")
    assert parse_line("out:db2b11ca") == CardSwipe("out", "DB2B11CA")            # không phân biệt hoa/thường
    assert parse_line("IN : AB 19 92 CA") == CardSwipe("in", "AB1992CA")         # bỏ dấu cách
    assert parse_line("IN:AB:19:92:CA") == CardSwipe("in", "AB1992CA")           # bỏ dấu ':' trong UID


def test_parse_reader_status():
    assert parse_line("STATUS:IN=1,OUT=0") == ReaderStatus({"in": True, "out": False})
    assert parse_line("status: out=1") == ReaderStatus({"out": True})            # chỉ báo một đầu đọc cũng được


def test_parse_barrier_events():
    assert parse_line("PASS:IN\r\n") == BarrierEvent("in", True)
    assert parse_line("PASS:OUT") == BarrierEvent("out", True)
    assert parse_line("NOPASS:IN") == BarrierEvent("in", False)
    assert parse_line("nopass: out") == BarrierEvent("out", False)               # không phân biệt hoa/thường


@pytest.mark.parametrize("line", ["PASS", "PASS:", "PASS:LEFT", "NOPASS:", "NOPASS:AB1992CA", "PASSED:IN"])
def test_parse_bad_barrier_lines(line):
    assert parse_line(line) == BadLine(line)


@pytest.mark.parametrize("line", ["", "   \r\n", "# dual_rfid san sang", "#"])
def test_parse_ignores_blank_and_comment_lines(line):
    assert parse_line(line) is None


@pytest.mark.parametrize("line", [
    "AB1992CA",              # firmware cũ: có UID nhưng không biết cổng nào
    "IN:", "IN:AB",          # thiếu / quá ngắn
    "IN:ZZ!!11",             # ký tự lạ
    "GATE:AB1992CA",         # tiền tố lạ
    "STATUS:", "STATUS:IN=2", "STATUS:FOO=1",
])
def test_parse_bad_lines(line):
    assert parse_line(line) == BadLine(line)


# ---------------------------------------------------------------- luồng đọc với Serial giả
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeSerial:
    """Mỗi phần tử của script: bytes = một dòng; số = hết thời gian chờ readline sau ngần ấy giây (trả b'');
    ngoại lệ = ném ra. Hết script thì dừng luồng đọc."""

    def __init__(self, script, clock, stop):
        self.script, self.clock, self.stop = list(script), clock, stop

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def readline(self):
        if not self.script:
            self.stop()
            return b""
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, (int, float)):
            self.clock.t += item
            return b""
        return item


class Recorder:
    def __init__(self):
        self.cards, self.status, self.readers, self.barriers = [], [], [], []

    def on_barrier(self, gate, passed):
        self.barriers.append((gate, passed))

    def on_card(self, gate, uid):
        self.cards.append((gate, uid))

    def on_status(self, connected, message):
        self.status.append((connected, message))

    def on_reader(self, gate, ok):
        self.readers.append((gate, ok))


def run_reader(opens, **kwargs):
    """opens: mỗi phần tử là script của một lần mở cổng COM, hoặc một ngoại lệ (mở cổng thất bại)."""
    rec, clock, opens = Recorder(), Clock(), list(opens)
    box = {}

    def factory(port, baud, timeout):
        item = opens.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeSerial(item, clock, lambda: box["reader"].stop())

    box["reader"] = ArduinoRfidReader("COM3", 9600, rec.on_card, rec.on_status, rec.on_reader,
                                      on_barrier=rec.on_barrier,
                                      serial_factory=factory, clock=clock, sleep=lambda s: None, **kwargs)
    box["reader"].run()          # chạy thẳng ở luồng này; luồng đọc tự dừng khi hết script
    return rec


def test_cards_are_routed_to_the_right_gate():
    rec = run_reader([[b"# san sang\n", b"STATUS:IN=1,OUT=1\n", b"IN:AB1992CA\n", b"OUT:DB2B11CA\n"]])
    assert rec.cards == [("in", "AB1992CA"), ("out", "DB2B11CA")]
    assert rec.status == [(True, "Arduino: đã kết nối COM3")]
    assert rec.readers == [("in", True), ("out", True)]


def test_barrier_results_are_routed_to_the_right_gate():
    rec = run_reader([[b"STATUS:IN=1,OUT=1\n", b"IN:AB1992CA\n", b"PASS:IN\n", b"OUT:DB2B11CA\n",
                       b"NOPASS:OUT\n", b"PASS:IN\n"]])
    assert rec.barriers == [("in", True), ("out", False), ("in", True)]     # không chống trùng: mỗi dòng là một kết quả
    assert rec.cards == [("in", "AB1992CA"), ("out", "DB2B11CA")]           # kết quả thanh chắn không lẫn vào thẻ
    assert rec.status == [(True, "Arduino: đã kết nối COM3")]               # và không làm báo sai định dạng


def test_barrier_lines_count_as_a_sign_of_life_and_do_not_trigger_format_alert():
    rec = run_reader([[b"PASS:IN\n", b"PASS:OUT\n", b"NOPASS:IN\n", b"NOPASS:OUT\n"]])
    assert rec.status == [(True, "Arduino: đã kết nối COM3")]
    assert len(rec.barriers) == 4


def test_reader_without_barrier_callback_ignores_results():
    box = {}

    def factory(port, baud, timeout):
        return FakeSerial([b"PASS:IN\n"], Clock(), lambda: box["reader"].stop())

    box["reader"] = ArduinoRfidReader("COM3", 9600, lambda g, u: None, serial_factory=factory,
                                      sleep=lambda s: None)
    box["reader"].run()          # không có on_barrier: không được ném lỗi


def test_debounce_is_per_gate_and_per_card():
    rec = run_reader([[b"IN:AAAA1111\n", b"IN:AAAA1111\n",          # quẹt trùng ở cùng cổng: bỏ
                       b"OUT:AAAA1111\n",                           # cùng thẻ nhưng ở CỔNG KHÁC: hợp lệ
                       b"IN:BBBB2222\n",                            # thẻ khác: hợp lệ
                       3.0, b"IN:AAAA1111\n"]],                     # sau khoảng chống trùng: hợp lệ
                     heartbeat_timeout=0)
    assert rec.cards == [("in", "AAAA1111"), ("out", "AAAA1111"), ("in", "BBBB2222"), ("in", "AAAA1111")]


def test_one_reader_down_is_reported_for_that_gate_only():
    rec = run_reader([[b"STATUS:IN=1,OUT=0\n"]])
    assert rec.readers == [("in", True), ("out", False)]
    assert rec.status == [(True, "Arduino: đã kết nối COM3")]       # Arduino vẫn tốt, chỉ đầu đọc RA lỗi


def test_com_port_failure_then_reconnect():
    rec = run_reader([serial.SerialException("could not open port 'COM3'"),
                      [b"STATUS:IN=1,OUT=1\n", b"IN:AAAA1111\n"]])
    connected, message = rec.status[0]
    assert connected is False and "MẤT KẾT NỐI COM3" in message and "could not open port" in message
    assert rec.readers[:2] == [("in", None), ("out", None)]         # chưa rõ chứ không đổ lỗi cho đầu đọc
    assert rec.status[1] == (True, "Arduino: đã kết nối COM3")      # cắm lại -> tự báo kết nối lại
    assert rec.cards == [("in", "AAAA1111")]


def test_unplugged_while_running_is_reported():
    rec = run_reader([[b"STATUS:IN=1,OUT=1\n", serial.SerialException("device disconnected")],
                      [b"STATUS:IN=1,OUT=1\n"]])
    assert [c for c, _ in rec.status] == [True, False, True]
    assert rec.readers == [("in", True), ("out", True), ("in", None), ("out", None), ("in", True), ("out", True)]


def test_silent_arduino_is_reported_then_recovers():
    rec = run_reader([[b"STATUS:IN=1,OUT=1\n", 5, 5, b"STATUS:IN=1,OUT=1\n"]], heartbeat_timeout=8)
    assert [c for c, _ in rec.status] == [True, False, True]
    assert "KHÔNG PHẢN HỒI" in rec.status[1][1] and "8" in rec.status[1][1]
    assert rec.readers == [("in", True), ("out", True), ("in", None), ("out", None), ("in", True), ("out", True)]


def test_short_silence_and_disabled_heartbeat_do_not_alert():
    rec = run_reader([[b"STATUS:IN=1,OUT=1\n", 5, b"STATUS:IN=1,OUT=1\n"]], heartbeat_timeout=8)
    assert [c for c, _ in rec.status] == [True]
    rec = run_reader([[b"STATUS:IN=1,OUT=1\n", 600]], heartbeat_timeout=0)
    assert [c for c, _ in rec.status] == [True]


def test_old_firmware_without_gate_prefix_is_reported():
    """Arduino còn nạp firmware cũ (chỉ gửi UID trần): không biết cổng nào, phải báo rõ chứ không im lặng."""
    rec = run_reader([[b"AB1992CA\n", b"AB1992CA\n"]])
    assert [c for c, _ in rec.status] == [True]                      # mới 2 dòng lạ: có thể là rác lúc khởi động
    rec = run_reader([[b"AB1992CA\n", b"1B12E1CB\n", b"DB2B11CA\n"]])
    assert [c for c, _ in rec.status] == [True, False]
    assert "sai định dạng" in rec.status[1][1] and "dual_rfid" in rec.status[1][1]
    assert rec.cards == []                                           # tuyệt đối không đoán cổng


def test_format_alert_clears_when_valid_line_arrives():
    rec = run_reader([[b"xx\n", b"yy\n", b"zz\n", b"IN:AAAA1111\n"]])
    assert [c for c, _ in rec.status] == [True, False, True]
    assert rec.cards == [("in", "AAAA1111")]


def test_boot_garbage_does_not_alert():
    rec = run_reader([[b"\xff\xfe\n", b"~~\n", b"STATUS:IN=1,OUT=1\n", b"IN:AAAA1111\n"]])
    assert [c for c, _ in rec.status] == [True]
    assert rec.cards == [("in", "AAAA1111")]


# ---------------------------------------------------------------- màn LCD 1602 (máy tính -> Arduino)
def test_lcd_text_strips_vietnamese_accents_and_limits_width():
    assert lcd_text("BIỂN SỐ LỆCH") == "BIEN SO LECH"
    assert lcd_text("Đã vào bãi") == "Da vao bai"
    assert lcd_text("X" * 40) == "X" * 16
    assert lcd_text("a|b") == "a/b"                       # '|' là dấu ngăn hai dòng trong giao thức
    assert lcd_text("a\tb\nc") == "abc"                   # bỏ ký tự điều khiển
    assert lcd_text("日本") == "??"                         # ký tự không biểu diễn được -> '?'
    assert lcd_text(None) == "" and lcd_text("") == ""


def test_format_lcd_command():
    assert format_lcd_command("XE VÀO OK", "BIỂN SỐ 25888") == "LCDIN:XE VAO OK|BIEN SO 25888\n"       # mặc định: cổng vào
    assert format_lcd_command("XE VÀO OK", "BIỂN SỐ 25888", "in") == "LCDIN:XE VAO OK|BIEN SO 25888\n"
    assert format_lcd_command("XE RA OK", "TIỀN 5.000 Đ", "out") == "LCDOUT:XE RA OK|TIEN 5.000 D\n"
    assert format_lcd_command("CONG VAO") == "LCDIN:CONG VAO|\n"
    for gate in ("in", "out"):
        cmd = format_lcd_command("A" * 99, "B" * 99, gate)
        body = cmd.split(":", 1)[1].rstrip("\n")
        assert len(body) == 16 + 1 + 16
        assert len(cmd.rstrip("\n")) <= 40                   # vừa bộ đệm 48 ký tự của Arduino (LCDOUT: dài nhất)


def test_format_lcd_command_rejects_unknown_gate():
    with pytest.raises(ValueError, match="cổng không hợp lệ"):
        format_lcd_command("A", "B", "left")


class WritableSerial:
    """Serial giả có write(): ghi lại các byte đã gửi xuống Arduino."""

    def __init__(self, script, clock, stop, sent, fail_write=False):
        self.script, self.clock, self.stop, self.sent, self.fail_write = list(script), clock, stop, sent, fail_write

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data):
        if self.fail_write:
            raise serial.SerialException("write failed")
        self.sent.append(data)

    def readline(self):
        if not self.script:
            self.stop()
            return b""
        return self.script.pop(0)


def _reader_with_writable_serial(script, sent, on_card, fail_write=False):
    clock, box = Clock(), {}

    def factory(port, baud, timeout):
        return WritableSerial(script, clock, lambda: box["reader"].stop(), sent, fail_write)

    box["reader"] = ArduinoRfidReader("COM3", 9600, on_card, serial_factory=factory, clock=clock,
                                      sleep=lambda s: None)
    return box["reader"]


def test_send_lcd_writes_one_ascii_line_per_gate_while_connected():
    sent, results = [], []
    box = {}

    def on_card(gate, uid):
        send = box["reader"].send_lcd
        results.append(send("BIỂN SỐ LỆCH", "HÃY CHỈNH XE"))                # mặc định: cổng vào
        results.append(send("XE RA OK", "TIỀN 5.000 Đ", gate="out"))        # cổng ra

    box["reader"] = _reader_with_writable_serial([b"STATUS:IN=1,OUT=1\n", b"IN:AAAA1111\n"], sent, on_card=on_card)
    box["reader"].run()
    assert results == [True, True]
    assert sent == [b"LCDIN:BIEN SO LECH|HAY CHINH XE\n", b"LCDOUT:XE RA OK|TIEN 5.000 D\n"]


def test_send_lcd_unknown_gate_is_a_programming_error():
    reader = ArduinoRfidReader("COM3", 9600, lambda gate, uid: None, serial_factory=None)
    with pytest.raises(ValueError):
        reader.send_lcd("A", "B", gate="middle")


def test_send_lcd_when_not_connected_returns_false_without_raising():
    reader = ArduinoRfidReader("COM3", 9600, lambda gate, uid: None, serial_factory=None)
    assert reader.send_lcd("CONG VAO", "MOI QUET THE") is False      # chưa mở cổng COM


def test_send_lcd_after_connection_closed_returns_false():
    sent = []
    reader = _reader_with_writable_serial([b"STATUS:IN=1,OUT=1\n"], sent, on_card=lambda g, u: None)
    reader.run()                                                      # hết script -> đóng cổng
    assert reader.send_lcd("A") is False and sent == []


def test_send_lcd_write_error_is_swallowed():
    sent, results = [], []
    box = {}
    reader = _reader_with_writable_serial(
        [b"IN:AAAA1111\n"], sent, fail_write=True,
        on_card=lambda gate, uid: results.append(box["reader"].send_lcd("A", "B")))
    box["reader"] = reader
    reader.run()
    assert results == [False] and sent == []                          # không ném ngoại lệ ra làm hỏng việc quẹt thẻ


# ---------------------------------------------------------------- servo thanh chắn
def test_format_servo_command():
    assert format_servo_command("in") == "SERVOIN:OPEN\n"                      # mặc định: mở, thời gian do firmware quyết
    assert format_servo_command("out") == "SERVOOUT:OPEN\n"
    assert format_servo_command("in", "OPEN", 3) == "SERVOIN:OPEN:3000\n"      # giây -> mili giây
    assert format_servo_command("out", "open", 2.5) == "SERVOOUT:OPEN:2500\n"  # không phân biệt hoa/thường
    assert format_servo_command("out", "CLOSE") == "SERVOOUT:CLOSE\n"
    assert format_servo_command("in", "CLOSE", 3) == "SERVOIN:CLOSE\n"         # CLOSE bỏ qua thời gian giữ


def test_format_servo_command_with_pass_window():
    assert format_servo_command("in", "OPEN", 3, 3) == "SERVOIN:OPEN:3000:3000\n"        # giữ mở + cửa sổ chờ xe qua
    assert format_servo_command("out", "OPEN", 5, 2.5) == "SERVOOUT:OPEN:5000:2500\n"
    assert format_servo_command("in", "CLOSE", 3, 3) == "SERVOIN:CLOSE\n"                # CLOSE bỏ qua cả hai thời gian


@pytest.mark.parametrize("args", [("in", "OPEN", 3, 0), ("in", "OPEN", 3, -1), ("in", "OPEN", None, 3)])
def test_format_servo_command_rejects_bad_pass_window(args):
    with pytest.raises(ValueError):
        format_servo_command(*args)


@pytest.mark.parametrize("args", [("left",), ("in", "TOGGLE"), ("in", ""), ("in", "OPEN", 0), ("in", "OPEN", -1)])
def test_format_servo_command_rejects_bad_input(args):
    with pytest.raises(ValueError):
        format_servo_command(*args)


def test_send_servo_writes_one_ascii_line_per_gate_while_connected():
    sent, results = [], []
    box = {}

    def on_card(gate, uid):
        send = box["reader"].send_servo
        results.append(send("in", "OPEN", 3))
        results.append(send("out"))
        results.append(send("out", "CLOSE"))

    box["reader"] = _reader_with_writable_serial([b"STATUS:IN=1,OUT=1\n", b"IN:AAAA1111\n"], sent, on_card=on_card)
    box["reader"].run()
    assert results == [True, True, True]
    assert sent == [b"SERVOIN:OPEN:3000\n", b"SERVOOUT:OPEN\n", b"SERVOOUT:CLOSE\n"]


def test_send_servo_unknown_gate_is_a_programming_error():
    reader = ArduinoRfidReader("COM3", 9600, lambda gate, uid: None, serial_factory=None)
    with pytest.raises(ValueError):
        reader.send_servo("middle")


def test_send_servo_when_not_connected_returns_false_without_raising():
    reader = ArduinoRfidReader("COM3", 9600, lambda gate, uid: None, serial_factory=None)
    assert reader.send_servo("in", "OPEN", 3) is False


def test_send_servo_write_error_is_swallowed():
    sent, results = [], []
    box = {}
    reader = _reader_with_writable_serial(
        [b"IN:AAAA1111\n"], sent, fail_write=True,
        on_card=lambda gate, uid: results.append(box["reader"].send_servo("in")))
    box["reader"] = reader
    reader.run()
    assert results == [False] and sent == []


# ---------------------------------------------------------------- góc servo ban đầu
def test_format_servo_angle_command():
    assert format_servo_angle_command("in", 0, 90) == "SERVOIN:ANGLE:0:90\n"
    assert format_servo_angle_command("out", 10, 120) == "SERVOOUT:ANGLE:10:120\n"
    assert format_servo_angle_command("in", 90, 0) == "SERVOIN:ANGLE:90:0\n"        # servo quay ngược
    assert format_servo_angle_command("in", 0, 180).endswith(":0:180\n")             # biên trên


@pytest.mark.parametrize("args", [("left", 0, 90), ("in", -1, 90), ("in", 0, 181), ("in", 0.5, 90),
                                  ("in", "0", 90), ("in", None, 90), ("in", True, 90)])
def test_format_servo_angle_command_rejects_bad_input(args):
    with pytest.raises(ValueError):
        format_servo_angle_command(*args)


def test_send_servo_angles_writes_one_line_and_never_raises_when_disconnected():
    sent, results = [], []
    box = {}
    box["reader"] = _reader_with_writable_serial(
        [b"IN:AAAA1111\n"], sent,
        on_card=lambda gate, uid: results.append(box["reader"].send_servo_angles("out", 5, 95)))
    box["reader"].run()
    assert results == [True] and sent == [b"SERVOOUT:ANGLE:5:95\n"]
    assert box["reader"].send_servo_angles("in", 0, 90) is False                  # đã đóng cổng COM


class _Cfg:
    def __init__(self, gate, closed=0, open_=90, enabled=True):
        self.gate, self.servo_closed_angle, self.servo_open_angle, self.servo_enabled = gate, closed, open_, enabled


def test_servo_init_commands_per_gate_and_skips_disabled_servo():
    assert servo_init_commands(_Cfg("in", 0, 90), _Cfg("out", 10, 100)) == \
        ["SERVOIN:ANGLE:0:90\n", "SERVOOUT:ANGLE:10:100\n"]
    assert servo_init_commands(_Cfg("out", 5, 95)) == ["SERVOOUT:ANGLE:5:95\n"]          # chạy một cổng
    assert servo_init_commands(_Cfg("in", enabled=False), _Cfg("out")) == ["SERVOOUT:ANGLE:0:90\n"]
    assert servo_init_commands() == []


def _init_reader(script, sent, init=("SERVOIN:ANGLE:0:90\n", "SERVOOUT:ANGLE:0:90\n"), fail_write=False):
    clock, box = Clock(), {}

    def factory(port, baud, timeout):
        return WritableSerial(script, clock, lambda: box["reader"].stop(), sent, fail_write)

    box["reader"] = ArduinoRfidReader("COM3", 9600, lambda g, u: None, serial_factory=factory, clock=clock,
                                      sleep=lambda s: None, init_commands=init)
    return box["reader"]


def test_init_commands_wait_for_the_first_status_then_are_sent_once():
    """Arduino Uno tự reset khi mở cổng COM: chưa gửi lúc vừa kết nối, mà chờ dòng STATUS (đã khởi động xong)."""
    sent = []
    _init_reader([b"# dual_rfid san sang\n"], sent).run()
    assert sent == []                                                  # mới có banner, chưa có STATUS -> chưa gửi

    sent.clear()
    _init_reader([b"# dual_rfid san sang\n", b"STATUS:IN=1,OUT=1\n", b"STATUS:IN=1,OUT=1\n",
                  b"STATUS:IN=1,OUT=1\n"], sent).run()
    assert sent == [b"SERVOIN:ANGLE:0:90\n", b"SERVOOUT:ANGLE:0:90\n"]       # đúng một lần dù có nhiều STATUS


def test_init_commands_are_resent_when_arduino_reboots():
    sent = []
    _init_reader([b"STATUS:IN=1,OUT=1\n", b"# dual_rfid san sang\n", b"STATUS:IN=1,OUT=1\n"], sent,
                 init=("SERVOIN:ANGLE:0:90\n",)).run()
    assert sent == [b"SERVOIN:ANGLE:0:90\n"] * 2                       # Arduino reset -> servo về mặc định -> cài lại


def test_init_commands_retry_after_a_failed_write_and_never_kill_the_reader():
    sent, cards = [], []
    reader = _init_reader([b"STATUS:IN=1,OUT=1\n", b"IN:AAAA1111\n"], sent, fail_write=True)
    reader.on_card = lambda gate, uid: cards.append(uid)
    reader.run()
    assert sent == [] and cards == ["AAAA1111"]                         # ghi lỗi: vẫn đọc thẻ bình thường
    assert reader._init_pending is True                                 # và sẽ thử lại ở STATUS kế tiếp


def test_init_commands_default_to_nothing():
    reader = ArduinoRfidReader("COM3", 9600, lambda g, u: None, serial_factory=None)
    assert reader.init_commands == ()


# ---------------------------------------------------------------- còi bíp
def test_format_buzzer_command():
    assert format_buzzer_command(2000, 120) == "BUZZER:TONE:2000:120\n"
    assert format_buzzer_command(100, 20) == "BUZZER:TONE:100:20\n"            # biên dưới
    assert format_buzzer_command(8000, 2000) == "BUZZER:TONE:8000:2000\n"      # biên trên


@pytest.mark.parametrize("args", [(99, 120), (8001, 120), (2000, 19), (2000, 2001), (2000.5, 120),
                                  ("2000", 120), (True, 120), (2000, None)])
def test_format_buzzer_command_rejects_bad_input(args):
    with pytest.raises(ValueError):
        format_buzzer_command(*args)


def test_buzzer_init_commands_uses_config_values():
    class Cfg:
        buzzer_freq_hz = 3000
        buzzer_beep_ms = 250

    assert buzzer_init_commands(Cfg()) == ["BUZZER:TONE:3000:250\n"]


def test_buzzer_commands_are_written_to_the_port():
    from hardware.rfid import ArduinoRfidReader
    sent = []
    r = ArduinoRfidReader("COM_TEST", 9600, on_card=lambda *a: None, on_status=lambda *a: None)
    r._write_line = lambda line: sent.append(line) or True
    assert r.send_buzzer_tone(3000, 200) is True
    assert r.send_buzzer_beep() is True
    assert sent == ["BUZZER:TONE:3000:200\n", "BUZZER:BEEP\n"]
