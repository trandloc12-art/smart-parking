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


# ======================================================================================================
# PassWindow + PassDetector chạy cùng nhau đúng thứ tự như Barrier::update:
#   1) detector.update  -> 'P' (xe đã qua hẳn: hạ thanh chắn + PASS)
#   2) window.expired   -> 'X' (cảm biến trước đã thấy xe rồi MẤT tín hiệu quá ân hạn mà cảm biến sau chưa thấy xe:
#                          xe rời đi, hạ thanh chắn + NOPASS; cảm biến trước còn tín hiệu thì KHÔNG hủy)
# Sau P / X thanh chắn đã đóng nên các dòng tiếp theo không còn theo dõi ('-').
# ======================================================================================================
WINDOW_DRIVER = r"""
#include <cstdio>
#include <iostream>
#include <string>
%s
%s
int main() {
  PassDetector d;
  PassWindow w;
  const unsigned long WINDOW = %d;
  bool open = true;
  unsigned long t;
  std::string b, a;
  while (std::cin >> t >> b >> a) {
    if (!open) { std::putchar('-'); continue; }
    if (d.update(b == "1", a == "1")) { open = false; std::putchar('P'); continue; }
    if (w.expired(d.seenBefore(), d.seenAfter(), b == "1", t, WINDOW)) { open = false; std::putchar('X'); continue; }
    std::putchar('.');
  }
  std::putchar('\n');
}
"""


@pytest.fixture(scope="module")
def barrier_sim(tmp_path_factory):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử PassWindow")
    det = INO[INO.index("// BEGIN PassDetector"):INO.index("// END PassDetector")]
    win = INO[INO.index("// BEGIN PassWindow"):INO.index("// END PassWindow")]
    d = tmp_path_factory.mktemp("pass_window")
    (d / "main.cpp").write_text(WINDOW_DRIVER % (det, win, 3000), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        """steps: (thời điểm ms, trước, sau) với 1 = bị chắn. Trả về 'P' = xe qua, 'X' = hủy (NOPASS), '.' = chưa gì,
        '-' = thanh chắn đã đóng."""
        text = "\n".join(f"{t} {b} {a}" for t, b, a in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


def test_vehicle_waiting_at_front_sensor_is_never_cancelled_while_the_signal_stays(barrier_sim):
    # xe đứng chờ ở cảm biến trước (còn tín hiệu): không hủy dù quá ân hạn bao lâu
    steps = [(0, 1, 0), (3000, 1, 0), (10000, 1, 0), (60000, 1, 0)]
    assert barrier_sim(steps) == "...."


def test_vehicle_leaving_after_front_sensor_loses_signal_is_cancelled_after_the_grace(barrier_sim):
    # cảm biến trước mất tín hiệu lúc 1000, cảm biến sau không thấy xe: hủy đúng 3000 ms sau đó, không sớm hơn
    steps = [(0, 1, 0), (1000, 0, 0), (3999, 0, 0), (4000, 0, 0), (5000, 0, 0)]
    assert barrier_sim(steps) == "...X-"


def test_rear_sensor_just_in_time_cancels_nothing(barrier_sim):
    # cảm biến sau thấy xe ở mốc 2900 (< 3000) -> không hủy; xe đi hết thì PASS
    steps = [(0, 1, 0), (2900, 1, 1), (3000, 1, 1), (4000, 0, 1), (5000, 0, 0)]
    assert barrier_sim(steps) == "....P"


def test_rear_sensor_at_the_same_tick_as_the_deadline_wins(barrier_sim):
    # cùng một vòng lặp: cảm biến sau vừa thấy xe đúng mốc hết hạn -> coi là kịp (detector chạy trước window)
    assert barrier_sim([(0, 1, 0), (3000, 1, 1)]) == ".."


def test_grace_counts_from_the_moment_the_front_sensor_loses_the_signal_not_from_when_it_saw_the_vehicle(barrier_sim):
    # thấy xe lúc 1000, xe đứng tới 5000 rồi đi: hạn chót là 8000 (5000 + 3000)
    steps = [(0, 0, 0), (1000, 1, 0), (5000, 1, 0), (5001, 0, 0), (8000, 0, 0), (8001, 0, 0)]
    assert barrier_sim(steps) == ".....X"


def test_front_sensor_blocked_again_during_the_grace_restarts_it(barrier_sim):
    # nhả lúc 1000, bị chắn lại lúc 2000 (xe quay lại), nhả lần nữa lúc 3500: hạn chót mới là 6500
    steps = [(0, 1, 0), (1000, 0, 0), (2000, 1, 0), (3500, 0, 0), (6499, 0, 0), (6500, 0, 0)]
    assert barrier_sim(steps) == ".....X"


def test_no_vehicle_at_the_front_sensor_never_triggers_the_window(barrier_sim):
    assert barrier_sim([(t, 0, 0) for t in (0, 3000, 6000, 20000)]) == "...."   # hạn chót chung của lần mở lo việc này


def test_vehicle_that_backs_out_after_touching_the_rear_sensor_is_cancelled_once_the_front_sensor_clears(barrier_sim):
    # chạm cảm biến sau rồi lùi ra, vẫn còn ở cảm biến trước (không hủy); cảm biến trước nhả lúc 6000 -> hủy lúc 9000
    steps = [(0, 1, 0), (1000, 1, 1), (1500, 1, 0), (5000, 1, 0), (6000, 0, 0), (8999, 0, 0), (9000, 0, 0)]
    assert barrier_sim(steps) == "......X"


def test_short_vehicle_clearing_the_front_sensor_before_reaching_the_rear_still_passes(barrier_sim):
    # xe ngắn: trước bật -> trước tắt -> sau bật -> sau tắt, tất cả trong cửa sổ
    assert barrier_sim([(0, 1, 0), (500, 0, 0), (1000, 0, 1), (1500, 0, 0)]) == "...P"


def test_front_sensor_off_then_rear_never_seen_is_cancelled_after_the_grace(barrier_sim):
    # xe thấy ở cảm biến trước lúc 0, mất tín hiệu lúc 500 (xe đi mất), cảm biến sau không thấy: hủy lúc 3500
    assert barrier_sim([(0, 1, 0), (500, 0, 0), (3499, 0, 0), (3500, 0, 0)]) == "...X"


def test_sensors_in_the_requested_order_rear_on_then_front_off_then_rear_off_is_a_pass(barrier_sim):
    # đúng chuỗi bạn mô tả: cảm biến 1 -> cảm biến 2 chắn -> cảm biến 1 tắt -> cảm biến 2 tắt = đã qua
    steps = [(0, 0, 0), (200, 1, 0), (900, 1, 1), (1500, 0, 1), (2000, 0, 0)]
    assert barrier_sim(steps) == "....P"


def test_front_off_before_rear_off_is_not_yet_a_pass(barrier_sim):
    # cảm biến sau còn chắn -> chưa hạ thanh chắn (xe còn nằm dưới thanh chắn)
    steps = [(0, 1, 0), (900, 1, 1), (1500, 0, 1), (2500, 0, 1)]
    assert barrier_sim(steps) == "...."


# ======================================================================================================
# Barrier::update đầy đủ (PassDetector + PassWindow + CloseCountdown) đúng thứ tự như firmware:
#   P = xe qua hẳn (hạ + PASS), X = hủy (hạ + NOPASS), '.' = thanh chắn vẫn mở, '-' = đã đóng.
# Cảm biến sau còn sáng thì KHÔNG BAO GIỜ đóng; đồng hồ đóng chỉ đếm từ lúc xe rời cảm biến trước.
# ======================================================================================================
BARRIER_DRIVER = r"""
#include <cstdio>
#include <iostream>
#include <string>
%s
%s
%s
int main() {
  PassDetector d;
  PassWindow w;
  CloseCountdown c;
  const unsigned long HOLD = %d, WINDOW = %d;
  const unsigned long OPENED_AT = 0;
  bool open = true;
  unsigned long t;
  std::string b, a;
  while (std::cin >> t >> b >> a) {
    if (!open) { std::putchar('-'); continue; }
    bool before = (b == "1"), after = (a == "1");
    if (d.update(before, after)) { open = false; std::putchar('P'); continue; }
    if (after) { c.reset(); std::putchar('.'); continue; }
    if (w.expired(d.seenBefore(), d.seenAfter(), before, t, WINDOW)) { open = false; std::putchar('X'); continue; }
    if (c.due(d.seenBefore(), before, after, OPENED_AT, t, HOLD)) { open = false; std::putchar('X'); continue; }
    std::putchar('.');
  }
  std::putchar('\n');
}
"""


def _build_barrier(tmp_path_factory, hold, window):
    gxx = shutil.which("g++")
    if gxx is None:
        pytest.skip("không có g++ để biên dịch thử Barrier")
    parts = [INO[INO.index(f"// BEGIN {n}"):INO.index(f"// END {n}")]
             for n in ("PassDetector", "PassWindow", "CloseCountdown")]
    d = tmp_path_factory.mktemp("barrier")
    (d / "main.cpp").write_text(BARRIER_DRIVER % (*parts, hold, window), encoding="utf-8")
    subprocess.run([gxx, "-std=c++11", "-Wall", "-Werror", str(d / "main.cpp"), "-o", str(d / "run")], check=True)

    def run(steps):
        text = "\n".join(f"{t} {b} {a}" for t, b, a in steps)
        out = subprocess.run([str(d / "run")], input=text, capture_output=True, text=True, check=True)
        return out.stdout.strip()

    return run


@pytest.fixture(scope="module")
def barrier(tmp_path_factory):
    return _build_barrier(tmp_path_factory, hold=3000, window=3000)


@pytest.fixture(scope="module")
def barrier_short_hold(tmp_path_factory):
    return _build_barrier(tmp_path_factory, hold=1000, window=5000)


@pytest.fixture(scope="module")
def barrier_short_window(tmp_path_factory):
    return _build_barrier(tmp_path_factory, hold=5000, window=1000)


def test_rear_sensor_lit_never_closes_the_barrier_however_long(barrier):
    # xe tới cảm biến trước lúc 0, vào cảm biến sau lúc 1000 rồi đứng đó (bản cũ hạ sau 3000 + 10000 ms)
    steps = [(0, 1, 0), (1000, 1, 1), (3000, 0, 1), (13000, 0, 1), (14000, 0, 1), (600000, 0, 1)]
    assert barrier(steps) == "......"


def test_countdown_restarts_when_the_rear_sensor_clears_after_a_reverse(barrier):
    # sau chắn lúc 1000, xe lùi: sau nhả lúc 5000 khi trước còn chắn (chưa đếm); trước nhả lúc 8000 -> hạ lúc 11000
    steps = [(0, 1, 0), (1000, 1, 1), (5000, 1, 0), (8000, 0, 0), (10999, 0, 0), (11000, 0, 0)]
    assert barrier(steps) == ".....X"


def test_countdown_starts_only_when_the_vehicle_leaves_the_front_sensor(barrier):
    # xe đứng ở cảm biến trước 20 giây (quá hạn mở 3 giây từ lâu) vẫn không đóng; rời lúc 20000 -> hạ lúc 23000
    steps = [(0, 1, 0), (10000, 1, 0), (20000, 1, 0), (20001, 0, 0), (22999, 0, 0), (23001, 0, 0)]
    assert barrier(steps) == ".....X"


def test_vehicle_that_never_arrives_closes_after_the_hold_from_opening(barrier):
    assert barrier([(1000, 0, 0), (2999, 0, 0), (3000, 0, 0), (4000, 0, 0)]) == "..X-"


def test_object_on_the_rear_sensor_only_blocks_the_arrival_deadline(barrier):
    # vật chắn riêng cảm biến sau (chưa từng chắn cảm biến trước): quá hạn chờ xe vẫn không đóng
    assert barrier([(1000, 0, 1), (5000, 0, 1), (60000, 0, 1)]) == "..."


def test_normal_pass_still_closes_immediately_when_rear_sensor_clears(barrier):
    steps = [(0, 0, 0), (500, 1, 0), (1500, 1, 1), (2500, 0, 1), (3000, 0, 0)]
    assert barrier(steps) == "....P"


def test_shorter_grace_window_cancels_before_the_hold_countdown(barrier_short_window):
    # hold 5000, ân hạn 1000: xe rời cảm biến trước lúc 500, sau không thấy xe -> hủy lúc 1500
    assert barrier_short_window([(0, 1, 0), (500, 0, 0), (1499, 0, 0), (1500, 0, 0)]) == "...X"


def test_shorter_hold_closes_before_the_grace_window(barrier_short_hold):
    # hold 1000, ân hạn 5000: đồng hồ đóng (đếm từ lúc xe rời cảm biến trước) hết trước -> hạ lúc 1500
    assert barrier_short_hold([(0, 1, 0), (500, 0, 0), (1499, 0, 0), (1500, 0, 0)]) == "...X"
