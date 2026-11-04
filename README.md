# smart-parking

Bãi đỗ xe thông minh bằng Python: quẹt thẻ RFID (Arduino qua cổng COM) -> chụp camera -> nhận diện biển số -> lưu SQL Server.
Hệ thống có **2 cổng trên cùng một máy**: **cổng vào** và **cổng ra**. Phần cứng gồm **MỘT Arduino** (một cổng COM) nối **hai đầu đọc RFID**, và mỗi cổng một camera.
Cả hai cổng hiện trong **MỘT cửa sổ** (hai khung camera cạnh nhau: CỔNG VÀO | CỔNG RA, lịch sử dùng chung ở dưới). Ngay trên cùng cửa sổ có **thanh tình trạng thiết bị**: thiết bị nào mất kết nối (Arduino, từng đầu đọc, từng camera, SQL Server) sẽ hiện dải cảnh báo đỏ nêu đúng tên thiết bị.
Arduino cần nạp sketch **`arduino/dual_rfid/dual_rfid.ino`** trong repo này (xem mục *Giao thức với Arduino*).
Tùy chọn: gắn thêm **hai màn LCD 1602 I2C** (một ở cổng vào, một ở cổng ra) để báo cho tài xế (VD "XE LECH VI TRI" khi không đọc đủ 5 số, "XE RA OK - TIEN 5.000 D") — xem mục *Hai màn LCD 1602 I2C*.
Tùy chọn: gắn **một còi bíp** dùng chung, mỗi lần quẹt thẻ (cổng vào hoặc cổng ra) còi kêu một tiếng — xem mục *Còi bíp*.
Tùy chọn: gắn **hai servo thanh chắn** (một ở cổng vào, một ở cổng ra): quẹt thẻ thành công thì servo của cổng đó tự mở rồi tự đóng lại — xem mục *Hai servo thanh chắn*.

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
   copy .env.example .env          (chung: RFID_PORT của Arduino, SQL Server, giá tiền...)
   copy .env.in.example .env.in    (riêng cổng vào: CAMERA_INDEX)
   copy .env.out.example .env.out  (riêng cổng ra: CAMERA_INDEX)
   ```
   Xem cổng COM: Device Manager, hoặc `python -m serial.tools.list_ports`.
   Các file `.env*` thật **không được commit** (có mật khẩu); chỉ commit các file `*.example`.

## Chạy
- **Windows, không cần gõ lệnh:** bấm đúp `setup.bat` một lần (tạo `.venv`, cài thư viện, tạo `.env*` từ file mẫu), sửa các file `.env*`, rồi chọn một trong các file chạy:

  | File | Kết quả |
  |---|---|
  | `run.bat` | MỘT cửa sổ chứa cả cổng vào và cổng ra (hai khung camera) |
  | `run-vao.bat` | Chỉ cổng vào (thẻ quẹt ở đầu đọc cổng ra bị bỏ qua) |
  | `run-ra.bat` | Chỉ cổng ra (thẻ quẹt ở đầu đọc cổng vào bị bỏ qua) |
- **Một cửa sổ, hai camera (mặc định):**
  ```
  python main.py            (tương đương python main.py --gate both)
  ```
  VS Code: chọn cấu hình **Một cửa sổ (vào + ra)** rồi nhấn F5.
- **Chỉ một cổng** (VD camera cổng kia đang hỏng, hoặc để thử):
  ```
  python main.py --gate in
  python main.py --gate out
  ```
  Chỉ chạy được **một tiến trình tại một thời điểm** vì cổng COM của Arduino chỉ một chương trình mở được (nên không còn chế độ "hai cửa sổ riêng").
Trước khi chạy: cắm 1 Arduino + 2 camera, **đóng Serial Monitor / Arduino IDE**.
Lần đầu chạy cần Internet để EasyOCR tải mô hình; chương trình tự tạo database + bảng (hai cổng khởi động cùng lúc vẫn an toàn).
Chế độ một cửa sổ chỉ nạp **một** bản EasyOCR dùng chung cho cả hai cổng (tiết kiệm RAM); nếu hai cổng quét cùng lúc thì lần lượt từng cổng. Chạy hai tiến trình riêng thì mỗi cổng nạp một bản.
Hai cổng trong một cửa sổ cần màn hình rộng khoảng 1850 px với `VIEW_W=420`; màn nhỏ hơn thì khung camera tự thu nhỏ cho vừa. Phím **Space** (thử nhận diện) chạy cho cổng đang được trỏ chuột vào.

Mẹo: cắm cố định vào cùng cổng USB để số COM và số camera không bị Windows đổi. Camera USB cắm chung một bộ điều khiển USB có thể tranh băng thông.

## Bảng cấu hình
`CAMERA_INDEX`, `WINDOW_POS` nằm trong `.env.in` / `.env.out` (riêng từng cổng); các biến còn lại, kể cả `RFID_PORT`, nằm trong `.env` (chung). Thứ tự ưu tiên: biến môi trường có sẵn > `.env.in`/`.env.out` > `.env` > mặc định. Chế độ một cửa sổ đọc đủ cả `.env.in` và `.env.out`; hai cổng **không được trùng** `CAMERA_INDEX`, và vì chỉ có một Arduino nên **`RFID_PORT` chỉ khai báo một lần trong `.env`** (chương trình báo lỗi ngay khi khởi động nếu sai).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RFID_PORT` | `COM3` | Cổng COM của **Arduino** (chung cho cả hai đầu đọc), trong `.env` |
| `CAMERA_INDEX` | `0` (vào), `1` (ra) | Số camera, trong `.env.in` / `.env.out` |
| `WINDOW_POS` | trống | Vị trí cửa sổ khi chạy từng cổng riêng, VD `+0+0` và `+920+0` (chế độ một cửa sổ bỏ qua biến này) |
| `DB_SERVER`, `DB_NAME` | `localhost\SQLEXPRESS`, `BienSoDB` | SQL Server |
| `DB_USER`, `DB_PASSWORD` | trống | Để trống `DB_USER` = Windows Authentication |
| `DB_DRIVER` | `ODBC Driver 17 for SQL Server` | Tên driver ODBC đã cài |
| `RFID_BAUD`, `RFID_DEBOUNCE` | `9600`, `2.0` | Tốc độ serial; số giây bỏ qua quẹt trùng (tính riêng từng cổng) |
| `RFID_HEARTBEAT_TIMEOUT` | `8` | Số giây không nhận được gì từ Arduino thì báo "không phản hồi" (`0` = không kiểm tra) |
| `AUTO_SAVE` | `1` | Cổng vào: `1` tự lưu khi chốt được 5 số, `0` luôn chờ xác nhận |
| `PRICE_PER_BLOCK`, `BLOCK_MINUTES` | `5000`, `60` | Giá một khối và độ dài khối |
| `SCAN_FRAMES`, `SCAN_INTERVAL`, `VOTE_MIN` | `5`, `0.25`, `2` | Số ảnh quét, giây giữa hai ảnh, số phiếu tối thiểu (`1..SCAN_FRAMES`) |
| `LCD_IDLE_SECONDS` | `5` | Số giây sau đó LCD tự về "MOI QUET THE" khi đã xong việc (xe vào/ra OK, thẻ bị từ chối). `0` = giữ thông báo đến lần quẹt sau. Thông báo cần nhân viên xử lý không tự biến mất |
| `VIEW_W`, `VIEW_H` | `420`, `315` | Kích thước khung camera (mỗi cửa sổ rộng khoảng 900 px) |
| `SERVO_ENABLED` | `1` | `1` = quẹt thẻ thành công thì mở servo thanh chắn; `0` = chưa gắn servo thì tắt đi (không gửi lệnh nào) |
| `SERVO_OPEN_SECONDS` | `3` | Số giây giữ thanh chắn mở rồi Arduino tự đóng lại (`0.5`..`30`) |
| `IMG_DIR` | `anh_chup/` trong project | Thư mục ảnh, hai cổng dùng chung |

## Xử lý sự cố
| Hiện tượng | Cách xử lý |
|---|---|
| Hộp thoại "Không kết nối được SQL Server" | Kiểm tra `DB_SERVER` trong `.env`, cài ODBC Driver, bật dịch vụ SQL Server |
| "Arduino: MẤT KẾT NỐI" | Đổi `RFID_PORT` trong `.env`, kiểm tra cáp USB, đóng Serial Monitor / Arduino IDE. Chương trình tự kết nối lại khi cổng sẵn sàng. Hai đầu đọc hiện "chưa rõ" (xám) cho tới khi Arduino trở lại |
| "Arduino: KHÔNG PHẢN HỒI" | Cổng COM còn mở nhưng Arduino im lặng (treo / mất nguồn / chưa nạp sketch). Nạp lại `dual_rfid.ino`, hoặc chỉnh `RFID_HEARTBEAT_TIMEOUT` |
| "Arduino: ... gửi dữ liệu sai định dạng" | Arduino còn nạp firmware cũ chỉ gửi UID trần. Nạp `arduino/dual_rfid/dual_rfid.ino` |
| "Đầu đọc CỔNG VÀO/RA: KHÔNG NHẬN ĐƯỢC module RFID" | Arduino vẫn tốt nhưng không nói chuyện được với module RC522 đó: kiểm tra dây SPI, chân SDA (SS), nguồn 3.3V |
| "Camera ...: KHÔNG MỞ ĐƯỢC" / "MẤT TÍN HIỆU" | Camera chưa mở được hoặc đã hết hình (rút dây, treo). Cắm lại, đổi số trong ô "Camera số" rồi bấm Mở camera |
| Chương trình báo "Cấu hình sai: ... RFID_PORT khác nhau" | Còn sót `RFID_PORT` của thời hai Arduino trong `.env.in` / `.env.out`: xóa dòng đó, chỉ giữ `RFID_PORT` trong `.env` |
| Báo thiếu `.env.in` / `.env.out` hoặc hai cổng trùng `CAMERA_INDEX` | Copy từ file `*.example` và sửa `CAMERA_INDEX` cho khác nhau |
| Một cửa sổ nhưng hai khung camera hiện cùng một hình | Hai cổng đang trùng `CAMERA_INDEX`: sửa lại trong `.env.in` / `.env.out` |
| Cửa sổ chung quá rộng, tràn màn hình | Giảm `VIEW_W` / `VIEW_H` trong `.env` (hoặc để chương trình tự thu nhỏ theo độ rộng màn hình) |
| "Không mở được camera" | Đổi số trong ô "Camera số" rồi bấm Mở camera; đóng ứng dụng khác đang dùng camera |
| Quẹt thẻ chậm | OCR chạy bằng CPU, mỗi ảnh có thể mất vài giây. Giảm `SCAN_FRAMES` nếu cần |
| Thẻ báo "đang ở trong bãi" dù xe đã đi | Lượt cũ chưa đóng: đóng bằng câu SQL ở trên |
| Cổng ra luôn chặn xe | Biển lúc vào nhập sai hoặc camera lệch góc: xem ảnh hai bên, nhập lại số hoặc cho ra kèm lý do |

## Giao thức với Arduino
**MỘT Arduino, MỘT cổng COM, hai đầu đọc.** Serial 9600 baud, mỗi dòng kết thúc bằng `\n`:

| Dòng | Ý nghĩa |
|---|---|
| `IN:AB1992CA` | Thẻ quẹt ở đầu đọc **cổng vào** (UID dạng HEX) |
| `OUT:DB2B11CA` | Thẻ quẹt ở đầu đọc **cổng ra** |
| `STATUS:IN=1,OUT=0` | Tình trạng từng đầu đọc (`1` = hoạt động, `0` = không nói chuyện được với module). Gửi lúc khởi động và mỗi ~2 giây; cũng là "nhịp tim" để phát hiện Arduino treo |
| `# ...` | Chú thích / log, bị bỏ qua |
| `LCDIN:dòng 1\|dòng 2` | **Chiều ngược lại (máy tính -> Arduino)**: hiển thị lên LCD **cổng vào**. Mỗi dòng tối đa 16 ký tự ASCII không dấu. Arduino không có LCD đó hoặc còn firmware cũ thì bỏ qua |
| `LCDOUT:dòng 1\|dòng 2` | Như trên nhưng cho LCD **cổng ra** |
| `LCD:dòng 1\|dòng 2` | Lệnh cũ, Arduino coi như `LCDIN:` (giữ lại cho tương thích) |
| `SERVOIN:OPEN` / `SERVOOUT:OPEN` | Mở servo **cổng vào** / **cổng ra**, giữ thời gian mặc định (3 giây) rồi Arduino **tự đóng** |
| `SERVOIN:OPEN:3000` | Như trên nhưng giữ 3000 ms (Arduino kẹp trong khoảng 500..30000 ms). Python gửi dạng này theo `SERVO_OPEN_SECONDS` |
| `SERVOIN:CLOSE` / `SERVOOUT:CLOSE` | Đóng ngay (dự phòng) |

Hướng đi do **tiền tố** (`IN:` / `OUT:`) quyết định. Dòng UID trần không có tiền tố (firmware cũ) bị coi là sai định dạng và báo lỗi trên thanh tình trạng, chương trình không đoán cổng.

Sketch mẫu `arduino/dual_rfid/dual_rfid.ino` dùng hai module **RC522** (thư viện MFRC522), đấu dây và chân SS ghi ngay đầu file. Đổi baud thì sửa `RFID_BAUD` trong `.env` và `BAUD_RATE` trong sketch.

## Hai màn LCD 1602 I2C (tùy chọn: một ở cổng vào, một ở cổng ra)
Hai màn LCD 1602 có **module I2C** (chip PCF8574) gắn vào chính Arduino đó. Không gắn màn nào thì chương trình vẫn chạy bình thường; gắn một trong hai màn cũng được (màn vắng mặt bị bỏ qua, màn còn lại vẫn chạy).

**Mỗi LCD một bus I2C riêng, dùng I2C phần mềm (bit-bang)** nên cắm vào chân analog tùy ý, không cần thư viện `Wire` hay `LiquidCrystal_I2C`:

| LCD (module I2C) | LCD cổng VÀO | LCD cổng RA |
|---|---|---|
| GND | GND | GND |
| VCC | **5V** | **5V** |
| SDA | **A0** | **A2** |
| SCL | **A1** | **A3** |

Tất cả GND nối chung. LCD cần 5V, **không** nối vào ray 3.3V của hai module RC522. Muốn đổi chân thì sửa 4 hằng số `PIN_LCD_*` ở đầu `dual_rfid.ino` rồi nạp lại. Không cần cài thêm thư viện nào cho LCD (chỉ còn **MFRC522** cho RFID).

Vì hai LCD nằm trên hai bus tách biệt nên **được trùng địa chỉ I2C** và **không cần hàn chân A0** trên module. Sketch tự dò địa chỉ `0x27` (chip PCF8574) rồi `0x3F` (chip PCF8574A) trên từng bus; muốn cố định địa chỉ thì sửa mảng `LCD_ADDRS`.

**Nội dung hiển thị** (LCD 1602 không có chữ có dấu nên viết không dấu; `hardware/rfid.py: lcd_text` tự bỏ dấu và cắt còn 16 ký tự):

| Tình huống | Dòng 1 | Dòng 2 |
|---|---|---|
| **Cổng vào** — sẵn sàng / nhân viên bấm Hủy | `CONG VAO` | `MOI QUET THE` |
| Vừa quẹt thẻ, đang quét ảnh (cả hai cổng) | `DANG KIEM TRA` | `VUI LONG CHO` |
| **Không đọc đủ 5 số (xe lệch vị trí)** (cả hai cổng) | `XE LECH VI TRI` | `HAY CHINH XE` |
| Hòa phiếu, chờ nhân viên — vào | `CHO NHAN VIEN` | `XAC NHAN BIEN SO` |
| Lưu xe vào thành công | `XE VAO OK` | `BIEN SO 25888` |
| Thẻ chưa đăng ký — vào / ra | `THE CHUA DANG KY` | `KHONG CHO VAO` / `KHONG CHO RA` |
| Thẻ đang ở trong bãi (cổng vào) | `THE DA VAO BAI` | `KHONG CHO VAO` |
| **Cổng ra** — sẵn sàng | `CONG RA` | `MOI QUET THE` |
| Biển khớp, cho ra (hoặc nhân viên duyệt) | `XE RA OK` | `TIEN 5.000 D` |
| Hòa phiếu, chờ nhân viên — ra | `CHO NHAN VIEN` | `KIEM TRA BIEN SO` |
| Lệch 1 số | `BIEN LECH 1 SO` | `CHO NHAN VIEN` |
| Lệch từ 2 số (không khớp) | `BIEN KHONG KHOP` | `GOI NHAN VIEN` |
| Nhân viên từ chối cho ra (giữ đến lần quẹt kế tiếp) | `XE CHUA DUOC RA` | `GOI NHAN VIEN` |
| Thẻ chưa có lượt vào (cổng ra) | `THE CHUA VAO BAI` | `KHONG CHO RA` |
| Lượt gửi xe đã bị đóng trước khi chốt | `LUOT DA DONG` | `GOI NHAN VIEN` |
| Lỗi hệ thống (VD mất SQL Server) | `LOI HE THONG` | `GOI NHAN VIEN` |
| Quẹt thẻ nhưng camera chưa có hình (cả hai cổng) | `LOI CAMERA` | `GOI NHAN VIEN` |
| Quẹt thẻ khi OCR chưa nạp xong (cả hai cổng) | `DANG KHOI DONG` | `VUI LONG CHO` |

**Tự quay về trạng thái sẵn sàng:** sau `LCD_IDLE_SECONDS` giây (mặc định 5), LCD về `CONG VAO` / `CONG RA` + `MOI QUET THE` với các thông báo đã xong việc: `XE VAO OK`, `XE RA OK`, thẻ chưa đăng ký, thẻ đã vào bãi, thẻ chưa vào bãi. Các thông báo cần nhân viên (`XE LECH VI TRI`, `CHO NHAN VIEN`, `BIEN LECH 1 SO`, `BIEN KHONG KHOP`, `XE CHUA DUOC RA`, `LUOT DA DONG`, `LOI HE THONG`, `LOI CAMERA`) được giữ nguyên đến khi nhân viên xử lý hoặc có lần quẹt thẻ kế tiếp. Lần quẹt bị bỏ qua vì đang xử lý hoặc đang chờ nhân viên không làm đổi LCD.

Số tiền hiện đủ trong 16 cột; nếu quá dài thì LCD báo `XEM TREN MAY` thay vì cắt cụt thành số sai. Cổng vào còn có dải đỏ "BIỂN SỐ LỆCH VỊ TRÍ" trên cửa sổ chương trình, hiện cùng lúc với dòng `XE LECH VI TRI` trên LCD. Nội dung LCD sửa ở các thuộc tính `LCD_*` đầu lớp `EntryApp` (`ui/entry_app.py`) và `ExitApp` (`ui/exit_app.py`); phần dùng chung ở đầu `ui/base_gate_app.py`.

**LCD không lên chữ:** mở Serial Monitor (9600), sẽ thấy `# LCD VAO: dia chi 0x27` và `# LCD RA: dia chi 0x27` nếu tìm thấy; `# LCD ...: khong tim thay` thì kiểm tra dây SDA/SCL (VÀO: A0/A1, RA: A2/A3), VCC 5V, GND. Có đèn nền mà không thấy chữ: vặn biến trở xanh ở mặt sau module I2C để chỉnh độ tương phản. Dây SDA/SCL nên ngắn (dưới ~30 cm); module I2C đã có điện trở kéo lên sẵn nên không cần thêm.

## Hai servo thanh chắn (tùy chọn: một ở cổng vào, một ở cổng ra)
Mỗi cổng một servo (SG90 / MG90S...) gắn vào chính Arduino đó. **Khi nào mở:** chỉ khi xe được chấp nhận, tức là cổng vào lưu xe thành công (tự động hoặc nhân viên bấm *Lưu xe vào*), cổng ra đóng lượt thành công (biển khớp, hoặc nhân viên bấm *Cho xe ra*). **Không mở** khi thẻ chưa đăng ký, thẻ đã ở trong bãi / chưa vào bãi, đang chờ nhân viên, biển không khớp, nhân viên từ chối hoặc có lỗi hệ thống.

**Đấu dây:**

| Servo | Dây tín hiệu (cam/vàng) | Dây đỏ | Dây nâu/đen |
|---|---|---|---|
| **Cổng VÀO** | **D6** | 5V | GND |
| **Cổng RA** | **D7** | 5V | GND |

Hai chân D6/D7 không trùng SPI (D8..D13), LCD (A0..A3), còi (D4) hay Serial. **Nguồn:** servo giật dòng lớn khi chạy nên nên cấp 5V riêng (pin / adapter 5V 2A) cho hai servo và **nối chung GND** với Arduino; cấp thẳng từ chân 5V của Arduino (qua USB) dễ làm Arduino reset, LCD nháy hoặc RC522 mất tín hiệu. Thư viện `Servo` có sẵn trong Arduino IDE; nạp lại `dual_rfid.ino`.

**Chỉnh cho khớp thanh chắn thật** (đầu `dual_rfid.ino`): `SERVO_CLOSED_ANGLE` (mặc định 0°) và `SERVO_OPEN_ANGLE` (mặc định 90°; đảo hai giá trị nếu servo quay ngược), `SERVO_HOLD_MS` (thời gian mở mặc định). Thời gian giữ mở thực tế do `SERVO_OPEN_SECONDS` trong `.env` quyết định.

**An toàn:** Arduino tự đóng bằng đồng hồ của chính nó nên máy tính treo hay rút cáp USB thì thanh chắn cũng không kẹt ở trạng thái mở; khởi động / reset luôn về vị trí đóng. Quẹt thẻ liên tiếp khi thanh chắn đang mở thì gia hạn thời gian, không đóng giữa chừng. Việc mở servo không bao giờ làm hỏng việc xử lý thẻ (mất kết nối, chưa gắn servo hay `SERVO_ENABLED=0` đều chỉ bỏ qua lệnh). Mở Serial Monitor (9600) sẽ thấy `# dual_rfid san sang (servo: vao=D6, ra=D7, coi=D4)`; gõ thử `SERVOIN:OPEN` hoặc `SERVOOUT:OPEN` để kiểm tra từng servo.

## Còi bíp (tùy chọn: MỘT còi dùng chung cho cả hai cổng)
Mỗi lần quẹt thẻ ở **bất kỳ cổng nào** (vào hoặc ra), còi kêu **một tiếng bíp ngắn** (mặc định 2000 Hz, 120 ms) để người quẹt biết thẻ đã được đọc. Còi do **Arduino tự điều khiển** ngay khi đọc được thẻ, không cần chờ máy tính, nên vẫn kêu khi chương trình Python chưa chạy; bíp kêu cho mọi thẻ đọc được, kể cả thẻ chưa đăng ký. Không có lệnh nào từ máy tính để điều khiển còi, và không có biến cấu hình trong `.env`.

**Đấu dây:**

| Còi | Chân Arduino |
|---|---|
| Chân dương (+) | **A5** |
| Chân âm (-) | GND |

D4 không trùng SPI (D8..D13), servo (D6/D7), LCD (A0..A3) hay Serial. Sketch dùng `tone()` nên chạy được **cả còi active lẫn passive** (không cần biết loại còi). Còi nhỏ (dưới khoảng 20 mA) nối thẳng chân D4; còi công suất lớn thì qua transistor. Đổi chân / tần số / độ dài tiếng bíp ở `PIN_BUZZER`, `BUZZER_FREQ_HZ`, `BUZZER_BEEP_MS` đầu `dual_rfid.ino`, rồi nạp lại. Nếu dùng còi active mà tiếng nghe rè, thử đổi `tone(...)` trong hàm `beep()` thành `digitalWrite(PIN_BUZZER, HIGH)` rồi `LOW` sau một khoảng ngắn.

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
arduino/dual_rfid/           dual_rfid.ino      firmware: MỘT Arduino đọc HAI module RFID (giao thức ở trên)
main.py                      python main.py [--gate in|out|both]   (mặc định both: một cửa sổ)
core/                        plate_utils.py     xử lý ảnh + chuỗi biển
                             recognizer.py      OCR 1 khung (EasyOCR)
                             plate_voting.py    bỏ phiếu giữa nhiều lần đọc
                             scanner.py         quét nhiều khung + bỏ phiếu
                             plate_match.py     so khớp 5 số vào / ra
hardware/                    rfid.py (Serial: một Arduino, hai đầu đọc, báo tình trạng, gửi lệnh LCD + servo), camera.py (đọc camera ở luồng nền, báo mất hình)
storage/                     database.py (SQL Server), schema.sql, models.py, errors.py
services/                    gate_service.py    phần chung (quét, lưu ảnh)
                             entry_service.py   nghiệp vụ cổng vào
                             exit_service.py    nghiệp vụ cổng ra
                             pricing.py         tính tiền
setup.bat, run*.bat          cài đặt một lần / các cách chạy chương trình (Windows)
ui/                          base_gate_app.py   giao diện chung
                             entry_app.py       cổng vào
                             exit_app.py        cổng ra (ảnh vào cạnh ảnh ra, đối chiếu)
                             dual_app.py        một cửa sổ chứa cả hai cổng + lịch sử dùng chung
                             device_status.py   thanh tình trạng thiết bị (cảnh báo đỏ khi mất kết nối)
tests/                       pytest
```

## Kiểm thử
```
python -m pip install -r requirements-dev.txt
python -m pytest
```
Test dùng camera, OCR và CSDL giả nên chạy được mà không cần phần cứng hay SQL Server. Test giao diện tự bỏ qua nếu máy không có màn hình.

## Nâng cấp từ bản cũ
**Từ hai Arduino lên một Arduino:** (1) nạp `arduino/dual_rfid/dual_rfid.ino` cho board còn dùng và đấu hai module RC522 vào cùng board (xem đầu file sketch); (2) trong `.env` đặt `RFID_PORT=` đúng cổng COM của board đó; (3) **xóa dòng `RFID_PORT`** khỏi `.env.in` và `.env.out` (còn sót hai giá trị khác nhau thì chương trình báo lỗi ngay khi khởi động); (4) chạy `run.bat`. Database và danh sách thẻ giữ nguyên. File `run-2-cua-so.bat` đã bị bỏ vì hai tiến trình không thể cùng mở một cổng COM.

**Giao diện một cửa sổ:** không cần đổi cấu hình hay database. `python main.py` giờ mở cả hai cổng trong một cửa sổ; muốn giữ cách cũ thì chạy `python main.py --gate in` và `--gate out` như trước.

**Sao lưu database trước** khi chạy lần đầu, vì chương trình tự sửa cấu trúc bảng `access_log`.

**File cấu hình:** `RFID_PORT` và `CAMERA_INDEX` trong `.env` cũ giờ phải chuyển sang `.env.in` (cổng vào) và `.env.out` (cổng ra); nếu không, hai cổng dùng chung một cổng COM/camera và tranh nhau (chương trình in cảnh báo khi thiếu file). Chú thích cùng dòng (`KEY=giá trị  # ghi chú`) được hỗ trợ.

`init_schema()` tự nâng cấp bảng `access_log` cũ (đổi tên `image_path` -> `image_in`, thêm cột mới, giữ nguyên dữ liệu). Dữ liệu cũ không bị kiểm tra lại ràng buộc 5 số.
Nếu bảng cũ có thẻ bị trùng lượt đang mở, chỉ mục chặn trùng sẽ chưa được tạo (có cảnh báo); hãy đóng bớt lượt rồi khởi động lại.
