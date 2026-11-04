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
                               "PIN_IR_IN_BEFORE", "PIN_IR_IN_AFTER", "PIN_IR_OUT_BEFORE", "PIN_IR_OUT_AFTER")}
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
                               "PIN_BUZZER")}
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
    assert 'PIN_IR_IN_AFTER, "IN")' in INO and 'PIN_IR_OUT_AFTER, "OUT")' in INO
    for line in ("PASS:IN", "NOPASS:OUT"):
        assert line in README
