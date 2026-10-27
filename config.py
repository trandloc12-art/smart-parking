"""Cấu hình tập trung. Có thể ghi đè bằng biến môi trường (không cần sửa code)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "anh_chup")

# --- Camera ---
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))

# --- RFID (cổng Serial: thiết bị gửi mỗi thẻ một dòng, VD "A1B2C3D4\n") ---
RFID_PORT = os.getenv("RFID_PORT", "COM3")
RFID_BAUD = int(os.getenv("RFID_BAUD", "9600"))
RFID_DEBOUNCE = float(os.getenv("RFID_DEBOUNCE", "2.0"))   # giây, bỏ qua quẹt trùng cùng thẻ

# --- SQL Server ---
DB_SERVER = os.getenv("DB_SERVER", r"localhost\SQLEXPRESS")
DB_NAME = os.getenv("DB_NAME", "BienSoDB")
DB_USER = os.getenv("DB_USER", "")           # để trống -> dùng Windows Authentication
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

# --- Nghiệp vụ ---
# True: quẹt thẻ mà OCR đọc đủ 5 số thì lưu luôn. Thiếu/sai thì hiện ô cho người dùng sửa rồi mới lưu.
AUTO_SAVE = os.getenv("AUTO_SAVE", "1") == "1"

# --- Tính tiền: làm tròn LÊN theo khối thời gian, tối thiểu 1 khối ---
# Mặc định: 5.000 đ cho mỗi giờ (hoặc phần lẻ của giờ). Ví dụ gửi 61 phút = 2 khối = 10.000 đ.
PRICE_PER_BLOCK = int(os.getenv("PRICE_PER_BLOCK", "5000"))   # VND mỗi khối
BLOCK_MINUTES = int(os.getenv("BLOCK_MINUTES", "60"))         # độ dài một khối (phút)
