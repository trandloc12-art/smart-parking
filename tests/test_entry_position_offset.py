"""Cổng vào: không đọc đủ 5 số -> cảnh báo 'biển số lệch vị trí'."""
from core.scanner import ScanResult
from ui.entry_app import plate_position_offset


def test_no_reading_at_all_is_offset():
    assert plate_position_offset(ScanResult(decided=False, tally=()))


def test_partial_digits_is_offset():
    assert plate_position_offset(ScanResult(suggestion="2588", decided=False, tally=()))


def test_decided_is_not_offset():
    assert not plate_position_offset(ScanResult(winner="25888", decided=True, tally=(("25888", 3),)))


def test_conflicting_full_candidates_is_not_offset():
    # có ứng viên đủ 5 số nhưng hòa phiếu -> OCR chưa chắc, không phải lệch vị trí
    assert not plate_position_offset(ScanResult(decided=False, tally=(("25888", 1), ("25883", 1))))


def test_none_scan_is_not_offset():
    assert not plate_position_offset(None)
