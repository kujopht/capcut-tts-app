#!/usr/bin/env python3
"""
Smoke test THAT cho backend chay tren Appwrite tu luu tru (dev/staging) —
xem `docs/DEV_SELFHOST_APPWRITE.md`.

    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_appwrite
    FAS_ENV_FILE=server/.env.selfhost python -m scripts.smoke_test_selfhost_appwrite --base-url http://127.0.0.1:8010

KHONG goi bat ky endpoint sinh anh TRA PHI nao (Shared Premium/BYOP) — chi
kiem KIEN TRUC Image Studio qua route liet ke model (khong tieu Pollen,
khong tao giao dich thanh toan nao). KHONG BAO GIO in gia tri bi mat —
script nay khong doc secret nao ca, chi goi HTTP toi backend dang chay.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_PORT = 8010
STARTUP_TIMEOUT_SECONDS = 30.0


@dataclass
class KetQuaKiemTra:
    ten: str
    dat: bool
    chi_tiet: str = ""


@dataclass
class BoKetQua:
    items: List[KetQuaKiemTra] = field(default_factory=list)

    def kiem(self, ten: str, dat: bool, chi_tiet: str = "") -> None:
        self.items.append(KetQuaKiemTra(ten, dat, chi_tiet))
        bieu_tuong = "OK  " if dat else "FAIL"
        print(f"[{bieu_tuong}] {ten}" + (f" — {chi_tiet}" if chi_tiet else ""))

    @property
    def tat_ca_dat(self) -> bool:
        return all(item.dat for item in self.items)


def _doi_backend_san_sang(base_url: str, *, timeout_seconds: float) -> bool:
    het_han = time.monotonic() + timeout_seconds
    client = httpx.Client(timeout=5.0, trust_env=False)
    try:
        while time.monotonic() < het_han:
            try:
                resp = client.get(f"{base_url}/api/health")
                if resp.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
        return False
    finally:
        client.close()


def chay(base_url: Optional[str], *, keep_user: bool) -> int:
    tien_trinh: Optional[subprocess.Popen] = None
    if base_url is None:
        base_url = f"http://127.0.0.1:{DEFAULT_PORT}"
        print(f"Chưa truyền --base-url — tự khởi backend tạm tại {base_url} ...")
        tien_trinh = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server.main:app",
             "--host", "127.0.0.1", "--port", str(DEFAULT_PORT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not _doi_backend_san_sang(base_url, timeout_seconds=STARTUP_TIMEOUT_SECONDS):
            print("LỖI: backend tạm không sẵn sàng sau "
                 f"{STARTUP_TIMEOUT_SECONDS:.0f}s.")
            tien_trinh.terminate()
            return 1

    ket_qua = BoKetQua()
    client = httpx.Client(timeout=15.0, trust_env=False, base_url=base_url)
    try:
        _chay_kiem_tra(client, ket_qua, keep_user=keep_user)
    finally:
        client.close()
        if tien_trinh is not None:
            tien_trinh.terminate()
            try:
                tien_trinh.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tien_trinh.kill()

    print()
    tong = len(ket_qua.items)
    dat = sum(1 for i in ket_qua.items if i.dat)
    print(f"Tổng: {dat}/{tong} kiểm tra đạt.")
    return 0 if ket_qua.tat_ca_dat else 1


def _chay_kiem_tra(client: httpx.Client, kq: BoKetQua, *, keep_user: bool) -> None:
    # -- health/ready ---------------------------------------------------
    r = client.get("/api/health")
    data = r.json() if r.status_code == 200 else {}
    kq.kiem("data_backend == appwrite",
           data.get("data_backend") == "appwrite",
           f"nhận được: {data.get('data_backend')!r}")

    r = client.get("/api/ready")
    kq.kiem("/api/ready trả 200", r.status_code == 200, f"HTTP {r.status_code}")

    # -- dang ky + dang nhap ---------------------------------------------
    email = f"smoke-{uuid.uuid4().hex[:12]}@fanficdev.invalid"
    r = client.post("/api/auth/register", json={
        "email": email, "password": "SmokeTest123", "display_name": "Smoke Test",
    })
    kq.kiem("đăng ký user mới", r.status_code == 201, f"HTTP {r.status_code}")
    if r.status_code != 201:
        return
    token = r.json().get("token", "")
    headers = {"Authorization": f"Bearer {token}"}

    # -- dang nhap rieng (phien thu hai, doc lap voi token dang ky) -------
    r = client.post("/api/auth/login", json={"email": email, "password": "SmokeTest123"})
    kq.kiem("đăng nhập lại bằng email/password vừa đăng ký", r.status_code == 200,
           f"HTTP {r.status_code}")
    login_token = r.json().get("token", "") if r.status_code == 200 else ""
    login_headers = {"Authorization": f"Bearer {login_token}"}

    r = client.get("/api/auth/me", headers=login_headers)
    kq.kiem("/api/auth/me trả đúng profile vừa đăng nhập",
           r.status_code == 200 and r.json().get("profile", {}).get("email") == email,
           f"HTTP {r.status_code}, email nhận: {r.json().get('profile', {}).get('email')!r}")

    # -- dang xuat: phien BI HUY that o may chu, khong chi xoa token cuc bo
    r = client.post("/api/auth/logout", headers=login_headers)
    kq.kiem("đăng xuất trả 200 và da_huy_phien == true",
           r.status_code == 200 and r.json().get("da_huy_phien") is True,
           f"HTTP {r.status_code}, thân: {r.json() if r.status_code == 200 else r.text}")

    r = client.get("/api/auth/me", headers=login_headers)
    kq.kiem("token đã đăng xuất KHÔNG còn dùng được cho /api/auth/me (401)",
           r.status_code == 401, f"HTTP {r.status_code}")

    # -- dang xuat mot token da het han/khong hop le van tra 200 -----------
    r = client.post("/api/auth/logout", headers={"Authorization": "Bearer token-khong-hop-le"})
    kq.kiem("đăng xuất token không hợp lệ vẫn trả 200 (da_huy_phien == false)",
           r.status_code == 200 and r.json().get("da_huy_phien") is False,
           f"HTTP {r.status_code}, thân: {r.json() if r.status_code == 200 else r.text}")

    # -- tien do doc / streak / quest (idempotency THAT) -----------------
    payload = {"novel_id": "smoke-novel", "chapter_id": "smoke-chapter"}
    r1 = client.post("/api/progress/read", json=payload, headers=headers)
    r2 = client.post("/api/progress/read", json=payload, headers=headers)
    kq.kiem("progress/read (lần 1)", r1.status_code == 200, f"HTTP {r1.status_code}")
    kq.kiem("progress/read (lần 2, cùng payload)", r2.status_code == 200,
           f"HTTP {r2.status_code}")

    r = client.get("/api/account/streak", headers=headers)
    streak = r.json() if r.status_code == 200 else {}
    kq.kiem("streak idempotent (current_streak == 1, không phải 2)",
           streak.get("current_streak") == 1,
           f"nhận được: {streak.get('current_streak')!r}")

    r = client.get("/api/account/quests", headers=headers)
    kq.kiem("/api/account/quests trả 200", r.status_code == 200, f"HTTP {r.status_code}")

    r = client.get("/api/account/progress", headers=headers)
    kq.kiem("/api/account/progress (XP) trả 200", r.status_code == 200,
           f"HTTP {r.status_code}")

    r = client.get("/api/account/cosmetics", headers=headers)
    kq.kiem("/api/account/cosmetics trả 200", r.status_code == 200, f"HTTP {r.status_code}")

    # -- bang xep hang (cong khai) ----------------------------------------
    r = client.get("/api/leaderboard", params={"mode": "all_time"})
    kq.kiem("leaderboard all_time trả 200", r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/api/leaderboard", params={"mode": "weekly"})
    kq.kiem("leaderboard weekly trả 200", r.status_code == 200, f"HTTP {r.status_code}")

    # -- Image Studio: CHI kien truc/metadata, KHONG sinh anh tra phi -----
    r = client.get("/api/image/models")
    kq.kiem("Image Studio: danh sách model (không sinh ảnh) trả 200",
           r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/api/image/wallet", headers=headers)
    kq.kiem("Image Studio: ví Fanfic Credit (kiến trúc ledger) trả 200",
           r.status_code == 200, f"HTTP {r.status_code}")
    r = client.get("/api/image/community-free/models", headers=headers)
    kq.kiem("Image Studio: danh sách Cộng đồng Free trả 200",
           r.status_code == 200, f"HTTP {r.status_code}")

    if not keep_user:
        print(f"(user test: {email} — dọn thủ công qua Appwrite console nếu cần, "
             "script này không tự xoá để tránh thao tác ghi ngoài dự kiến)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None,
                       help="Backend đã chạy sẵn (vd http://127.0.0.1:8010). "
                            "Bỏ trống để script tự khởi một tiến trình tạm.")
    parser.add_argument("--keep-user", action="store_true",
                       help="Chỉ ảnh hưởng thông điệp in ra cuối — không xoá gì "
                            "trong cả hai trường hợp (script không có quyền xoá).")
    args = parser.parse_args()
    return chay(args.base_url, keep_user=args.keep_user)


if __name__ == "__main__":
    raise SystemExit(main())
