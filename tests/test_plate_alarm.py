"""Báo động biển số trùng: còi kêu lặp tới khi xe trùng rời cảm biến trước, rồi Arduino tự tắt và báo ALARMCLR.

Gồm: giao thức (lệnh ALARMIN/ALARMOUT, dòng ALARMCLR), lớp PlateAlarm của firmware (biên dịch bằng g++) và việc nối vào loop()."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from hardware.rfid import AlarmClear, ArduinoRfidReader, BadLine, format_alarm_command, parse_line

ROOT = Path(__file__).resolve().parent.parent
INO = (ROOT / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------- giao thức
def test_alarm_commands_per_gate():
    assert format_alarm_command("in", True) == "ALARMIN:ON\n"
    assert format_alarm_command("in", False) == "ALARMIN:OFF\n"
    assert format_alarm_command("out", True) == "ALARMOUT:ON\n"
    assert format_alarm_command("in") == "ALARMIN:ON\n"


def test_alarm_command_unknown_gate_is_a_programming_error():
    with pytest.raises(ValueError):
        format_alarm_command("left", True)


def test_parse_alarm_clear():
    assert parse_line("ALARMCLR:IN\r\n") == AlarmClear("in")
    assert parse_line("alarmclr: out") == AlarmClear("out")


@pytest.mark.parametrize("line", ["ALARMCLR", "ALARMCLR:", "ALARMCLR:LEFT", "ALARM:IN"])
def test_parse_bad_alarm_lines(line):
    assert parse_line(line) == BadLine(line)


class _Ser:
    def __init__(self, lines, sent):
        self.lines, self.sent = list(lines), sent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data):
        self.sent.append(data)

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        box["reader"].stop()
        return b""


box = {}


def _run(lines, **kwargs):
    sent, cleared = [], []
    box["reader"] = ArduinoRfidReader("COM3", 9600, lambda g, u: None, on_alarm_clear=cleared.append,
                                      serial_factory=lambda port, baud, timeout: _Ser(lines, sent),
                                      sleep=lambda s: None, **kwargs)
    return box["reader"], sent, cleared


def test_reader_routes_alarm_clear_to_the_callback():
    reader, sent, cleared = _run([b"STATUS:IN=1,OUT=1\n", b"ALARMCLR:IN\n", b"ALARMCLR:OUT\n"])
    reader.run()
    assert cleared == ["in", "out"]


def test_reader_without_alarm_callback_ignores_the_line():
    sent = []
    reader = ArduinoRfidReader("COM3", 9600, lambda g, u: None,
                               serial_factory=lambda port, baud, timeout: _Ser([b"ALARMCLR:IN\n"], sent),
                               sleep=lambda s: None)
    box["reader"] = reader
    reader.run()                                # không ném lỗi


def test_send_alarm_writes_one_line_and_never_raises_when_disconnected():
    reader, sent, _ = _run([])
    assert reader.send_alarm("in") is False     # chưa kết nối
    reader._ser = _Ser([], sent)
    assert reader.send_alarm("in") is True and reader.send_alarm("out", False) is True
    assert sent == [b"ALARMIN:ON\n", b"ALARMOUT:OFF\n"]


# ---------------------------------------------------------------- firmware: lớp PlateAlarm (biên dịch bằng g++)
DRIVER = r"""
#include <cstdio>
#include <iostream>
#include <string>
%s
int main() {
  PlateAlarm a;
  std::string op;
  int v;
  while (std::cin >> op >> v) {
    if (op == "S") a.set(v == 1);
    else std::putchar(a.update(v == 1) ? 'C' : (a.active() ? 'A' : '.'));
  }
  std::putchar('\n');
}
"""


@pytest.fixture(scope="module")
def alarm(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử PlateAlarm")
    code = INO[INO.index("// BEGIN PlateAlarm"):INO.index("// END PlateAlarm")]
    d = tmp_path_factory.mktemp("plate_alarm")
    (d / "main.cpp").write_text(DRIVER % code, encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        """steps: ("S", 1|0) = set(bật|tắt); ("U", 1|0) = update(cảm biến trước bị chắn?). Ra: 'A' đang báo, 'C' vừa hết vì xe rời, '.' không báo."""
        text = "\n".join(f"{op} {v}" for op, v in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


def test_alarm_stays_on_while_vehicle_blocks_the_front_sensor_for_any_length_of_time(alarm):
    assert alarm([("S", 1)] + [("U", 1)] * 50) == "A" * 50                 # không có giới hạn thời gian


def test_alarm_ends_exactly_once_when_the_vehicle_leaves(alarm):
    # xe đứng (A, A), rời đi (C: hết báo + gửi ALARMCLR đúng một lần), sau đó chắn lại cũng không báo nữa (., .)
    assert alarm([("S", 1), ("U", 1), ("U", 1), ("U", 0), ("U", 0), ("U", 1)]) == "AAC.."


def test_idle_alarm_does_nothing(alarm):
    assert alarm([("U", 1), ("U", 0), ("U", 1)]) == "..."                  # chưa bật thì cảm biến thế nào cũng không báo ALARMCLR


def test_manual_off_stops_without_reporting_clear(alarm):
    assert alarm([("S", 1), ("U", 1), ("S", 0), ("U", 0)]) == "A" + "."    # tắt tay: không 'C'


def test_alarm_can_be_raised_again_for_the_next_vehicle(alarm):
    assert alarm([("S", 1), ("U", 0), ("S", 1), ("U", 1), ("U", 0)]) == "C" + "A" + "C"


def test_alarm_set_while_the_vehicle_already_left_clears_immediately(alarm):
    assert alarm([("S", 1), ("U", 0)]) == "C"                              # xe đã đi trong lúc OCR: báo hết ngay


# ---------------------------------------------------------------- firmware: nối vào Barrier / loop / lệnh
def test_barrier_reports_alarmclr_with_the_gate_tag():
    assert 'report(F("ALARMCLR:"))' in INO
    body = INO[INO.index("class Barrier"):INO.index("Barrier barrierIn(")]
    update = body[body.index("void update()"):]
    # kiểm tra hết báo động nằm TRƯỚC `if (!open_) return;` để chạy cả khi thanh chắn đóng (xe bị từ chối nên thanh chắn không mở)
    assert update.index("alarm_.update(") < update.index("if (!open_) return;")
    assert "alarm_.update(before_.blocked())" in update                    # chỉ cảm biến TRƯỚC


def test_loop_beeps_while_alarming_without_blocking():
    loop = INO[INO.index("void loop()"):]
    assert "barrierIn.alarming() || barrierOut.alarming()" in loop
    assert "STUCK_BEEP_PERIOD_MS" in loop and "beep();" in loop
    assert "delay(" not in loop


def test_alarm_commands_are_handled_per_gate():
    assert 'afterPrefix(cmd, "ALARMIN:")' in INO and 'afterPrefix(cmd, "ALARMOUT:")' in INO
    assert "handleAlarm(barrierIn, args)" in INO and "handleAlarm(barrierOut, args)" in INO
    handler = INO[INO.index("void handleAlarm("):INO.index("void handleCommand(")]
    assert 'strcmp(args, "ON") == 0' in handler and 'strcmp(args, "OFF") == 0' in handler


def test_alarm_protocol_is_documented_in_sketch_and_readme():
    for text in (INO, README):
        for token in ("ALARMIN:ON", "ALARMIN:OFF", "ALARMCLR:IN"):
            assert token in text, f"thiếu {token}"
