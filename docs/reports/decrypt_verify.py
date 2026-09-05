#!/usr/bin/env python3
"""Chung minh `_APP_OPENSSL_KEY_V1` trong .env DUNG voi du lieu da khoi phuc.

Day la phep thu QUYET DINH cho cau hoi "khoa co con giai ma duoc du lieu that
khong". Cac phep thu khac deu vong: tao user moi roi doc lai chi chung minh
Appwrite tu nhat quan voi khoa cua CHINH NO — ke ca khi do la khoa SAI. Chi
viec giai ma duoc CIPHERTEXT CO SAN moi chung minh khoa khop du lieu cu.

KHONG BAO GIO in ban ro. Chi in: giai ma duoc hay khong, do dai, va loai ky
tu. Do la du de ket luan ma khong lam lo mot bi mat nao.

Chay TREN may dien tap:
    python3 decrypt_verify.py <duong-dan-.env> <tep-json-ciphertext>
"""
import base64
import json
import sys
from pathlib import Path


def doc_khoa(env_path: Path) -> bytes:
    """Lay _APP_OPENSSL_KEY_V1 tu .env. Khong in gia tri."""
    for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("_APP_OPENSSL_KEY_V1="):
            return line.split("=", 1)[1].strip().encode()
    raise SystemExit("khong thay _APP_OPENSSL_KEY_V1 trong .env")


def thu_giai_ma(blob: dict, key: bytes):
    """Giai ma theo dung hinh dang Appwrite: aes-128-gcm, iv+tag rieng."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    data = blob["data"]
    iv = blob["iv"]
    tag = blob["tag"]

    # Appwrite ma hoa bang openssl_encrypt(...) roi base64 toan bo; iv/tag
    # duoc luu hex. Thu ca hai cach doc cho chac.
    def _b(v):
        try:
            return bytes.fromhex(v)
        except ValueError:
            return base64.b64decode(v)

    ct = base64.b64decode(data)
    iv_b = _b(iv)
    tag_b = _b(tag)

    # Khoa cua Appwrite la chuoi; aes-128 can 16 byte.
    k = key[:16]
    aes = AESGCM(k)
    return aes.decrypt(iv_b, ct + tag_b, None)


def mo_ta(pt: bytes) -> str:
    """Mo ta ban ro ma KHONG lo noi dung."""
    try:
        s = pt.decode("utf-8")
    except UnicodeDecodeError:
        return f"{len(pt)} byte nhi phan"
    loai = []
    if any(c.isdigit() for c in s):
        loai.append("so")
    if any(c.isalpha() for c in s):
        loai.append("chu")
    if any(not c.isalnum() for c in s):
        loai.append("ky tu khac")
    return f"{len(s)} ky tu utf-8 gom [{', '.join(loai) or 'rong'}]"


def main() -> int:
    env_path = Path(sys.argv[1])
    ct_path = Path(sys.argv[2])
    key = doc_khoa(env_path)
    mau = json.loads(ct_path.read_text(encoding="utf-8"))

    dat = 0
    hong = 0
    for ten, chuoi in mau.items():
        try:
            blob = json.loads(chuoi)
        except json.JSONDecodeError:
            print(f"  {ten}: khong phai JSON ciphertext")
            continue
        try:
            pt = thu_giai_ma(blob, key)
        except Exception as exc:  # noqa: BLE001
            hong += 1
            print(f"  {ten}: GIAI MA HONG ({type(exc).__name__})")
            continue
        dat += 1
        print(f"  {ten}: GIAI MA DUOC -> {mo_ta(pt)}")

    print(f"\nGIAI_MA_DAT={dat}  GIAI_MA_HONG={hong}")
    print("KET LUAN: " + (
        "_APP_OPENSSL_KEY_V1 KHOP du lieu da khoi phuc"
        if dat and not hong else
        "KHOA KHONG khop — du lieu ma hoa se khong doc duoc"))
    return 0 if dat and not hong else 1


if __name__ == "__main__":
    raise SystemExit(main())
