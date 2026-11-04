"""Thử logic đèn LED báo xe vào của firmware (lớp LedTimer trong dual_rfid.ino).

Đoạn mã giữa BEGIN/END LedTimer không phụ thuộc Arduino nên được biên dịch bằng g++ thường và chạy với các kịch bản
thời gian. Máy không có g++ thì bỏ qua.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INO = (Path(__file__).resolve().parent.parent / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")

# Mỗi dòng đầu vào: "T <ms>" = trigger tại ms; "U <ms>" = update tại ms (in '1' nếu đèn sáng, '0' nếu tắt).
DRIVER = r"""
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <string>
%s
int main() {
  LedTimer led(%d);
  std::string op;
  uint32_t t;
  while (std::cin >> op >> t) {
    if (op == "T") led.trigger(t);
    else std::putchar(led.update(t) ? '1' : '0');
  }
  std::putchar('\n');
}
"""


def led_on_ms():
    return int(re.search(r"const unsigned long LED_ON_MS\s*=\s*(\d+);", INO).group(1))


@pytest.fixture(scope="module")
def led(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử LedTimer")
    code = INO[INO.index("// BEGIN LedTimer"):INO.index("// END LedTimer")]
    # Arduino AVR: unsigned long = 32 bit. Trên máy 64 bit phải ép về uint32_t thì mới thử được lúc millis() tràn.
    code = code.replace("unsigned long", "uint32_t")
    d = tmp_path_factory.mktemp("led_timer")
    (d / "main.cpp").write_text(DRIVER % (code, led_on_ms()), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        """steps: [("T", ms) | ("U", ms)]. Trả về chuỗi '1' / '0' cho mỗi lần update."""
        text = "\n".join(f"{op} {ms}" for op, ms in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


def test_default_duration_is_20_seconds():
    assert led_on_ms() == 20000


def test_off_until_triggered(led):
    assert led([("U", 0), ("U", 5000), ("U", 100000)]) == "000"


def test_on_for_20_seconds_then_turns_off(led):
    # trigger lúc 1000 ms: còn sáng ở 1000, 10000, 20999; tắt đúng lúc đủ 20000 ms (21000) và về sau
    assert led([("T", 1000), ("U", 1000), ("U", 10000), ("U", 20999), ("U", 21000), ("U", 30000)]) == "11100"


def test_trigger_while_lit_restarts_the_countdown(led):
    # xe thứ hai vào lúc 15 s: đèn phải sáng đến 35 s chứ không tắt ở 20 s
    steps = [("T", 0), ("U", 14000), ("T", 15000), ("U", 20000), ("U", 34999), ("U", 35000)]
    assert led(steps) == "1110"


def test_can_be_triggered_again_after_turning_off(led):
    steps = [("T", 0), ("U", 20000), ("U", 25000), ("T", 30000), ("U", 31000), ("U", 50000)]
    assert led(steps) == "00" + "10"


def test_works_across_millis_overflow(led):
    # millis() tràn số sau ~49 ngày: trigger cách mốc 2^32 đúng 5001 ms, update sau khi đã quay về gần 0.
    # Lúc t = 10000 đã trôi 15001 ms (còn sáng); t = 14998 trôi 19999 ms (còn sáng); t = 14999 trôi đúng 20000 ms (tắt).
    start = 2**32 - 5001
    steps = [("T", start), ("U", start), ("U", 10000), ("U", 14998), ("U", 14999)]
    assert led(steps) == "1110"
