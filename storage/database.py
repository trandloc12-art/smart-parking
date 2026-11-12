"""Lưu trữ vào SQL Server (pyodbc). Mỗi thao tác mở một kết nối ngắn -> an toàn khi gọi từ nhiều luồng
và từ nhiều tiến trình (cổng vào + cổng ra chạy song song). ODBC có connection pooling nên không chậm."""
import re
import time
from contextlib import contextmanager
from pathlib import Path

import pyodbc  # pip install pyodbc  (cần cài thêm "ODBC Driver 17/18 for SQL Server")

from storage.errors import AlreadyInside, PlateAlreadyInside, SessionAlreadyClosed
from storage.models import AccessEvent

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
_COLUMNS = ("id, card_uid, plate_number, plate_full, image_in, time_in, time_out, fee, "
            "plate_out, image_out, match_status, override_note, gate_in, gate_out")
_OPEN_INDEX = "UX_access_log_open_card"
_OPEN_PLATE_INDEX = "UX_access_log_open_plate"
_PASS_COLUMNS = {"in": ("pass_in_status", "pass_in_at"), "out": ("pass_out_status", "pass_out_at")}


def _to_event(r):
    return AccessEvent(r.id, r.card_uid or "", r.plate_number or "", r.plate_full or "",
                       r.image_in or "", r.time_in, r.time_out, r.fee,
                       r.plate_out or "", r.image_out or "", r.match_status or "",
                       r.override_note or "", r.gate_in or "", r.gate_out or "")


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
    def init_schema(self, attempts=3, delay=1.5):
        """Tạo database (nếu chưa có), bảng, và nạp thẻ. Ném pyodbc.Error nếu không kết nối được.

        Hai cổng có thể khởi động cùng lúc và cùng chạy script này. Script chạy lại nhiều lần được,
        nên nếu hai bên đụng nhau (VD cùng CREATE TABLE) thì bên sau chỉ cần thử lại."""
        for attempt in range(1, attempts + 1):
            try:
                self._init_schema_once()
                return
            except pyodbc.Error:
                if attempt == attempts:
                    raise
                time.sleep(delay)

    def _init_schema_once(self):
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

    def find_open_session_by_plate(self, plate_number):
        """Lượt gửi xe chưa có giờ ra đang giữ 5 số biển này (của bất kỳ thẻ nào), hoặc None."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT TOP (1) {_COLUMNS} FROM dbo.access_log "
                "WHERE plate_number = ? AND time_out IS NULL ORDER BY id DESC", plate_number).fetchone()
        return _to_event(row) if row else None

    def count_open_sessions(self):
        """Số xe đang ở trong bãi (số lượt chưa có giờ ra)."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM dbo.access_log WHERE time_out IS NULL").fetchone()[0]

    def add_entry(self, card_uid, plate_number, plate_full, image_in, time_in, votes="", gate=""):
        """Ghi lượt VÀO. Ném AlreadyInside nếu thẻ đã có lượt đang mở, PlateAlreadyInside nếu biển đã có xe khác đang ở trong bãi."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "INSERT INTO dbo.access_log "
                    "(card_uid, plate_number, plate_full, image_in, time_in, votes_in, gate_in) "
                    "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?)",
                    card_uid, plate_number, plate_full, image_in, time_in, votes, gate).fetchone()
                conn.commit()
        except pyodbc.IntegrityError as e:
            if _OPEN_INDEX in str(e):
                raise AlreadyInside(f"Thẻ {card_uid} đã có lượt vào chưa đóng") from e
            if _OPEN_PLATE_INDEX in str(e):
                raise PlateAlreadyInside(f"Biển số {plate_number} đang có xe khác ở trong bãi") from e
            raise
        return AccessEvent(row.id, card_uid, plate_number, plate_full, image_in, time_in,
                           gate_in=gate)

    def close_session(self, session_id, time_out, fee, plate_out, image_out, match_status,
                      override_note="", votes_out="", gate=""):
        """Ghi giờ ra + tiền + kết quả đối chiếu. Chỉ cập nhật nếu lượt này chưa được đóng."""
        with self._connect() as conn:
            changed = conn.execute(
                "UPDATE dbo.access_log SET time_out = ?, fee = ?, plate_out = ?, image_out = ?, "
                "match_status = ?, override_note = ?, votes_out = ?, gate_out = ? "
                "WHERE id = ? AND time_out IS NULL",
                time_out, fee, plate_out, image_out, match_status, override_note,
                votes_out, gate, session_id).rowcount
            conn.commit()
        if changed != 1:
            raise SessionAlreadyClosed("Lượt gửi xe này đã được đóng trước đó")

    def record_pass(self, session_id, gate, status, at):
        """Ghi kết quả thanh chắn của cổng `gate` ('in' / 'out') cho một lượt: status = PASSED / TIMEOUT.

        Mỗi cổng chỉ ghi một lần cho mỗi lượt (không đè kết quả đã có). Trả về True nếu đã ghi."""
        status_col, at_col = _PASS_COLUMNS[gate]          # tên cột lấy từ bảng cố định, không từ dữ liệu ngoài
        with self._connect() as conn:
            changed = conn.execute(
                f"UPDATE dbo.access_log SET {status_col} = ?, {at_col} = ? "
                f"WHERE id = ? AND {status_col} IS NULL", status, at, session_id).rowcount
            conn.commit()
        return changed == 1

    def recent(self, limit=100):
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT TOP (?) {_COLUMNS} FROM dbo.access_log ORDER BY id DESC", limit).fetchall()
        return [_to_event(r) for r in rows]
