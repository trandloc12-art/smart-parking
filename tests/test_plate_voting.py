from core.plate_voting import tally_votes


def test_clear_winner():
    v = tally_votes(["25888", "25888", "25883"])
    assert v.winner == "25888" and v.decided and v.votes == 2 and v.runner_up == 1


def test_needs_min_votes():
    v = tally_votes(["25888", "11111", "22222"])           # mỗi số 1 phiếu
    assert not v.decided and v.winner == "" and v.suggestion == "25888"


def test_tie_is_not_decided():
    v = tally_votes(["25888", "25883", "25888", "25883"])
    assert not v.decided and v.winner == ""
    assert v.tally == (("25888", 2), ("25883", 2))          # thứ tự ổn định


def test_single_vote_ok_when_min_is_one():
    assert tally_votes(["25888"], min_votes=1).winner == "25888"


def test_incomplete_numbers_do_not_vote():
    v = tally_votes(["2588", "2588", "", "2588"])           # 4 số: không có phiếu nào
    assert not v.decided and v.tally == () and v.suggestion == "2588"


def test_partial_suggestion_prefers_longest():
    assert tally_votes(["25", "2588", "258"]).suggestion == "2588"


def test_empty():
    v = tally_votes([])
    assert not v.decided and v.suggestion == "" and v.winner == ""


def test_settled_logic():
    v = tally_votes(["25888", "25888", "25888"])
    assert v.is_settled(remaining=2)                         # 3-0 > 2
    v2 = tally_votes(["25888", "25888"])
    assert not v2.is_settled(remaining=3)                    # 2-0 > 3 sai
    v3 = tally_votes(["25888", "25888", "25883"])
    assert not v3.is_settled(remaining=2)                    # 2-1 > 2 sai


def test_tally_text():
    assert tally_votes(["25888", "25888", "25883"]).tally_text() == "25888:2,25883:1"
