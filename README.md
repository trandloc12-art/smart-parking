# bien_so_app

Project Python: nhận mã thẻ từ Arduino (cổng COM) -> chụp camera -> nhận diện biển số -> lưu SQL Server.
Cần project **rfid_arduino** đã nạp cho board (hai project độc lập, chỉ giao tiếp qua cổng COM).

## Cài đặt
1. Python 3.10+, SQL Server, **ODBC Driver 17/18 for SQL Server**.
2. Mở thư mục này bằng VS Code, rồi trong Terminal:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   ```
3. Ctrl+Shift+P -> **Python: Select Interpreter** -> chọn `.venv\Scripts\python.exe`.
4. Copy `.env.example` thành `.env`, sửa `RFID_PORT`, `DB_SERVER`...
   (xem cổng COM: Device Manager, hoặc `python -m serial.tools.list_ports`)

## Chạy
- VS Code: nhấn **F5** (dùng cấu hình trong `.vscode/launch.json`, tự nạp `.env`).
- Hoặc terminal: đặt biến môi trường rồi `python main.py`.

Trước khi chạy: cắm Arduino, **đóng Serial Monitor / Arduino IDE**.
Lần đầu chạy cần Internet để EasyOCR tải mô hình; chương trình tự tạo database + bảng.

## Giao thức với Arduino
Serial 9600 baud, mỗi thẻ một dòng HEX (VD `A1B2C3D4\n`). Đổi baud thì sửa `RFID_BAUD` ở đây và `BAUD_RATE` bên rfid_arduino.

## Cấu trúc
```
config.py                 cấu hình (đọc biến môi trường)
main.py                   nối các thành phần
core/                     plate_utils.py, recognizer.py   (nhận diện biển số)
hardware/                 rfid.py (Serial), camera.py
storage/                  database.py (SQL Server), schema.sql
services/access_service.py  thẻ + khung hình -> nhận diện -> lưu
ui/app.py                 giao diện Tkinter
```

## Thẻ hợp lệ, vào / ra, tiền
- Chỉ các thẻ trong bảng `dbo.cards` mới được xử lý. Thẻ lạ: báo đỏ, **không nhận diện, không lưu**.
- 3 thẻ nạp sẵn (tự thêm khi chạy lần đầu): `AB1992CA`, `DB2B11CA`, `1B12E1CB`.
- Quẹt lần 1 = **xe vào** (nhận diện biển, lưu `time_in`). Quẹt lần 2 = **xe ra** (lưu `time_out` + `fee`).
- Tiền: làm tròn LÊN theo khối (`BLOCK_MINUTES`, mặc định 60 phút), tối thiểu 1 khối, mỗi khối `PRICE_PER_BLOCK` (mặc định 5.000 đ).
- Nút "Thử nhận diện" chỉ để thử, **không lưu** vì không có thẻ.

Thêm / khóa thẻ bằng SQL (mã thẻ viết HOA, không dấu cách):
```sql
INSERT INTO BienSoDB.dbo.cards (card_uid) VALUES (N'AABBCCDD');
UPDATE BienSoDB.dbo.cards SET is_active = 0 WHERE card_uid = N'AABBCCDD';
```
