"""Còi cảnh báo xe dừng quá lâu: xe đã quẹt thẻ (thanh chắn đang mở) mà đứng yên ở cảm biến trước / sau quá ngưỡng thì
còi kêu lặp. Logic nằm ở firmware (StuckTimer + handleStuck + loop), Python chỉ cấu hình và gửi ngưỡng qua lệnh STUCK:."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import config
from hardware import rfid

ROOT = Path(__file__).resolve().parent.parent
INO = (ROOT / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _const(name):
    return int(re.search(rf"const unsigned long {name}\s*=\s*(\d+);", INO).group(1))


# ---------------------------------------------------------------- StuckTimer (g++)
TIMER_DRIVER = r"""
#include <cstdio>
#include <iostream>
#include <string>
%s
int main() {
  StuckTimer s;
  const unsigned long LIMIT = %d;
  unsigned long t;
  std::string b, a;
  while (std::cin >> t >> b >> a) {
    if (b == "R") { s.reset(); continue; }
    std::putchar(s.update(b == "1", a == "1", t, LIMIT) ? 'S' : '.');
  }
  std::putchar('\n');
}
"""


@pytest.fixture(scope="module")
def stuck(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử StuckTimer")
    code = INO[INO.index("// BEGIN StuckTimer"):INO.index("// END StuckTimer")]
    d = tmp_path_factory.mktemp("stuck_timer")
    (d / "main.cpp").write_text(TIMER_DRIVER % (code, 10000), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        """steps: (thời điểm ms, trước, sau), 1 = bị chắn. Trả về 'S' = đang cảnh báo, '.' = không."""
        text = "\n".join(f"{t} {b} {a}" for t, b, a in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


def test_vehicle_standing_on_the_front_sensor_alarms_after_the_limit(stuck):
    assert stuck([(0, 1, 0), (9999, 1, 0), (10000, 1, 0), (30000, 1, 0)]) == "..SS"


def test_vehicle_standing_on_the_rear_sensor_alarms_after_the_limit(stuck):
    assert stuck([(0, 0, 1), (9999, 0, 1), (10000, 0, 1)]) == "..S"


def test_vehicle_covering_both_sensors_alarms_after_the_limit(stuck):
    assert stuck([(0, 1, 1), (10000, 1, 1)]) == ".S"


def test_no_vehicle_on_any_sensor_never_alarms(stuck):
    assert stuck([(0, 0, 0), (10000, 0, 0), (600000, 0, 0)]) == "..."


def test_moving_vehicle_restarts_the_clock(stuck):
    # trước -> (lúc 8000) cả hai -> (lúc 16000) chỉ sau: mỗi lần đổi trạng thái là đếm lại, chưa đủ 10 giây nên không báo
    assert stuck([(0, 1, 0), (8000, 1, 1), (16000, 0, 1), (25999, 0, 1), (26000, 0, 1)]) == "....S"


def test_alarm_stops_as_soon_as_the_vehicle_moves_or_leaves(stuck):
    assert stuck([(0, 1, 0), (10000, 1, 0), (10001, 1, 1), (10002, 0, 0), (10003, 0, 0)]) == ".S..."


def test_vehicle_leaving_then_another_arriving_restarts_the_clock(stuck):
    # rời hết cảm biến lúc 9000 rồi xe khác tới lúc 9500: đếm lại từ 9500, nên chưa báo lúc 12000
    assert stuck([(0, 1, 0), (9000, 0, 0), (9500, 1, 0), (12000, 1, 0), (19500, 1, 0)]) == "....S"


def test_reset_forgets_the_standing_vehicle(stuck):
    # thanh chắn đóng rồi mở lại (reset): xe vẫn đứng đó nhưng phải đứng đủ ngưỡng kể từ lần theo dõi mới
    assert stuck([(0, 1, 0), (10000, 1, 0), (10001, "R", 0), (10002, 1, 0), (19000, 1, 0), (20002, 1, 0)]) == ".S..S"


# ---------------------------------------------------------------- lệnh STUCK: (g++)
CMD_DRIVER = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
const unsigned long STUCK_WARN_MS = %d, STUCK_WARN_MIN_MS = %d, STUCK_WARN_MAX_MS = %d;
unsigned long stuckWarnMs = STUCK_WARN_MS;
%s
int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    char buf[64];
    std::strncpy(buf, line.c_str(), sizeof buf - 1);
    buf[sizeof buf - 1] = '\0';
    handleStuck(buf);
    std::printf("%%lu\n", stuckWarnMs);
  }
}
"""


@pytest.fixture(scope="module")
def stuck_cmd(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử handleStuck")
    start = INO.index("void handleStuck(char *args)")
    func = INO[start:INO.index("\n}\n", start) + 3]
    d = tmp_path_factory.mktemp("stuck_cmd")
    consts = (_const("STUCK_WARN_MS"), _const("STUCK_WARN_MIN_MS"), _const("STUCK_WARN_MAX_MS"))
    (d / "main.cpp").write_text(CMD_DRIVER % (*consts, func), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(*args):
        """args: phần sau 'STUCK:'. Trả về ngưỡng (ms) sau từng lệnh."""
        out = subprocess.run([str(d / "run")], input="\n".join(args) + "\n", capture_output=True, text=True, check=True)
        return [int(x) for x in out.stdout.split()]

    return run


def test_stuck_command_sets_the_threshold(stuck_cmd):
    assert stuck_cmd("5000", "30000") == [5000, 30000]


def test_stuck_command_zero_disables_and_edges_are_accepted(stuck_cmd):
    assert stuck_cmd("0", "1000", "600000") == [0, 1000, 600000]


@pytest.mark.parametrize("cmd", ["", "abc", "999", "600001", "-5", "10000x", "1.5e3", " "])
def test_bad_stuck_commands_keep_the_old_threshold(stuck_cmd, cmd):
    assert stuck_cmd(cmd) == [10000]


# ---------------------------------------------------------------- nối dây trong firmware
def test_barrier_updates_stuck_only_while_open_and_close_clears_it():
    body = INO[INO.index("class Barrier"):INO.index("Barrier barrierIn(")]
    update = body[body.index("void update()"):]
    open_guard = update.index("if (!open_) return;")
    stuck_at = update.index("stuckTimer_.update(")
    detector_at = update.index("detector_.update(")
    assert open_guard < stuck_at < detector_at          # chỉ theo dõi khi thanh chắn đang mở, trước khi PASS đóng thanh chắn
    close = body[body.index("void close()"):body.index("void setAngles(")]
    assert "stuck_ = false" in close and "stuckTimer_.reset()" in close
    opened = body[body.index("void open("):body.index("void close()")]
    assert "stuckTimer_.reset()" in opened


def test_loop_beeps_repeatedly_while_either_gate_is_stuck():
    loop = INO[INO.index("void loop()"):]
    assert "barrierIn.stuck() || barrierOut.stuck()" in loop
    assert "STUCK_BEEP_PERIOD_MS" in loop and "beep();" in loop
    assert "delay(" not in loop                          # không chặn vòng đọc thẻ / cảm biến


def test_stuck_command_is_routed_in_handle_command():
    handle = INO[INO.index("void handleCommand(char *cmd)"):]
    assert 'afterPrefix(cmd, "STUCK:")' in handle and "handleStuck(args)" in handle


# ---------------------------------------------------------------- Python <-> firmware <-> tài liệu
def test_range_and_default_agree_between_firmware_python_and_docs():
    lo, hi = _const("STUCK_WARN_MIN_MS") / 1000, _const("STUCK_WARN_MAX_MS") / 1000
    assert (lo, hi) == config.STUCK_WARN_RANGE == rfid.STUCK_WARN_RANGE
    default = _const("STUCK_WARN_MS") / 1000
    assert config.Settings.__dataclass_fields__["stuck_warn_seconds"].default == default
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(rf"^STUCK_WARN_SECONDS={int(default)}\b", example, re.M)
    assert f"| `STUCK_WARN_SECONDS` | `{int(default)}` |" in README
    assert "`STUCK:10000`" in README


def test_stuck_period_is_longer_than_the_default_beep():
    beep_ms = int(re.search(r"const unsigned int BUZZER_BEEP_MS\s*=\s*(\d+);", INO).group(1))
    assert _const("STUCK_BEEP_PERIOD_MS") > beep_ms     # còn khoảng lặng giữa hai tiếng bíp


def test_format_stuck_command():
    assert rfid.format_stuck_command(10) == "STUCK:10000\n"
    assert rfid.format_stuck_command(1.5) == "STUCK:1500\n"
    assert rfid.format_stuck_command(0) == "STUCK:0\n"          # tắt
    assert rfid.format_stuck_command(1) == "STUCK:1000\n"        # biên dưới
    assert rfid.format_stuck_command(600) == "STUCK:600000\n"    # biên trên


@pytest.mark.parametrize("bad", [0.5, 601, -1, True, "10", None])
def test_format_stuck_command_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        rfid.format_stuck_command(bad)


def test_stuck_init_commands_uses_config_value():
    class Cfg:
        stuck_warn_seconds = 20.0
    assert rfid.stuck_init_commands(Cfg()) == ["STUCK:20000\n"]


def test_stuck_command_is_written_to_the_port():
    sent = []
    r = rfid.ArduinoRfidReader("COM_TEST", 9600, on_card=lambda *a: None, on_status=lambda *a: None)
    r._write_line = lambda line: sent.append(line) or True
    assert r.send_stuck_warn(7) is True
    assert sent == ["STUCK:7000\n"]


def test_settings_default_override_and_validation(monkeypatch):
    monkeypatch.delenv("STUCK_WARN_SECONDS", raising=False)
    assert config.load_settings("in").stuck_warn_seconds == 10.0
    assert config.load_settings("out", {"STUCK_WARN_SECONDS": "30"}).stuck_warn_seconds == 30.0
    assert config.load_settings("in", {"STUCK_WARN_SECONDS": "0"}).stuck_warn_seconds == 0      # tắt
    for ok in ("1", "600", "2.5"):
        assert config.load_settings("in", {"STUCK_WARN_SECONDS": ok}) is not None
    for bad in ("0.5", "601", "-1"):
        with pytest.raises(ValueError, match="STUCK_WARN_SECONDS"):
            config.load_settings("in", {"STUCK_WARN_SECONDS": bad})
