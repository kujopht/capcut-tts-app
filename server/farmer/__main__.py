"""Chay farmer: `python -m server.farmer`.

Cung khuon voi `python -m server.worker` ma may AWS da chay — cung thu muc,
cung venv, cung kieu unit systemd. Khong dung mot co che khoi chay thu hai.

    python -m server.farmer --once        # MOT vong, roi thoat
    python -m server.farmer --dry-run     # khong ghi gi, chi bao se lam gi
    python -m server.farmer               # chay mai (systemd goi kieu nay)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from server.farmer.covers import CoverGate, build_cover_provider
from server.farmer.integrity import InterpreterNotSecure, assert_interpreter_secure
from server.farmer.loop import ProductionFarmer
from server.farmer.metrics import MetricsWriter, status_path
from server.farmer.production_writer import ProductionWriter
from server.farmer.quotas import AlreadyRunning, FarmerQuotas, SingleInstanceLock
from server.farmer.review import ReviewUnavailable, build_reviewer


class _ReviewerVangMat:
    """Cho `--dry-run` khi chua co khoa Gemini.

    No KHONG duyet gi — no nem `ReviewUnavailable`, dung nhu mot cong danh
    gia hong that su, nen vong lap fail closed y het. Muc dich duy nhat la
    de `--dry-run` chay den duoc buoc do va BAO CAO thieu khoa, thay vi
    chet ngay luc khoi dung.
    """

    model = "(chua cau hinh)"
    min_score = 0

    def review(self, **kwargs):
        raise ReviewUnavailable(
            "chua co FARMER_GEMINI_API_KEY tren may nay — cong danh gia dong")


def _r2_io():
    """(tai_len, tai_ve) tren R2.

    Cung adapter ma worker/pipeline dang dung — khong mo mot duong R2 thu hai.
    """
    import os as _os

    # Chi tro `FAS_ENV_FILE` vao tep .env.production khi no THAT SU ton tai
    # (may Windows cua nguoi phat trien). Tren may san xuat, bi mat den bang
    # duong systemd `EnvironmentFile=` va tep do khong co — tro vao mot duong
    # dan khong ton tai la mot cach lam ro rang mot cau hinh dang chay tot.
    _env_file = Path(__file__).resolve().parents[2] / "server" / ".env.production"
    if _env_file.is_file():
        _os.environ.setdefault("FAS_ENV_FILE", str(_env_file))
    from server.config import get_settings
    from server.r2_adapter import R2StorageAdapter

    adapter = R2StorageAdapter(get_settings().r2)

    def tai_len(key: str, data: bytes) -> None:
        adapter.put(key, data, "application/json")

    return tai_len, adapter.get, adapter.put


def _build(dry_run: bool) -> ProductionFarmer:
    from server.appwrite_store import AppwriteMetadataStore
    from server.config import load_settings
    from server.cover_pipeline import CoverPipelineService
    from server.farmer import adapters

    # CONG TOAN VEN — truoc moi thu khac. Neu trinh thong dich (hoac duong
    # dan toi no) ghi duoc boi group/other thi moi bao dam con lai deu vo
    # nghia, va farmer khong duoc khoi dong.
    integrity = assert_interpreter_secure()

    settings = load_settings()
    store = AppwriteMetadataStore(settings.appwrite)
    quotas = FarmerQuotas()

    # Cong danh gia MAC DINH la HANG DOI: may nay xep viec, may Windows
    # (Router V4 + pool Antigravity da dang nhap) poll ra ngoai va tra ban an.
    # Khong khoa Gemini o day, va khong co duong roi ve am tham nao sang mot
    # han muc co tra phi — xem `review_provider.build_review_provider`.
    from server.farmer import review_keys
    from server.farmer.review_provider import build_review_provider

    tai_len, tai_ve, dat_object = _r2_io()
    reviewer = build_review_provider(
        store,
        upload_sample=tai_len,
        download_verdict=tai_ve,
        sample_key_for=review_keys.sample_key,
        verdict_key_for=review_keys.verdict_key)

    covers = CoverGate(
        CoverPipelineService(media_asset_store=store,
                             provider=build_cover_provider()),
        media_asset_store=store)

    token = "" if dry_run else adapters.harvester_token()

    # Kho san xuat CHINH TAC. `--dry-run` KHONG duoc ghi gi, nen no khong co
    # writer — va `run_text_lane` cung khong bao gio den do vi buoc tao ban
    # nhap da nem truoc.
    writer = None if dry_run else ProductionWriter(
        put_object=dat_object, get_object=tai_ve)

    if dry_run:
        def khong_ghi(*a, **k):
            raise RuntimeError("--dry-run: khong ghi gi")
        publish, enqueue_tts, enqueue_audio = khong_ghi, khong_ghi, khong_ghi
    else:
        publish = adapters.make_text_publisher(token)
        enqueue_tts = adapters.make_tts_enqueuer(token)
        enqueue_audio = adapters.make_audio_enqueuer(store)

    farmer = ProductionFarmer(
        store=store, quotas=quotas, reviewer=reviewer, cover_gate=covers,
        metrics_writer=MetricsWriter(),
        discover_audio=adapters.make_audio_discovery(store),
        discover_text=_text_discovery(),
        fetch_text=adapters.make_text_fetcher(),
        publish_text=publish, enqueue_tts=enqueue_tts,
        enqueue_audio_item=enqueue_audio, production_writer=writer)
    farmer._integrity = integrity.as_dict()
    return farmer


def _text_discovery():
    """Nguon truyen chu — doc tu tep cau hinh, KHONG nhung danh sach vao ma.

    Mot danh sach nguon nhung cung trong ma nghia la moi lan them mot nguon
    la mot lan deploy. Tep nay o ngoai kho ma, tren chinh may gat.
    """
    import os

    from server.farmer.dedup import LANE_TEXT
    from server.farmer.loop import Candidate

    duong_dan = Path(os.environ.get("FARMER_TEXT_SOURCES")
                     or "/etc/fanfic-audio/farmer-text-sources.json")

    def discover(gioi_han: int):
        if not duong_dan.is_file():
            return []
        try:
            data = json.loads(duong_dan.read_text(encoding="utf-8"))
        except ValueError:
            return []
        ra = []
        for muc in (data.get("sources") or []):
            if len(ra) >= gioi_han:
                break
            # `_disabled: true` = tam tat MOT muc ma khong phai xoa no. Loc
            # TRUOC khi cat theo `gioi_han`, neu khong mot muc da tat van
            # chiem mot suat va lam vong do khong lam duoc gi.
            if muc.get("_disabled"):
                continue
            url = (muc.get("url") or "").strip()
            if not url:
                continue
            ra.append(Candidate(lane=LANE_TEXT, url=url,
                                title=muc.get("title", ""),
                                meta=muc))
        return ra
    return discover


def _verify_credential() -> int:
    """Goi Gemini DUNG MOT lan bang mot cau re nhat, roi bao OK/FAIL.

    KHONG BAO GIO in khoa, va khong in ca do dai khoa hay bon ky tu dau —
    mot "prefix de nhan dang" van la mot phan cua bi mat.

    Ton tai vi buoc kiem trong script bootstrap khong duoc phep dat khoa vao
    dong lenh (`ps` doc duoc argv cua moi tien trinh tren may). O day khoa di
    tu tep env -> bien moi truong cua CHINH tien trinh nay, khong qua argv.
    """
    try:
        reviewer = build_reviewer()
    except ReviewUnavailable as exc:
        print(json.dumps({"credential": "MISSING", "detail": str(exc)},
                         ensure_ascii=False))
        return 2

    try:
        verdict = reviewer.review(
            title="kiem tra khoa",
            body="Day la mot doan van ban ngan de kiem tra khoa API. "
                 "Noi dung khong quan trong; chi can mot lan goi thanh cong.",
            lane="text")
    except ReviewUnavailable as exc:
        print(json.dumps({"credential": "UNUSABLE", "detail": str(exc)[:300]},
                         ensure_ascii=False))
        return 3

    print(json.dumps({
        "credential": "OK",
        "model": verdict.model,
        "min_score": reviewer.min_score,
        # Bang chung khoa THAT SU dung duoc: mot phan hoi co cau truc da ve.
        "sample_score": verdict.score,
    }, ensure_ascii=False))
    return 0


def _check_review_queue() -> int:
    """Kiem duong hang doi danh gia — CHI DOC, khong goi model nao.

    Buoc nay thay cho `--verify-credential` khi che do la `queue`: cai can
    kiem khong con la mot khoa API ma la "hang doi co doc duoc khong". Neu
    collection chua duoc cap phat, bao ro o day thay vi de farmer phat hien
    giua chung roi fail closed im lang.
    """
    from server.appwrite_store import AppwriteMetadataStore
    from server.config import load_settings

    try:
        store = AppwriteMetadataStore(load_settings().appwrite)
        cho = store.list_review_jobs(status="PENDING", limit=1)
    except Exception as exc:                                    # noqa: BLE001
        print(json.dumps({
            "review_queue": "UNAVAILABLE",
            "detail": f"{type(exc).__name__}: {exc}"[:300],
            "hint": "collection 'review_jobs' co the chua duoc cap phat — xem "
                    "docs/reports/OVERNIGHT_BLOCKERS.md muc B1",
        }, ensure_ascii=False))
        return 5

    print(json.dumps({
        "review_queue": "OK",
        "provider": os.environ.get("FARMER_REVIEW_PROVIDER") or "queue",
        "pending_visible": len(cho),
    }, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="chay MOT vong roi thoat")
    ap.add_argument("--dry-run", action="store_true",
                    help="khong ghi gi — chi kham pha, khu trung lap, va bao cao")
    ap.add_argument("--sleep", type=int, default=None,
                    help="giay nghi giua hai vong (mac dinh lay tu cau hinh)")
    ap.add_argument("--status", action="store_true",
                    help="in tep trang thai hien tai roi thoat")
    ap.add_argument("--verify-credential", action="store_true",
                    help="goi Gemini MOT lan de kiem khoa; in OK/FAIL, "
                         "KHONG BAO GIO in khoa (chi khi bat gemini_direct)")
    ap.add_argument("--check-review-queue", action="store_true",
                    help="kiem hang doi danh gia doc duoc khong — KHONG goi "
                         "model nao")
    args = ap.parse_args(argv)

    if args.verify_credential:
        return _verify_credential()

    if args.check_review_queue:
        return _check_review_queue()

    if args.status:
        p = status_path()
        if not p.is_file():
            print(json.dumps({"status": "CHUA_CHAY", "path": str(p)}))
            return 1
        print(p.read_text(encoding="utf-8"))
        return 0

    try:
        farmer = _build(args.dry_run)
    except InterpreterNotSecure as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         ensure_ascii=False))
        return 4
    except ReviewUnavailable as exc:
        # Fail closed ngay tu luc khoi dong: khong co cong danh gia thi
        # farmer khong duoc phep san xuat gi ca.
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         ensure_ascii=False))
        return 2

    # DUNG MOT farmer tai mot thoi diem — ke ca khi mot lan chay tay dam vao
    # dich vu systemd dang chay.
    khoa = SingleInstanceLock()
    try:
        khoa.acquire()
    except AlreadyRunning as exc:
        print(json.dumps({"status": "ALREADY_RUNNING", "reason": str(exc)},
                         ensure_ascii=False))
        return 6

    try:
        return _run(farmer, args)
    finally:
        khoa.release()


def _run(farmer: ProductionFarmer, args) -> int:
    if args.once or args.dry_run:
        lanes = farmer.run_once()
        print(json.dumps(
            {"status": "PASS",
             "lanes": {k: v.as_dict() for k, v in lanes.items()},
             "status_path": str(status_path())},
            ensure_ascii=False, indent=2))
        return 0

    farmer.run_forever(sleep_seconds=args.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
