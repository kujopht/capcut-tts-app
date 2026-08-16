"""
Loc bo gia tri bi mat truoc khi bat ky thu gi tro thanh chuoi de in/log/nem
loi — lop phong thu THEM (khong thay the) cho cach lam da co san trong
`appwrite_store.py`/`appwrite_adapter.py`/... (chi lay truong `message`,
khong bao gio in nguyen van body/trace cua Appwrite).

VI SAO MODULE NAY TON TAI (su co that, 2026-08-16): mot script CHAN DOAN
tam thoi (khong nam trong repo, da bi xoa) goi truc tiep `httpx` toi Appwrite
va in `resp.json()` NGUYEN VAN khi loi — Appwrite o `_APP_ENV=development`
tra ve stack trace debug chua nguyen van tham so request (bao gom
`apiKey`) long trong `trace[].args[]`, sau nhieu tang long nhau. Script do
KHONG di qua cac ham `_call()` an toan da co trong `server/appwrite_*.py`
(nhung ham do chi bao gio lay `body["message"]`, khong bao gio cham
`trace`) — nen loi nam o mot cong cu tam thoi ben ngoai, khong phai o code
production. Module nay ton tai de: (1) bat ky script chan doan/migration
NAO viet SAU NAY deu co mot ham DUY NHAT, DA KIEM THU de goi thay vi tu viet
lai logic in loi, va (2) them mot lop loc theo MAU (regex) ben canh loc
theo TEN TRUONG, phong truong hop bi mat lot vao mot truong khong nam trong
danh sach ten đã biết.

KHONG lam thay doi hanh vi cac `_call()` hien co (van chi lay `message`) —
chi bo sung, khong thay the.
"""

from __future__ import annotations

import re
from typing import Any

#: Ten truong (khong phan biet hoa/thuong, so khop CHINH XAC sau khi ha
#: chu, KHONG phai substring) duoc coi la bi mat va luon bi thay the.
#:
#: CO Y khong dung substring rong nhu "key" — nhieu truong hop le KHONG
#: phai bi mat lai co hau to "_key" (`storage_key`, `avatar_key`,
#: `cosmetic_key`, `cover_key`, `keyId` cua mot document...). Dung danh
#: sach TEN CHINH XAC tranh xoa nham du lieu khong nhay cam.
SECRET_KEY_NAMES = frozenset({
    "apikey", "api_key", "x-appwrite-key",
    "authorization", "auth",
    "secret", "client_secret",
    "password", "app_password",
    "access_token", "refresh_token", "id_token",
    "encrypted_access_token", "encrypted_refresh_token",
    "code_verifier", "code_challenge",
    "cookie", "cookies", "session_secret",
    "private_key", "byop_master_key", "openssl_key", "master_key",
})

#: Mau THEO GIA TRI (khong phu thuoc ten truong) — bat bi mat lot vao mot
#: truong khong nam trong `SECRET_KEY_NAMES`, hoac xuat hien tu do trong
#: van ban (vi du thong diep loi tu do). Danh sach cang HEP cang tot — chi
#: khop HINH DANG bi mat that su gap trong du an nay, tranh xoa nham chuoi
#: dai vo hai (id, hash noi dung, ...).
_MAU_BI_MAT_THEO_GIA_TRI = [
    # Khoa API Appwrite, dang "standard_<hex dai>" hoac "console_<hex dai>" —
    # xem dinh dang that quan sat duoc luc tao key tren self-host.
    re.compile(r"\b(?:standard|console)_[a-f0-9]{40,}\b", re.IGNORECASE),
    # Header/gia tri dang "Bearer <token>".
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE),
    # JWT (header.payload.signature, dang base64url ba doan cach nhau dau cham).
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\b"),
]

_THAY_THE = "<redacted>"


def _ten_nhay_cam(ten: Any) -> bool:
    return isinstance(ten, str) and ten.strip().lower() in SECRET_KEY_NAMES


def loc_bo_theo_gia_tri(van_ban: str) -> str:
    """Ap cac mau theo-gia-tri len MOT chuoi — dung cho van ban tu do (vd
    thong diep loi da rut trich, dong log, output subprocess)."""
    ra = van_ban
    for mau in _MAU_BI_MAT_THEO_GIA_TRI:
        ra = mau.sub(_THAY_THE, ra)
    return ra


def loc_bo_de_qui(du_lieu: Any, *, do_sau_toi_da: int = 12) -> Any:
    """
    Duyet DE QUI dict/list/tuple, thay gia tri cua bat ky khoa nao khop
    `SECRET_KEY_NAMES` bang `<redacted>`, VA ap `loc_bo_theo_gia_tri` len
    moi chuoi con lai (bat bi mat lot vao truong khong nam trong danh sach
    ten, dung nhu ca that da xay ra: `apiKey` nam trong `trace[].args[2]`,
    mot vi tri KHONG the liet ke het truoc).

    `do_sau_toi_da` chan de qui vo han tren du lieu vong lap ngau nhien —
    khong nem loi, chi ngung loc sau vao va tra nguyen trang phan con lai
    (an toan hon la crash giua chung mot ham dang xu ly loi).
    """
    if do_sau_toi_da <= 0:
        return du_lieu
    if isinstance(du_lieu, dict):
        ra = {}
        for k, v in du_lieu.items():
            if _ten_nhay_cam(k):
                ra[k] = _THAY_THE
            else:
                ra[k] = loc_bo_de_qui(v, do_sau_toi_da=do_sau_toi_da - 1)
        return ra
    if isinstance(du_lieu, (list, tuple)):
        loai = type(du_lieu)
        return loai(loc_bo_de_qui(v, do_sau_toi_da=do_sau_toi_da - 1) for v in du_lieu)
    if isinstance(du_lieu, str):
        return loc_bo_theo_gia_tri(du_lieu)
    return du_lieu


def thong_diep_loi_an_toan(body: Any, *, status_code: int, gioi_han_ky_tu: int = 300) -> str:
    """
    Chuyen mot response body (da `.json()` hoac None) thanh MOT chuoi an
    toan de in/nem loi — CUNG hanh vi voi `_call()` hien co trong
    `appwrite_store.py` (uu tien truong `message`), CONG THEM loc theo mau
    gia tri o buoc cuoi de phong `message` vo tinh chua chuoi trong danh
    sach `_MAU_BI_MAT_THEO_GIA_TRI`.

    KHONG BAO GIO tra ve nguyen van `body` — chi mot cau, cat o
    `gioi_han_ky_tu`.
    """
    message = f"Appwrite trả về lỗi {status_code}."
    if isinstance(body, dict) and body.get("message"):
        message = str(body["message"])
    return loc_bo_theo_gia_tri(message)[:gioi_han_ky_tu]
