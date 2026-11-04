"""Bộ đếm chỗ trống của bãi (ui/slots.py): thuần Python, không cần Tkinter."""
from ui.slots import SlotCounter


def make(capacity=3, free=3):
    c = SlotCounter(capacity)
    c.update(free, c.version)
    calls = []
    c.subscribe(lambda: calls.append(c.free))
    return c, calls


def test_starts_unknown_and_not_full():
    c = SlotCounter(3)
    assert c.free is None and not c.full and c.tracking


def test_no_capacity_means_not_tracking():
    c = SlotCounter(None)
    assert not c.tracking
    c.adjust(-1)
    c.force(0)
    assert c.update(2, c.version) is False and c.free is None and not c.full


def test_vehicle_in_and_out_adjust_and_notify():
    c, calls = make()
    c.adjust(-1)
    c.adjust(-1)
    c.adjust(-1)
    assert c.free == 0 and c.full
    c.adjust(+1)
    assert c.free == 1 and not c.full
    assert calls == [2, 1, 0, 1]


def test_adjust_is_clamped_to_capacity():
    c, _ = make()
    c.adjust(+1)                    # không thể trống nhiều hơn số chỗ
    assert c.free == 3
    c.force(0)
    c.adjust(-1)
    assert c.free == 0


def test_listener_is_not_called_when_nothing_changes():
    c, calls = make()
    c.update(3, c.version)
    c.force(3)
    assert calls == []


def test_stale_database_answer_is_ignored_after_a_local_change():
    c, _ = make()
    asked_at = c.version            # hỏi SQL Server lúc còn 3 chỗ...
    c.adjust(-1)                    # ...trong lúc đó có xe vào
    assert c.update(3, asked_at) is False and c.free == 2
    assert c.update(2, c.version) is True and c.free == 2


def test_database_answer_corrects_a_drifted_counter():
    c, calls = make()
    c.adjust(-1)
    assert c.update(0, c.version) is True and c.full
    assert calls == [2, 0]


def test_adjust_before_first_answer_only_invalidates_it():
    c = SlotCounter(3)
    asked_at = c.version
    c.adjust(-1)                    # chưa biết số chỗ: chưa cộng trừ được
    assert c.free is None
    assert c.update(3, asked_at) is False
    assert c.update(2, c.version) is True and c.free == 2


def test_force_overrides_and_notifies():
    c, calls = make()
    c.force(0)
    assert c.full and calls == [0]
