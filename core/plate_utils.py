"""Các hàm xử lý ảnh và chuỗi biển số (thuần, không phụ thuộc GUI/phần cứng/DB)."""
import re

import cv2
import numpy as np

NUMBER_LEN = 5

# Định dạng biển số VN: 2 số tỉnh + 1-2 ký tự series + 4-5 số (VD: 51F12345, 59X112345)
PLATE_RE = re.compile(r"^\d{2}[A-Z][A-Z0-9]?\d{4,5}$")

# Bảng sửa các ký tự hay bị nhầm
TO_DIGIT = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1",
            "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4"}
TO_LETTER = {"0": "D", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"}

# Có cả "-" và "." để OCR nhận ra chúng là dấu phân cách, không đọc nhầm thành chữ số.
OCR_ALLOWLIST = "ABCDEFGHIKLMNPQRSTUVXYZ0123456789-."


def _iou(a, b):
    """Độ chồng lấp giữa hai khung (x, y, w, h)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0


def find_plate_candidates(img):
    """Tìm các vùng hình chữ nhật có thể là biển số. Trả về list (x, y, w, h)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    edges = cv2.Canny(gray, 30, 200)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:30]

    h, w = img.shape[:2]
    boxes = []
    for c in contours:
        hull = cv2.convexHull(c)
        (_, _), (rw, rh), _ = cv2.minAreaRect(hull)
        if rw == 0 or rh == 0:
            continue
        ratio = max(rw, rh) / min(rw, rh)
        area = rw * rh
        extent = cv2.contourArea(hull) / area
        if not (1.1 <= ratio <= 6 and extent >= 0.75
                and 0.003 * w * h <= area <= 0.95 * w * h):
            continue
        box = cv2.boundingRect(hull)
        if any(_iou(box, b) > 0.6 for b in boxes):
            continue
        boxes.append(box)

    boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)[:3]
    if not boxes:  # không thấy khung nào -> thử đọc cả ảnh
        boxes.append((0, 0, w, h))
    return boxes


def preprocess_crop(crop):
    """Phóng to, chuyển xám, tăng tương phản để OCR dễ đọc."""
    crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)


def read_lines(reader, crop):
    """OCR vùng biển số, trả về danh sách các DÒNG chữ, từ trên xuống dưới."""
    results = reader.readtext(preprocess_crop(crop), allowlist=OCR_ALLOWLIST, detail=1)

    items = []  # (tâm y, tâm x, chiều cao, text)
    for box, text, conf in results:
        if conf < 0.25 or not text.strip():
            continue
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        items.append(((min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2,
                      max(ys) - min(ys), text.strip()))
    if not items:
        return []

    items.sort(key=lambda i: i[0])
    lines = []
    for it in items:
        if lines and abs(it[0] - lines[-1]["y"]) < 0.5 * it[2]:
            lines[-1]["items"].append(it)
            lines[-1]["y"] = sum(i[0] for i in lines[-1]["items"]) / len(lines[-1]["items"])
        else:
            lines.append({"y": it[0], "items": [it]})

    return ["".join(i[3] for i in sorted(ln["items"], key=lambda i: i[1])) for ln in lines]


def extract_number(lines, n=NUMBER_LEN):
    """Lấy n chữ số cuối ở dòng dưới cùng, bỏ '-' và '.'. VD: ["27-B1","258.88"] -> "25888"."""
    if not lines:
        return ""
    text = lines[-1].upper()
    digits = "".join(TO_DIGIT.get(ch, ch) for ch in text if ch not in "-. ")
    digits = "".join(ch for ch in digits if ch.isdigit())
    # dấu '.' bị đọc nhầm thành 1 chữ số (ra 6 số) -> bỏ chữ số ở vị trí dấu chấm
    if len(digits) == n + 1 and "." not in text:
        digits = digits[:3] + digits[4:]
    return digits[-n:] if len(digits) > n else digits


def fix_plate(text):
    """Sửa lỗi nhầm ký tự dựa vào vị trí trong biển số."""
    s = re.sub(r"[^A-Z0-9]", "", text.upper())
    if len(s) < 7:
        return s
    chars = list(s)
    for i in (0, 1):
        chars[i] = TO_DIGIT.get(chars[i], chars[i])
    chars[2] = TO_LETTER.get(chars[2], chars[2])
    for i in range(4, len(chars)):
        chars[i] = TO_DIGIT.get(chars[i], chars[i])
    return "".join(chars)


def format_plate(s):
    """51F12345 -> 51F-123.45 (ô tô) ;  27B125888 -> 27-B1 258.88 (xe máy)"""
    m = re.match(r"^(\d{2})([A-Z])(\d{5})$", s)
    if m:
        prov, series, num = m.groups()
        return f"{prov}{series}-{num[:3]}.{num[3:]}"
    m = re.match(r"^(\d{2})([A-Z][A-Z0-9])(\d{4,5})$", s)
    if m:
        prov, series, num = m.groups()
        if len(num) == 5:
            num = f"{num[:3]}.{num[3:]}"
        return f"{prov}-{series} {num}"
    return s
