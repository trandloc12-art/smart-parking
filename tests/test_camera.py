"""Camera đọc ở luồng nền: dùng cv2.VideoCapture giả, không cần camera thật."""
import time

import numpy as np

from hardware import camera as camera_mod


class FakeCapture:
    def __init__(self, frames=None, opened=True):
        self.frames = list(frames) if frames is not None else None
        self.opened = opened
        self.released = False
        self.reads = 0

    def isOpened(self):
        return self.opened

    def read(self):
        self.reads += 1
        if self.frames is None:                       # camera chạy mãi: mỗi lần một khung mới
            time.sleep(0.005)
            return True, np.full((4, 4, 3), self.reads % 255, dtype=np.uint8)
        if self.frames:
            return True, self.frames.pop(0)
        time.sleep(0.005)
        return False, None                            # hết khung

    def release(self):
        self.released = True


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def patch_capture(monkeypatch, cap):
    monkeypatch.setattr(camera_mod.cv2, "VideoCapture", lambda *a, **k: cap)


def test_open_fails_when_camera_missing(monkeypatch):
    cap = FakeCapture(opened=False)
    patch_capture(monkeypatch, cap)
    cam = camera_mod.Camera()
    assert cam.open(0) is False and cap.released and cam.read() is None


def test_read_returns_only_new_frames(monkeypatch):
    a, b = np.zeros((2, 2, 3), np.uint8), np.ones((2, 2, 3), np.uint8)
    patch_capture(monkeypatch, FakeCapture(frames=[a, b]))
    cam = camera_mod.Camera()
    assert cam.open(0)
    try:
        assert wait_for(lambda: cam._seq == 2)        # luồng nền đã đọc xong cả hai khung
        assert cam.read() is b                        # đọc được khung MỚI NHẤT
        assert cam.read() is None                     # không có khung mới -> None, không trả lại khung cũ
    finally:
        cam.release()


def test_latest_frame_wins_and_release_stops_thread(monkeypatch):
    cap = FakeCapture()
    patch_capture(monkeypatch, cap)
    cam = camera_mod.Camera()
    assert cam.open(0)
    assert wait_for(lambda: cam._seq >= 3)
    frame = cam.read()
    assert frame is not None and frame.shape == (4, 4, 3)
    thread = cam._thread
    cam.release()
    assert cap.released and not thread.is_alive()     # luồng nền đã dừng, camera đã nhả
    reads = cap.reads
    time.sleep(0.05)
    assert cap.reads == reads                         # không còn ai đọc camera nữa
    assert cam.read() is None


def test_reopen_replaces_old_capture(monkeypatch):
    caps = [FakeCapture(), FakeCapture()]
    it = iter(caps)
    monkeypatch.setattr(camera_mod.cv2, "VideoCapture", lambda *a, **k: next(it))
    cam = camera_mod.Camera()
    assert cam.open(0) and cam.open(1)
    assert caps[0].released and not caps[1].released
    assert wait_for(lambda: cam.read() is not None)
    cam.release()
    assert caps[1].released
