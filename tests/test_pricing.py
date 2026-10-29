from datetime import datetime, timedelta

from services.pricing import calculate_fee

T0 = datetime(2026, 1, 1, 8, 0, 0)


def test_minimum_one_block():
    assert calculate_fee(T0, T0) == 5000
    assert calculate_fee(T0, T0 + timedelta(minutes=1)) == 5000


def test_exact_hour_is_one_block():
    assert calculate_fee(T0, T0 + timedelta(minutes=60)) == 5000


def test_round_up():
    assert calculate_fee(T0, T0 + timedelta(minutes=61)) == 10000
    assert calculate_fee(T0, T0 + timedelta(hours=3, minutes=1)) == 20000


def test_custom_block():
    assert calculate_fee(T0, T0 + timedelta(minutes=31), 3000, 30) == 6000


def test_negative_duration_is_minimum():
    assert calculate_fee(T0, T0 - timedelta(minutes=5)) == 5000
