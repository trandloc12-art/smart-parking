"""Kiểm tra sketch Arduino và README nói cùng một số chân (từng bị lệch: README ghi servo D5/D6, code dùng D6/D7;
còi đổi sang A5 nhưng tài liệu vẫn ghi D4)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INO = (ROOT / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def pin(name):
    """Nhãn chân của hằng số trong sketch: số -> 'D6', analog -> 'A5'."""
    m = re.search(rf"const uint8_t {name}\s*=\s*(A\d|\d+);", INO)
    assert m, f"không thấy {name} trong dual_rfid.ino"
    value = m.group(1)
    return value if value.startswith("A") else f"D{value}"


def test_servo_pins_match_readme():
    vao, ra = pin("PIN_SERVO_IN"), pin("PIN_SERVO_OUT")
    assert re.search(rf"\*\*Cổng VÀO\*\* \| \*\*{vao}\*\* \| 5V", README)
    assert re.search(rf"\*\*Cổng RA\*\* \| \*\*{ra}\*\* \| 5V", README)
    assert f"servo: vao={vao}, ra={ra}" in INO
    assert f"servo: vao={vao}, ra={ra}" in README


def test_buzzer_pin_matches_readme_and_does_not_clash():
    buzzer = pin("PIN_BUZZER")
    assert buzzer == "A5"
    assert f"| Chân dương (+) | **{buzzer}** |" in README
    assert f"coi={buzzer}" in INO and f"coi={buzzer}" in README
    others = {pin(n) for n in ("PIN_RST", "PIN_SS_IN", "PIN_SS_OUT", "PIN_SERVO_IN", "PIN_SERVO_OUT",
                               "PIN_LCD_IN_SDA", "PIN_LCD_IN_SCL", "PIN_LCD_OUT_SDA", "PIN_LCD_OUT_SCL",
                               "PIN_IR_IN_BEFORE", "PIN_IR_IN_AFTER", "PIN_IR_OUT_BEFORE", "PIN_IR_OUT_AFTER",
                               "PIN_LED")}
    others |= {"D0", "D1", "D11", "D12", "D13"}   # Serial + SPI (MOSI/MISO/SCK)
    assert buzzer not in others


def test_no_stale_buzzer_pin_in_docs():
    """Còi ở A5: không còn chỗ nào nói còi ở D4 (D4 nay là cảm biến hồng ngoại cổng ra)."""
    for text in (INO, README):
        assert not re.search(r"còi[^\n]{0,40}D4|D4[^\n]{0,40}còi|coi=D4", text), "vẫn còn ghi còi ở D4"


def test_ir_pins_match_readme_and_do_not_clash():
    pins = {name: pin(name) for name in ("PIN_IR_IN_BEFORE", "PIN_IR_IN_AFTER",
                                         "PIN_IR_OUT_BEFORE", "PIN_IR_OUT_AFTER")}
    assert len(set(pins.values())) == 4
    assert f"| **Cổng VÀO, trước** thanh chắn | **{pins['PIN_IR_IN_BEFORE']}** |" in README
    assert f"| **Cổng VÀO, sau** thanh chắn | **{pins['PIN_IR_IN_AFTER']}** |" in README
    assert f"| **Cổng RA, trước** thanh chắn | **{pins['PIN_IR_OUT_BEFORE']}** |" in README
    assert f"| **Cổng RA, sau** thanh chắn | **{pins['PIN_IR_OUT_AFTER']}** |" in README
    ir = f"ir: vao={pins['PIN_IR_IN_BEFORE']}/{pins['PIN_IR_IN_AFTER']}, " \
         f"ra={pins['PIN_IR_OUT_BEFORE']}/{pins['PIN_IR_OUT_AFTER']}"
    assert ir in INO and ir in README
    others = {pin(n) for n in ("PIN_RST", "PIN_SS_IN", "PIN_SS_OUT", "PIN_SERVO_IN", "PIN_SERVO_OUT",
                               "PIN_LCD_IN_SDA", "PIN_LCD_IN_SCL", "PIN_LCD_OUT_SDA", "PIN_LCD_OUT_SCL",
                               "PIN_BUZZER", "PIN_LED")}
    others |= {"D0", "D1", "D11", "D12", "D13"}
    assert not set(pins.values()) & others


def test_flash_string_macro_not_used_at_global_scope():
    """F("...") chứa biểu thức lệnh nên Arduino báo lỗi biên dịch nếu dùng ngoài hàm (từng gặp ở Barrier barrierIn(...)).
    Mọi dòng có F(" phải thụt lề (nằm trong hàm); khai báo toàn cục ở cột 0 thì không được có."""
    for number, line in enumerate(INO.splitlines(), 1):
        if 'F("' in line and not line.startswith((" ", "\t", "//", "/*", "*")):
            raise AssertionError(f"dual_rfid.ino:{number}: F(\"...\") ở phạm vi toàn cục: {line.strip()}")


def test_every_card_swipe_beeps_before_reporting():
    """Còi nằm trong pollReader (dùng chung cho cả hai đầu đọc) và kêu trước khi gửi dòng UID."""
    body = INO[INO.index("void pollReader"):]
    body = body[:body.index("\n}\n")]
    assert "beep();" in body
    assert body.index("beep();") < body.index("Serial.print(tag)")
    assert "tone(PIN_BUZZER" in INO


def test_barrier_reports_pass_and_nopass_with_the_gate_tag():
    """Giao thức PASS:/NOPASS: trong sketch phải khớp bên Python (hardware/rfid.py) và README."""
    assert 'report(F("PASS:"))' in INO and 'report(F("NOPASS:"))' in INO
    assert 'PIN_IR_IN_AFTER, "IN"' in INO and 'PIN_IR_OUT_AFTER, "OUT"' in INO   # cổng vào còn thêm tham số đèn
    for line in ("PASS:IN", "NOPASS:OUT"):
        assert line in README


def test_servo_angle_defaults_agree_between_sketch_env_example_and_readme():
    """Góc mặc định trong sketch, .env.example và README phải nói cùng một số (0° đóng / 90° mở)."""
    closed = int(re.search(r"const uint8_t SERVO_CLOSED_ANGLE\s*=\s*(\d+);", INO).group(1))
    open_ = int(re.search(r"const uint8_t SERVO_OPEN_ANGLE\s*=\s*(\d+);", INO).group(1))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(rf"^SERVO_CLOSED_ANGLE={closed}\b", example, re.M)
    assert re.search(rf"^SERVO_OPEN_ANGLE={open_}\b", example, re.M)
    assert f"| `SERVO_CLOSED_ANGLE`, `SERVO_OPEN_ANGLE` | `{closed}`, `{open_}` |" in README


def test_servo_angle_command_is_documented_and_implemented_on_both_sides():
    """Lệnh SERVOIN:ANGLE: có trong sketch (xử lý + chú thích đầu file), README, và hardware/rfid.py gửi đúng dạng đó."""
    assert 'strncmp(args, "ANGLE:", 6)' in INO
    assert "SERVOIN:ANGLE:" in INO and "SERVOOUT:ANGLE:" in INO
    assert "`SERVOIN:ANGLE:0:90`" in README
    from hardware.rfid import format_servo_angle_command
    assert format_servo_angle_command("in", 0, 90) == "SERVOIN:ANGLE:0:90\n"
    assert format_servo_angle_command("out", 0, 90) == "SERVOOUT:ANGLE:0:90\n"


def test_sketch_boot_banner_matches_what_python_waits_for():
    """Python cài lại góc servo khi thấy dòng này (Arduino vừa khởi động lại): sketch phải còn in đúng tiền tố đó."""
    from hardware.rfid import BOOT_BANNER
    assert f'Serial.println(F("{BOOT_BANNER} san sang' in INO


def test_barrier_uses_runtime_angles_not_the_constants_directly():
    """Chỉ phần khởi tạo giá trị mặc định mới được dùng hằng số góc; còn lại phải dùng biến để lệnh ANGLE có tác dụng."""
    body = INO[INO.index("class Barrier"):INO.index("Barrier barrierIn(")]
    assert "servo_.write(SERVO_CLOSED_ANGLE)" not in body and "servo_.write(SERVO_OPEN_ANGLE)" not in body
    assert "servo_.write(closedAngle_)" in body and "servo_.write(openAngle_)" in body


def test_led_pin_matches_readme_and_does_not_clash():
    led = pin("PIN_LED")
    assert led == "A4"
    assert f"| Chân dương (anode, chân dài) -> điện trở 220 ohm | **{led}** |" in README
    assert f"led={led}" in INO and f"led={led}" in README
    others = {pin(n) for n in ("PIN_RST", "PIN_SS_IN", "PIN_SS_OUT", "PIN_SERVO_IN", "PIN_SERVO_OUT",
                               "PIN_LCD_IN_SDA", "PIN_LCD_IN_SCL", "PIN_LCD_OUT_SDA", "PIN_LCD_OUT_SCL",
                               "PIN_IR_IN_BEFORE", "PIN_IR_IN_AFTER", "PIN_IR_OUT_BEFORE", "PIN_IR_OUT_AFTER",
                               "PIN_BUZZER")}
    others |= {"D0", "D1", "D11", "D12", "D13"}   # Serial + SPI (MOSI/MISO/SCK)
    assert led not in others


def test_led_duration_is_20_seconds_in_sketch_and_readme():
    ms = int(re.search(r"const unsigned long LED_ON_MS\s*=\s*(\d+);", INO).group(1))
    assert ms == 20000
    assert f"`LED_ON_MS` (mili giây, mặc định `{ms}`)" in README


def test_only_the_entry_barrier_drives_the_led_and_only_after_a_real_pass():
    """Đèn chỉ gắn vào Barrier cổng vào và chỉ bật cùng lúc PASS (xe qua hẳn), không bật ở nhánh NOPASS / close()."""
    assert 'PIN_IR_IN_AFTER, "IN", &entryLed)' in INO
    assert 'PIN_IR_OUT_AFTER, "OUT")' in INO and "&entryLed" not in INO[INO.index("Barrier barrierOut("):].split("\n")[0]
    body = INO[INO.index("class Barrier"):INO.index("Barrier barrierIn(")]
    assert body.count("led_->trigger(") == 1
    trigger_at = body.index("led_->trigger(")
    assert body.index('report(F("PASS:"))') > trigger_at > body.index("detector_.update(")
    assert trigger_at < body.index('report(F("NOPASS:"))')
    # trigger nằm trong nhánh PASS (trước dòng return của nhánh đó), không phải sau nhánh hết giờ
    assert "return;" in body[trigger_at:body.index('report(F("NOPASS:"))')]


def test_led_is_off_at_boot_and_updated_every_loop_without_blocking():
    setup = INO[INO.index("void setup()"):INO.index("void loop()")]
    assert "pinMode(PIN_LED, OUTPUT)" in setup and "digitalWrite(PIN_LED, LOW)" in setup
    loop = INO[INO.index("void loop()"):]
    assert "entryLed.update(millis())" in loop
    assert "delay(" not in loop
