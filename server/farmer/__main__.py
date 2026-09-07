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
import sys
from pathlib import Path

from server.farmer.covers import CoverGate, build_cover_provider
from server.farmer.loop import ProductionFarmer
from server.farmer.metrics import MetricsWriter, status_path
from server.farmer.quotas import FarmerQuotas
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


def _build(dry_run: bool) -> ProductionFarmer:
    from server.appwrite_store import AppwriteMetadataStore
    from server.config import load_settings
    from server.cover_pipeline import CoverPipelineService
    from server.farmer import adapters

    settings = load_settings()
    store = AppwriteMetadataStore(settings.appwrite)
    quotas = FarmerQuotas()

    # `--dry-run` van chay duoc khi CHUA co khoa Gemini: no chi kham pha,
    # khu trung lap, va do han muc — khong muc nao di toi cong danh gia vi
    # khong muc nao duoc san xuat. Nho vay nguoi van hanh kiem duoc nua duoi
    # cua duong day TRUOC khi dat khoa vao may.
    #
    # Duong CHAY THAT thi khong: `build_reviewer()` nem, va `main()` tra
    # BLOCKED. Khong co khoa thi khong duyet, khong duyet thi khong san xuat.
    if dry_run:
        try:
            reviewer = build_reviewer()
        except ReviewUnavailable:
            reviewer = _ReviewerVangMat()
    else:
        reviewer = build_reviewer()

    covers = CoverGate(
        CoverPipelineService(media_asset_store=store,
                             provider=build_cover_provider()),
        media_asset_store=store)

    token = "" if dry_run else adapters.harvester_token()

    if dry_run:
        def khong_ghi(*a, **k):
            raise RuntimeError("--dry-run: khong ghi gi")
        publish, enqueue_tts, enqueue_audio = khong_ghi, khong_ghi, khong_ghi
    else:
        publish = adapters.make_text_publisher(token)
        enqueue_tts = adapters.make_tts_enqueuer(token)
        enqueue_audio = adapters.make_audio_enqueuer(store)

    return ProductionFarmer(
        store=store, quotas=quotas, reviewer=reviewer, cover_gate=covers,
        metrics_writer=MetricsWriter(),
        discover_audio=adapters.make_audio_discovery(store),
        discover_text=_text_discovery(),
        fetch_text=adapters.make_text_fetcher(),
        publish_text=publish, enqueue_tts=enqueue_tts,
        enqueue_audio_item=enqueue_audio)


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
        for muc in (data.get("sources") or [])[:gioi_han]:
            url = (muc.get("url") or "").strip()
            if not url:
                continue
            ra.append(Candidate(lane=LANE_TEXT, url=url,
                                title=muc.get("title", ""),
                                meta=muc))
        return ra
    return discover


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="chay MOT vong roi thoat")
    ap.add_argument("--dry-run", action="store_true",
                    help="khong ghi gi — chi kham pha, khu trung lap, va bao cao")
    ap.add_argument("--sleep", type=int, default=None,
                    help="giay nghi giua hai vong (mac dinh lay tu cau hinh)")
    ap.add_argument("--status", action="store_true",
                    help="in tep trang thai hien tai roi thoat")
    args = ap.parse_args(argv)

    if args.status:
        p = status_path()
        if not p.is_file():
            print(json.dumps({"status": "CHUA_CHAY", "path": str(p)}))
            return 1
        print(p.read_text(encoding="utf-8"))
        return 0

    try:
        farmer = _build(args.dry_run)
    except ReviewUnavailable as exc:
        # Fail closed ngay tu luc khoi dong: khong co cong danh gia thi
        # farmer khong duoc phep san xuat gi ca.
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         ensure_ascii=False))
        return 2

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
