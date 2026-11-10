"""Thử cách firmware hiểu lệnh servo từ máy tính (hàm handleServo trong dual_rfid.ino), nhất là lệnh đặt góc
SERVOIN:ANGLE:<đóng>:<mở>. Hàm được trích ra, biên dịch bằng g++ thường với một Barrier giả (không cần Arduino).
Máy không có g++ thì bỏ qua."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
INO = (ROOT / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")

DRIVER = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <string>
const unsigned long SERVO_HOLD_MS = 3000;
const unsigned long PASS_WINDOW_MS = 3000;
struct Barrier {                      // chỉ ghi lại lời gọi; setAngles kẹp 180 giống bản thật
  void open(unsigned long h, unsigned long w) { std::printf("open %%lu %%lu\n", h, w); }
  void close() { std::printf("close\n"); }
  void setAngles(uint8_t c, uint8_t o) { std::printf("angles %%d %%d\n", c > 180 ? 180 : c, o > 180 ? 180 : o); }
};
%s
int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    char buf[64];
    std::strncpy(buf, line.c_str(), sizeof buf - 1);
    buf[sizeof buf - 1] = '\0';
    Barrier b;
    handleServo(b, buf);
    std::puts("--");                  // hết một lệnh (lệnh bị bỏ qua thì không in gì trước dòng này)
  }
}
"""


@pytest.fixture(scope="module")
def servo_cmd(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử handleServo")
    start = INO.index("void handleServo(Barrier &barrier, char *args)")
    func = INO[start:INO.index("\n}\n", start) + 3]
    d = tmp_path_factory.mktemp("servo_cmd")
    (d / "main.cpp").write_text(DRIVER % func, encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(*args):
        """args: phần sau 'SERVOIN:' (VD 'ANGLE:0:90'). Trả về list các tác động lên Barrier giả."""
        out = subprocess.run([str(d / "run")], input="\n".join(args) + "\n", capture_output=True, text=True,
                             check=True).stdout
        groups, cur = [], []
        for line in out.splitlines():
            if line == "--":
                groups.append(cur)
                cur = []
            else:
                cur.append(line)
        return groups

    return run


@pytest.mark.parametrize("cmd, expected", [
    ("ANGLE:0:90", "angles 0 90"),
    ("ANGLE:10:120", "angles 10 120"),
    ("ANGLE:90:0", "angles 90 0"),            # servo quay ngược
    ("ANGLE:0:180", "angles 0 180"),          # biên
    ("ANGLE:180:0", "angles 180 0"),
])
def test_angle_command_sets_both_angles(servo_cmd, cmd, expected):
    assert servo_cmd(cmd) == [[expected]]


@pytest.mark.parametrize("cmd", [
    "ANGLE:", "ANGLE:90", "ANGLE:90:", "ANGLE::90", "ANGLE:abc:90", "ANGLE:0:xyz",
    "ANGLE:-1:90", "ANGLE:0:181", "ANGLE:999:90",
    "ANGLE:256:90", "ANGLE:300:0",             # ép sang uint8 sẽ thành góc nhỏ sai: phải bị chặn từ trước
])
def test_bad_angle_commands_are_ignored_entirely(servo_cmd, cmd):
    assert servo_cmd(cmd) == [[]]               # sai định dạng / ngoài 0..180: không đổi góc nào


def test_open_and_close_commands_still_work(servo_cmd):
    assert servo_cmd("OPEN", "OPEN:2500", "OPEN:abc", "OPEN:0", "CLOSE", "NOPE") == [
        ["open 3000 3000"], ["open 2500 3000"], ["open 3000 3000"], ["open 3000 3000"], ["close"], []]


def test_open_command_carries_the_pass_window(servo_cmd):
    """OPEN:<giữ mở ms>:<cửa sổ chờ xe qua ms> — phần thứ ba là hạn chót để cảm biến sau thấy xe."""
    assert servo_cmd("OPEN:3000:4500", "OPEN:2500:1000", "OPEN:3000:0", "OPEN:3000:abc", "OPEN:3000:") == [
        ["open 3000 4500"], ["open 2500 1000"], ["open 3000 3000"], ["open 3000 3000"], ["open 3000 3000"]]


def test_bad_hold_does_not_break_the_pass_window_default(servo_cmd):
    # "OPEN:abc:4000": số giữ mở hỏng -> dùng mặc định; không đoán cửa sổ chờ từ phần sau
    assert servo_cmd("OPEN:abc:4000") == [["open 3000 3000"]]


# ---------------------------------------------------------------- còi bíp: handleBuzzer
BUZZER_DRIVER = r"""
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <string>
const unsigned int BUZZER_FREQ_HZ = 2000, BUZZER_BEEP_MS = 120;
const unsigned int BUZZER_FREQ_MIN_HZ = %s, BUZZER_FREQ_MAX_HZ = %s, BUZZER_BEEP_MIN_MS = %s, BUZZER_BEEP_MAX_MS = %s;
const int PIN_BUZZER = 0;
static void tone(int, unsigned int f, unsigned int d) { std::printf("beep %%u %%u\n", f, d); }
unsigned int buzzerFreqHz = BUZZER_FREQ_HZ;
unsigned int buzzerBeepMs = BUZZER_BEEP_MS;
%s
int main() {
  std::string line;
  while (std::getline(std::cin, line)) {          // mỗi dòng: một lệnh sau "BUZZER:"; rồi kêu thử để thấy giá trị hiện tại
    char buf[64];
    std::strncpy(buf, line.c_str(), sizeof buf - 1);
    buf[sizeof buf - 1] = '\0';
    handleBuzzer(buf);
    std::printf("now %%u %%u\n", buzzerFreqHz, buzzerBeepMs);
  }
}
"""


def _ino_const(name):
    import re
    return re.search(rf"{name}\s*=\s*(\d+)", INO).group(1)


@pytest.fixture(scope="module")
def buzzer_cmd(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử handleBuzzer")
    beep_start = INO.index("void beep() {")
    start = INO.index("void handleBuzzer(char *args)")
    funcs = INO[beep_start:INO.index("\n}\n", beep_start) + 3] + INO[start:INO.index("\n}\n", start) + 3]
    consts = [_ino_const(n) for n in ("BUZZER_FREQ_MIN_HZ", "BUZZER_FREQ_MAX_HZ", "BUZZER_BEEP_MIN_MS", "BUZZER_BEEP_MAX_MS")]
    d = tmp_path_factory.mktemp("buzzer_cmd")
    (d / "main.cpp").write_text(BUZZER_DRIVER % (*consts, funcs), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(*args):
        """args: phần sau 'BUZZER:'. Trả về, cho từng lệnh, các dòng in ra (beep ... / now <Hz> <ms>)."""
        out = subprocess.run([str(d / "run")], input="\n".join(args) + "\n", capture_output=True, text=True,
                             check=True).stdout.splitlines()
        return out

    return run


def test_buzzer_firmware_range_matches_python():
    import config
    from hardware import rfid
    freq = (int(_ino_const("BUZZER_FREQ_MIN_HZ")), int(_ino_const("BUZZER_FREQ_MAX_HZ")))
    beep = (int(_ino_const("BUZZER_BEEP_MIN_MS")), int(_ino_const("BUZZER_BEEP_MAX_MS")))
    assert freq == config.BUZZER_FREQ_RANGE == rfid.BUZZER_FREQ_RANGE
    assert beep == config.BUZZER_BEEP_RANGE == rfid.BUZZER_BEEP_RANGE


def test_buzzer_tone_command_sets_sound_and_beep_plays_it(buzzer_cmd):
    assert buzzer_cmd("TONE:3000:250", "BEEP") == ["now 3000 250", "beep 3000 250", "now 3000 250"]


def test_buzzer_beep_before_any_tone_uses_defaults(buzzer_cmd):
    assert buzzer_cmd("BEEP") == ["beep 2000 120", "now 2000 120"]


@pytest.mark.parametrize("cmd", [
    "TONE:", "TONE:3000", "TONE:3000:", "TONE::200", "TONE:abc:200", "TONE:3000:xyz",
    "TONE:99:200", "TONE:8001:200", "TONE:3000:19", "TONE:3000:2001", "TONE:-5:200", "TONE:3000:-5", "NOPE",
])
def test_bad_buzzer_commands_keep_the_old_sound(buzzer_cmd, cmd):
    assert buzzer_cmd(cmd) == ["now 2000 120"]


def test_buzzer_edges_are_accepted(buzzer_cmd):
    assert buzzer_cmd("TONE:100:20", "TONE:8000:2000") == ["now 100 20", "now 8000 2000"]
