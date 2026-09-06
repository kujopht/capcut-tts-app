#!/usr/bin/env python3
"""
CONG DIEU KIEN TIEN QUYET cua canary Cloud Run TTS — chay MOT lenh, tra loi
duy nhat mot cau: da san sang bat canary chua.

    python scripts/ops/canary_prereq_gate.py

CHI DOC. Khong bat gi, khong ghi gi, khong gui job nao. Ma thoat 0 = san sang.

Bon cong, va CA BON deu phai dat:

  1. Hai secret R2 production co mat, va khoa do THAT SU xac thuc + doc duoc
     `fanfic-prod` (goi lai `verify_prod_r2_credential.py`, khong sao chep).
  2. Anh xa `fanfic_world_prod` <-> `fanfic-prod` FAIL CLOSED — kiem bang cach
     hoi chinh `Settings.validate()`, tuc dung ma nguon ma service chay.
  3. Service Cloud Run con TOI: `/health` bao `enabled=false`, `POST /tasks/tts`
     tra 503.
  4. Hang doi Cloud Tasks con PAUSED.

Cong 3 va 4 la co y: mot ban "san sang" ma da tu bat san thi khong phai san
sang, no la mot canary da chay ma khong ai quyet dinh.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

GCP = "gen-lang-client-0793420657"
VUNG = "asia-southeast1"
URL = "https://tts-task-service-1007100453671.asia-southeast1.run.app"
GCLOUD = r"C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"


def _chay(argv, timeout=180):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {e}"


def cong_1_khoa_r2() -> tuple[bool, str]:
    ma, out, err = _chay([sys.executable,
                          str(GOC / "scripts" / "ops" / "verify_prod_r2_credential.py")],
                         timeout=300)
    if ma == 0:
        return True, "khoa R2 production xac thuc + doc duoc fanfic-prod"
    dong = [d for d in (out + "\n" + err).splitlines() if d.strip()]
    return False, dong[-1][:200] if dong else f"exit {ma}"


def cong_2_fail_closed() -> tuple[bool, str]:
    """
    Hoi CHINH `Settings.validate()`, khong viet lai luat o day.

    Phai dung ca hai chieu: cap LECH bi tu choi, va cap DUNG duoc qua. Chi kiem
    mot chieu thi mot `validate()` bi lam rong van "dat".
    """
    from server.config import AppwriteSettings, ConfigError, R2Settings, Settings

    def dung(bucket: str) -> Settings:
        return Settings(
            environment="production", data_backend="appwrite",
            storage_backend="r2", inline_worker=False,
            cors_origins=("https://fanfic.world",),
            appwrite=AppwriteSettings(
                endpoint="https://appwrite-dev.fanfic.world/v1",
                project_id="fanfic-world-prod", api_key="k" * 40,
                database_id="fanfic_world_prod"),
            r2=R2Settings(account_id="a" * 32, access_key_id="b" * 32,
                          secret_access_key="c" * 64, bucket=bucket),
        )

    try:
        dung("fanfic-staging").validate()
        return False, "cap LECH (prod DB + staging bucket) van duoc CHAP NHAN"
    except ConfigError:
        pass
    try:
        dung("fanfic-prod").validate()
    except ConfigError as e:
        return False, f"cap DUNG bi tu choi oan: {str(e)[:120]}"
    return True, "fanfic_world_prod chi di duoc voi fanfic-prod"


def cong_3_service_toi() -> tuple[bool, str]:
    ma, tok, _ = _chay([GCLOUD, "auth", "print-identity-token"])
    if ma != 0 or not tok:
        return False, "khong lay duoc identity token"
    import httpx

    with httpx.Client(timeout=60) as c:
        h = c.get(f"{URL}/health", headers={"Authorization": f"Bearer {tok}"})
        if h.status_code != 200:
            return False, f"/health -> HTTP {h.status_code}"
        bat = h.json().get("enabled")
        if bat is not False:
            return False, f"/health enabled={bat!r} — service KHONG con toi"
        p = c.post(f"{URL}/tasks/tts",
                   headers={"Authorization": f"Bearer {tok}",
                            "Content-Type": "application/json"},
                   json={"job_id": "cong_kiem_khong_ton_tai"})
        if p.status_code != 503:
            return False, f"POST /tasks/tts -> {p.status_code} (phai 503)"
    return True, "service TOI: enabled=false, POST 503"


def cong_4_queue_paused() -> tuple[bool, str]:
    ma, out, _ = _chay([GCLOUD, "tasks", "queues", "describe", "tts-jobs",
                        f"--location={VUNG}", f"--project={GCP}",
                        "--format=value(state)"])
    if ma != 0:
        return False, "khong doc duoc trang thai hang doi"
    return (out == "PAUSED"), f"hang doi = {out}"


def main() -> int:
    cong = [
        ("1 khoa R2 production", cong_1_khoa_r2),
        ("2 fail-closed DB<->bucket", cong_2_fail_closed),
        ("3 service con TOI", cong_3_service_toi),
        ("4 hang doi PAUSED", cong_4_queue_paused),
    ]
    ket = []
    for ten, ham in cong:
        try:
            dat, ghi_chu = ham()
        except Exception as e:
            dat, ghi_chu = False, f"{type(e).__name__}: {str(e)[:150]}"
        ket.append((ten, dat, ghi_chu))
        print(f"  [{'DAT ' if dat else 'TRUOT'}] {ten:28} {ghi_chu}")

    san_sang = all(d for _, d, _ in ket)
    print()
    if san_sang:
        print("CANARY READY = YES")
        print("Buoc dau tien: xem docs/reports/cloudrun-tts-canary-runbook.md muc 2.")
        return 0
    thieu = [t for t, d, _ in ket if not d]
    print(f"CANARY READY = NO — con truot: {', '.join(thieu)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
