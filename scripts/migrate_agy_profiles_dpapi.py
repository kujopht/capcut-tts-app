"""Di trú `saved_profiles/accN.bin` từ THUẦN sang DPAPI — hẹp nhất có thể.

VÌ SAO: tệp profile là JSON thuần chứa OAuth token dùng lại được. ACL siết
lại là lớp thứ nhất, nhưng nó đã bị đặt sai một lần trong thực tế (lần siết
ACL ngày 2026-09-03 vô tình khiến CẢ CÂY không đọc được, và lệnh
`acc relogin 8` sau đó im lặng không làm gì). Mã hoá tại chỗ theo phạm vi
NGƯỜI DÙNG Windows là lớp thứ hai: đọc được byte cũng không dùng được.

BA THAY ĐỔI, không hơn:

  1. `agy_profile.py`: chèn một hàm đọc/ghi nhận biết định dạng và đổi ĐÚNG
     hai chỗ đọc/ghi tệp profile. Vá **idempotent** (chạy lại không sao).
  2. Mỗi `accN.bin` được ghi lại thành `MAGIC + DPAPI(ciphertext)`.
  3. Bản lưu của cả launcher lẫn 8 tệp cũ được đặt cạnh, để hoàn tác dễ.

TƯƠNG THÍCH NGƯỢC: hàm đọc mới nhìn magic header — không có thì trả nguyên
văn. Nên tệp cũ vẫn chạy, trạng thái nửa-di-trú vẫn chạy, và hoàn tác chỉ là
đặt lại tệp cũ.

KHÔNG BAO GIỜ in bản rõ. Script chỉ in tên tệp, kích thước, và ĐẠT/HỎNG.

    python scripts/migrate_agy_profiles_dpapi.py --check
    python scripts/migrate_agy_profiles_dpapi.py --apply
    python scripts/migrate_agy_profiles_dpapi.py --rollback
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.router_v4 import profile_crypto as PC

LAUNCHER = Path(r"C:\Users\nguye\agy-profiles\agy_profile.py")
PROFILES = Path(r"C:\Users\nguye\agy-profiles\saved_profiles")
BACKUP = Path(r"C:\Users\nguye\agy-profiles\.backup-pre-dpapi")

#: Doan duoc chen vao launcher. TU CHUA hoan toan (khong import gi tu kho),
#: vi launcher phai chay duoc du kho co o day hay khong.
DAU = "# --- BEGIN dpapi-profile-io (Router V4) ---"
CUOI = "# --- END dpapi-profile-io ---"

DOAN_VA = f'''{DAU}
# Doc/ghi tep profile co nhan biet dinh dang. Chen boi
# scripts/migrate_agy_profiles_dpapi.py.
#
# TUONG THICH NGUOC: tep co dang THUAN van doc duoc (khong co magic header),
# nen mot trang thai nua-di-tru chay dung va hoan tac chi la dat lai tep cu.
# TU CHUA: khong import gi ngoai stdlib, de launcher khong phu thuoc vao kho.
import ctypes as _ct
from ctypes import wintypes as _wt

_AGYP_MAGIC = b"AGYP1\\x00"
_AGYP_ENTROPY = b"fanfic-router-v4/agy-profile"
_AGYP_UI_FORBIDDEN = 0x1


class _AgypBlob(_ct.Structure):
    _fields_ = [("cbData", _wt.DWORD), ("pbData", _ct.POINTER(_ct.c_char))]


def _agyp_in(data):
    buf = _ct.create_string_buffer(data, len(data))
    return _AgypBlob(len(data), _ct.cast(buf, _ct.POINTER(_ct.c_char)))


def _agyp_out(b):
    ra = _ct.string_at(b.pbData, b.cbData)
    _ct.windll.kernel32.LocalFree(b.pbData)
    return ra


def _agyp_protect(plain):
    din, dent, dout = _agyp_in(plain), _agyp_in(_AGYP_ENTROPY), _AgypBlob()
    if not _ct.windll.crypt32.CryptProtectData(
            _ct.byref(din), None, _ct.byref(dent), None, None,
            _AGYP_UI_FORBIDDEN, _ct.byref(dout)):
        raise OSError("CryptProtectData that bai")
    return _AGYP_MAGIC + _agyp_out(dout)


def _agyp_unprotect(raw):
    din, dent, dout = (_agyp_in(raw[len(_AGYP_MAGIC):]),
                       _agyp_in(_AGYP_ENTROPY), _AgypBlob())
    if not _ct.windll.crypt32.CryptUnprotectData(
            _ct.byref(din), None, _ct.byref(dent), None, None,
            _AGYP_UI_FORBIDDEN, _ct.byref(dout)):
        raise OSError("CryptUnprotectData that bai — blob thuoc tai khoan "
                      "Windows KHAC, hoac tep da hong")
    return _agyp_out(dout)


def read_profile_blob(path):
    with open(path, 'rb') as f:
        raw = f.read()
    return _agyp_unprotect(raw) if raw[:len(_AGYP_MAGIC)] == _AGYP_MAGIC else raw


def write_profile_blob(path, plain):
    import os as _os
    tmp = str(path) + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(_agyp_protect(plain))
    _os.replace(tmp, path)
{CUOI}
'''

#: Hai cho doc/ghi tep profile trong launcher, va ban thay the.
THAY = [
    # switch_profile: doc profile
    ("""    with open(prof_path, 'rb') as f:
        blob = f.read()
    if set_credential(blob):""",
     """    blob = read_profile_blob(prof_path)
    if set_credential(blob):"""),
    # save_profile: ghi profile
    ("""    prof_path = os.path.join(PROFILES_DIR, f'{name}.bin')
    with open(prof_path, 'wb') as f:
        f.write(cred['blob'])""",
     """    prof_path = os.path.join(PROFILES_DIR, f'{name}.bin')
    write_profile_blob(prof_path, cred['blob'])"""),
    # get_active_profile_name: so khop -> phai giai ma truoc khi so
    ("""            with open(os.path.join(PROFILES_DIR, f), 'rb') as fp:
                if fp.read() == curr['blob']:
                    return f[:-4]""",
     """            try:
                if read_profile_blob(
                        os.path.join(PROFILES_DIR, f)) == curr['blob']:
                    return f[:-4]
            except OSError:
                continue"""),
]


def _in(s: str) -> None:
    print(s)


def kiem_tra() -> int:
    _in("=" * 70)
    _in("TRANG THAI DI TRU DPAPI")
    _in("=" * 70)
    _in(f"  DPAPI kha dung : {PC.kha_dung()}")
    _in(f"  launcher       : {LAUNCHER}")
    da_va = LAUNCHER.is_file() and DAU in LAUNCHER.read_text(
        encoding="utf-8", errors="replace")
    _in(f"  launcher da va : {'CO' if da_va else 'chua'}")
    _in(f"  ban luu        : {'CO' if BACKUP.is_dir() else 'chua'} ({BACKUP})")
    _in("")
    ma, thuan = 0, 0
    for n in range(1, 9):
        p = PROFILES / f"acc{n}.bin"
        if not p.is_file():
            _in(f"  acc{n}: (khong co tep)")
            continue
        enc, kt = PC.trang_thai(p)
        ma, thuan = ma + int(enc), thuan + int(not enc)
        trang = "DA MA HOA" if enc else "THUAN"
        ok = ""
        if enc:
            try:
                PC.doc_blob(p)         # giai ma thu, KHONG in
                ok = "  (giai ma OK)"
            except PC.CryptoError as e:
                ok = f"  (GIAI MA HONG: {e})"
        _in(f"  acc{n}: {trang:<10} {kt:>5} byte{ok}")
    _in("")
    _in(f"  tong: {ma} da ma hoa, {thuan} con thuan")
    return 0 if thuan == 0 else 1


def _sao_luu() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    dau_thoi_gian = time.strftime("%Y%m%d-%H%M%S")
    d = BACKUP / dau_thoi_gian
    d.mkdir(parents=True, exist_ok=True)
    if LAUNCHER.is_file():
        shutil.copy2(LAUNCHER, d / LAUNCHER.name)
    for p in sorted(PROFILES.glob("*.bin")):
        shutil.copy2(p, d / p.name)
    _in(f"  ban luu -> {d}")
    (BACKUP / "LATEST").write_text(dau_thoi_gian, encoding="utf-8")


def _va_launcher() -> bool:
    t = LAUNCHER.read_text(encoding="utf-8", errors="replace")
    if DAU in t:
        _in("  launcher: da va tu truoc, bo qua (idempotent)")
        return True
    thieu = [cu for cu, _ in THAY if cu not in t]
    if thieu:
        _in(f"  launcher: KHONG khop {len(thieu)}/{len(THAY)} doan can doi "
            f"— TU CHOI va de tranh lam hong launcher")
        return False
    for cu, moi in THAY:
        t = t.replace(cu, moi, 1)
    # Chen doan tu chua NGAY SAU khoi import dau tien.
    moc = "SESSIONS_DIR = "
    i = t.find(moc)
    if i == -1:
        _in("  launcher: khong tim thay moc chen")
        return False
    j = t.find("\n", i) + 1
    t = t[:j] + "\n" + DOAN_VA + "\n" + t[j:]
    LAUNCHER.write_text(t, encoding="utf-8")
    _in("  launcher: da va (doc/ghi profile nhan biet dinh dang)")
    return True


def ap_dung() -> int:
    if not PC.kha_dung():
        _in("DPAPI khong kha dung — dung.")
        return 2
    _in("=" * 70)
    _in("AP DUNG DI TRU DPAPI")
    _in("=" * 70)
    _sao_luu()
    if not _va_launcher():
        return 3

    _in("")
    doi = 0
    for n in range(1, 9):
        p = PROFILES / f"acc{n}.bin"
        if not p.is_file():
            continue
        enc, _ = PC.trang_thai(p)
        if enc:
            _in(f"  acc{n}: da ma hoa, bo qua")
            continue
        plain = PC.doc_blob(p)         # con thuan -> tra nguyen van
        PC.ghi_blob(p, plain)
        # XAC MINH VONG TRON ngay lap tuc: doc lai va so BYTE, khong in.
        lai = PC.doc_blob(p)
        if lai != plain:
            _in(f"  acc{n}: VONG TRON HONG — hoan tac tep nay")
            shutil.copy2(BACKUP / (BACKUP / "LATEST").read_text().strip()
                         / p.name, p)
            return 4
        enc2, kt = PC.trang_thai(p)
        _in(f"  acc{n}: -> DA MA HOA {kt} byte, vong tron OK")
        doi += 1
    _in("")
    _in(f"  da ma hoa {doi} tep")
    return 0


def hoan_tac() -> int:
    m = BACKUP / "LATEST"
    if not m.is_file():
        _in("khong co ban luu nao.")
        return 1
    d = BACKUP / m.read_text(encoding="utf-8").strip()
    _in(f"hoan tac tu {d}")
    for p in sorted(d.glob("*.bin")):
        shutil.copy2(p, PROFILES / p.name)
        _in(f"  {p.name} <- ban luu")
    lp = d / LAUNCHER.name
    if lp.is_file():
        shutil.copy2(lp, LAUNCHER)
        _in(f"  {LAUNCHER.name} <- ban luu")
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--rollback", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        return kiem_tra()
    if a.apply:
        return ap_dung()
    return hoan_tac()


if __name__ == "__main__":
    sys.exit(main())
