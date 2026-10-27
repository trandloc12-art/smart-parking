"""Lưu trữ vào SQL Server (pyodbc). Mỗi thao tác mở một kết nối ngắn -> an toàn khi gọi từ nhiều luồng
(ODBC có connection pooling nên không chậm)."""
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyodbc  # pip install pyodbc  (cần cài thêm "ODBC Driver 17/18 for SQL Server")

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
_COLUMNS = "id, card_uid, plate_number, plate_full, image_path, time_in, time_out, fee"


@dataclass
class AccessEvent:
    """Một lượt gửi xe. time_out/fee là None cho đến khi xe ra."""
    id: int
    card_uid: str
    plate_number: str
    plate_full: str
    image_path: str
    time_in: datetime
    time_out: datetime | None = None
    fee: int | None = None


def _to_event(r):
    return AccessEvent(r.id, r.card_uid or "", r.plate_number or "", r.plate_full or "",
                       r.image_path or "", r.time_in, r.time_out, r.fee)


class Database:
    def __init__(self, server, database, user="", password="",
                 driver="ODBC Driver 17 for SQL Server", timeout=5):
        if not re.fullmatch(r"\w+", database):
            raise ValueError("Tên database chỉ được gồm chữ, số, dấu gạch dưới")
        self.server, self.database = server, database
        self.user, self.password = user, password
        self.driver, self.timeout = driver, timeout

    # ---------- Kết nối ----------
    def _conn_str(self, database):
        parts = [f"DRIVER={{{self.driver}}}", f"SERVER={self.server}", f"DATABASE={database}",
                 "TrustServerCertificate=yes"]
        if self.user:
            parts += [f"UID={self.user}", f"PWD={self.password}"]
        else:
            parts.append("Trusted_Connection=yes")   # Windows Authentication
        return ";".join(parts)

    @contextmanager
    def _connect(self, database=None, autocommit=False):
        conn = pyodbc.connect(self._conn_str(database or self.database),
                              autocommit=autocommit, timeout=self.timeout)
        try:
            yield conn
        finally:
            conn.close()

    # ---------- Khởi tạo ----------
    def init_schema(self):
        """Tạo database (nếu chưa có), bảng, và nạp thẻ. Ném pyodbc.Error nếu không kết nối được."""
        with self._connect("master", autocommit=True) as conn:
            conn.execute(f"IF DB_ID(N'{self.database}') IS NULL CREATE DATABASE [{self.database}]")

        script = SCHEMA_FILE.read_text(encoding="utf-8")
        batches = re.split(r"^\s*GO\s*$", script, flags=re.IGNORECASE | re.MULTILINE)
        with self._connect() as conn:
            for batch in batches:
                if batch.strip():
                    conn.execute(batch)
            conn.commit()

    # ---------- Thẻ ----------
    def is_card_registered(self, card_uid):
        """True nếu thẻ có trong bảng cards và đang được phép dùng."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM dbo.cards WHERE card_uid = ? AND is_active = 1",
                               card_uid).fetchone()
        return row is not None

    # ---------- Lượt gửi xe ----------
    def find_open_session(self, card_uid):
        """Lượt gửi xe chưa có giờ ra của thẻ này (xe còn trong bãi), hoặc None."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT TOP (1) {_COLUMNS} FROM dbo.access_log "
                "WHERE card_uid = ? AND time_out IS NULL ORDER BY id DESC", card_uid).fetchone()
        return _to_event(row) if row else None

    def add_entry(self, card_uid, plate_number, plate_full, image_path, time_in):
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO dbo.access_log (card_uid, plate_number, plate_full, image_path, time_in) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?)",
                card_uid, plate_number, plate_full, image_path, time_in).fetchone()
            conn.commit()
        return AccessEvent(row.id, card_uid, plate_number, plate_full, image_path, time_in)

    def close_session(self, session_id, time_out, fee):
        """Ghi giờ ra + tiền. Chỉ cập nhật nếu lượt này chưa được đóng."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE dbo.access_log SET time_out = ?, fee = ? WHERE id = ? AND time_out IS NULL",
                time_out, fee, session_id).rowcount
            conn.commit()
        if changed != 1:
            raise RuntimeError("Lượt gửi xe này đã được đóng trước đó")

    def recent(self, limit=100):
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT TOP (?) {_COLUMNS} FROM dbo.access_log ORDER BY id DESC", limit).fetchall()
        return [_to_event(r) for r in rows]
