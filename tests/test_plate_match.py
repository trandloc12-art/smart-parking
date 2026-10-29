from core.plate_match import MatchLevel, compare_numbers


def test_exact():
    m = compare_numbers("25888", "25888")
    assert m.level is MatchLevel.EXACT and m.distance == 0


def test_one_digit_off():
    m = compare_numbers("25888", "25883")
    assert m.level is MatchLevel.CLOSE and m.distance == 1


def test_many_digits_off():
    assert compare_numbers("25888", "11111").level is MatchLevel.MISMATCH
    assert compare_numbers("25888", "25833").level is MatchLevel.MISMATCH


def test_bad_input_is_mismatch():
    assert compare_numbers("", "25888").level is MatchLevel.MISMATCH
    assert compare_numbers("2588", "25888").level is MatchLevel.MISMATCH   # biển cũ 4 số, khác độ dài
    assert compare_numbers(None, None).level is MatchLevel.MISMATCH
