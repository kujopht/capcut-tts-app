# -*- coding: utf-8 -*-
"""Kiểm một bản đóng gói TRƯỚC KHI GIAO — chỉ đọc, không ký, không đổi gì.

    python scripts/kiem_ban_dong_goi.py dist-v061                # thư mục dist
    python scripts/kiem_ban_dong_goi.py "dist-v061/Router Control Center/Router Control Center.exe"
    python scripts/kiem_ban_dong_goi.py dist-v04 dist-v05 dist-v06 dist-v061 --so-sanh
    python scripts/kiem_ban_dong_goi.py dist-v061 --ghi           # ghi KIEM_DONG_GOI.txt vào dist
    python scripts/kiem_ban_dong_goi.py dist-v061 --dll           # quét cả _internal/*.dll|*.pyd

Với mỗi EXE báo:

  * SHA256, cỡ, mốc PE (TimeDateStamp), subsystem (GUI/console);
  * CHỮ KÝ Authenticode: trạng thái theo `WinVerifyTrust` (không có / hợp lệ /
    gốc không tin cậy / hết hạn / hỏng…), người ký (Subject CN), nhà phát hành,
    vân tay SHA1 của chứng chỉ ký;
  * Mark-of-the-Web (`Zone.Identifier`): có/không, ZoneId;
  * phần BOOTLOADER (ảnh PE tới hết section cuối) băm riêng — hai bản dựng cùng
    PyInstaller thì phần này TRÙNG, chỉ phần overlay (kho CArchive/PYZ nối sau)
    khác; băm `.rsrc` riêng (manifest/version/icon);
  * DỰ ĐOÁN tương thích Smart App Control — theo luật Microsoft công bố, không
    đoán mò: SAC không dùng kho gốc cục bộ, chỉ tin (a) người ký có danh tiếng
    trong ISG, (b) băm tệp được ISG biết/dự đoán an toàn. Tệp KHÔNG KÝ mới dựng
    = băm mới = "không đảm bảo": lần chạy đầu có thể bị chặn trong lúc tra, và
    có thể bị chặn vĩnh viễn nếu dự đoán là "không rõ".

VÌ SAO TỆP NÀY TỒN TẠI: 2026-09-10 một bản `dist-v061` dựng lại sạch bị Smart
App Control chặn ("we could not verify its publisher") trong khi các bản trước
chạy được — cùng PyInstaller, cùng mã. Không có báo cáo chữ ký/băm/MOTW ở bước
đóng gói thì mọi so sánh đều là đoán. Xem `docs/reports/SMART_APP_CONTROL_V061.md`.

Không phụ thuộc gói ngoài: PE đọc tay, chữ ký qua `wintrust`/`crypt32` (ctypes).
Trên hệ không phải Windows chỉ có phần băm/PE.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import struct
import sys
import time
from ctypes import wintypes as W
from pathlib import Path
from typing import Dict, List, Optional

TEN_EXE = "Router Control Center.exe"
TEN_THU_MUC = "Router Control Center"

# ------------------------------------------------------------------ bam/PE --

def sha256_tep(p: Path, *, den: Optional[int] = None) -> str:
    h = hashlib.sha256()
    con = den
    with p.open("rb") as f:
        while True:
            n = 1 << 20 if con is None else min(1 << 20, con)
            if n <= 0:
                break
            khoi = f.read(n)
            if not khoi:
                break
            h.update(khoi)
            if con is not None:
                con -= len(khoi)
    return h.hexdigest()


def pe_thong_tin(p: Path) -> Dict:
    """Đọc tay đầu PE: mốc dựng, subsystem, bảng section, thư mục Security
    (chữ ký nhúng), cỡ overlay. Không ném — lỗi ghi vào `loi`."""
    kq: Dict = {"la_pe": False}
    try:
        du = p.read_bytes()
    except OSError as exc:
        kq["loi"] = f"không đọc được: {exc}"
        return kq
    kq["co"] = len(du)
    if len(du) < 0x40 or du[:2] != b"MZ":
        kq["loi"] = "không phải PE (thiếu MZ)"
        return kq
    e_lfanew = struct.unpack_from("<I", du, 0x3C)[0]
    if du[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        kq["loi"] = "không phải PE (thiếu PE\\0\\0)"
        return kq
    kq["la_pe"] = True
    coff = e_lfanew + 4
    machine, so_section, timestamp, _, _, co_opt, _dac = struct.unpack_from("<HHIIIHH", du, coff)
    kq["machine"] = {0x8664: "x64", 0x14C: "x86", 0xAA64: "arm64"}.get(machine, hex(machine))
    kq["pe_timestamp"] = timestamp
    kq["pe_timestamp_iso"] = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(timestamp)) + "Z" \
        if 0 < timestamp < 4102444800 else "(không phải mốc thời gian)"
    opt = coff + 20
    magic = struct.unpack_from("<H", du, opt)[0]
    pe32plus = magic == 0x20B
    kq["subsystem"] = {2: "GUI (không console)", 3: "console"}.get(
        struct.unpack_from("<H", du, opt + 68)[0], "khác")
    so_dir = struct.unpack_from("<I", du, opt + (108 if pe32plus else 92))[0]
    dir0 = opt + (112 if pe32plus else 96)
    if so_dir > 4:
        sec_rva, sec_size = struct.unpack_from("<II", du, dir0 + 4 * 8)
        # Thu muc Security: "VirtualAddress" la OFFSET tep, khong phai RVA.
        kq["security_dir"] = {"offset": sec_rva, "size": sec_size}
    else:
        kq["security_dir"] = {"offset": 0, "size": 0}
    sec0 = opt + co_opt
    het_section = 0
    rsrc = None
    for i in range(so_section):
        o = sec0 + i * 40
        ten = du[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
        raw_size, raw_ptr = struct.unpack_from("<II", du, o + 16)
        het_section = max(het_section, raw_ptr + raw_size)
        if ten == ".rsrc":
            rsrc = (raw_ptr, raw_size)
    kq["het_section"] = het_section
    kq["bootloader_sha256"] = hashlib.sha256(du[:het_section]).hexdigest()
    kq["rsrc_sha256"] = hashlib.sha256(du[rsrc[0]:rsrc[0] + rsrc[1]]).hexdigest() if rsrc else ""
    sec = kq["security_dir"]
    cuoi_overlay = sec["offset"] if sec["size"] and sec["offset"] >= het_section else len(du)
    kq["overlay_size"] = max(0, cuoi_overlay - het_section)
    kq["overlay_sha256"] = hashlib.sha256(du[het_section:cuoi_overlay]).hexdigest() \
        if kq["overlay_size"] else ""
    # PyInstaller: overlay ket thuc bang MAGIC "MEI\014\013\012\013\016" trong COOKIE.
    kq["pyinstaller_overlay"] = b"MEI\014\013\012\013\016" in du[het_section:cuoi_overlay][-4096:] \
        if kq["overlay_size"] else False
    return kq


# ------------------------------------------------------------- Zone/MOTW ---

def motw(p: Path) -> Dict:
    """Mark-of-the-Web = luồng NTFS `Zone.Identifier`. Không có = tệp sinh cục bộ."""
    try:
        with open(str(p) + ":Zone.Identifier", "r", encoding="utf-8", errors="replace") as f:
            van = f.read(4096)
    except OSError:
        return {"co": False, "zone_id": None}
    zone = None
    for dong in van.splitlines():
        if dong.strip().lower().startswith("zoneid="):
            zone = dong.split("=", 1)[1].strip()
    return {"co": True, "zone_id": zone, "noi_dung": van.strip()[:300]}


# --------------------------------------------------------------- chu ky ----

_MA_TRUST = {
    0x00000000: ("hop_le", "chữ ký hợp lệ, chuỗi tin cậy tới gốc hệ thống"),
    0x800B0100: ("khong_ky", "KHÔNG có chữ ký Authenticode (TRUST_E_NOSIGNATURE)"),
    0x800B0109: ("goc_khong_tin", "có chữ ký nhưng gốc KHÔNG tin cậy — tự ký/gốc lạ (CERT_E_UNTRUSTEDROOT)"),
    0x800B0101: ("het_han", "chứng chỉ hết hạn (CERT_E_EXPIRED)"),
    0x800B010A: ("chuoi_hong", "không dựng được chuỗi tin cậy (CERT_E_CHAINING)"),
    0x800B0111: ("bi_cam", "chứng chỉ bị đánh dấu KHÔNG tin cậy tường minh (CERT_E_EXPLICIT_DISTRUST)"),
    0x80096010: ("hong", "chữ ký không khớp nội dung — tệp đã đổi sau khi ký (TRUST_E_BAD_DIGEST)"),
    0x80096004: ("hong", "chữ ký sai (TRUST_E_CERT_SIGNATURE)"),
    0x80092026: ("chan_boi_chinh_sach", "chính sách bảo mật chặn (CRYPT_E_SECURITY_SETTINGS)"),
    0x800B0004: ("khong_tin", "chủ thể không được tin cậy cho việc này (TRUST_E_SUBJECT_NOT_TRUSTED)"),
    0x800B0110: ("sai_muc_dich", "chứng chỉ không dùng cho ký mã (CERT_E_WRONG_USAGE)"),
}


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", ctypes.c_ubyte * 8)]


class _WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [("cbStruct", W.DWORD), ("pcwszFilePath", W.LPCWSTR), ("hFile", W.HANDLE),
                ("pgKnownSubject", ctypes.POINTER(_GUID))]


class _WINTRUST_DATA(ctypes.Structure):
    _fields_ = [("cbStruct", W.DWORD), ("pPolicyCallbackData", W.LPVOID), ("pSIPClientData", W.LPVOID),
                ("dwUIChoice", W.DWORD), ("fdwRevocationChecks", W.DWORD), ("dwUnionChoice", W.DWORD),
                ("pFile", ctypes.POINTER(_WINTRUST_FILE_INFO)), ("dwStateAction", W.DWORD),
                ("hWVTStateData", W.HANDLE), ("pwszURLReference", W.LPCWSTR), ("dwProvFlags", W.DWORD),
                ("dwUIContext", W.DWORD), ("pSignatureSettings", W.LPVOID)]


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", W.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class _ALG(ctypes.Structure):
    _fields_ = [("pszObjId", ctypes.c_char_p), ("Parameters", _BLOB)]


class _ATTRS(ctypes.Structure):
    _fields_ = [("cAttr", W.DWORD), ("rgAttr", W.LPVOID)]


class _SIGNER_INFO(ctypes.Structure):
    _fields_ = [("dwVersion", W.DWORD), ("Issuer", _BLOB), ("SerialNumber", _BLOB),
                ("HashAlgorithm", _ALG), ("HashEncryptionAlgorithm", _ALG), ("EncryptedHash", _BLOB),
                ("AuthAttrs", _ATTRS), ("UnauthAttrs", _ATTRS)]


class _BIT_BLOB(ctypes.Structure):
    _fields_ = [("cbData", W.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte)), ("cUnusedBits", W.DWORD)]


class _PUBKEY(ctypes.Structure):
    _fields_ = [("Algorithm", _ALG), ("PublicKey", _BIT_BLOB)]


class _CERT_INFO(ctypes.Structure):
    _fields_ = [("dwVersion", W.DWORD), ("SerialNumber", _BLOB), ("SignatureAlgorithm", _ALG),
                ("Issuer", _BLOB), ("NotBefore", W.FILETIME), ("NotAfter", W.FILETIME),
                ("Subject", _BLOB), ("SubjectPublicKeyInfo", _PUBKEY), ("IssuerUniqueId", _BIT_BLOB),
                ("SubjectUniqueId", _BIT_BLOB), ("cExtension", W.DWORD), ("rgExtension", W.LPVOID)]


class _CERT_CONTEXT(ctypes.Structure):
    _fields_ = [("dwCertEncodingType", W.DWORD), ("pbCertEncoded", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbCertEncoded", W.DWORD), ("pCertInfo", ctypes.POINTER(_CERT_INFO)), ("hCertStore", W.HANDLE)]


def _trang_thai_wintrust(p: Path) -> Dict:
    wintrust = ctypes.WinDLL("wintrust")
    wintrust.WinVerifyTrust.restype = ctypes.c_long
    wintrust.WinVerifyTrust.argtypes = [W.HWND, ctypes.POINTER(_GUID), ctypes.POINTER(_WINTRUST_DATA)]
    guid = _GUID(0x00AAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))
    fi = _WINTRUST_FILE_INFO(ctypes.sizeof(_WINTRUST_FILE_INFO), str(p), None, None)
    wd = _WINTRUST_DATA()
    wd.cbStruct = ctypes.sizeof(_WINTRUST_DATA)
    wd.dwUIChoice = 2                      # WTD_UI_NONE
    wd.fdwRevocationChecks = 0             # WTD_REVOKE_NONE — khong ra mang
    wd.dwUnionChoice = 1                   # WTD_CHOICE_FILE
    wd.pFile = ctypes.pointer(fi)
    wd.dwStateAction = 1                   # WTD_STATEACTION_VERIFY
    wd.dwProvFlags = 0x10 | 0x1000         # REVOCATION_CHECK_NONE | CACHE_ONLY_URL_RETRIEVAL
    ma = wintrust.WinVerifyTrust(None, ctypes.byref(guid), ctypes.byref(wd)) & 0xFFFFFFFF
    wd.dwStateAction = 2                   # WTD_STATEACTION_CLOSE
    wintrust.WinVerifyTrust(None, ctypes.byref(guid), ctypes.byref(wd))
    loai, mo_ta = _MA_TRUST.get(ma, ("khac", f"mã WinVerifyTrust 0x{ma:08X}"))
    return {"ma": f"0x{ma:08X}", "loai": loai, "mo_ta": mo_ta}


def _nguoi_ky(p: Path) -> Dict:
    """Subject/Issuer/vân tay của chứng chỉ ký nhúng (không xét tin cậy)."""
    crypt32 = ctypes.WinDLL("crypt32")
    enc, ctype, ftype = W.DWORD(), W.DWORD(), W.DWORD()
    h_store, h_msg = W.HANDLE(), W.HANDLE()
    crypt32.CryptQueryObject.restype = W.BOOL
    ok = crypt32.CryptQueryObject(
        1, ctypes.c_wchar_p(str(p)), 1 << 10, 2, 0, ctypes.byref(enc), ctypes.byref(ctype),
        ctypes.byref(ftype), ctypes.byref(h_store), ctypes.byref(h_msg), None)
    if not ok:
        return {}
    try:
        cb = W.DWORD()
        crypt32.CryptMsgGetParam(h_msg, 6, 0, None, ctypes.byref(cb))       # CMSG_SIGNER_INFO_PARAM
        if not cb.value:
            return {}
        buf = ctypes.create_string_buffer(cb.value)
        if not crypt32.CryptMsgGetParam(h_msg, 6, 0, buf, ctypes.byref(cb)):
            return {}
        si = ctypes.cast(buf, ctypes.POINTER(_SIGNER_INFO)).contents
        ci = _CERT_INFO()
        ci.Issuer = si.Issuer
        ci.SerialNumber = si.SerialNumber
        crypt32.CertFindCertificateInStore.restype = ctypes.POINTER(_CERT_CONTEXT)
        p_cert = crypt32.CertFindCertificateInStore(h_store, 0x10001, 0, 0xB0000,   # CERT_FIND_SUBJECT_CERT
                                                    ctypes.byref(ci), None)
        if not p_cert:
            return {}
        try:
            def ten(flag: int) -> str:
                n = crypt32.CertGetNameStringW(p_cert, 4, flag, None, None, 0)   # SIMPLE_DISPLAY
                b = ctypes.create_unicode_buffer(max(n, 1))
                crypt32.CertGetNameStringW(p_cert, 4, flag, None, b, n)
                return b.value
            van_tay = ""
            cbh = W.DWORD(20)
            hb = (ctypes.c_ubyte * 20)()
            if crypt32.CertGetCertificateContextProperty(p_cert, 3, hb, ctypes.byref(cbh)):  # SHA1_HASH
                van_tay = bytes(hb[:cbh.value]).hex()
            return {"subject": ten(0), "issuer": ten(1), "sha1": van_tay}
        finally:
            crypt32.CertFreeCertificateContext(p_cert)
    finally:
        if h_store:
            crypt32.CertCloseStore(h_store, 0)
        if h_msg:
            crypt32.CryptMsgClose(h_msg)


def chu_ky(p: Path) -> Dict:
    if os.name != "nt":
        return {"loai": "khong_kiem_duoc", "mo_ta": "chỉ kiểm được trên Windows"}
    try:
        kq = _trang_thai_wintrust(p)
    except Exception as exc:                                    # noqa: BLE001
        return {"loai": "khong_kiem_duoc", "mo_ta": f"wintrust lỗi: {type(exc).__name__}: {exc}"}
    if kq["loai"] != "khong_ky":
        try:
            kq.update(_nguoi_ky(p))
        except Exception as exc:                                # noqa: BLE001
            kq["nguoi_ky_loi"] = f"{type(exc).__name__}: {exc}"
    return kq


# ------------------------------------------------------------- du doan SAC --

def du_doan_sac(ck: Dict, pe: Dict) -> Dict:
    """Theo tài liệu Microsoft (Smart App Control / App Control + ISG): SAC KHÔNG
    tra kho gốc cục bộ; cho chạy khi (a) người ký có danh tiếng tốt trong ISG,
    hoặc (b) băm tệp được ISG biết/dự đoán an toàn. Đây là DỰ ĐOÁN, không phải
    phép đo — phép đo duy nhất là chạy thật và đọc sự kiện 3077."""
    loai = ck.get("loai")
    if loai == "hop_le":
        issuer = (ck.get("issuer") or "").lower()
        if "microsoft" in issuer:
            return {"muc": "cao", "ly_do": "ký bởi chuỗi Microsoft — SAC tin trực tiếp"}
        return {"muc": "kha", "ly_do": ("ký hợp lệ bởi CA công cộng — SAC tin nếu chứng chỉ/nhà phát hành có "
                                        "danh tiếng ISG (Trusted Signing: có ngay; chứng chỉ OV/EV mới: có thể "
                                        "phải gây danh tiếng)")}
    if loai == "goc_khong_tin":
        return {"muc": "chan", "ly_do": ("chữ ký tự ký/gốc lạ: SAC không dùng kho gốc cục bộ — bị chặn như "
                                         "không ký, kể cả khi đã cài gốc vào Trusted Root")}
    if loai in ("het_han", "chuoi_hong", "bi_cam", "hong", "khong_tin", "sai_muc_dich"):
        return {"muc": "chan", "ly_do": f"chữ ký không dùng được: {ck.get('mo_ta')}"}
    if loai == "khong_ky":
        them = " (overlay PyInstaller: mỗi lần dựng lại là một băm mới)" if pe.get("pyinstaller_overlay") else ""
        return {"muc": "khong_dam_bao",
                "ly_do": ("không ký: SAC chỉ cho chạy nếu ISG dự đoán an toàn cho ĐÚNG băm này; lần chạy "
                          "đầu có thể bị chặn trong lúc tra, và bị chặn vĩnh viễn nếu dự đoán 'không rõ'"
                          + them)}
    return {"muc": "khong_ro", "ly_do": ck.get("mo_ta", "không kiểm được chữ ký")}


# --------------------------------------------------------------- bao cao ---

def kiem_exe(p: Path) -> Dict:
    pe = pe_thong_tin(p)
    ck = chu_ky(p) if pe.get("la_pe") else {"loai": "khong_kiem_duoc", "mo_ta": pe.get("loi", "")}
    kq = {"duong_dan": str(p), "co": p.stat().st_size, "mtime": time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)), "sha256": sha256_tep(p),
          "pe": pe, "chu_ky": ck, "motw": motw(p), "sac": du_doan_sac(ck, pe)}
    return kq


def quet_dll(thu_muc: Path) -> Dict:
    """Thống kê chữ ký của DLL/PYD trong `_internal` — SAC kiểm cả DLL."""
    tk: Dict[str, int] = {}
    khong_ky: List[str] = []
    for f in sorted(thu_muc.rglob("*")):
        if f.suffix.lower() not in (".dll", ".pyd", ".exe"):
            continue
        ck = chu_ky(f)
        nhan = ck.get("subject") or ck.get("loai") or "?"
        if ck.get("loai") == "khong_ky":
            nhan = "(không ký)"
            khong_ky.append(str(f.relative_to(thu_muc)))
        tk[nhan] = tk.get(nhan, 0) + 1
    return {"theo_nguoi_ky": dict(sorted(tk.items(), key=lambda x: -x[1])), "khong_ky": khong_ky}


def tim_exe(muc: Path) -> Path:
    if muc.is_file():
        return muc
    for ung in (muc / TEN_THU_MUC / TEN_EXE, muc / TEN_EXE):
        if ung.is_file():
            return ung
    raise FileNotFoundError(f"không thấy EXE trong {muc}")


def dong_bao_cao(kq: Dict) -> str:
    pe, ck, mo, sac = kq["pe"], kq["chu_ky"], kq["motw"], kq["sac"]
    d = [f"tệp        : {kq['duong_dan']}",
         f"sha256     : {kq['sha256']}",
         f"cỡ         : {kq['co']} byte · sửa lúc {kq['mtime']}",
         f"PE         : {pe.get('machine', '?')} · {pe.get('subsystem', '?')} · mốc dựng {pe.get('pe_timestamp_iso', '?')}",
         f"bootloader : sha256 {pe.get('bootloader_sha256', '')[:16]}… (tới hết section) · .rsrc {pe.get('rsrc_sha256', '')[:16]}…",
         f"overlay    : {pe.get('overlay_size', 0)} byte" + (" · PyInstaller CArchive" if pe.get('pyinstaller_overlay') else ""),
         f"chữ ký     : {ck.get('mo_ta', '?')}" + (f" · {ck.get('ma')}" if ck.get('ma') else ""),
         ]
    if ck.get("subject"):
        d.append(f"người ký   : {ck['subject']} · phát hành bởi {ck.get('issuer', '?')} · sha1 {ck.get('sha1', '')}")
    else:
        d.append("người ký   : (không có)")
    d.append(f"MOTW       : " + (f"CÓ Zone.Identifier (ZoneId={mo.get('zone_id')})" if mo.get("co") else "không (tệp sinh cục bộ)"))
    d.append(f"Smart App Control (dự đoán, KHÔNG phải phép đo): [{sac['muc'].upper()}] {sac['ly_do']}")
    return "\n".join(d)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("muc", nargs="+", help="thư mục dist hoặc đường dẫn EXE")
    ap.add_argument("--ghi", action="store_true", help="ghi KIEM_DONG_GOI.txt vào thư mục dist")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dll", action="store_true", help="quét chữ ký DLL/PYD trong _internal")
    ap.add_argument("--so-sanh", action="store_true", help="bảng so sánh bootloader/overlay giữa các bản")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    tat_ca = []
    for m in a.muc:
        muc = Path(m)
        try:
            exe = tim_exe(muc)
        except FileNotFoundError as exc:
            print(f"!! {exc}")
            continue
        kq = kiem_exe(exe)
        if a.dll and (exe.parent / "_internal").is_dir():
            kq["dll"] = quet_dll(exe.parent / "_internal")
        tat_ca.append(kq)
        if a.json:
            continue
        print("=" * 78)
        print(dong_bao_cao(kq))
        if kq.get("dll"):
            print("DLL/PYD    : " + " · ".join(f"{k}: {v}" for k, v in kq["dll"]["theo_nguoi_ky"].items()))
            if kq["dll"]["khong_ky"]:
                print("  không ký : " + ", ".join(kq["dll"]["khong_ky"][:12])
                      + (" …" if len(kq["dll"]["khong_ky"]) > 12 else ""))
        if a.ghi:
            dich = (exe.parent.parent if exe.parent.name == TEN_THU_MUC else exe.parent) / "KIEM_DONG_GOI.txt"
            dich.write_text("Kiểm bản đóng gói (chỉ đọc) — " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n"
                            + dong_bao_cao(kq) + "\n", encoding="utf-8")
            print(f"-> đã ghi {dich}")
    if a.json:
        print(json.dumps(tat_ca, ensure_ascii=False, indent=1))
    if a.so_sanh and len(tat_ca) > 1:
        print("=" * 78)
        print("SO SÁNH   " + "bản".ljust(12) + "bootloader".ljust(18) + ".rsrc".ljust(18)
              + "overlay(byte)".ljust(15) + "sha256 tệp".ljust(18) + "chữ ký")
        for kq in tat_ca:
            pe = kq["pe"]
            ten = Path(kq["duong_dan"]).parent.parent.name if Path(kq["duong_dan"]).parent.name == TEN_THU_MUC \
                else Path(kq["duong_dan"]).name
            print("          " + ten.ljust(12) + pe.get("bootloader_sha256", "")[:16].ljust(18)
                  + pe.get("rsrc_sha256", "")[:16].ljust(18) + str(pe.get("overlay_size", 0)).ljust(15)
                  + kq["sha256"][:16].ljust(18) + kq["chu_ky"].get("loai", "?"))
        bl = {kq["pe"].get("bootloader_sha256") for kq in tat_ca}
        print("          -> bootloader " + ("TRÙNG NHAU ở mọi bản" if len(bl) == 1 else f"KHÁC NHAU ({len(bl)} biến thể)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
