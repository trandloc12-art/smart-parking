"""Hai cổng dùng chung một PlateRecognizer: mô hình OCR chỉ được nạp đúng một lần."""
import sys
import threading
import time
import types

from core.recognizer import PlateRecognizer


def test_load_is_idempotent_and_thread_safe(monkeypatch):
    created = []

    class FakeReader:
        def __init__(self, langs, gpu=False):
            time.sleep(0.05)                          # nạp chậm để hai luồng chắc chắn đụng nhau
            created.append((tuple(langs), gpu))

    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=FakeReader))
    rec = PlateRecognizer()
    assert not rec.ready
    threads = [threading.Thread(target=rec.load) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rec.load()                                        # gọi thêm lần nữa vẫn không nạp lại
    assert rec.ready and created == [(("en",), False)]
