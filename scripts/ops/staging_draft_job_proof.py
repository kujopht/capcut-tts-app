"""Chung minh CHINH MAY NAY nhan va hoan tat mot job DRAFT that.

Chay TREN may staging, bang user dich vu (doc duoc /etc/fanfic-audio/*.env):

    python -m scripts.ops.staging_draft_job_proof

VI SAO DETERMINISTIC MA KHONG PHAI DUNG WORKER NAO
--------------------------------------------------
Hang doi staging dang duoc CHIA voi mot worker khac (`fanfic-staging-worker`
tren GCE, chay lien tuc tu 2026-08-23). Neu chi tao mot job binh thuong roi
xem no xong, ta chi chung minh "mot trong hai worker lam duoc" — khong phai
"MAY NAY lam duoc".

Nhung `server/main.py` da co san mot co che NHUONG chinh xac cho viec nay:

    if (not settings.inline_worker
            and not tts_bridge.voice_runnable_on_this_machine(job.voice_id)):
        report["bo_qua_thieu_model"] += 1
        continue

Mot worker CHUYEN TRACH **khong nhan** job co giong ma may no khong co model.
Da do tren may that:

    GCE fanfic-staging-worker : khong co FAS_PIPER_MODELS_DIR,
                                /opt/fanfic-models KHONG ton tai, 0 tep .onnx
    may staging AWS           : 25 .onnx + 25 symlink, co ngochuyennew

Nen mot job `voice_id="piper:ngochuyennew"` CHI may nay nhan duoc. Do la co
che CO SAN cua san pham, khong phai mot duong rieng bay ra de test, va no
KHONG doi dung hay sua worker nao khac.

AN TOAN
-------
- Fixture deu mang tien to `[SMOKE-AWS]`, deu bi xoa o `finally`, ke ca khi
  that bai.
- Novel/Chapter tao ra o trang thai **DRAFT** (mac dinh cua `PublishState`),
  va KHONG buoc nao chuyen sang PUBLIC.
- KHONG in gia tri bi mat. Chi in id fixture, trang thai, va thoi gian.
- Khong cham production: cau hinh den tu /etc/fanfic-audio/*.env cua may nay,
  va bai kiem dau tien la doi `FAS_ENV == staging`.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TIEN_TO = "[SMOKE-AWS]"
GIONG = "piper:ngochuyennew"          # chi may co model moi nhan duoc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--voice", default=GIONG)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--text", default="Đây là một đoạn kiểm thử ngắn.")
    a = ap.parse_args()

    from server.config import get_settings
    s = get_settings()
    moi_truong = (getattr(s, "environment", "") or "").lower()
    print(f"  moi truong        : {moi_truong}")
    if moi_truong != "staging":
        print("DUNG LAI: chi chay tren staging. Khong cham moi truong khac.")
        return 2
    print(f"  data_backend      : {s.data_backend}")
    print(f"  storage_backend   : {s.storage_backend}")
    print(f"  inline_worker     : {s.inline_worker}")
    if s.inline_worker:
        print("DUNG LAI: `inline_worker` phai TAT thi co che nhuong moi ap dung.")
        return 2

    from server import tts_bridge
    chay_duoc = tts_bridge.voice_runnable_on_this_machine(a.voice)
    print(f"  giong {a.voice}")
    print(f"  may NAY chay duoc : {chay_duoc}")
    if not chay_duoc:
        print("DUNG LAI: may nay khong co model cho giong do — job se bi NHUONG "
              "cho may khac, nen phep chung minh mat y nghia.")
        return 3

    from server.domain import Chapter, JobStatus, Novel, PublishState, TtsJob
    from server.main import store

    nguoi = f"smoke-aws-{int(time.time())}"
    novel = chuong = job = None
    t0 = time.time()
    try:
        # -- fixture: novel + chapter, CA HAI o trang thai DRAFT -------------
        novel = store.create_novel(Novel(
            owner_id=nguoi, title=f"{TIEN_TO} novel", description="tam thoi",
            state=PublishState.DRAFT))
        chuong = store.create_chapter(Chapter(
            novel_id=novel.novel_id, owner_id=nguoi,
            title=f"{TIEN_TO} chuong", content=a.text,
            state=PublishState.DRAFT))
        print(f"\n  novel   : {novel.novel_id}  (state={novel.state.value})")
        print(f"  chuong  : {chuong.chapter_id}  (state={chuong.state.value})")
        if chuong.state is not PublishState.DRAFT:
            print("DUNG LAI: chuong khong o DRAFT.")
            return 4

        import hashlib
        bam = hashlib.sha256(a.text.encode("utf-8")).hexdigest()
        job = store.create_job(TtsJob(
            owner_id=nguoi, chapter_id=chuong.chapter_id, voice_id=a.voice,
            content_hash=bam, status=JobStatus.PENDING))
        print(f"  job     : {job.job_id}  (status={job.status.value})")
        print(f"\n  cho worker NAY nhan (toi da {a.timeout:.0f}s) ...")

        cuoi = time.time() + a.timeout
        truoc = ""
        chu = None
        while time.time() < cuoi:
            chu = store.get_job(job.job_id)
            tt = chu.status.value
            if tt != truoc:
                print(f"    [{time.time() - t0:6.1f}s] {tt}"
                      + (f"  lease_owner={chu.lease_owner}" if chu.lease_owner else ""))
                truoc = tt
            if chu.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                break
            time.sleep(2.0)

        giay = time.time() - t0
        if chu is None:
            print("DUNG LAI: khong doc lai duoc job.")
            return 5
        print(f"\n  trang thai cuoi   : {chu.status.value}")
        print(f"  lease_owner       : {chu.lease_owner}")
        print(f"  output_key        : {chu.output_key}")
        print(f"  so phan           : {chu.done_parts}/{chu.total_parts}")
        print(f"  thoi gian tuong   : {giay:.1f}s")
        if chu.error_message:
            print(f"  loi               : {chu.error_kind}: {chu.error_message[:160]}")

        if chu.status is not JobStatus.COMPLETED:
            print("\nFAIL: job khong hoan tat.")
            return 6

        # -- CHINH MAY NAY da nhan job chua? --------------------------------
        # `WORKER_ID` = "<pid>-<hex>". Tien trinh worker chay o dich vu rieng
        # nen pid khac tien trinh nay; doi chieu bang cach hoi he thong xem pid
        # do co phai worker cua may nay khong.
        chu_so_huu = chu.lease_owner or ""
        pid = chu_so_huu.split("-")[0] if "-" in chu_so_huu else ""
        cua_may_nay = False
        if pid.isdigit():
            cua_may_nay = Path(f"/proc/{pid}").exists()
        print(f"\n  pid trong lease_owner : {pid or '(khong ro)'}")
        print(f"  pid do co tren MAY NAY: {cua_may_nay}")
        if not cua_may_nay:
            print("\nFAIL: khong chung minh duoc chinh may nay nhan job.")
            return 7

        print("\nPASS: may NAY nhan va hoan tat mot job DRAFT that.")
        print(f"AWS_DRAFT_SECONDS={giay:.1f}")
        return 0
    finally:
        # Don sach, ke ca khi that bai o tren.
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
    sys.exit(main())
