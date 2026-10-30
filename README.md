# smart-parking

Bãi đỗ xe thông minh bằng Python: quẹt thẻ RFID (Arduino qua cổng COM) -> chụp camera -> nhận diện biển số -> lưu SQL Server.
Hệ thống có **2 cổng trên cùng một máy**: **cổng vào** và **cổng ra**, mỗi cổng một camera và một đầu đọc RFID.
Mặc định cả hai cổng hiện trong **MỘT cửa sổ** (hai khung camera cạnh nhau: CỔNG VÀO | CỔNG RA, lịch sử dùng chung ở dưới). Vẫn có thể chạy riêng từng cổng, mỗi cổng một cửa sổ / tiến trình.
Cần project **rfid_arduino** đã nạp cho board (hai project chỉ giao tiếp qua cổng COM).

## Cài đặt
1. Python 3.10+, SQL Server, **ODBC Driver 17/18 for SQL Server**.
2. Mở thư mục này bằng VS Code, rồi trong Terminal:
   ```
   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt
   ```
3. Ctrl+Shift+P -> **Python: Select Interpreter** -> chọn `.venv\Scripts\python.exe`.
4. Tạo file cấu hình từ các file mẫu:
   ```
   copy .env.example .env          (chung: SQL Server, giá tiền...)
   copy .env.in.example .env.in    (riêng cổng vào: RFID_PORT, CAMERA_INDEX)
   copy .env.out.example .env.out  (riêng cổng ra)
   ```
   Xem cổng COM: Device Manager, hoặc `python -m serial.tools.list_ports`.
   Các file `.env*` thật **không được commit** (có mật khẩu); chỉ commit các file `*.example`.

## Chạy
- **Windows, không cần gõ lệnh:** bấm đúp `setup.bat` (một lần: tạo `.venv`, cài thư viện, tạo `.env*` từ file mẫu), sửa các file `.env*`, rồi bấm đúp `run.bat` (cả hai cổng, một cửa sổ). `run.bat in` / `run.bat out` chạy riêng từng cổng.
- **Một cửa sổ, hai camera (mặc định):**
  ```
  python main.py            (tương đương python main.py --gate both)
  ```
  VS Code: chọn cấu hình **Một cửa sổ (vào + ra)** rồi nhấn F5.
- **Mỗi cổng một cửa sổ riêng** (hai tiến trình, mở 2 terminal):
  ```
  python main.py --gate in
  python main.py --gate out
  ```
  VS Code: **Cổng VÀO**, **Cổng RA** hoặc **Cả hai cổng (vào + ra)** (hai cửa sổ).
Trước khi chạy: cắm 2 Arduino + 2 camera, **đóng Serial Monitor / Arduino IDE**.
Lần đầu chạy cần Internet để EasyOCR tải mô hình; chương trình tự tạo database + bảng (hai cổng khởi động cùng lúc vẫn an toàn).
Chế độ một cửa sổ chỉ nạp **một** bản EasyOCR dùng chung cho cả hai cổng (tiết kiệm RAM); nếu hai cổng quét cùng lúc thì lần lượt từng cổng. Chạy hai tiến trình riêng thì mỗi cổng nạp một bản.
Hai cổng trong một cửa sổ cần màn hình rộng khoảng 1850 px với `VIEW_W=420`; màn nhỏ hơn thì khung camera tự thu nhỏ cho vừa. Phím **Space** (thử nhận diện) chạy cho cổng đang được trỏ chuột vào.

Mẹo: cắm cố định vào cùng cổng USB để số COM và số camera không bị Windows đổi. Camera USB cắm chung một bộ điều khiển USB có thể tranh băng thông.

## Bảng cấu hình
`RFID_PORT`, `CAMERA_INDEX`, `WINDOW_POS` nằm trong `.env.in` / `.env.out` (riêng từng cổng); các biến còn lại nằm trong `.env` (chung). Thứ tự ưu tiên: biến môi trường có sẵn > `.env.in`/`.env.out` > `.env` > mặc định. Chế độ một cửa sổ vẫn đọc đủ cả `.env.in` và `.env.out`; hai cổng **không được trùng** `RFID_PORT` hay `CAMERA_INDEX` (chương trình báo lỗi ngay khi khởi động).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RFID_PORT` | `COM3` (vào), `COM4` (ra) | Cổng COM của đầu đọc RFID |
| `CAMERA_INDEX` | `0` (vào), `1` (ra) | Số camera |
| `WINDOW_POS` | trống | Vị trí cửa sổ khi chạy từng cổng riêng, VD `+0+0` và `+920+0` (chế độ một cửa sổ bỏ qua biến này) |
| `DB_SERVER`, `DB_NAME` | `localhost\SQLEXPRESS`, `BienSoDB` | SQL Server |
| `DB_USER`, `DB_PASSWORD` | trống | Để trống `DB_USER` = Windows Authentication |
| `DB_DRIVER` | `ODBC Driver 17 for SQL Server` | Tên driver ODBC đã cài |
| `RFID_BAUD`, `RFID_DEBOUNCE` | `9600`, `2.0` | Tốc độ serial; số giây bỏ qua quẹt trùng |
| `AUTO_SAVE` | `1` | Cổng vào: `1` tự lưu khi chốt được 5 số, `0` luôn chờ xác nhận |
| `PRICE_PER_BLOCK`, `BLOCK_MINUTES` | `5000`, `60` | Giá một khối và độ dài khối |
| `SCAN_FRAMES`, `SCAN_INTERVAL`, `VOTE_MIN` | `5`, `0.25`, `2` | Số ảnh quét, giây giữa hai ảnh, số phiếu tối thiểu (`1..SCAN_FRAMES`) |
| `VIEW_W`, `VIEW_H` | `420`, `315` | Kích thước khung camera (mỗi cửa sổ rộng khoảng 900 px) |
| `IMG_DIR` | `anh_chup/` trong project | Thư mục ảnh, hai cổng dùng chung |

## Xử lý sự cố
| Hiện tượng | Cách xử lý |
|---|---|
| Hộp thoại "Không kết nối được SQL Server" | Kiểm tra `DB_SERVER` trong `.env`, cài ODBC Driver, bật dịch vụ SQL Server |
| RFID đỏ "chưa kết nối" | Đổi `RFID_PORT`, đóng Serial Monitor / Arduino IDE. Chương trình tự kết nối lại khi cổng sẵn sàng |
| Hai cổng báo lỗi cổng COM hoặc camera | Thiếu `.env.in` / `.env.out`, hoặc hai cổng trùng `RFID_PORT` / `CAMERA_INDEX` |
| Một cửa sổ nhưng hai khung camera hiện cùng một hình | Hai cổng đang trùng `CAMERA_INDEX`: sửa lại trong `.env.in` / `.env.out` |
| Cửa sổ chung quá rộng, tràn màn hình | Giảm `VIEW_W` / `VIEW_H` trong `.env` (hoặc để chương trình tự thu nhỏ theo độ rộng màn hình) |
| "Không mở được camera" | Đổi số trong ô "Camera số" rồi bấm Mở camera; đóng ứng dụng khác đang dùng camera |
| Quẹt thẻ chậm | OCR chạy bằng CPU, mỗi ảnh có thể mất vài giây. Giảm `SCAN_FRAMES` nếu cần |
| Thẻ báo "đang ở trong bãi" dù xe đã đi | Lượt cũ chưa đóng: đóng bằng câu SQL ở trên |
| Cổng ra luôn chặn xe | Biển lúc vào nhập sai hoặc camera lệch góc: xem ảnh hai bên, nhập lại số hoặc cho ra kèm lý do |

## Giao thức với Arduino
Serial 9600 baud, mỗi thẻ một dòng HEX (VD `A1B2C3D4\n`). Đổi baud thì sửa `RFID_BAUD` ở đây và `BAUD_RATE` bên rfid_arduino.

## Quy tắc nghiệp vụ

**Hướng đi do CỔNG quyết định**, trạng thái thẻ chỉ để kiểm tra hợp lệ:

| Tình huống | Kết quả |
|---|---|
| Thẻ không có trong bảng `cards` (hoặc `is_active = 0`) | Từ chối ở cả hai cổng, không nhận diện, không lưu |
| Cổng vào, thẻ đang ở trong bãi | Từ chối (không cho vào lần nữa) |
| Cổng ra, thẻ chưa có lượt vào | Từ chối (xe chưa vào bãi) |
| Cổng vào, thẻ hợp lệ | Quét ảnh, bỏ phiếu 5 số, lưu `time_in` |
| Cổng ra, thẻ hợp lệ | Quét ảnh, bỏ phiếu 5 số, **đối chiếu với 5 số lúc vào**, lưu `time_out` + `fee` |

**Chỉ dùng 5 số cuối của biển** (bỏ chữ cái và các dấu `-` `.` vì dễ gây lỗi OCR). Biển số **bắt buộc đủ đúng 5 chữ số** ở cả hai cổng, nút Lưu / Cho xe ra bị khóa cho đến khi đủ.
Biển cũ chỉ có 4 số: nhập thêm số `0` ở đầu (VD `1234` -> `01234`) ở cả cổng vào và cổng ra để hai lần nhập khớp nhau.

**Quét 5 ảnh, bỏ phiếu.** Sau mỗi lần quẹt thẻ, hệ thống lấy `SCAN_FRAMES` (mặc định 5) khung hình cách nhau `SCAN_INTERVAL` giây, OCR từng khung, rồi chọn 5 số xuất hiện nhiều nhất.
- Chỉ kết quả đủ 5 số mới có phiếu. Số thắng phải có ít nhất `VOTE_MIN` phiếu (mặc định 2) **và** nhiều phiếu hơn số đứng thứ hai. Hòa, hoặc không đủ phiếu -> chuyển cho nhân viên.
- Dừng sớm khi kết quả không thể bị lật nữa (VD 3 ảnh đầu cùng một số).
- Ảnh lưu lại là khung hình cho ra số thắng. Kết quả bỏ phiếu được ghi vào cột `votes_in` / `votes_out` (VD `25888:3,25883:1`).

**Đối chiếu ở cổng ra:**
- Khớp hoàn toàn: tự đóng lượt, tính tiền, cho ra.
- Lệch 1 chữ số: chờ nhân viên, **bắt buộc nhập lý do** rồi mới cho ra.
- Lệch từ 2 chữ số, hoặc không đọc đủ 5 số: chặn. Nhân viên có thể nhập lại 5 số (nếu khớp thì không cần lý do), hoặc cho ra kèm lý do, hoặc từ chối (lượt vẫn mở).
- Kết quả được ghi ở cột `match_status` (`MATCH` / `APPROVED_CLOSE` / `APPROVED_MISMATCH`) và `override_note`.
- Giờ ra tính tại **lúc quẹt thẻ**, không phải lúc nhân viên bấm xác nhận.

**Tiền:** làm tròn LÊN theo khối (`BLOCK_MINUTES`, mặc định 60 phút), tối thiểu 1 khối, mỗi khối `PRICE_PER_BLOCK` (mặc định 5.000 đ).

3 thẻ nạp sẵn (tự thêm khi chạy lần đầu): `AB1992CA`, `DB2B11CA`, `1B12E1CB`.
Nút "Thử nhận diện" chỉ để thử (1 ảnh), **không lưu** vì không có thẻ.

Thêm / khóa thẻ bằng SQL (mã thẻ viết HOA, không dấu cách):
```sql
INSERT INTO BienSoDB.dbo.cards (card_uid) VALUES (N'AABBCCDD');
UPDATE BienSoDB.dbo.cards SET is_active = 0 WHERE card_uid = N'AABBCCDD';
```
Thẻ bị kẹt "đang trong bãi" (mất xe, quẹt vào mà không ra...) tạm thời đóng bằng SQL:
```sql
UPDATE BienSoDB.dbo.access_log
SET time_out = SYSDATETIME(), fee = 0, match_status = N'APPROVED_MISMATCH', override_note = N'Đóng thủ công: <lý do>'
WHERE card_uid = N'AABBCCDD' AND time_out IS NULL;
```

## Cấu trúc
```
config.py                    cấu hình theo từng cổng (đọc biến môi trường / file .env*)
main.py                      python main.py [--gate in|out|both]   (mặc định both: một cửa sổ)
core/                        plate_utils.py     xử lý ảnh + chuỗi biển
                             recognizer.py      OCR 1 khung (EasyOCR)
                             plate_voting.py    bỏ phiếu giữa nhiều lần đọc
                             scanner.py         quét nhiều khung + bỏ phiếu
                             plate_match.py     so khớp 5 số vào / ra
hardware/                    rfid.py (Serial), camera.py (đọc camera ở luồng nền)
storage/                     database.py (SQL Server), schema.sql, models.py, errors.py
services/                    gate_service.py    phần chung (quét, lưu ảnh)
                             entry_service.py   nghiệp vụ cổng vào
                             exit_service.py    nghiệp vụ cổng ra
                             pricing.py         tính tiền
setup.bat / run.bat          cài đặt một lần / chạy chương trình (Windows)
ui/                          base_gate_app.py   giao diện chung
                             entry_app.py       cổng vào
                             exit_app.py        cổng ra (ảnh vào cạnh ảnh ra, đối chiếu)
                             dual_app.py        một cửa sổ chứa cả hai cổng + lịch sử dùng chung
tests/                       pytest
```

## Kiểm thử
```
python -m pip install -r requirements-dev.txt
python -m pytest
```
Test dùng camera, OCR và CSDL giả nên chạy được mà không cần phần cứng hay SQL Server. Test giao diện tự bỏ qua nếu máy không có màn hình.

## Nâng cấp từ bản cũ
**Giao diện một cửa sổ:** không cần đổi cấu hình hay database. `python main.py` giờ mở cả hai cổng trong một cửa sổ; muốn giữ cách cũ thì chạy `python main.py --gate in` và `--gate out` như trước.

**Sao lưu database trước** khi chạy lần đầu, vì chương trình tự sửa cấu trúc bảng `access_log`.

**File cấu hình:** `RFID_PORT` và `CAMERA_INDEX` trong `.env` cũ giờ phải chuyển sang `.env.in` (cổng vào) và `.env.out` (cổng ra); nếu không, hai cổng dùng chung một cổng COM/camera và tranh nhau (chương trình in cảnh báo khi thiếu file). Chú thích cùng dòng (`KEY=giá trị  # ghi chú`) được hỗ trợ.

`init_schema()` tự nâng cấp bảng `access_log` cũ (đổi tên `image_path` -> `image_in`, thêm cột mới, giữ nguyên dữ liệu). Dữ liệu cũ không bị kiểm tra lại ràng buộc 5 số.
Nếu bảng cũ có thẻ bị trùng lượt đang mở, chỉ mục chặn trùng sẽ chưa được tạo (có cảnh báo); hãy đóng bớt lượt rồi khởi động lại.
