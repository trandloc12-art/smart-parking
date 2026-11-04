"""Danh sách thẻ nạp sẵn trong schema.sql: đúng 5 thẻ của bãi (UID viết HEX hoa, không dấu cách)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = (ROOT / "storage" / "schema.sql").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")

# AB 19 92 CA / DB 2B 11 CA / 1B 12 E1 CB / 1B AE 10 CB / 8B 06 6E CA
EXPECTED = {"AB1992CA", "DB2B11CA", "1B12E1CB", "1BAE10CB", "8B066ECA"}


def seeded_uids():
    block = SCHEMA.split("INSERT INTO dbo.cards", 1)[1].split("AS v(uid)", 1)[0]
    return set(re.findall(r"N'([0-9A-F]+)'", block))


def test_schema_seeds_exactly_the_five_cards():
    assert seeded_uids() == EXPECTED


def test_readme_lists_the_same_cards():
    line = next(l for l in README.splitlines() if "thẻ nạp sẵn" in l)
    assert set(re.findall(r"`([0-9A-F]{8})`", line)) == EXPECTED
