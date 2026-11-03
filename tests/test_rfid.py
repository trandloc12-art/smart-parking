"""MỘT Arduino, HAI đầu đọc: giao thức một dòng và luồng đọc Serial (dùng cổng Serial giả, không cần phần cứng)."""
import pytest
import serial

from hardware.rfid import ArduinoRfidReader, BadLine, CardSwipe, ReaderStatus, parse_line


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
        self.cards, self.status, self.readers = [], [], []

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
                                      serial_factory=factory, clock=clock, sleep=lambda s: None, **kwargs)
    box["reader"].run()          # chạy thẳng ở luồng này; luồng đọc tự dừng khi hết script
    return rec


def test_cards_are_routed_to_the_right_gate():
    rec = run_reader([[b"# san sang\n", b"STATUS:IN=1,OUT=1\n", b"IN:AB1992CA\n", b"OUT:DB2B11CA\n"]])
    assert rec.cards == [("in", "AB1992CA"), ("out", "DB2B11CA")]
    assert rec.status == [(True, "Arduino: đã kết nối COM3")]
    assert rec.readers == [("in", True), ("out", True)]


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
