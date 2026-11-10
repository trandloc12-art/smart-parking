# smart-parking

Bãi đỗ xe thông minh bằng Python: quẹt thẻ RFID (Arduino qua cổng COM) -> chụp camera -> nhận diện biển số -> lưu SQL Server.
Hệ thống có **2 cổng trên cùng một máy**: **cổng vào** và **cổng ra**. Phần cứng gồm **MỘT Arduino** (một cổng COM) nối **hai đầu đọc RFID**, và mỗi cổng một camera.
Cả hai cổng hiện trong **MỘT cửa sổ** (hai khung camera cạnh nhau: CỔNG VÀO | CỔNG RA, lịch sử dùng chung ở dưới). Ngay trên cùng cửa sổ có **thanh tình trạng thiết bị**: thiết bị nào mất kết nối (Arduino, từng đầu đọc, từng camera, SQL Server) sẽ hiện dải cảnh báo đỏ nêu đúng tên thiết bị.
Arduino cần nạp sketch **`arduino/dual_rfid/dual_rfid.ino`** trong repo này (xem mục *Giao thức với Arduino*).
Tùy chọn: gắn thêm **hai màn LCD 1602 I2C** (một ở cổng vào, một ở cổng ra) để báo cho tài xế (VD "XE LECH VI TRI" khi không đọc đủ 5 số, "XE RA OK - TIEN 5.000 D") — xem mục *Hai màn LCD 1602 I2C*.
Tùy chọn: gắn **một còi bíp** dùng chung, mỗi lần quẹt thẻ (cổng vào hoặc cổng ra) còi kêu một tiếng — xem mục *Còi bíp*.
Tùy chọn: gắn **một đèn LED** ở cổng vào: xe đi qua hẳn thanh chắn thì đèn sáng 20 giây rồi tự tắt — xem mục *Đèn LED báo xe vào*.
Bãi có số chỗ (slot) giới hạn (`PARKING_CAPACITY`, mặc định **3**): LCD hiện số chỗ còn trống, **đủ chỗ thì cổng vào không nhận quẹt thẻ** — xem mục *Số chỗ đỗ xe*.
Tùy chọn: gắn **hai servo thanh chắn** (một ở cổng vào, một ở cổng ra): quẹt thẻ thành công thì servo của cổng đó tự mở rồi tự đóng lại — xem mục *Hai servo thanh chắn*.
Tùy chọn: gắn **bốn cảm biến hồng ngoại** (mỗi cổng hai cái, trước và sau thanh chắn) để biết xe đã đi qua thanh chắn chưa: **quẹt thẻ xong, xe phải đi qua thì phiên mới được lưu vào SQL Server; xe không đi qua thì phiên quẹt thẻ bị hủy** (không lưu gì cả), xe qua rồi thì hạ thanh chắn ngay — xem mục *Cảm biến hồng ngoại*.

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
| `PARKING_CAPACITY` | `3` | Số chỗ (slot) của bãi. LCD hiện số chỗ còn trống; đủ chỗ thì cổng vào không nhận quẹt thẻ |
| `AUTO_SAVE` | `1` | Cổng vào: `1` tự lưu khi chốt được 5 số, `0` luôn chờ xác nhận |
| `PRICE_PER_BLOCK`, `BLOCK_MINUTES` | `5000`, `60` | Giá một khối và độ dài khối |
| `SCAN_FRAMES`, `SCAN_INTERVAL`, `VOTE_MIN` | `5`, `0.25`, `2` | Số ảnh quét, giây giữa hai ảnh, số phiếu tối thiểu (`1..SCAN_FRAMES`) |
| `LCD_IDLE_SECONDS` | `5` | Số giây sau đó LCD tự về màn hình chờ (`CON TRONG: 2/3`) khi đã xong việc (xe vào/ra OK, thẻ bị từ chối). `0` = giữ thông báo đến lần quẹt sau. Thông báo cần nhân viên xử lý không tự biến mất |
| `VIEW_W`, `VIEW_H` | `420`, `315` | Kích thước khung camera (mỗi cửa sổ rộng khoảng 900 px) |
| `SERVO_ENABLED` | `1` | `1` = quẹt thẻ thành công thì mở servo thanh chắn; `0` = chưa gắn servo thì tắt đi (không gửi lệnh nào) |
| `SERVO_OPEN_SECONDS` | `3` | Số giây đếm ngược rồi Arduino tự đóng thanh chắn, **tính từ lúc xe rời cảm biến trước** (xe chưa tới cảm biến trước thì tính từ lúc mở); cảm biến sau còn sáng thì không đóng (`0.5`..`30`) |
| `SERVO_CLOSED_ANGLE`, `SERVO_OPEN_ANGLE` | `0`, `90` | **Góc ban đầu** (thanh chắn hạ) và góc thanh chắn nâng của servo, `0`..`180` độ. Gửi cho Arduino mỗi lần nó khởi động. Servo quay ngược thì đảo hai giá trị; hai cổng gắn khác nhau thì đặt riêng trong `.env.in` / `.env.out` |
| `BUZZER_FREQ_HZ` | `2000` | Cao độ tiếng còi, `100`..`8000` Hz, trong `.env` (xem *Còi bíp*). Còi active không đổi được tần số |
| `BUZZER_BEEP_MS` | `120` | Độ dài một tiếng bíp, `20`..`2000` ms, trong `.env` |
| `STUCK_WARN_SECONDS` | `10` | Xe **đã quẹt thẻ** mà **đứng yên** ở cảm biến trước / sau quá ngần này giây thì **còi kêu lặp** tới khi xe nhúc nhích (`1`..`600`; `0` = tắt), trong `.env` (xem *Còi bíp*). Gửi cho Arduino mỗi khi nó khởi động |
| `IR_ENABLED` | `1` | `1` = quẹt thẻ xong **chờ cảm biến xác nhận xe đã đi qua thanh chắn rồi mới lưu** (không qua thì hủy phiên); `0` = chưa gắn cảm biến thì tắt đi (lưu ngay khi quẹt thẻ như bản cũ, bỏ qua `PASS` / `NOPASS` từ Arduino). Chỉ chờ khi `SERVO_ENABLED=1` và có Arduino để gửi lệnh mở thanh chắn |
| `IR_PASS_TIMEOUT_SECONDS` | `3` | **Ân hạn** (`0.5`..`30` giây) tính từ lúc **cảm biến trước mất tín hiệu** mà **cảm biến sau** chưa từng thấy xe thì xe được coi là rời đi và **hủy phiên quẹt thẻ**. Cảm biến trước còn tín hiệu (xe đang đứng chờ) thì **không hủy**. Đặt `0.5` để hủy gần như ngay khi cảm biến trước mất tín hiệu. Hai cổng khác nhau thì đặt riêng trong `.env.in` / `.env.out` |
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
| Bấm "Test servo" thanh chắn không nhúc nhích / quay sai góc | Xem dòng trạng thái: `KHÔNG gửi được lệnh` = Arduino chưa kết nối; `SERVO_ENABLED=0` = servo đang bị tắt. Nếu lệnh đã gửi mà servo không động: kiểm tra dây tín hiệu (D6 cổng vào, D7 cổng ra) và nguồn 5V riêng + nối chung GND. Quay sai chiều hoặc không khớp thanh chắn: chỉnh `SERVO_CLOSED_ANGLE` / `SERVO_OPEN_ANGLE` (đảo hai giá trị nếu ngược) rồi chạy lại chương trình |
| Quẹt thẻ chậm | OCR chạy bằng CPU, mỗi ảnh có thể mất vài giây. Giảm `SCAN_FRAMES` nếu cần |
| Cổng vào luôn báo "BÃI ĐÃ ĐẦY" dù bãi trống | Còn lượt cũ chưa đóng (xe đã đi mà thẻ chưa quẹt ra) chiếm chỗ: đóng bằng câu SQL ở dưới, hoặc tăng `PARKING_CAPACITY` |
| Thẻ báo "đang ở trong bãi" dù xe đã đi | Lượt cũ chưa đóng: đóng bằng câu SQL ở trên |
| Cổng ra luôn chặn xe | Biển lúc vào nhập sai hoặc camera lệch góc: xem ảnh hai bên, nhập lại số hoặc cho ra kèm lý do |
| Quẹt thẻ xong luôn bị "ĐÃ HỦY phiên quẹt thẻ" (LCD `HAY QUET LAI THE`), xe không được lưu | Cảm biến hồng ngoại chưa gắn / sai dây / sai mức tín hiệu (`IR_ACTIVE_LOW`), xe không chắn đủ hai cảm biến theo thứ tự trước -> sau, hoặc xe là xe ngắn: cảm biến trước nhả ra lâu hơn `IR_PASS_TIMEOUT_SECONDS` rồi cảm biến sau mới thấy xe (tăng giá trị này). Chưa gắn cảm biến thì đặt `IR_ENABLED=0` |
| Thanh chắn không hạ xuống dù xe đã đi qua | Cảm biến sau còn bị chắn (lệch hướng, vật chắn cố định, cảm biến hỏng/sai `IR_ACTIVE_LOW`): **theo thiết kế thanh chắn sẽ không hạ khi cảm biến sau còn sáng**, không có giới hạn thời gian. Dời vật chắn đi hoặc kiểm tra cảm biến sau; có thể gõ `SERVOIN:CLOSE` / `SERVOOUT:CLOSE` trong Serial Monitor để hạ thủ công |

## Giao thức với Arduino
**MỘT Arduino, MỘT cổng COM, hai đầu đọc.** Serial 9600 baud, mỗi dòng kết thúc bằng `\n`:

| Dòng | Ý nghĩa |
|---|---|
| `IN:AB1992CA` | Thẻ quẹt ở đầu đọc **cổng vào** (UID dạng HEX) |
| `OUT:DB2B11CA` | Thẻ quẹt ở đầu đọc **cổng ra** |
| `STATUS:IN=1,OUT=0` | Tình trạng từng đầu đọc (`1` = hoạt động, `0` = không nói chuyện được với module). Gửi lúc khởi động và mỗi ~2 giây; cũng là "nhịp tim" để phát hiện Arduino treo |
| `PASS:IN` / `PASS:OUT` | Xe đã **đi qua hẳn** thanh chắn cổng vào / cổng ra (cảm biến hồng ngoại); Arduino đã hạ thanh chắn. Máy tính chỉ **lưu** phiên quẹt thẻ khi nhận dòng này. `PASS:IN` còn làm **đèn LED cổng vào sáng 20 giây** (Arduino tự làm) |
| `NOPASS:IN` / `NOPASS:OUT` | Xe **không đi qua** (xe rời đi): cảm biến trước đã thấy xe rồi mất tín hiệu quá `IR_PASS_TIMEOUT_SECONDS` mà cảm biến sau chưa thấy xe, hoặc hết giờ mở thanh chắn mà xe chưa tới cảm biến trước; Arduino đã hạ thanh chắn. Máy tính **hủy** phiên quẹt thẻ (không lưu gì) |
| `# ...` | Chú thích / log, bị bỏ qua |
| `LCDIN:dòng 1\|dòng 2` | **Chiều ngược lại (máy tính -> Arduino)**: hiển thị lên LCD **cổng vào**. Mỗi dòng tối đa 16 ký tự ASCII không dấu. Arduino không có LCD đó hoặc còn firmware cũ thì bỏ qua |
| `LCDOUT:dòng 1\|dòng 2` | Như trên nhưng cho LCD **cổng ra** |
| `LCD:dòng 1\|dòng 2` | Lệnh cũ, Arduino coi như `LCDIN:` (giữ lại cho tương thích) |
| `SERVOIN:OPEN` / `SERVOOUT:OPEN` | Mở servo **cổng vào** / **cổng ra**, giữ thời gian mặc định (3 giây) rồi Arduino **tự đóng** |
| `SERVOIN:OPEN:3000` | Như trên nhưng giữ 3000 ms (Arduino kẹp trong khoảng 500..30000 ms). Python gửi dạng này theo `SERVO_OPEN_SECONDS` |
| `SERVOIN:OPEN:3000:3000` | Như trên, thêm **ân hạn khi xe rời đi** (ms, kẹp 500..30000): cảm biến trước mất tín hiệu quá ngần này mà cảm biến sau chưa thấy xe thì Arduino hạ thanh chắn và gửi `NOPASS`. Python gửi dạng này theo `SERVO_OPEN_SECONDS` và `IR_PASS_TIMEOUT_SECONDS` khi chờ xe qua |
| `BUZZER:TONE:2000:120` | Đặt **âm thanh còi**: tần số (`100`..`8000` Hz) rồi độ dài một tiếng bíp (`20`..`2000` ms). Lệnh sai định dạng hoặc ngoài khoảng bị bỏ qua cả lệnh. Python gửi lệnh này theo `BUZZER_FREQ_HZ` / `BUZZER_BEEP_MS` mỗi khi Arduino khởi động |
| `BUZZER:BEEP` | Kêu thử một tiếng bíp với âm thanh hiện tại |
| `STUCK:10000` | Đặt **ngưỡng cảnh báo xe dừng quá lâu** (ms, `1000`..`600000`; `0` = tắt): thanh chắn đang mở (đã quẹt thẻ) mà xe đứng yên ở cảm biến trước / sau quá ngưỡng này thì còi kêu lặp. Lệnh sai định dạng hoặc ngoài khoảng bị bỏ qua cả lệnh. Python gửi lệnh này theo `STUCK_WARN_SECONDS` mỗi khi Arduino khởi động |
| `SERVOIN:CLOSE` / `SERVOOUT:CLOSE` | Đóng ngay (dự phòng) |
| `SERVOIN:ANGLE:0:90` | Đặt **góc đóng (vị trí ban đầu)** rồi **góc mở** (`0`..`180` độ) cho servo cổng vào (`SERVOOUT:ANGLE:...` cho cổng ra); servo chạy tới góc mới ngay. Lệnh sai định dạng hoặc ngoài `0`..`180` bị bỏ qua cả lệnh. Python gửi lệnh này theo `SERVO_CLOSED_ANGLE` / `SERVO_OPEN_ANGLE` mỗi khi Arduino khởi động |

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
| **Cổng vào** — màn hình chờ, còn chỗ / nhân viên bấm Hủy | `CONG VAO` | `CON TRONG: 2/3` |
| **Cổng vào** — bãi đã đủ chỗ, không nhận quẹt thẻ | `BAI DA DAY` | `HET CHO` |
| Vừa quẹt thẻ, đang quét ảnh (cả hai cổng) | `DANG KIEM TRA` | `VUI LONG CHO` |
| **Không đọc đủ 5 số (xe lệch vị trí)** (cả hai cổng) | `XE LECH VI TRI` | `HAY CHINH XE` |
| Hòa phiếu, chờ nhân viên — vào | `CHO NHAN VIEN` | `XAC NHAN BIEN SO` |
| Lưu xe vào thành công | `XE VAO OK` | `BIEN SO 25888` |
| Thẻ chưa đăng ký — vào / ra | `THE CHUA DANG KY` | `KHONG CHO VAO` / `KHONG CHO RA` |
| Thẻ đang ở trong bãi (cổng vào) | `THE DA VAO BAI` | `KHONG CHO VAO` |
| **Cổng ra** — màn hình chờ | `CONG RA` | `CON TRONG: 2/3` |
| Biển khớp, cho ra (hoặc nhân viên duyệt) | `XE RA OK` | `TIEN 5.000 D` |
| Hòa phiếu, chờ nhân viên — ra | `CHO NHAN VIEN` | `KIEM TRA BIEN SO` |
| Lệch 1 số | `BIEN LECH 1 SO` | `CHO NHAN VIEN` |
| Lệch từ 2 số (không khớp) | `BIEN KHONG KHOP` | `GOI NHAN VIEN` |
| Nhân viên từ chối cho ra (giữ đến lần quẹt kế tiếp) | `XE CHUA DUOC RA` | `GOI NHAN VIEN` |
| Thẻ chưa có lượt vào (cổng ra) | `THE CHUA VAO BAI` | `KHONG CHO RA` |
| Lượt gửi xe đã bị đóng trước khi chốt | `LUOT DA DONG` | `GOI NHAN VIEN` |
| Lỗi hệ thống (VD mất SQL Server) | `LOI HE THONG` | `GOI NHAN VIEN` |
| Quẹt thẻ nhưng camera chưa có hình (cả hai cổng) | `LOI CAMERA` | `GOI NHAN VIEN` |
| **Chờ xe đi qua** thanh chắn (đã chốt biển, CHƯA lưu) — vào / ra | `MOI XE VAO` / `MOI XE RA` | `QUA THANH CHAN` |
| **Xe không đi qua**, phiên quẹt thẻ bị hủy (hiện 2 giây rồi về màn hình chờ) — vào / ra | `XE CHUA VAO BAI` / `XE CHUA RA BAI` | `HAY QUET LAI THE` |
| Quẹt thẻ khi OCR chưa nạp xong (cả hai cổng) | `DANG KHOI DONG` | `VUI LONG CHO` |

**Tự quay về trạng thái sẵn sàng:** sau `LCD_IDLE_SECONDS` giây (mặc định 5), LCD về màn hình chờ (`CONG VAO` / `CONG RA` + `CON TRONG: x/y`, hoặc `BAI DA DAY` / `HET CHO` ở cổng vào khi hết chỗ; chưa biết số chỗ thì tạm hiện `MOI QUET THE`) với các thông báo đã xong việc: `XE VAO OK`, `XE RA OK`, thẻ chưa đăng ký, thẻ đã vào bãi, thẻ chưa vào bãi. Thông báo **hủy phiên** (`HAY QUET LAI THE`) chỉ hiện **2 giây** rồi LCD về màn hình chờ. Các thông báo cần nhân viên (`XE LECH VI TRI`, `CHO NHAN VIEN`, `BIEN LECH 1 SO`, `BIEN KHONG KHOP`, `XE CHUA DUOC RA`, `LUOT DA DONG`, `LOI HE THONG`, `LOI CAMERA`) được giữ nguyên đến khi nhân viên xử lý hoặc có lần quẹt thẻ kế tiếp. Lần quẹt bị bỏ qua vì đang xử lý hoặc đang chờ nhân viên không làm đổi LCD. **Ngoại lệ ở cả cổng vào và cổng ra:** khi không đọc đủ 5 số (không có số nào hoặc chỉ đọc được 1..4 số, LCD `XE LECH VI TRI`), tài xế chỉ cần **quẹt lại đúng thẻ đó** là hệ thống quét lại, nhân viên không phải bấm *Từ chối / Hủy* trên máy (chưa ghi gì nên bỏ ca cũ an toàn). Hòa phiếu, `AUTO_SAVE=0` chờ xác nhận, lệch biển hoặc không khớp vẫn phải do nhân viên xử lý, và thẻ khác quẹt vào lúc đó vẫn bị bỏ qua.

Số tiền hiện đủ trong 16 cột; nếu quá dài thì LCD báo `XEM TREN MAY` thay vì cắt cụt thành số sai. Cổng vào còn có dải đỏ "BIỂN SỐ LỆCH VỊ TRÍ" trên cửa sổ chương trình, hiện cùng lúc với dòng `XE LECH VI TRI` trên LCD. Nội dung LCD sửa ở các thuộc tính `LCD_*` đầu lớp `EntryApp` (`ui/entry_app.py`) và `ExitApp` (`ui/exit_app.py`); phần dùng chung ở đầu `ui/base_gate_app.py`.

**LCD không lên chữ:** mở Serial Monitor (9600), sẽ thấy `# LCD VAO: dia chi 0x27` và `# LCD RA: dia chi 0x27` nếu tìm thấy; `# LCD ...: khong tim thay` thì kiểm tra dây SDA/SCL (VÀO: A0/A1, RA: A2/A3), VCC 5V, GND. Có đèn nền mà không thấy chữ: vặn biến trở xanh ở mặt sau module I2C để chỉnh độ tương phản. Dây SDA/SCL nên ngắn (dưới ~30 cm); module I2C đã có điện trở kéo lên sẵn nên không cần thêm.

## Hai servo thanh chắn (tùy chọn: một ở cổng vào, một ở cổng ra)
Mỗi cổng một servo (SG90 / MG90S...) gắn vào chính Arduino đó. **Khi nào mở:** chỉ khi xe được chấp nhận, tức là cổng vào chốt được biển (tự động hoặc nhân viên bấm *Lưu xe vào*), cổng ra biển khớp (hoặc nhân viên bấm *Cho xe ra*). Có cảm biến hồng ngoại (`IR_ENABLED=1`) thì **chỉ khi xe đi qua hẳn thanh chắn phiên mới được lưu / đóng lượt**; không có thì lưu ngay như bản cũ. **Không mở** khi thẻ chưa đăng ký, thẻ đã ở trong bãi / chưa vào bãi, đang chờ nhân viên, biển không khớp, nhân viên từ chối hoặc có lỗi hệ thống.

**Đấu dây:**

| Servo | Dây tín hiệu (cam/vàng) | Dây đỏ | Dây nâu/đen |
|---|---|---|---|
| **Cổng VÀO** | **D6** | 5V | GND |
| **Cổng RA** | **D7** | 5V | GND |

Hai chân D6/D7 không trùng SPI (D8..D13), LCD (A0..A3), cảm biến hồng ngoại (D2..D5), còi (A5) hay Serial. **Nguồn:** servo giật dòng lớn khi chạy nên nên cấp 5V riêng (pin / adapter 5V 2A) cho hai servo và **nối chung GND** với Arduino; cấp thẳng từ chân 5V của Arduino (qua USB) dễ làm Arduino reset, LCD nháy hoặc RC522 mất tín hiệu. Thư viện `Servo` có sẵn trong Arduino IDE; nạp lại `dual_rfid.ino`.

**Góc ban đầu và góc mở** do `SERVO_CLOSED_ANGLE` (mặc định 0°, vị trí ban đầu = thanh chắn hạ) và `SERVO_OPEN_ANGLE` (mặc định 90°) trong `.env` quyết định (đảo hai giá trị nếu servo quay ngược; hai cổng khác nhau thì đặt riêng trong `.env.in` / `.env.out`). Chương trình gửi hai góc này cho Arduino (`SERVOIN:ANGLE:...`) ngay khi Arduino khởi động xong, và gửi lại nếu Arduino bị reset, nên **đổi góc chỉ cần sửa `.env` rồi chạy lại chương trình, không phải nạp lại sketch**. Lúc mới cấp điện, trước khi chương trình kịp gửi, servo ở góc mặc định trong sketch (`SERVO_CLOSED_ANGLE` / `SERVO_OPEN_ANGLE` đầu `dual_rfid.ino`, 0° / 90°), nên có thể thấy servo giật nhẹ một lần nếu `.env` đặt góc khác. `SERVO_HOLD_MS` trong sketch là thời gian mở mặc định; thời gian giữ mở thực tế do `SERVO_OPEN_SECONDS` quyết định.

**Nút "🔧 Test servo"** (mỗi cổng một nút, nằm cạnh nút *Thử với ảnh từ máy*): bấm để mở thanh chắn của cổng đó, rồi Arduino tự đóng sau `SERVO_OPEN_SECONDS` giây. Dùng để kiểm tra dây, nguồn và chỉnh góc mà không cần quẹt thẻ. Lần thử **không tạo lượt gửi xe, không đụng LCD và không ghi gì vào SQL Server** (kết quả cảm biến của lần thử bị bỏ qua). Nút bị khóa khi đang xử lý một lần quẹt thẻ hoặc đang chờ nhân viên xác nhận. Nút báo ngay trên dòng trạng thái nếu không gửi được: `SERVO_ENABLED=0` hoặc Arduino chưa kết nối.

**An toàn:** Arduino tự đóng bằng đồng hồ của chính nó nên máy tính treo hay rút cáp USB thì thanh chắn cũng không kẹt ở trạng thái mở; khởi động / reset luôn về vị trí đóng. Ngoại lệ có chủ ý: cảm biến sau còn sáng thì Arduino không đóng (xem *Đồng hồ đóng thanh chắn*). Quẹt thẻ liên tiếp khi thanh chắn đang mở thì gia hạn thời gian, không đóng giữa chừng. Việc mở servo không bao giờ làm hỏng việc xử lý thẻ (mất kết nối, chưa gắn servo hay `SERVO_ENABLED=0` đều chỉ bỏ qua lệnh). Mở Serial Monitor (9600) sẽ thấy `# dual_rfid san sang (servo: vao=D6, ra=D7, coi=A5, ir: vao=D2/D3, ra=D4/D5, led=A4)`; gõ thử `SERVOIN:OPEN` hoặc `SERVOOUT:OPEN` để kiểm tra từng servo (hoặc `SERVOIN:ANGLE:0:90` để đặt góc).

## Còi bíp (tùy chọn: MỘT còi dùng chung cho cả hai cổng)
Mỗi lần quẹt thẻ ở **bất kỳ cổng nào** (vào hoặc ra), còi kêu **một tiếng bíp ngắn** (mặc định 2000 Hz, 120 ms) để người quẹt biết thẻ đã được đọc. Còi do **Arduino tự điều khiển** ngay khi đọc được thẻ, không cần chờ máy tính, nên vẫn kêu khi chương trình Python chưa chạy; bíp kêu cho mọi thẻ đọc được, kể cả thẻ chưa đăng ký. Âm thanh của tiếng bíp (cao độ và độ dài) chỉnh bằng hai biến `BUZZER_FREQ_HZ` / `BUZZER_BEEP_MS` trong `.env` (xem *Chỉnh âm thanh còi* bên dưới); việc **kêu** vẫn do Arduino tự làm.

**Đấu dây:**

| Còi | Chân Arduino |
|---|---|
| Chân dương (+) | **A5** |
| Chân âm (-) | GND |

A5 không trùng SPI (D8..D13), servo (D6/D7), cảm biến hồng ngoại (D2..D5), LCD (A0..A3) hay Serial. Sketch dùng `tone()` nên chạy được **cả còi active lẫn passive** (không cần biết loại còi). Còi nhỏ (dưới khoảng 20 mA) nối thẳng chân A5; còi công suất lớn thì qua transistor. Đổi chân ở `PIN_BUZZER` đầu `dual_rfid.ino` rồi nạp lại; còn tần số / độ dài tiếng bíp chỉnh trong `.env`, **không cần nạp lại sketch** (hằng số `BUZZER_FREQ_HZ` / `BUZZER_BEEP_MS` trong sketch chỉ là giá trị mặc định khi chưa nhận được lệnh từ máy tính). Nếu dùng còi active mà tiếng nghe rè, thử đổi `tone(...)` trong hàm `beep()` thành `digitalWrite(PIN_BUZZER, HIGH)` rồi `LOW` sau một khoảng ngắn.

**Chỉnh âm thanh còi:** hai giá trị trong `.env` (dùng chung cho cả hai cổng, chương trình gửi cho Arduino bằng lệnh `BUZZER:TONE:<Hz>:<ms>` mỗi khi Arduino khởi động và gửi lại nếu Arduino bị reset, nên **đổi giá trị chỉ cần sửa `.env` rồi chạy lại chương trình**):

| Biến | Mặc định | Khoảng | Tác dụng |
|---|---|---|---|
| `BUZZER_FREQ_HZ` | `2000` | `100`..`8000` | **Cao độ.** Số càng cao tiếng càng thanh / chói, càng thấp càng trầm. Gợi ý: `1000` trầm, dịu; `2000` bíp thường; `3000`..`4000` thanh, vang to nhất với đa số còi passive (gần tần số cộng hưởng) |
| `BUZZER_BEEP_MS` | `120` | `20`..`2000` | **Độ dài** một tiếng bíp (mili giây). `60` ngắn gọn; `300` kéo dài rõ ràng |

Giá trị ngoài khoảng làm chương trình báo lỗi ngay khi khởi động. **Kêu thử không cần quẹt thẻ:** mở Serial Monitor (9600) gõ `BUZZER:BEEP` để nghe với âm thanh hiện tại; gõ `BUZZER:TONE:3000:200` để đổi thử tức thì (chỉ tới khi Arduino reset, muốn giữ lâu dài thì ghi vào `.env`). Lệnh sai định dạng hoặc ngoài khoảng bị bỏ qua cả lệnh.

**Giới hạn:** Arduino không chỉnh được **âm lượng** bằng `tone()`: còi **active** chỉ kêu một tần số cố định nên `BUZZER_FREQ_HZ` không đổi được tiếng (chỉ `BUZZER_BEEP_MS` có tác dụng); còi **passive** đổi được cao độ, và vì còi kêu to nhất ở gần tần số cộng hưởng nên chỉnh tần số cũng làm tiếng to hơn hoặc nhỏ đi phần nào. Muốn nhỏ hẳn thì mắc thêm điện trở nối tiếp (VD 100..470 ohm) hoặc biến trở với chân (+) của còi.

**Còi cảnh báo xe dừng quá lâu:** ngoài tiếng bíp khi quẹt thẻ, còi còn **kêu lặp liên tục** (mỗi 0,4 giây một tiếng bíp) khi một xe **đã quẹt thẻ** (thanh chắn đang mở) mà **đứng yên ở cảm biến trước hoặc cảm biến sau quá `STUCK_WARN_SECONDS` giây** (mặc định 10; `0` = tắt). Dùng chung một còi cho cả hai cổng, nên cổng nào có xe dừng quá lâu thì còi cũng kêu.
- "Đứng yên" nghĩa là trạng thái của **cả hai cảm biến không đổi**: xe đang tiến từ cảm biến trước sang cảm biến sau (hoặc lùi ra) thì đồng hồ đếm lại từ đầu, không báo.
- Còi **tắt ngay** khi xe nhúc nhích, khi xe rời khỏi cả hai cảm biến, hoặc khi thanh chắn đóng (xe qua hẳn `PASS`, hoặc hủy `NOPASS`). Cảnh báo chỉ hoạt động trong lúc thanh chắn đang mở, nên xe đứng ở cảm biến khi chưa quẹt thẻ không làm còi kêu.
- Cảm biến sau còn sáng thì thanh chắn không đóng (xem *Đồng hồ đóng thanh chắn*), nên xe đứng ở cảm biến sau mà không đi thì còi sẽ kêu cho tới khi xe đi hoặc bị dời ra: đây là cách báo cho người trực biết.
- Do Arduino tự làm bằng `millis()`, không chặn vòng đọc thẻ / cảm biến, và hoạt động cả khi chương trình Python bị treo. Ngưỡng chỉnh trong `.env` (không cần nạp lại sketch); chu kỳ bíp là `STUCK_BEEP_PERIOD_MS` trong `dual_rfid.ino`. Kiểm tra: gõ `STUCK:1000` trong Serial Monitor, quẹt thẻ cho thanh chắn mở, đặt vật vào cảm biến trước hoặc sau rồi giữ yên khoảng 1 giây: còi kêu lặp; bỏ vật ra thì ngưng.

## Cảm biến hồng ngoại (tùy chọn: bốn cảm biến, mỗi cổng hai cái)
Mỗi cổng có hai cảm biến hồng ngoại: một ở **trước** thanh chắn (phía xe đi tới) và một ở **sau** thanh chắn, để Arduino biết xe đã đi qua thanh chắn chưa. Không gắn cảm biến thì hệ thống vẫn chạy như cũ (thanh chắn tự đóng theo giờ); nhớ đặt `IR_ENABLED=0` trong `.env` để chương trình không ghi nhận `NOPASS` cho mọi lượt.

**Đấu dây** (mỗi cảm biến: VCC -> 5V, GND -> GND, ngõ ra OUT -> chân số):

| Cảm biến | Chân Arduino |
|---|---|
| **Cổng VÀO, trước** thanh chắn | **D2** |
| **Cổng VÀO, sau** thanh chắn | **D3** |
| **Cổng RA, trước** thanh chắn | **D4** |
| **Cổng RA, sau** thanh chắn | **D5** |

Mặc định ngõ ra xuống LOW khi có vật chắn (đa số module E18-D80NK / FC-51). Loại ngược lại thì đổi `IR_ACTIVE_LOW` thành `false` trong `dual_rfid.ino`. Các chân đổi được ở `PIN_IR_*`. Chân dùng `INPUT_PULLUP` nên ngõ ra open-collector cũng chạy được.

**Quẹt thẻ -> chờ xe đi qua -> mới lưu** (khi `IR_ENABLED=1`, `SERVO_ENABLED=1`): quẹt thẻ, quét biển và chốt được đúng 5 số (tự động, hoặc nhân viên bấm *Lưu xe vào* / *Cho xe ra*) thì chương trình **mở thanh chắn nhưng CHƯA ghi gì vào SQL Server**. Màn hình hiện "CHƯA lưu", LCD hiện `MOI XE VAO` / `MOI XE RA`, các lần quẹt thẻ khác và nút *Test servo* bị khóa tới khi có kết quả:
- Xe **đi qua hẳn** (Arduino gửi `PASS`): **lúc này mới lưu** lượt vào (cổng vào) hoặc đóng lượt + tính tiền (cổng ra), cộng / trừ chỗ trống, LCD hiện `XE VAO OK` / `XE RA OK`.
- Xe **không đi qua** (Arduino gửi `NOPASS`): **hủy phiên quẹt thẻ**, không lưu gì (không lượt vào/ra, không biển số, không ảnh, không đổi trạng thái thẻ, không đổi số chỗ). LCD hiện `HAY QUET LAI THE` trong 2 giây, thẻ quẹt lại được ngay. Ở cổng ra, lượt vào vẫn mở như trước khi quẹt.
- Máy tính không nhận được `PASS` / `NOPASS` nào (Arduino mất kết nối / reset giữa chừng) sau `SERVO_OPEN_SECONDS` + 15 giây thì cũng **hủy**, để không treo cổng.
- Không gửi được lệnh mở thanh chắn (Arduino mất kết nối) thì không có gì để chờ: lưu ngay như bản cũ.

**Cách hoạt động** (Arduino tự đo, tính từ lúc thanh chắn MỞ): xe chắn cảm biến trước (xe đã ở **đúng vị trí**), rồi chắn cảm biến sau, rồi rời khỏi cả hai theo thứ tự đó thì Arduino coi là **đã qua**: **hạ thanh chắn ngay** (không chờ hết `SERVO_OPEN_SECONDS`) và gửi `PASS:<cổng>`. Xe lùi ra (cảm biến sau nhả khi cảm biến trước còn bị chắn) thì không tính là đã qua. Vật chỉ chắn cảm biến sau mà chưa từng chắn cảm biến trước (VD người đi ngược chiều) cũng bị bỏ qua. Tín hiệu được chống nhiễu `IR_DEBOUNCE_MS` (30 ms).

**Hủy phiên khi xe rời đi** (`IR_PASS_TIMEOUT_SECONDS`, mặc định 3 giây): **cảm biến trước còn tín hiệu thì KHÔNG hủy** (xe đang đứng chờ, bao lâu cũng được). Chỉ khi cảm biến trước đã thấy xe rồi **mất tín hiệu** mà cảm biến sau chưa từng thấy xe thì Arduino mới bắt đầu đếm ân hạn; hết ân hạn mà cảm biến sau vẫn chưa thấy xe (xe lùi ra hoặc đổi ý không vào) thì hạ thanh chắn và gửi `NOPASS:<cổng>`. Ân hạn giúp xe ngắn kịp chạy từ cảm biến trước sang cảm biến sau; cảm biến trước bị chắn lại trong lúc đếm thì đếm lại từ đầu; cảm biến sau thấy xe kịp lúc thì không hủy. Cảm biến trước chưa từng thấy xe thì không có đồng hồ này, chỉ có hạn chót chung của lần mở thanh chắn (`SERVO_OPEN_SECONDS`).

**Đồng hồ đóng thanh chắn (cả hai cổng):**
- **Cảm biến sau còn sáng thì thanh chắn KHÔNG BAO GIỜ hạ xuống**, chờ bao lâu cũng được (không còn mốc chờ thêm 10 giây như bản cũ). Đồng hồ đang đếm bị hủy và đếm lại từ đầu khi cảm biến sau nhả ra. Xe đi hết (cảm biến trước rồi cảm biến sau đều đã nhả) thì Arduino hạ thanh chắn ngay và gửi `PASS`.
- **Đồng hồ chỉ bắt đầu đếm ngược từ lúc xe RỜI cảm biến trước** (cảm biến trước nhả ra), đếm `SERVO_OPEN_SECONDS` giây; xe còn đứng ở cảm biến trước thì chưa đếm, đứng bao lâu cũng được. Hết giờ đếm mà xe chưa qua (xe lùi ra, hoặc rời đi không vào) thì hạ thanh chắn và gửi `NOPASS`.
- **Xe chưa tới cảm biến trước** (quẹt thẻ rồi chưa chạy tới) thì chưa có mốc "rời" để đếm, nên vẫn tính `SERVO_OPEN_SECONDS` từ lúc mở thanh chắn (hạn chót chờ xe) để thanh chắn không mở mãi. Nhưng nếu lúc đó cảm biến sau đang sáng (vật chắn riêng cảm biến sau) thì cũng không hạ.
- `IR_PASS_TIMEOUT_SECONDS` (ân hạn hủy khi xe rời cảm biến trước mà cảm biến sau không thấy xe) cũng tính từ lúc xe rời cảm biến trước; cái nào hết trước thì hủy trước.
- Phía máy tính, đồng hồ dự phòng (`SERVO_OPEN_SECONDS` + 15 giây) **không hủy phiên khi Arduino còn kết nối** (còn nhịp tim), mà chờ tiếp tối đa 5 phút (`PASS_WAIT_MAX_SECONDS` trong `ui/base_gate_app.py`); Arduino mất kết nối thì hủy như cũ.

**Ghi nhận:** chỉ phiên có xe **đi qua** mới vào `access_log`, kèm cột `pass_in_status` / `pass_in_at` (cổng vào) hoặc `pass_out_status` / `pass_out_at` (cổng ra) = `PASSED`. Phiên bị hủy **không để lại dòng nào** (nên không còn trạng thái `TIMEOUT` cho phiên mới; dữ liệu cũ giữ nguyên). Khi hủy, thanh trạng thái của cổng đó hiện cảnh báo vàng "ĐÃ HỦY phiên quẹt thẻ ...". Xem nhanh:
```sql
SELECT id, card_uid, time_in, pass_in_status, pass_in_at, time_out, pass_out_status, pass_out_at
FROM BienSoDB.dbo.access_log ORDER BY id DESC;
```
Trong lúc chờ xe đi qua, các lần quẹt thẻ khác ở cổng đó bị bỏ qua (hiện "đang chờ xe ... đi qua thanh chắn"), nên mỗi lần mở thanh chắn chỉ có đúng **một** phiên và một kết quả.

**Giới hạn:** chỉ dùng hai cảm biến nên khó phân biệt xe ngắn đã chạy tới cảm biến sau rồi lùi ra hẳn (cảm biến trước đã nhả) với xe đã qua. Cần chắc chắn hơn thì cân nhắc thêm vòng cảm ứng từ hoặc đặt khoảng cách hai cảm biến ngắn hơn chiều dài xe.

**Kiểm tra:** mở Serial Monitor (9600), gõ `SERVOIN:OPEN:3000:3000` rồi đưa vật qua lần lượt cảm biến trước -> sau rồi bỏ ra: thấy thanh chắn hạ và dòng `PASS:IN` (cổng ra: gõ `SERVOOUT:OPEN:3000:3000`, thấy `PASS:OUT`). Đưa vật vào cảm biến trước rồi **không** đưa tiếp tới cảm biến sau: sau 3 giây thấy `NOPASS:IN`; không đưa gì qua thì sau `SERVO_OPEN_SECONDS` giây cũng thấy `NOPASS:...`. Logic nhận biết "xe qua" và "cửa sổ chờ" còn được thử tự động bằng `python -m pytest tests/test_pass_detector.py` (biên dịch đoạn mã firmware bằng g++).

## Đèn LED báo xe vào (tùy chọn: một đèn ở cổng vào)
Khi cảm biến hồng ngoại xác nhận xe **đã đi qua hẳn thanh chắn cổng vào** (đúng lúc Arduino gửi `PASS:IN`), đèn LED **sáng 20 giây rồi tự tắt**. Đèn do **Arduino tự điều khiển** (đếm giờ bằng `millis()`, không chặn vòng đọc thẻ / cảm biến), không cần máy tính và không có lệnh hay biến cấu hình nào trong `.env`. Chỉ cổng vào có đèn; cổng ra không.

**Đấu dây:**

| Đèn LED | Chân Arduino |
|---|---|
| Chân dương (anode, chân dài) -> điện trở 220 ohm | **A4** |
| Chân âm (cathode, chân ngắn) | GND |

A4 không trùng SPI (D8..D13), servo (D6/D7), cảm biến hồng ngoại (D2..D5), LCD (A0..A3), còi (A5) hay Serial. Đèn công suất lớn (đèn 12V, dải LED...) thì **không nối thẳng** chân A4 (tối đa ~20 mA): đi qua transistor hoặc relay.

**Quy tắc:**
- Đèn chỉ sáng khi xe **đã qua hẳn** (chắn cảm biến trước, rồi sau, rồi rời cả hai). Xe lùi ra, vật chắn riêng cảm biến sau, hoặc hết giờ mở thanh chắn mà xe chưa qua (`NOPASS:IN`) đều **không** làm đèn sáng.
- Có xe khác đi qua khi đèn còn sáng thì **đếm lại 20 giây từ đầu**, đèn không tắt giữa chừng.
- Mở nguồn hoặc Arduino reset thì đèn luôn **tắt**.
- Đổi thời gian hoặc chân: sửa `LED_ON_MS` (mili giây, mặc định `20000`) và `PIN_LED` (mặc định `A4`) đầu `dual_rfid.ino` rồi nạp lại.
- Đèn dựa vào **hai cảm biến hồng ngoại cổng vào** (D2, D3) nên phải gắn đủ hai cái thì đèn mới sáng. `IR_ENABLED` trong `.env` chỉ quyết định Python có ghi kết quả vào SQL Server hay không, **không** ảnh hưởng đèn.

**Kiểm tra:** mở Serial Monitor (9600), quẹt thẻ cho thanh chắn mở rồi đưa vật qua lần lượt cảm biến trước (D2) -> sau (D3) rồi bỏ ra: thấy dòng `PASS:IN` và đèn sáng; sau 20 giây đèn tắt. Không đưa gì qua thì chỉ thấy `NOPASS:IN` và đèn không sáng.

## Số chỗ đỗ xe (slot)
Bãi có `PARKING_CAPACITY` chỗ (mặc định **3**). Số chỗ trống = `PARKING_CAPACITY` trừ số xe đang ở trong bãi (đếm từ SQL Server: các lượt chưa có giờ ra).

- **LCD** của cả hai cổng ở màn hình chờ hiện số chỗ còn trống (`CON TRONG: 2/3`) và tự cập nhật ngay khi có xe vào hoặc ra ở cổng nào cũng được.
- **Đủ chỗ:** cổng vào **không nhận quẹt thẻ**: không quét ảnh, không lưu, không mở thanh chắn; LCD cổng vào hiện `BAI DA DAY` / `HET CHO`, thanh trạng thái báo đỏ "BÃI ĐÃ ĐẦY". Thẻ chưa đăng ký hoặc thẻ đã ở trong bãi quẹt ở cổng vào lúc đầy cũng chỉ thấy báo đầy.
- **Cổng ra vẫn hoạt động bình thường** khi bãi đầy. Xe ra thì trả lại một chỗ và LCD cổng vào tự đổi về `CON TRONG: 1/3`.
- Nhân viên bấm *Lưu xe vào* sau khi bãi đã đầy (VD trong lúc chờ xác nhận có xe khác vào) cũng bị từ chối.
- Giao diện cộng trừ số chỗ ngay khi có xe vào / ra và đối chiếu lại với SQL Server mỗi 5 giây (nếu ai đó sửa SQL bằng tay). Số chỗ luôn tính theo SQL Server nên đúng cả khi khởi động lại chương trình.

## Quy tắc nghiệp vụ

**Hướng đi do CỔNG quyết định**, trạng thái thẻ chỉ để kiểm tra hợp lệ:

| Tình huống | Kết quả |
|---|---|
| Thẻ không có trong bảng `cards` (hoặc `is_active = 0`) | Từ chối ở cả hai cổng, không nhận diện, không lưu |
| Cổng vào, thẻ đang ở trong bãi | Từ chối (không cho vào lần nữa) |
| Cổng ra, thẻ chưa có lượt vào | Từ chối (xe chưa vào bãi) |
| Cổng vào, bãi đã đủ chỗ | Không nhận quẹt thẻ: không quét ảnh, không mở thanh chắn (xem *Số chỗ đỗ xe*) |
| Cổng vào, thẻ hợp lệ | Quét ảnh, bỏ phiếu 5 số, mở thanh chắn; **xe đi qua hẳn** (cảm biến) thì mới lưu `time_in`, xe không qua thì hủy phiên, không lưu gì (không có cảm biến: `IR_ENABLED=0` thì lưu ngay) |
| Cổng ra, thẻ hợp lệ | Quét ảnh, bỏ phiếu 5 số, **đối chiếu với 5 số lúc vào**, mở thanh chắn; **xe đi qua hẳn** thì mới lưu `time_out` + `fee`, xe không qua thì hủy phiên (lượt vào vẫn mở) |

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

5 thẻ nạp sẵn (tự thêm khi chạy, thẻ nào đã có thì bỏ qua): `AB1992CA`, `DB2B11CA`, `1B12E1CB`, `1BAE10CB`, `8B066ECA` (UID đọc trên thẻ `AB 19 92 CA` thì viết liền thành `AB1992CA`).
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
hardware/                    rfid.py (Serial: một Arduino, hai đầu đọc, báo tình trạng + kết quả cảm biến PASS/NOPASS, gửi lệnh LCD + servo), camera.py (đọc camera ở luồng nền, báo mất hình)
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
                             slots.py           bộ đếm chỗ trống của bãi (dùng chung hai cổng)
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
