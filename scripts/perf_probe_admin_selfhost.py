#!/usr/bin/env python3
"""
Do do tre THAT cua cac route /api/admin/* chong Appwrite tu luu tru dev
(Phase 5 — Overnight Pre-Production Hardening Marathon V1). KHONG dung cho
CI, chi dung mot lan de lay so do. KHONG ghi gi vao Appwrite ngoai mot user
smoke-test dang ky qua /api/auth/register (giong cac script smoke test khac
trong repo). Quyen OWNER duoc cap CUC BO cho tien trinh backend tam thoi qua
bien moi truong FAS_OWNER_USER_IDS — day KHONG PHAI mot cot du lieu Appwrite
(xem server/config.py Settings.admin_role_of), nen khong dung toi Appwrite
console/thao tac tay nao.

    FAS_ENV_FILE=server/.env.selfhost .venv/Scripts/python.exe scripts/perf_probe_admin_selfhost.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

import httpx

PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cho_san_sang(client: httpx.Client, timeout_s: float = 30.0) -> bool:
    het_han = time.monotonic() + timeout_s
    while time.monotonic() < het_han:
        try:
            r = client.get(f"{BASE}/api/health")
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    return False


def do(client: httpx.Client, ten: str, method: str, path: str, **kw) -> None:
    t0 = time.monotonic()
    try:
        r = client.request(method, f"{BASE}{path}", **kw)
        dt = time.monotonic() - t0
        print(f"  {ten:42s} HTTP {r.status_code:3d}  {dt*1000:8.1f} ms")
    except httpx.HTTPError as exc:
        dt = time.monotonic() - t0
        print(f"  {ten:42s} LOI {exc!r}  {dt*1000:8.1f} ms")


def main() -> int:
    env_file = os.environ.get("FAS_ENV_FILE", "server/.env.selfhost")

    # Buoc 1: dang ky mot user smoke-test qua tien trinh KHONG co quyen dac
    # biet, de lay user_id that.
    env1 = dict(os.environ)
    env1["FAS_ENV_FILE"] = env_file
    env1["PORT"] = str(PORT)
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env1,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    user_id = ""
    email = f"perfprobe-{uuid.uuid4().hex[:12]}@fanficdev.invalid"
    try:
        with httpx.Client(timeout=15.0, trust_env=False) as client:
            if not cho_san_sang(client):
                print("Backend khong san sang (lan 1) — dung.")
                return 1
            r = client.post(f"{BASE}/api/auth/register",
                            json={"email": email, "password": "PerfProbe123",
                                  "display_name": "Perf Probe"})
            if r.status_code != 201:
                print(f"Dang ky that bai: HTTP {r.status_code} {r.text}")
                return 1
            token = r.json().get("token", "")
            me = client.get(f"{BASE}/api/auth/me",
                            headers={"Authorization": f"Bearer {token}"})
            user_id = me.json().get("profile", {}).get("user_id", "")
    finally:
        p.terminate()
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()

    if not user_id:
        print("Khong lay duoc user_id — dung.")
        return 1
    print(f"(user_id thu nghiem: {user_id[:8]}… — chi cap OWNER CUC BO cho tien trinh tam nay)")

    # Buoc 2: khoi lai backend, LAN NAY cap OWNER cuc bo (chi bien moi
    # truong cua tien trinh con, khong ghi gi vao Appwrite) cho dung user_id
    # vua tao, roi dang nhap that + goi that cac route /api/admin/*.
    env2 = dict(env1)
    env2["FAS_OWNER_USER_IDS"] = user_id
    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env2,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            if not cho_san_sang(client):
                print("Backend khong san sang (lan 2) — dung.")
                return 1
            r = client.post(f"{BASE}/api/auth/login",
                            json={"email": email, "password": "PerfProbe123"})
            if r.status_code != 200:
                print(f"Dang nhap that bai: HTTP {r.status_code}")
                return 1
            token = r.json().get("token", "")
            h = {"Authorization": f"Bearer {token}"}

            print("\n=== Do tre /api/admin/* (OWNER that, Appwrite dev that) ===")
            do(client, "GET /api/admin/overview", "GET", "/api/admin/overview", headers=h)
            do(client, "GET /api/admin/overview (lan 2)", "GET", "/api/admin/overview", headers=h)
            do(client, "GET /api/admin/analytics/detail?range=7d", "GET",
              "/api/admin/analytics/detail", params={"range": "7d"}, headers=h)
            do(client, "GET /api/admin/users?limit=25", "GET", "/api/admin/users",
              params={"limit": 25}, headers=h)
            do(client, "GET /api/admin/animation/series?limit=25", "GET",
              "/api/admin/animation/series", params={"limit": 25}, headers=h)
            do(client, "GET /api/admin/animation/sources", "GET",
              "/api/admin/animation/sources", headers=h)
            do(client, "GET /api/admin/animation/imports?limit=25", "GET",
              "/api/admin/animation/imports", params={"limit": 25}, headers=h)
            do(client, "GET /api/admin/image-studio/spending", "GET",
              "/api/admin/image-studio/spending", headers=h)
            do(client, "GET /api/admin/events?limit=25", "GET", "/api/admin/events",
              params={"limit": 25}, headers=h)
    finally:
        p2.terminate()
        try:
            p2.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p2.kill()

    print(f"\n(user thu nghiem {email} khong tu xoa — anh huong khong dang ke,"
         " co the don tay qua Appwrite console)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
