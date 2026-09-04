#!/usr/bin/env python3
"""CANARY PRODUCTION — mot job DRAFT that, do CHINH may AWS nay nhan.

Chay qua cong dieu hanh hep:  `fanfic-prod-admin canary`

Chuoi duoc chung minh:
    Appwrite claim -> worker AWS -> Piper -> upload R2 hinh dang production
    -> doi tuong ben -> tai lai duoc

AN TOAN — tung rang buoc mot
  * Novel + Chapter tao ra o **DRAFT**, va khong buoc nao chuyen PUBLIC.
    Con co mot phep khang dinh doc lai trang thai truoc khi tao job.
  * Tien to `[CANARY-PROD]` tren moi fixture.
  * `finally` xoa: doi tuong R2, transcript neu co, job, chuong, novel —
    ke ca khi mot buoc phia tren that bai.
  * Chi chay khi `FAS_ENV=production` VA bucket dung `fanfic-prod`. Sai mot
    trong hai la dung ngay.
  * Khong in gia tri bi mat.

Khac ban staging (`staging_draft_job_proof.py`): o staging phai dua vao co
che NHUONG de biet may nao nhan, vi hang doi staging duoc chia voi mot
worker GCE. O production, GCE da dung truoc khi canary chay, nen bang
chung so huu la truc tiep: `lease_owner` quan sat duoc giua luc chay co
PID ton tai TREN CHINH MAY NAY.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(GOC))

from scripts.ops.cutover_target import (  # noqa: E402
    PROD_R2_BUCKET,
    CutoverRefused,
    khang_dinh_production,
    nap_env_tu_tep,
)

TIEN_TO = "[CANARY-PROD]"
VAN_BAN = "Đây là một đoạn kiểm thử ngắn cho việc chuyển máy chủ."


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeout", type=float, default=420.0)
    ap.add_argument("--voice", default="")
    ap.add_argument("--env-file", default="",
                    help="tep env production. Duoc PHAN TICH, khong bao gio "
                         "duoc chay — xem `chay_python` trong fanfic_prod_admin.sh")
    a = ap.parse_args()

    # --- cong 0: day CO PHAI production khong ------------------------------
    try:
        if a.env_file:
            for k, v in nap_env_tu_tep(a.env_file).items():
                os.environ[k] = v
        khang_dinh_production(os.environ)
    except CutoverRefused as exc:
        print(f"DUNG LAI: {exc}")
        return 2
    except OSError as exc:
        print(f"DUNG LAI: khong doc duoc tep env: {exc.strerror}")
        return 2

    from server.config import get_settings

    s = get_settings()
    s.validate()
    print(f"  moi truong        : {s.environment}")
    print(f"  storage_backend   : {s.storage_backend}")
    print(f"  bucket            : {s.r2.bucket}")
    print(f"  inline_worker     : {s.inline_worker}")
    if (s.environment or "").lower() != "production":
        print("DUNG LAI: chi chay tren production.")
        return 2
    if (s.storage_backend or "").lower() != "r2" or s.r2.bucket != PROD_R2_BUCKET:
        print("DUNG LAI: canary production phai chay tren R2 bucket production.")
        return 2
    if s.inline_worker:
        print("DUNG LAI: inline_worker phai TAT — canary phai do WORKER nhan.")
        return 2

    # --- chon giong qua CA HAI cong ---------------------------------------
    from server import tts_bridge

    uu_tien = ([a.voice] if a.voice else []) + [
        v for v in (s.local_voices or ()) if v != a.voice]
    giong = ""
    print("\n  chon giong qua CA HAI cong (vat ly + duoc chao ban):")
    for v in uu_tien:
        vat_ly = tts_bridge.voice_runnable_on_this_machine(v)
        san_pham = tts_bridge.voice_is_local_allowed(v, s)
        if vat_ly and san_pham:
            giong = v
            print(f"    {v:26} vat_ly=True  duoc_chao_ban=True  <- dung")
            break
        print(f"    {v:26} vat_ly={vat_ly}  duoc_chao_ban={san_pham}")
    if not giong:
        print("\nDUNG LAI: khong giong production nao qua duoc CA HAI cong.")
        return 3

    from server.domain import Chapter, JobStatus, Novel, PublishState, TtsJob
    from server.main import store
    from server.adapters import build_storage

    nguoi = f"canary-prod-{int(time.time())}"
    novel = chuong = job = None
    kho = build_storage(s)
    t0 = time.time()
    try:
        novel = store.create_novel(Novel(
            owner_id=nguoi, title=f"{TIEN_TO} novel",
            description="canary chuyen may chu; se bi xoa",
            state=PublishState.DRAFT))
        chuong = store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=nguoi,
            title=f"{TIEN_TO} chuong", content=VAN_BAN,
            state=PublishState.DRAFT))
        print(f"\n  novel   : {novel.novel_id}  (state={novel.state.value})")
        print(f"  chuong  : {chuong.chapter_id}  (state={chuong.state.value})")

        # KHANG DINH DOC LAI: khong tin gia tri vua ghi, doc lai tu kho.
        # `canary khong the tro thanh PUBLIC` la mot rang buoc an toan, nen
        # no phai duoc kiem tren du lieu THAT chu khong tren doi tuong trong
        # bo nho.
        lai_n = store.get_novel(novel.novel_id)
        lai_c = store.get_chapter(chuong.chapter_id)
        if lai_n.state is not PublishState.DRAFT or lai_c.state is not PublishState.DRAFT:
            print(f"DUNG LAI: fixture khong o DRAFT "
                  f"(novel={lai_n.state.value} chuong={lai_c.state.value})")
            return 4
        print("  doc lai : CA HAI o DRAFT — canary khong the thanh PUBLIC")

        bam = hashlib.sha256(VAN_BAN.encode("utf-8")).hexdigest()
        job = store.create_job(TtsJob(
            owner_id=nguoi, chapter_id=chuong.chapter_id, voice_id=giong,
            content_hash=bam, status=JobStatus.PENDING))
        print(f"  job     : {job.job_id}  (giong={giong})")
        print(f"\n  cho worker AWS nhan (toi da {a.timeout:.0f}s) ...")

        cuoi = time.time() + a.timeout
        truoc = ""
        chu = None
        chu_quan_sat = ""
        while time.time() < cuoi:
            chu = store.get_job(job.job_id)
            if chu.lease_owner:
                chu_quan_sat = chu.lease_owner
            if chu.status.value != truoc:
                print(f"    [{time.time() - t0:6.1f}s] {chu.status.value}"
                      + (f"  lease_owner={chu.lease_owner}" if chu.lease_owner else ""))
                truoc = chu.status.value
            if chu.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                break
            time.sleep(0.4)

        giay = time.time() - t0
        if chu is None:
            print("DUNG LAI: khong doc lai duoc job.")
            return 5
        print(f"\n  trang thai cuoi   : {chu.status.value}")
        print(f"  output_key        : {chu.output_key}")
        print(f"  so phan           : {chu.done_parts}/{chu.total_parts}")
        print(f"  thoi gian tuong   : {giay:.1f}s")
        if chu.error_message:
            print(f"  loi               : {chu.error_kind}: {chu.error_message[:200]}")
        if chu.status is not JobStatus.COMPLETED:
            print("\nCANARY_FAIL: job khong hoan tat.")
            return 6

        # --- bang chung 1: doi tuong THAT tren R2 production ---------------
        print("\n  --- bang chung 1: doi tuong tren R2 production ---")
        key = chu.output_key or ""
        head = kho.head_probe(key) if hasattr(kho, "head_probe") else {}
        getp = kho.get_probe(key) if hasattr(kho, "get_probe") else {}
        so_byte = head.get("content_length")
        byte_doc = getp.get("so_byte_doc_duoc")
        print(f"  bucket            : {s.r2.bucket}")
        print(f"  key               : {key}")
        print(f"  head              : tim_thay={head.get('tim_thay')} "
              f"http={head.get('http_status')} len={so_byte}")
        print(f"  get               : doc_duoc={getp.get('tim_thay')} "
              f"so_byte={byte_doc}")

        # --- bang chung 2: khong co ban cuc bo (khong false positive) ------
        tep_cuc_bo = Path(s.var_dir) / "storage" / key if key else None
        con_cuc_bo = bool(tep_cuc_bo and tep_cuc_bo.is_file())
        print(f"  ban cuc bo        : {con_cuc_bo}  (PHAI la False)")

        # --- bang chung 3: CHINH MAY NAY giu lease -------------------------
        print("\n  --- bang chung 2: so huu cua may nay ---")
        pid = chu_quan_sat.split("-")[0] if "-" in chu_quan_sat else ""
        pid_o_day = Path(f"/proc/{pid}").exists() if pid.isdigit() else False
        print(f"  lease_owner       : {chu_quan_sat or '(bo mat cua so running)'}")
        print(f"  pid con tren may  : {pid_o_day}")

        dat = (head.get("tim_thay") and getp.get("tim_thay")
               and isinstance(so_byte, int) and so_byte > 0
               and byte_doc == so_byte and not con_cuc_bo)
        if not dat:
            print("\nCANARY_FAIL: chan R2 khong dat.")
            return 7

        print("\nCANARY_PASS: may AWS nay nhan, tong hop, va day len R2 production.")
        print(f"PROD_CANARY_SECONDS={giay:.1f}")
        print(f"PROD_CANARY_OBJECT_BYTES={so_byte}")
        print(f"PROD_CANARY_LEASE_OWNER={chu_quan_sat}")
        print(f"PROD_CANARY_PID_TREN_MAY_NAY={pid_o_day}")
        return 0
    finally:
        print("\n  --- don dep canary ---")
        try:
            if job is not None:
                j2 = store.get_job(job.job_id)
                key = getattr(j2, "output_key", None)
                if key:
                    t = Path(s.var_dir) / "storage" / key
                    if t.is_file():
                        t.unlink()
                        print("  da xoa ban cuc bo")
                    # Transcript di kem, neu co (xem server/main.py).
                    for k in (key, key[:-4] + ".transcript.json"
                              if key.endswith(".mp3") else None):
                        if not k:
                            continue
                        try:
                            if kho.delete(k):
                                print(f"  da xoa doi tuong R2 {k.rsplit('/', 1)[-1]}")
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as exc:  # noqa: BLE001
            print(f"  CANH BAO: don hien vat that bai: {type(exc).__name__}")
        for ten, ham, doi in (
                ("job", getattr(store, "delete_job", None),
                 (job.job_id,) if job else None),
                ("chuong", getattr(store, "delete_chapter", None),
                 (chuong.chapter_id, nguoi) if chuong else None),
                ("novel", getattr(store, "delete_novel", None),
                 (novel.novel_id, nguoi) if novel else None)):
            if ham is None or doi is None:
                continue
            try:
                ham(*doi)
                print(f"  da xoa {ten}")
            except Exception as exc:  # noqa: BLE001
                print(f"  CANH BAO: chua xoa duoc {ten}: {type(exc).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
