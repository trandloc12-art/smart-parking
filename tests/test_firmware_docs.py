"""Kiểm tra sketch Arduino và README nói cùng một số chân (từng bị lệch: README ghi servo D5/D6, code dùng D6/D7)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INO = (ROOT / "arduino" / "dual_rfid" / "dual_rfid.ino").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def pin(name):
    m = re.search(rf"const uint8_t {name}\s*=\s*(\d+);", INO)
    assert m, f"không thấy {name} trong dual_rfid.ino"
    return int(m.group(1))


def test_servo_pins_match_readme():
    vao, ra = pin("PIN_SERVO_IN"), pin("PIN_SERVO_OUT")
    assert re.search(rf"\*\*Cổng VÀO\*\* \| \*\*D{vao}\*\* \| 5V", README)
    assert re.search(rf"\*\*Cổng RA\*\* \| \*\*D{ra}\*\* \| 5V", README)
    assert f"servo: vao=D{vao}, ra=D{ra}" in INO
    assert f"servo: vao=D{vao}, ra=D{ra}" in README


def test_buzzer_pin_matches_readme_and_does_not_clash():
    buzzer = pin("PIN_BUZZER")
    assert f"| Chân dương (+) | **D{buzzer}** |" in README
    assert f"coi=D{buzzer}" in INO
    used = {pin(n) for n in ("PIN_RST", "PIN_SS_IN", "PIN_SS_OUT", "PIN_SERVO_IN", "PIN_SERVO_OUT")}
    used |= {0, 1, 11, 12, 13}   # Serial + SPI (MOSI/MISO/SCK)
    assert buzzer not in used


def test_every_card_swipe_beeps_before_reporting():
    """Còi nằm trong pollReader (dùng chung cho cả hai đầu đọc) và kêu trước khi gửi dòng UID."""
    body = INO[INO.index("void pollReader"):]
    body = body[:body.index("\n}\n")]
    assert "beep();" in body
    assert body.index("beep();") < body.index("Serial.print(tag)")
    assert "tone(PIN_BUZZER" in INO
