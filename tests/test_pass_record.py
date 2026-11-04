"""Ghi kết quả cảm biến hồng ngoại (xe đã qua thanh chắn / hết giờ chưa qua) vào lượt gửi xe."""
import re
from pathlib import Path

from helpers import FakeCamera, FakeDb, ScriptedRecognizer
from services.entry_service import EntryService
from services.exit_service import ExitService
from services.gate_service import PASS_PASSED, PASS_TIMEOUT, now

ROOT = Path(__file__).resolve().parent.parent


def make_services(tmp_path):
    db, rec = FakeDb(), ScriptedRecognizer(["25888"])
    return (EntryService(rec, db, str(tmp_path), sleep=lambda s: None),
            ExitService(rec, db, str(tmp_path), sleep=lambda s: None), db)


def test_entry_and_exit_record_into_their_own_gate_column(tmp_path):
    entry, exit_, db = make_services(tmp_path)
    session = entry.handle_card("CARD1", lambda: FakeCamera().read()).event
    at = now()

    assert entry.record_pass(session.id, True, at) is True
    assert exit_.record_pass(session.id, False, at) is True
    assert db.passes == [(session.id, "in", PASS_PASSED, at), (session.id, "out", PASS_TIMEOUT, at)]


def test_pass_result_is_written_once_per_gate(tmp_path):
    entry, _, db = make_services(tmp_path)
    session = entry.handle_card("CARD1", lambda: FakeCamera().read()).event
    assert entry.record_pass(session.id, True) is True
    assert entry.record_pass(session.id, False) is False          # không đè kết quả đã có
    assert [p[2] for p in db.passes] == [PASS_PASSED]


def test_record_pass_defaults_to_now(tmp_path):
    entry, _, db = make_services(tmp_path)
    session = entry.handle_card("CARD1", lambda: FakeCamera().read()).event
    entry.record_pass(session.id, True)
    assert abs((db.passes[0][3] - now()).total_seconds()) < 5


def test_schema_has_the_columns_that_database_writes():
    """database.py ghi vào các cột pass_*; schema.sql phải tạo đúng các cột đó (không import pyodbc)."""
    code = (ROOT / "storage" / "database.py").read_text(encoding="utf-8")
    schema = (ROOT / "storage" / "schema.sql").read_text(encoding="utf-8")
    block = code[code.index("_PASS_COLUMNS"):].split("\n", 1)[0]
    columns = re.findall(r'"(pass_\w+)"', block)
    assert sorted(columns) == ["pass_in_at", "pass_in_status", "pass_out_at", "pass_out_status"]
    for col in columns:
        assert re.search(rf"COL_LENGTH\(N'dbo\.access_log', N'{col}'\)\s+IS NULL\s+ALTER TABLE", schema), col
