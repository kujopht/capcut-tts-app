"""
Ma hoa BYOK (V5.1) — API key CA NHAN cua nguoi dung ma hoa truoc khi luu.

AES-256-GCM (authenticated encryption) qua `cryptography.hazmat` — KHONG tu
viet thuat toan ma hoa, dung mot nguyen thuy da duoc kiem duyet rong rai.
Master key backend-CHI (`TRANSLATION_BYOK_MASTER_KEY`), KHONG BAO GIO la
`NEXT_PUBLIC_*`, KHONG BAO GIO commit, TACH RIENG voi cau hinh Appwrite
(`server/config.py::AppwriteSettings`) — mat mot cai khong lam lo cai kia.

Dinh dang chuoi luu trong Appwrite/mock (MOT truong string, khong can them
cot rieng cho nonce):

    "byok.v1.<base64 nonce 12 byte>.<base64 ciphertext+tag>"

"v1" la PHIEN BAN dinh dang/khoa — chuan bi SAN cho xoay khoa sau nay (vd
them `TRANSLATION_BYOK_MASTER_KEY_V2`, giai ma theo dung phien ban da ghi
trong chuoi, ma hoa MOI luon dung khoa MOI NHAT). Chua trien khai xoay khoa
that (chi mot khoa "v1" hien tai) nhung dinh dang du de them sau ma KHONG
can migrate lai du lieu cu.

AAD (associated data) rang buoc ciphertext voi CHINH XAC (user_id,
provider_id) no thuoc ve — copy `encrypted_secret` tu ban ghi cua nguoi dung
A sang ban ghi cua nguoi dung B (vd qua mot loi logic o tang khac, hoac thao
tac CSDL truc tiep) se GIAI MA THAT BAI ngay ca khi dung dung master key, vi
AAD khong khop. Day la lop phong thu THU HAI, DOC LAP voi kiem tra
`connection.user_id == nguoi_goi.user_id` o tang service — mot cai hong
khong keo theo cai kia hong.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: Tien to dinh dang — doi khi doi so do ma hoa/khoa (xem docstring dau file).
FORMAT_PREFIX = "byok.v1."
_NONCE_BYTES = 12
_KEY_BYTES = 32


class ByokConfigError(Exception):
    """Thieu/sai `TRANSLATION_BYOK_MASTER_KEY` — nem NGAY luc khoi dong tinh
    nang BYOK, khong am tham vo hieu hoa tinh nang hay dung mock."""


class ByokDecryptError(Exception):
    """
    Giai ma that bai — sai khoa, ciphertext hong, hoac AAD khong khop (vd
    ciphertext khong thuoc ve dung (user_id, provider_id) duoc truyen vao).

    LUON that bai KIN (fail closed): khong bao gio tra ve du lieu mot phan,
    khong bao gio "doan" mot gia tri du phong.
    """


def _doc_master_key(raw: Optional[str] = None) -> bytes:
    gia_tri = raw if raw is not None else os.environ.get(
        "TRANSLATION_BYOK_MASTER_KEY", "")
    gia_tri = (gia_tri or "").strip()
    if not gia_tri:
        raise ByokConfigError(
            "Thiếu TRANSLATION_BYOK_MASTER_KEY — không thể mã hoá/giải mã "
            "API key cá nhân của người dùng.")
    try:
        khoa = base64.b64decode(gia_tri, validate=True)
    except Exception as exc:
        raise ByokConfigError(
            "TRANSLATION_BYOK_MASTER_KEY không phải base64 hợp lệ.") from exc
    if len(khoa) != _KEY_BYTES:
        raise ByokConfigError(
            f"TRANSLATION_BYOK_MASTER_KEY phải là base64 của đúng "
            f"{_KEY_BYTES} byte (AES-256), nhận được {len(khoa)} byte.")
    return khoa


def sinh_master_key_moi() -> str:
    """
    Sinh MOT master key moi (32 byte ngau nhien, ma hoa base64) — dung cho
    tai lieu/thiet lap lan dau/xoay khoa.

    KHONG BAO GIO goi ham nay trong luong chay production binh thuong: moi
    lan goi la MOT khoa hoan toan moi, se khong giai ma duoc bat ky du lieu
    BYOK nao da ma hoa bang khoa cu. Dung mot lan de dien vao `server/.env`
    (khong bao gio commit gia tri that — xem `server/.env.example`, CHI co
    placeholder).
    """
    return base64.b64encode(secrets.token_bytes(_KEY_BYTES)).decode("ascii")


@dataclass
class ByokCrypto:
    """Boc AES-256-GCM voi MOT master key cu the — tiem duoc qua constructor
    cho test (khong doc `os.environ`), dung `tu_moi_truong()` de doc that."""

    master_key: bytes

    @classmethod
    def tu_moi_truong(cls, raw_key: Optional[str] = None) -> "ByokCrypto":
        """`raw_key=None` (mac dinh) doc `TRANSLATION_BYOK_MASTER_KEY` that.
        Nem `ByokConfigError` NGAY neu thieu/sai — khong bao gio am tham
        chay tiep voi mot trang thai ma hoa khong dinh nghia duoc."""
        return cls(master_key=_doc_master_key(raw_key))

    @staticmethod
    def _aad(user_id: str, provider_id: str) -> bytes:
        return f"{user_id}:{provider_id}".encode("utf-8")

    def ma_hoa(self, plaintext: str, *, user_id: str, provider_id: str) -> str:
        """Ma hoa MOT api key that. `user_id`/`provider_id` PHAI la gia tri
        THAT SU cua ban ghi se luu — dung sai o day nghia la sau nay giai ma
        se that bai (dung y thiet ke, xem AAD o docstring dau file)."""
        if not plaintext:
            raise ValueError("Không có gì để mã hoá.")
        aesgcm = AESGCM(self.master_key)
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"),
                           self._aad(user_id, provider_id))
        return (FORMAT_PREFIX
               + base64.b64encode(nonce).decode("ascii") + "."
               + base64.b64encode(ct).decode("ascii"))

    def giai_ma(self, encrypted: str, *, user_id: str, provider_id: str) -> str:
        """`user_id`/`provider_id` PHAI khop CHINH XAC voi luc ma hoa — dung
        gia tri tu CHINH ban ghi (`connection.user_id`/`connection.
        provider_id`), khong dung gia tri nguoi goi tu xung (xem kiem tra
        quyen so huu RIENG, BAT BUOC, o tang service TRUOC khi goi ham nay)."""
        if not encrypted.startswith(FORMAT_PREFIX):
            raise ByokDecryptError("Định dạng bản mã không hợp lệ.")
        phan = encrypted[len(FORMAT_PREFIX):].split(".")
        if len(phan) != 2:
            raise ByokDecryptError("Định dạng bản mã không hợp lệ.")
        try:
            nonce = base64.b64decode(phan[0], validate=True)
            ct = base64.b64decode(phan[1], validate=True)
        except Exception as exc:
            raise ByokDecryptError("Định dạng bản mã không hợp lệ.") from exc
        aesgcm = AESGCM(self.master_key)
        try:
            plaintext = aesgcm.decrypt(nonce, ct, self._aad(user_id, provider_id))
        except InvalidTag as exc:
            raise ByokDecryptError(
                "Giải mã thất bại — sai khoá, dữ liệu hỏng, hoặc không "
                "thuộc về người dùng/nhà cung cấp này.") from exc
        return plaintext.decode("utf-8")


def build_byok_crypto(env: Optional[dict] = None) -> Optional[ByokCrypto]:
    """
    Doc `TRANSLATION_BYOK_MASTER_KEY` va dung `ByokCrypto` neu co — CHO PHEP
    RONG (tra `None`, tinh nang BYOK don gian KHONG hoat dong) khi bien nay
    hoan toan VANG MAT, cung y voi cac `build_*` khac trong du an (dev/test
    khong co credential van phai chay duoc). NHUNG neu bien CO MAT ma SAI
    dinh dang (khong phai base64 32 byte) thi NEM LOI NGAY — mot moi truong
    tuong minh bat BYOK ma cau hinh sai PHAI chet luc khoi dong, khong duoc
    chay tiep roi am tham hong khi nguoi dung dau tien thu ket noi.
    """
    e = env if env is not None else os.environ
    gia_tri = (e.get("TRANSLATION_BYOK_MASTER_KEY", "") or "").strip()
    if not gia_tri:
        return None
    return ByokCrypto.tu_moi_truong(gia_tri)


def lay_4_ky_tu_cuoi(plaintext_key: str) -> str:
    """4 ky tu CUOI de hien thi trong UI — KHONG BAO GIO du de doan lai key
    that (Groq key that dai ~56 ky tu, 4 ky tu cuoi khong ro ri gi ve phan
    con lai)."""
    sach = (plaintext_key or "").strip()
    return sach[-4:] if len(sach) >= 4 else sach
