"""Noi farmer voi ha tang THAT — va chi noi, khong xay lai.

Moi ham o day la mot ban chuyen doi mong: no dich mot `Candidate` sang dung
loi goi ma kho nay DA CO, roi tra ket qua ve. Khong mot cong doan san xuat
nao duoc viet lai o day.

    kham pha truyen chu  -> `server.scraper` (FanFicFare/HTTP fetcher)
    tao ban nhap         -> `POST /api/novels` + `/api/chapters` (cung duong
                            ma `ship_*_runner.py` da dung, cung tinh idempotent)
    TTS                  -> `POST /api/jobs` roi `tts_dispatch.enqueue`
                            (Cloud Run — KHONG tong hop tren may gat)
    nap hang doi audio   -> `content_queue` qua `create_queue_item_once`

`DEFAULT_API`/`goi` lay tu `mission_g_rezero_draft_runner` — cung mot ham ma
`chinese_media_pipeline` dang dung, nen token duoc xu ly o DUNG MOT cho.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from server.domain import ChineseMediaQueueItem  # noqa: E402
from server.farmer.dedup import FARMER_OWNER, LANE_AUDIO, LANE_TEXT  # noqa: E402
from server.farmer.loop import Candidate  # noqa: E402

#: Giong san xuat hien tai — cung giong moi runner khac dang dung.
DEFAULT_VOICE_ID = "piper:ngochuyennew"
ENV_VOICE = "FARMER_VOICE_ID"


def _api():
    from mission_g_rezero_draft_runner import DEFAULT_API, goi
    return DEFAULT_API, goi


def harvester_token() -> str:
    """Token dich vu, lay tu broker — KHONG bao gio tu tep trong kho ma."""
    import fanfic_credential_broker as broker

    tok = broker.fetch("FAS_HARVESTER_SERVICE_TOKEN") or ""
    if not tok:
        raise RuntimeError(
            "thieu FAS_HARVESTER_SERVICE_TOKEN — farmer khong ghi duoc gi")
    return tok


# ------------------------------------------------------------- lan audio --
def make_audio_discovery(store: Any) -> Callable[[int], Sequence[Candidate]]:
    """Kham pha nguon audio qua CHINH watcher da co.

    Dung lai `chinese_media_watcher`: cong dieu kien thoi luong, phan loai
    quyen, va `queue_item_id` tat dinh deu da song o do. Farmer khong tu do
    thoi luong hay tu phan loai quyen lan nua.
    """
    def discover(gioi_han: int) -> List[Candidate]:
        from chinese_media_watcher import (
            fetch_channel_feed, probe_duration_seconds, queue_item_id,
        )
        from server.scraper import media_eligibility
        from server.scraper.chinese_media_sources import actionable_sources

        cap = media_eligibility.max_source_seconds()
        ra: List[Candidate] = []
        for src in actionable_sources():
            if len(ra) >= gioi_han:
                break
            try:
                entries = fetch_channel_feed(src.channel_id)
            except Exception:
                continue
            for e in entries:
                if len(ra) >= gioi_han:
                    break
                vid = e.get("video_id") or ""
                if not vid:
                    continue
                probed = probe_duration_seconds(vid)
                if probed.state == "unavailable":
                    continue
                verdict = media_eligibility.evaluate(probed.seconds, cap)
                if not verdict.eligible:
                    continue
                ra.append(Candidate(
                    lane=LANE_AUDIO,
                    url=f"https://www.youtube.com/watch?v={vid}",
                    title=e.get("title") or "",
                    queue_item_id=queue_item_id(src.platform, vid),
                    meta={"source_id": src.source_id,
                          "platform": src.platform,
                          "episode_ref": vid,
                          "description": e.get("description") or "",
                          "duration_seconds": probed.seconds},
                ))
        return ra
    return discover


def make_audio_enqueuer(store: Any) -> Callable[[Candidate], None]:
    """Nap MOT muc vao `content_queue` — va dung o do.

    Farmer khong chay cac cong doan cua orchestrator: boc loi la ASR, va ASR
    tren may nay chay 0,96x thoi gian thuc.
    """
    def enqueue(c: Candidate) -> None:
        from chinese_media_watcher import find_source_captions
        from server.scraper.chinese_media_sources import classify_rights

        meta = c.meta or {}
        co_phu_de = False
        try:
            co_phu_de = find_source_captions(
                meta.get("platform", "youtube"),
                meta.get("episode_ref", "")) is not None
        except Exception:
            pass
        item = ChineseMediaQueueItem(
            item_id=c.queue_item_id,
            source_id=meta.get("source_id", "farmer"),
            platform=meta.get("platform", "youtube"),
            series_slug=meta.get("source_id", "farmer"),
            episode_ref=meta.get("episode_ref", ""),
            title=c.title,
            source_url=c.url,
            rights_mode=classify_rights(
                description=meta.get("description", ""),
                has_real_captions=co_phu_de),
        )
        store.create_queue_item_once(item)
    return enqueue


# -------------------------------------------------------------- lan text --
def make_text_fetcher(fetcher: Optional[Any] = None
                      ) -> Callable[[Candidate], str]:
    """Lay + lam sach van ban qua duong trich xuat DA CO.

    Dung `HttpFetcher` mac dinh chu khong `urlopen` tran: no da mang san ba
    thu mot con bo thu thap tu dong BAT BUOC phai co — chan SSRF, ton trong
    `robots.txt`, va gioi han toc do theo host. Tu viet lai mot fetcher o day
    la vut bo ca ba.
    """
    def fetch(c: Candidate) -> str:
        from server.scraper.html_extract import extract
        from server.scraper.http_fetcher import HttpFetcher

        # FanFicFare TRUOC, cho host no ho tro: no hieu phan trang chuong,
        # sieu du lieu, va cach tung site dung HTML — mot phep trich xuat
        # tong quat tren mot trang fanfic nhieu chuong se ra mot mo dieu
        # huong lan van ban.
        #
        # `resolve_acquisition_route` la nguoi quyet dinh, khong phai mot danh
        # sach host viet tay o day: no da biet host nao FanFicFare an duoc,
        # va no KHONG BAO GIO tra ve mot duong can trinh duyet/cloudscraper.
        if fetcher is None:
            try:
                van_ban = _thu_fanficfare(c.url)
                if van_ban:
                    return van_ban
            except Exception:
                # FanFicFare hong -> roi ve HTTP thuong. Mot nguon lay duoc
                # bang duong tong quat van tot hon khong lay duoc gi.
                pass

        client = fetcher or HttpFetcher()
        ket_qua = client.fetch(c.url)
        # 304 tra than RONG theo giao thuc — doc no nhu "trang rong that su"
        # se dua mot chuoi rong vao cong danh gia va tieu mot lan goi co phi.
        if ket_qua.not_modified:
            raise RuntimeError(f"nguon tra 304 (khong doi): {c.url}")
        return extract(ket_qua.text).visible_text()
    return fetch


def _thu_fanficfare(url: str) -> str:
    """Lay truyen qua FanFicFare neu host duoc ho tro. Rong = khong dung duoc.

    Ghep cac chuong thanh MOT van ban de dua qua cong danh gia — cong danh gia
    cham diem tac pham, khong cham diem tung chuong.
    """
    import tempfile
    from pathlib import Path as _Path

    from server.scraper.fanficfare_provider import (
        parse_fanficfare_epub, resolve_acquisition_route, _run_fanficfare_cli,
    )

    if resolve_acquisition_route(url) != "fanficfare":
        return ""
    with tempfile.TemporaryDirectory(prefix="farmer-fff-") as tmp:
        ket_qua = _run_fanficfare_cli(url, workdir=_Path(tmp))
        if not ket_qua.ok or not ket_qua.epub_path:
            return ""
        acq = parse_fanficfare_epub(ket_qua.epub_path)
        return "\n\n".join(
            ch.content for ch in (acq.chapters or []) if (ch.content or "").strip())


def make_text_publisher(token: str) -> Callable[[Candidate, str], str]:
    """Tao Novel + Chapter o trang thai NHAP qua API that.

    Idempotent theo `external_source_url` — cung quy tac ma `ship_draft` dung,
    nen mot lan chay lai khong sinh ban trung.
    """
    def publish(c: Candidate, body: str) -> str:
        api, goi = _api()
        meta = c.meta or {}

        ma, r = goi(api, "POST", "/api/novels", {
            "title": c.title or "(khong tieu de)",
            "description": (meta.get("description")
                            or f"Thu thap tu dong tu {c.url}"),
            "tags": ["Farmer"],
            "publication_mode": "full_text",
            "external_author_name": meta.get("author", ""),
            "external_source_url": c.url,
            "language": meta.get("language", "vi"),
            "status": "ongoing",
        }, token=token)
        if ma != 201:
            raise RuntimeError(f"POST /api/novels -> {ma}: {r}")
        novel_id = (r.get("novel") or r)["novel_id"]

        ma, r = goi(api, "POST", "/api/chapters", {
            "novel_id": novel_id,
            "title": c.title or "Chuong 1",
            "content": body,
            "order_index": 1,
        }, token=token)
        if ma != 201:
            raise RuntimeError(f"POST /api/chapters -> {ma}: {r}")
        return novel_id
    return publish


def make_tts_enqueuer(token: str) -> Callable[[str], Optional[str]]:
    """Tao job TTS roi bao Cloud Run — tong hop KHONG chay tren may gat."""
    def enqueue(novel_id: str) -> Optional[str]:
        api, goi = _api()
        voice = os.environ.get(ENV_VOICE) or DEFAULT_VOICE_ID

        ma, r = goi(api, "GET", f"/api/novels/{novel_id}", token=token)
        if ma != 200:
            raise RuntimeError(f"GET /api/novels/{novel_id} -> {ma}: {r}")
        chapters = sorted(r.get("chapters") or [],
                          key=lambda c: c.get("order_index", 0))
        if not chapters:
            raise RuntimeError(f"{novel_id} chua co chuong nao de doc")

        ma, r = goi(api, "POST", "/api/jobs", {
            "chapter_id": chapters[0]["chapter_id"], "voice_id": voice,
        }, token=token)
        if ma != 201:
            raise RuntimeError(f"POST /api/jobs -> {ma}: {r}")
        job_id = (r.get("job") or r)["job_id"]

        # Bao cho Cloud Run. `enqueue` tra None khi dieu phoi TAT — do la
        # cau hinh hop le (worker se tu nhat), khong phai loi.
        from server import tts_dispatch

        return tts_dispatch.enqueue(job_id)
    return enqueue
