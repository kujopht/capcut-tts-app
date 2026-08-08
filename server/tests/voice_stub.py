"""
Cho registry biet cac `voice_id` GIA LAP ma bo test dung (`mock:v1`, `v`, ...).

VI SAO CAN: `POST /api/jobs` nay cuong che pham vi giong — chi giong tieng Viet,
va giong cuc bo phai nam trong danh sach trang. De tra loi duoc "giong nay tieng
gi", route phai tra cuu registry. Cac bo test cu dung `voice_id` bia dat von
khong co trong registry that, nen chung se bi tu choi 400 truoc khi kip kiem tra
thu ma chung thuc su quan tam (vong doi job, phan quyen, audio...).

Ban stub nay KHONG lam yeu rang buoc: no chi khai bao rang `mock:v1` la mot
giong tieng Viet co that trong pham vi bai test. Test nao co viec kiem tra dung
viec loc giong thi dung registry that — xem `server/tests/test_vietnamese_scope.py`.
"""

from __future__ import annotations

from typing import Any, List

from server import tts_bridge

#: Cac id gia lap dang duoc dung rai rac trong bo test.
VOICE_IDS_GIA_LAP = ("mock:v1", "mock:v2", "v")


class _GiongGia:
    def __init__(self, voice_id: str):
        self.id = voice_id
        provider, _, key = voice_id.partition(":")
        self.provider = provider or "mock"
        self.voice_key = key or voice_id
        self.engine_voice_id = self.voice_key
        self.display_name = voice_id
        self.description = ""
        self.language = "vi-VN"       # trong pham vi cua web
        self.gender = ""
        self.installed = True
        self.provider_label = self.provider


class _TrangThaiGia:
    class _S:
        value = "available"
        label = "Sẵn sàng"

    status = _S()
    reason = ""


class _RegistryGia:
    def __init__(self, voice_ids):
        self.voices: List[Any] = [_GiongGia(v) for v in voice_ids]

    def voice_by_id(self, voice_id: str):
        for v in self.voices:
            if v.id == voice_id:
                return v
        return None

    def status_of(self, voice):
        return _TrangThaiGia()

    def close(self):
        pass


def dung_registry_gia(test_case, *voice_ids: str) -> None:
    """
    Cai registry gia cho MOT bai test, tu go ra khi test ket thuc.

    Goi trong `setUp`. Khong dat lai `_registry` ve `None` ma tra lai gia tri
    CU: mot so bo test khac da cai registry rieng cua chung.
    """
    ids = voice_ids or VOICE_IDS_GIA_LAP
    with tts_bridge._registry_lock:
        cu = tts_bridge._registry
        tts_bridge._registry = _RegistryGia(ids)

    def hoan_nguyen() -> None:
        with tts_bridge._registry_lock:
            tts_bridge._registry = cu

    test_case.addCleanup(hoan_nguyen)
