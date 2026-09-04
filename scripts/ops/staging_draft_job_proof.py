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
#: KHONG dong cung mot ten giong. Giong duoc CHON luc chay theo CA HAI cong
#: (vat ly + san pham) — xem phan chon giong trong `main()`. De rong nghia la
#: "tu chon"; truyen `--voice` de ep mot giong cu the.
GIONG = ""


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

    # CHON giong theo CA HAI cong, thay vi dong cung mot ten.
    #
    # Co HAI cong khac nhau, va lan truoc toi chi nhin mot:
    #   voice_runnable_on_this_machine()  cau hoi VAT LY  — model co tren dia?
    #                                     -> quyet dinh worker NHAN hay NHUONG
    #   voice_is_local_allowed()          cau hoi SAN PHAM — co duoc chao ban?
    #                                     -> `ensure_voice_runnable` nem
    #                                        VOICE_NOT_FOUND neu khong
    #
    # `piper:ngochuyennew` qua cong 1 (model co that tren dia) nhung TRUOT
    # cong 2 (khong nam trong `local_voices`). Hau qua do that: worker NHAN
    # job roi that bai voi "Giọng 'piper:ngochuyennew' hiện không được cung
    # cấp." — job chet chu khong duoc nhuong, va phep chung minh bao FAIL vi
    # mot ly do khong lien quan gi den AWS.
    #
    # Nen o day chon giong dau tien qua CA HAI cong. Van deterministic cho
    # AWS: may GCE staging co 0 tep .onnx nen BAT KY giong `piper:*` nao cung
    # bi no nhuong.
    uu_tien = [a.voice] if a.voice else []
    uu_tien += [v for v in (s.local_voices or ()) if v not in uu_tien]
    giong = ""
    print("\n  chon giong qua CA HAI cong:")
    for v in uu_tien:
        vat_ly = tts_bridge.voice_runnable_on_this_machine(v)
        san_pham = tts_bridge.voice_is_local_allowed(v, s)
        print(f"    {v:24} vat_ly={vat_ly}  duoc_chao_ban={san_pham}")
        if vat_ly and san_pham and not giong:
            giong = v
    if not giong:
        print("\nDUNG LAI: khong giong nao qua duoc CA HAI cong.")
        print("  - qua cong VAT LY nhung truot SAN PHAM -> them vao "
              "`FAS_LOCAL_VOICES` (khoa chinh sach, xem staging_reconcile_env.sh)")
        print("  - truot cong VAT LY -> thieu model tren may nay")
        return 3
    print(f"  -> dung: {giong}")
    a.voice = giong

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
        # GIU LAI chu so huu lease quan sat duoc GIUA LUC CHAY.
        #
        # `server/main.py:2478-2487` ghi job `completed` voi `lease_owner=None`
        # — CO Y, vi job xong thi khong con ai giu lease. Ban truoc cua bai
        # nay doc `lease_owner` SAU khi hoan tat, nen luon nhan chuoi rong va
        # bao exit=7 ("khong chung minh duoc may nay nhan job") du job DA
        # chay xong tot dep. Loi cua phep do, khong phai cua san pham.
        chu_quan_sat = ""
        while time.time() < cuoi:
            chu = store.get_job(job.job_id)
            tt = chu.status.value
            if chu.lease_owner:
                chu_quan_sat = chu.lease_owner
            if tt != truoc:
                print(f"    [{time.time() - t0:6.1f}s] {tt}"
                      + (f"  lease_owner={chu.lease_owner}" if chu.lease_owner else ""))
                truoc = tt
            if chu.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                break
            # Poll day hon 2s: cua so `running` co the rat ngan voi mot doan
            # van ban ngan, va bo mat no la mat bang chung lease.
            time.sleep(0.4)

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

        # -- CHINH MAY NAY da lam job nay chua? -----------------------------
        #
        # BANG CHUNG CHINH (ben, khong dua vao thoi diem do): voi
        # `STORAGE_BACKEND=local`, `LocalStorageAdapter` ghi vao
        # `settings.var_dir / "storage" / <output_key>` — tuc TREN DIA MAY NAY
        # (`server/adapters.py:2166`). Tep audio ton tai o day la bang chung
        # VAT LY rang chinh may nay da tong hop, khong phai suy dien tu mot
        # truong metadata co the bi xoa.
        print("\n  --- bang chung 1 (BEN): hien vat tren dia may nay ---")
        goc = Path(s.var_dir) / "storage"
        tep_ra = goc / (chu.output_key or "")
        co_hien_vat = bool(chu.output_key) and tep_ra.is_file()
        print(f"  goc luu tru cuc bo : {goc}")
        print(f"  tep audio          : {tep_ra}")
        print(f"  ton tai            : {co_hien_vat}"
              + (f"  ({tep_ra.stat().st_size} byte)" if co_hien_vat else ""))

        # BANG CHUNG PHU (co the vang neu bo mat cua so `running`): chu lease
        # quan sat duoc giua luc chay. `WORKER_ID` = "<pid>-<hex>".
        print("\n  --- bang chung 2 (phu): chu lease giua luc chay ---")
        pid = chu_quan_sat.split("-")[0] if "-" in chu_quan_sat else ""
        pid_o_day = Path(f"/proc/{pid}").exists() if pid.isdigit() else False
        print(f"  lease_owner quan sat: {chu_quan_sat or '(bo mat cua so running)'}")
        print(f"  pid con tren may nay: {pid_o_day}")

        if not co_hien_vat:
            print("\nFAIL: khong thay hien vat audio tren dia may nay — "
                  "khong chung minh duoc chinh may nay tong hop.")
            return 7

        print("\nPASS: may NAY nhan va hoan tat mot job DRAFT that.")
        print(f"  hien vat: {tep_ra.stat().st_size} byte tai {goc}")
        print(f"AWS_DRAFT_SECONDS={giay:.1f}")
        return 0
    finally:
        # Hien vat audio smoke: xoa luon, no chi la rac cua phep do.
        try:
            if job is not None:
                j2 = store.get_job(job.job_id)
                if getattr(j2, "output_key", None):
                    t = Path(s.var_dir) / "storage" / j2.output_key
                    if t.is_file():
                        t.unlink()
                        print(f"  da xoa hien vat {t.name}")
        except Exception:  # noqa: BLE001
            pass
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
