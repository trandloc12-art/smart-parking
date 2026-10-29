from core.recognizer import RecognitionResult
from core.scanner import scan_best_of
from helpers import make_frame


def run(numbers, frames=5, min_votes=2):
    """Chạy scan với kịch bản các số OCR; trả về (kết quả, số lần OCR, danh sách thời gian chờ)."""
    calls, sleeps, progress = [], [], []
    seq = iter(numbers)

    def get_frame():
        return make_frame(len(calls))

    def recognize(frame):
        n = next(seq)
        calls.append(n)
        return RecognitionResult(frame, f"full-{n}", n)

    res = scan_best_of(recognize, get_frame, frames, 0.25, min_votes,
                       on_progress=lambda i, t: progress.append((i, t)), sleep=sleeps.append)
    return res, calls, sleeps, progress


def test_stops_early_when_unbeatable():
    res, calls, sleeps, progress = run(["25888"] * 5)
    assert res.decided and res.winner == "25888"
    assert len(calls) == 3 and res.scanned == 3 and res.votes == 3   # 3-0 > 2 còn lại -> dừng
    assert sleeps == [0.25, 0.25]                                    # chờ giữa các khung, không chờ sau khung cuối
    assert progress == [(1, 5), (2, 5), (3, 5)]


def test_majority_over_all_frames():
    res, calls, *_ = run(["25888", "25883", "25888", "25883", "25888"])
    assert len(calls) == 5 and res.winner == "25888" and res.votes == 3


def test_tie_leaves_undecided_with_suggestion():
    res, *_ = run(["25888", "25883", "25888", "25883", "99999"])
    assert not res.decided and res.winner == "" and res.suggestion == "25888"
    assert res.number == "25888"
    assert res.tally[0] == ("25888", 2)


def test_ocr_noise_ignored():
    res, *_ = run(["", "2588", "25888", "", "25888"])
    assert res.winner == "25888" and res.votes == 2


def test_picks_image_of_winning_frame():
    res, *_ = run(["11111", "25888", "25888", "25888", "25888"])
    # khung thắng đầu tiên là khung thứ 2 (frame value = 1)
    assert res.image is not None and int(res.image[0, 0, 0]) == 1
    assert res.plate_full == "full-25888"


def test_nothing_readable():
    res, *_ = run([""] * 5)
    assert not res.decided and res.number == "" and res.scanned == 5
    assert res.image is not None            # vẫn trả ảnh để nhân viên xem


def test_no_frames_from_camera():
    res = scan_best_of(lambda f: None, lambda: None, 3, 0.0, 2, sleep=lambda s: None)
    assert res.image is None and not res.decided and res.scanned == 3


def test_votes_text():
    res, *_ = run(["25888", "25883", "25888", "25883", "25888"])
    assert res.votes_text() == "25888:3,25883:2"
