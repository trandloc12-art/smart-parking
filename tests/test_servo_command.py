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
