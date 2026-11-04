"""Thử logic nhận biết "xe đã qua thanh chắn" của firmware (lớp PassDetector trong dual_rfid.ino).

Đoạn mã giữa BEGIN/END PassDetector không phụ thuộc Arduino nên được biên dịch bằng g++ thường và chạy với các
kịch bản cảm biến. Máy không có g++ thì bỏ qua.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

INO = (Path(__file__).resolve().parent.parent / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")

DRIVER = r"""
#include <cstdio>
#include <iostream>
#include <string>
%s
int main() {
  PassDetector d;
  std::string a, b;
  while (std::cin >> a) {
    if (a == "R") { d.reset(); continue; }
    std::cin >> b;
    std::putchar(d.update(a == "1", b == "1") ? 'P' : '.');
  }
  std::putchar('\n');
}
"""


@pytest.fixture(scope="module")
def detector(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử PassDetector")
    code = INO[INO.index("// BEGIN PassDetector"):INO.index("// END PassDetector")]
    d = tmp_path_factory.mktemp("pass_detector")
    (d / "main.cpp").write_text(DRIVER % code, encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        """steps: các cặp (trước, sau) = 0/1 (1 = bị chắn). Trả về chuỗi: 'P' = xe vừa qua hẳn, '.' = chưa."""
        text = "\n".join(f"{b} {a}" for b, a in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


def test_long_vehicle_passes_when_it_leaves_the_last_sensor(detector):
    # xe dài: chắn trước, chắn cả hai, nhả trước, nhả sau
    assert detector([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]) == "....P"


def test_short_vehicle_never_covering_both_sensors_still_passes(detector):
    assert detector([(1, 0), (0, 0), (0, 1), (0, 0)]) == "...P"


def test_both_sensors_blocked_at_the_same_moment(detector):
    assert detector([(1, 1), (0, 1), (0, 0)]) == "..P"


def test_not_passed_while_vehicle_still_on_a_sensor(detector):
    assert detector([(1, 0), (1, 1), (0, 1)]) == "..."          # còn nằm trên cảm biến sau
    assert detector([(1, 0), (1, 1), (1, 0)]) == "..."          # cảm biến sau nhả nhưng trước còn chắn


def test_reversing_out_is_not_a_pass(detector):
    assert detector([(1, 0), (1, 1), (1, 0), (0, 0)]) == "...."


def test_vehicle_reverses_then_drives_through(detector):
    assert detector([(1, 0), (1, 1), (1, 0), (1, 1), (0, 1), (0, 0)]) == ".....P"


def test_something_crossing_only_the_rear_sensor_is_ignored(detector):
    assert detector([(0, 0), (0, 1), (0, 0)]) == "..."          # chưa từng chắn cảm biến trước


def test_idle_sensors_never_report(detector):
    assert detector([(0, 0)] * 5) == "....."


def test_reports_once_and_can_track_the_next_vehicle(detector):
    one = [(1, 0), (1, 1), (0, 1), (0, 0)]
    assert detector(one + [(0, 0), (0, 0)] + one) == "...P" + ".." + "...P"
