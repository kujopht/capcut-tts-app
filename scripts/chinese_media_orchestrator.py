#!/usr/bin/env python3
"""Chinese Media Orchestrator — hang doi `content_queue` -> san pham that.

Day la ban tieu thu (consumer) ma HAI cho trong ma nguon da goi ten truoc
khi no ton tai:

  * `server/domain.py::ChineseMediaQueueItem` — "xem
    `scripts/chinese_media_watcher.py` (tao) va
    `scripts/chinese_media_orchestrator.py` (chay tiep)"
  * `server/appwrite_store.py::list_queue_items_by_state` — "muc dich duy
    nhat cua ham nay la nguon viec cho `chinese_media_orchestrator.py`"

`chinese_media_watcher.py` chi PHAT HIEN va ghi hang doi. Toan bo cong doan
xu ly da co san, da QA_PASS, va DONG BANG trong `chinese_media_pipeline.py`.
Tep nay KHONG sao chep mot dong logic nao cua chung — no chi *dieu phoi*:
chon viec, kiem tien dieu kien, goi dung ham, roi ghi lai trang thai tung
cong doan vao hang doi.

## Vi sao can no — chi phi do duoc, khong phai gia dinh

`chinese_media_pipeline.main()` la duong chay MOT tap, KHONG diem dung.
Chinh docstring cua `translate_zh_to_vi()` ghi lai gia phai tra: bon lan thu
noi lai ung vien #2, "each requiring a fresh ~35-90 min ASR re-run, since
transcript output is never checkpointed to disk".

Truong `transcript_key` trong schema `content_queue` sinh ra dung de chua
diem dung do — va cho toi tep nay, KHONG CO GI ghi vao no. Orchestrator ghi
transcript (ZH, kem timestamp) len R2 ngay khi ASR xong, nen mot lan chay
lai KHONG BAO GIO lam lai ASR.

## Do thi phu thuoc giua cac cong doan

    transcript -> translation -> subtitle -+-> dub (tuy chon)
                                           +-> draft  (can subtitle DONE va
                                                       dub DONE/SKIPPED)

    render: NHANH RIENG, co cong quyen — xem `stage_render`.

`draft` KHONG cho `render`. Do la dung hanh vi da chung minh cua
`chinese_media_pipeline.main()`: no ship draft (phu de + dub) ma khong render
gi ca, vi khong duoc phep giu lai byte media goc.

## Ky luat ban quyen — cuong che bang MA, khong bang loi hua

1. Tep nay KHONG BAO GIO tai media tu YouTube/Bilibili/bat ky dau. Cung dung
   ranh gioi `chinese_media_pipeline.py` tu dat cho minh: buoc lay media la
   quyet dinh RIENG cua nguoi van hanh cho tung ung vien, va o day duoc dua
   vao qua `--audio` (mot tep CUC BO nguoi van hanh cung cap).
2. Cong doan `render` chi chay voi `rights_mode="REHOST_ALLOWED"`. Moi gia
   tri khac -> `SKIPPED` kem ly do, khong bao gio la `FAILED`: day la quyet
   dinh co chu dich, khong phai su co. Ca 30 muc that dang nam trong hang
   doi hom nay deu `REFERENCE_ONLY`.
3. Khong co bien moi truong / co dong lenh nao trong tep nay noi long duoc
   dieu 2.

## Gia dinh MOT nguoi ghi — noi thang gioi han

Cong cu nay AN TOAN khi mot tien trinh chay tai mot thoi diem. No **khong**
an toan khi hai tien trinh cung rut mot hang doi.

Ly do la co that va khong vong qua duoc o tang nay: Appwrite khong co cap
nhat CO DIEU KIEN, va schema `content_queue` khong co truong lease. Nen
khong the "gianh" mot cong doan mot cach nguyen tu. Hai tien trinh cung doc
mot muc PENDING se cung chay ASR; ket qua ve muon co the ghi de trang thai
moi hon; hai lan that bai dong thoi deu ghi `attempts = cu + 1` va lam mat
mot luot.

Da lam duoc gi: doc lai muc ngay truoc khi ghi RUNNING va bo qua neu trang
thai da doi. Dieu do THU HEP cua so, khong dong duoc no.

Muon dong han thi phai them truong lease (`lease_owner`, `lease_expires`)
vao schema `content_queue` — mot lan migration tren Appwrite production, co
y KHONG lam trong phien nay.

## PENDING khac FAILED — va vi sao phan biet nay quan trong

Mot muc thieu media do nguoi van hanh cung cap thi **giu nguyen PENDING** va
KHONG bi cong `attempts`. No khong that bai; no chua toi luot. Danh dau
FAILED se lam no dung han sau `--max-attempts` lan chay khong lam gi ca —
mot cach im lang danh mat viec.

Usage:
    python -m scripts.chinese_media_orchestrator --status
    python -m scripts.chinese_media_orchestrator --dry-run
    python -m scripts.chinese_media_orchestrator --item cmq_ab12 --audio ep1.wav --dub
    python -m scripts.chinese_media_orchestrator --limit 5
    python -m scripts.chinese_media_orchestrator --reclaim-stale 120
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.domain import ChineseMediaQueueItem  # noqa: E402

import chinese_media_pipeline as pipeline  # noqa: E402

#: Thu tu chay. `render` co y dat SAU `draft`: no la nhanh rieng, va dat cuoi
#: de mot lan chay bi ngat van kip ship draft truoc.
STAGE_ORDER = ("transcript", "translation", "subtitle", "dub", "draft", "render")

#: Cong doan -> ten truong trang thai trong `content_queue`.
STAGE_FIELD = {s: f"{s}_state" for s in STAGE_ORDER}

#: Tien dieu kien: cong doan -> {cong doan truoc: cac trang thai chap nhan}.
STAGE_REQUIRES: Dict[str, Dict[str, tuple]] = {
    "transcript": {},
    "translation": {"transcript": ("DONE",)},
    "subtitle": {"translation": ("DONE",)},
    "dub": {"subtitle": ("DONE",)},
    # `draft` can biet dub DA NGA NGU chua (DONE hay SKIPPED) de dinh kem
    # dung tep — cho o giua se ship mot draft thieu dub roi khong bao gio
    # quay lai sua.
    "draft": {"subtitle": ("DONE",), "dub": ("DONE", "SKIPPED")},
    "render": {"subtitle": ("DONE",)},
}

#: Cung chu so huu R2 ma `chinese_media_pipeline.ship_draft` va
#: `AppwriteMetadataStore.CONTENT_QUEUE_OWNER` dang dung.
R2_OWNER = "svc_harvester"

#: Tran mot trang truy van Appwrite. Giu bang `server.appwrite_store.PAGE_SIZE`
#: — khong import truc tiep de tep nay con nap duoc khi chua co cau hinh
#: Appwrite (moi bai test o `scripts/tests` deu nap no nhu vay).
QUERY_PAGE_SIZE = 100


def transcript_key(item_id: str) -> str:
    return f"transcripts/{R2_OWNER}/{item_id}.json"


def subtitle_key(item_id: str) -> str:
    return f"subtitles/{R2_OWNER}/{item_id}.srt"


def dub_key(item_id: str) -> str:
    return f"dub_audio/{R2_OWNER}/{item_id}.mp3"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> Optional[datetime]:
    """`updated_at` la chuoi ISO do `server.domain.now_iso()` sinh. Mot muc co
    dau thoi gian khong doc duoc thi coi nhu KHONG the doi tuoi — an toan hon
    la doan no da cu roi cuop lai viec cua mot tien trinh dang song."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class Outcome:
    """Ket qua MOT cong doan tren MOT muc.

    `state` la gia tri se ghi vao `<stage>_state`. `fields` la cac truong khac
    ghi cung mot the (vd `transcript_key`, `novel_id`).
    """

    state: str                      # PENDING | RUNNING | DONE | SKIPPED | FAILED
    note: str = ""
    fields: Dict[str, Any] = field(default_factory=dict)
    #: True khi muc dung lai vi thieu dau vao nguoi van hanh phai cung cap.
    #: KHONG cong `attempts` — xem docstring dau tep.
    blocked: bool = False


@dataclass
class Context:
    store: Any
    token: str = ""
    ffmpeg: str = ""
    dub_enabled: bool = False
    whisper_model: str = "small"
    #: item_id -> tep media CUC BO do nguoi van hanh cung cap.
    audio: Dict[str, Path] = field(default_factory=dict)
    dry_run: bool = False
    max_attempts: int = 3
    #: item_id -> ket qua `find_source_captions`. Precheck phai goi ham nay de
    #: biet mot muc co bi chan hay khong; nho lai de cong doan that KHONG goi
    #: lan hai qua mang.
    captions_cache: Dict[str, Optional[List[pipeline.Segment]]] = field(default_factory=dict)

    def audio_for(self, item: ChineseMediaQueueItem) -> Optional[Path]:
        path = self.audio.get(item.item_id)
        if path and path.is_file():
            return path
        return None

    def captions_for(self, item: ChineseMediaQueueItem):
        if item.item_id not in self.captions_cache:
            self.captions_cache[item.item_id] = pipeline.find_source_captions(
                item.platform, item.episode_ref)
        return self.captions_cache[item.item_id]


# ---------------------------------------------------------------------------
# Doc/ghi diem dung transcript tren R2. Chieu GHI dung lai nguyen
# `pipeline.upload_to_r2` (cung credential, cung duong ghi); chieu DOC khong
# ton tai o do nen mo o day, van qua `R2StorageAdapter` chinh chu.
# ---------------------------------------------------------------------------

def _r2_adapter():
    import os

    os.environ.setdefault("FAS_ENV_FILE",
                          str(REPO_ROOT / "server" / ".env.production"))
    from server.config import get_settings
    from server.r2_adapter import R2StorageAdapter

    return R2StorageAdapter(get_settings().r2)


def download_from_r2(key: str) -> bytes:
    return _r2_adapter().get(key)


def exists_in_r2(key: str) -> bool:
    """Dung de NHAT LAI diem dung ASR sau mot lan sap tien trinh.

    Co mot khe cua so that giua luc tai transcript len R2 va luc ghi
    `transcript_key` vao Appwrite. Tien trinh chet dung trong khe do se de lai
    mot object DUNG tren R2 ma hang doi khong biet — va lan chay sau se chay
    lai ASR (35-90 phut) mot cach vo ich. Vi khoa la TAT DINH theo `item_id`,
    chi can hoi R2 xem no co san chua."""
    try:
        return _r2_adapter().exists(key)
    except Exception:
        # Khong hoi duoc R2 thi coi nhu chua co: chay lai ASR ton kem nhung
        # DUNG, con bo qua nham thi mat han transcript.
        return False


def segments_to_json(segments: List[pipeline.Segment]) -> bytes:
    payload = {
        "version": 1,
        "segments": [
            {"start": s.start, "end": s.end, "zh_text": s.zh_text,
             "vi_text": s.vi_text}
            for s in segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def segments_from_json(raw: bytes) -> List[pipeline.Segment]:
    payload = json.loads(raw.decode("utf-8"))
    return [
        pipeline.Segment(start=float(s["start"]), end=float(s["end"]),
                         zh_text=s.get("zh_text", ""), vi_text=s.get("vi_text", ""))
        for s in payload.get("segments", [])
    ]


# ---------------------------------------------------------------------------
# Cac cong doan. Moi ham nhan (ctx, item) va tra ve Outcome — khong ham nao tu
# ghi vao store; viec ghi tap trung o `run_stage()` de MOT cho duy nhat chiu
# trach nhiem ve `attempts`/`last_error`/RUNNING.
# ---------------------------------------------------------------------------

def precheck_transcript(ctx: Context, item: ChineseMediaQueueItem) -> Optional[Outcome]:
    # Khong bao gio lam lai ASR neu diem dung da co — day la toan bo ly do ton
    # tai cua truong `transcript_key`.
    if item.transcript_key:
        return Outcome("DONE", "transcript da co diem dung, khong chay lai ASR")

    # Nhat lai diem dung mo coi sau mot lan sap tien trinh: khoa tat dinh nen
    # chi can hoi R2. Khong lam buoc nay thi mot lan chet dung khe cua so se
    # tra gia bang mot luot ASR 35-90 phut hoan toan vo ich.
    #
    # Nhung KHONG duoc tin moi su ton tai. Mot lan tai len dut doan de lai
    # object rong/hong; nhan bua no la DONE se tao ra mot cai bay khong loi ra:
    # `transcript_key` da co nen ASR khong bao gio chay lai, con moi cong doan
    # sau deu chet khi doc. Phai tai ve va doc thu that su.
    key = transcript_key(item.item_id)
    if exists_in_r2(key):
        try:
            recovered = segments_from_json(download_from_r2(key))
        except Exception as exc:                                # noqa: BLE001
            recovered = []
            print(f"[transcript] diem dung tai {key} khong doc duoc "
                  f"({type(exc).__name__}), se chay lai ASR")
        if recovered:
            return Outcome("DONE",
                           f"nhat lai diem dung transcript tren R2 "
                           f"({len(recovered)} doan)",
                           fields={"transcript_key": key})

    if ctx.audio_for(item) is not None:
        return None
    if ctx.captions_for(item) is not None:
        return None
    return Outcome(
        "PENDING",
        "khong co phu de goc; can media CUC BO do nguoi van hanh cung cap "
        "(--audio). Cong cu nay khong tai media tu nguon.",
        blocked=True,
    )


def stage_transcript(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    segments = ctx.captions_for(item)
    if segments is None:
        audio_path = ctx.audio_for(item)
        if audio_path is None:                       # precheck da chan truoc
            return Outcome("PENDING", "khong co nguon transcript", blocked=True)
        segments = pipeline.transcribe_mandarin(audio_path, ctx.whisper_model)

    if not segments:
        return Outcome("FAILED", "khong tim thay doan tieng noi nao")

    key = transcript_key(item.item_id)
    pipeline.upload_to_r2(key, segments_to_json(segments), "application/json")
    return Outcome("DONE", f"{len(segments)} doan da luu diem dung",
                   fields={"transcript_key": key})


def precheck_needs_transcript(ctx: Context, item: ChineseMediaQueueItem) -> Optional[Outcome]:
    if not item.transcript_key:
        return Outcome("PENDING", "chua co transcript_key", blocked=True)
    return None


def stage_translation(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    segments = segments_from_json(download_from_r2(item.transcript_key))
    if not segments:
        return Outcome("FAILED", "diem dung transcript rong")
    if all(s.vi_text for s in segments):
        return Outcome("DONE", "da dich san, khong dich lai")

    # `translate_zh_to_vi` sua `vi_text` tai cho va giu nguyen `zh_text`, nen
    # ghi de len CUNG mot khoa vua an toan vua van resume duoc.
    pipeline.translate_zh_to_vi(segments)
    translated = sum(1 for s in segments if s.vi_text)

    # Ghi lai phan da dich TRUOC khi phan xu thanh/bai: du co thieu doan, cong
    # sue da bo ra khong duoc mat, va lan chay sau chi phai dich phan con lai.
    pipeline.upload_to_r2(item.transcript_key, segments_to_json(segments),
                          "application/json")

    if translated < len(segments):
        # DICH THIEU KHONG PHAI LA XONG. Neu danh dau DONE o day, cong doan
        # phu de se lang le loc bo cac doan chua dich va cho ra mot ban phu de
        # THIEU NOI DUNG ma khong ai biet — con cong doan dich thi khong bao
        # gio chay lai nua.
        return Outcome("FAILED",
                       f"moi dich duoc {translated}/{len(segments)} doan; "
                       f"da luu phan da dich de lan sau dich tiep")
    return Outcome("DONE", f"{translated}/{len(segments)} doan da dich")


def stage_subtitle(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    segments = [s for s in segments_from_json(download_from_r2(item.transcript_key))
                if s.vi_text]
    if not segments:
        return Outcome("FAILED", "khong co doan da dich de dung phu de")

    with tempfile.TemporaryDirectory() as tmp:
        srt_path = Path(tmp) / "subs.srt"
        pipeline.write_srt(segments, srt_path)
        data = srt_path.read_bytes()
    pipeline.upload_to_r2(subtitle_key(item.item_id), data, "text/srt")
    return Outcome("DONE", f"{len(segments)} dong phu de ({len(data)} byte)")


def precheck_dub(ctx: Context, item: ChineseMediaQueueItem) -> Optional[Outcome]:
    if not ctx.dub_enabled:
        return Outcome("SKIPPED", "khong yeu cau dub (--dub tat)")
    if not ctx.ffmpeg:
        return Outcome("PENDING", "khong tim thay ffmpeg", blocked=True)
    return precheck_needs_transcript(ctx, item)


def stage_dub(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    segments = [s for s in segments_from_json(download_from_r2(item.transcript_key))
                if s.vi_text]
    if not segments:
        return Outcome("FAILED", "khong co doan da dich de dub")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dub.mp3"
        pipeline.dub_segments(segments, out, ctx.ffmpeg)
        data = out.read_bytes()
    pipeline.upload_to_r2(dub_key(item.item_id), data, "audio/mpeg")
    return Outcome("DONE", f"dub {len(data)} byte")


def precheck_draft(ctx: Context, item: ChineseMediaQueueItem) -> Optional[Outcome]:
    if not ctx.token:
        return Outcome("PENDING", "khong co FAS_HARVESTER_SERVICE_TOKEN", blocked=True)
    return None


def stage_draft(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    srt_bytes = download_from_r2(subtitle_key(item.item_id))
    dub_bytes = download_from_r2(dub_key(item.item_id)) if item.dub_state == "DONE" else None

    novel_id = pipeline.ship_draft(
        title=item.title or item.episode_ref,
        source_url=item.source_url,
        author="",
        rights_mode=item.rights_mode,
        platform=item.platform,
        embed_ref=item.episode_ref,
        srt_bytes=srt_bytes,
        dub_bytes=dub_bytes,
        token=ctx.token,
        # Khoa TAT DINH theo item_id: mot lan chay lai ghi de dung object cu
        # thay vi de lai mot object mo coi moi lan.
        subtitle_key=subtitle_key(item.item_id),
        dub_key=dub_key(item.item_id),
    )
    return Outcome("DONE", f"draft {novel_id}", fields={"novel_id": novel_id})


def rights_verdict(item: ChineseMediaQueueItem) -> Optional[Outcome]:
    """CONG QUYEN. Khong co duong nao vong qua duoc: mot gia tri rights_mode
    khac REHOST_ALLOWED nghia la chua ai xac lap quyen phan phoi lai media
    goc, nen khong duoc phep tao ban sao co chua byte goc.

    Tach rieng khoi `stage_render` vi phan quyet nay KHONG phu thuoc vao tien
    do duong day: no dung ngay tu luc muc duoc phat hien. `process_item` ap no
    truoc, de mot muc dang cho `--audio` van hien ro `render=SKIPPED` thay vi
    ket PENDING vo thoi han va nhin nhu chinh sach chua duoc ap."""
    if item.rights_mode != "REHOST_ALLOWED":
        return Outcome(
            "SKIPPED",
            f"rights_mode={item.rights_mode} — khong phan phoi lai media goc")
    return None


def precheck_render(ctx: Context, item: ChineseMediaQueueItem) -> Optional[Outcome]:
    verdict = rights_verdict(item)
    if verdict is not None:
        return verdict
    return Outcome(
        "PENDING",
        "REHOST_ALLOWED: render + luu tru la buoc nguoi van hanh chay tay "
        "(chinese_media_pipeline.compose_with_source roi archive_final_render); "
        "orchestrator khong tu render.",
        blocked=True,
    )


def stage_render(ctx: Context, item: ChineseMediaQueueItem) -> Outcome:
    # Khong bao gio toi day: `precheck_render` luon tra ve mot phan quyet.
    return precheck_render(ctx, item)


STAGE_FN: Dict[str, Callable[[Context, ChineseMediaQueueItem], Outcome]] = {
    "transcript": stage_transcript,
    "translation": stage_translation,
    "subtitle": stage_subtitle,
    "dub": stage_dub,
    "draft": stage_draft,
    "render": stage_render,
}

#: Dieu kien kiem duoc RE, chay TRUOC khi danh dau RUNNING. Muc bi chan vi
#: thieu dau vao nguoi van hanh khong duoc di qua trang thai RUNNING: mot lan
#: sap tien trinh o giua se de no ket RUNNING vinh vien du no chua he chay gi.
STAGE_PRECHECK: Dict[str, Callable[[Context, ChineseMediaQueueItem], Optional[Outcome]]] = {
    "transcript": precheck_transcript,
    "translation": precheck_needs_transcript,
    "subtitle": precheck_needs_transcript,
    "dub": precheck_dub,
    "draft": precheck_draft,
    "render": precheck_render,
}


# ---------------------------------------------------------------------------
# Dieu phoi
# ---------------------------------------------------------------------------

def stage_state(item: ChineseMediaQueueItem, stage: str) -> str:
    return getattr(item, STAGE_FIELD[stage])


def unmet_requirement(item: ChineseMediaQueueItem, stage: str) -> Optional[str]:
    for needed, ok_states in STAGE_REQUIRES[stage].items():
        actual = stage_state(item, needed)
        if actual not in ok_states:
            return f"{needed}_state={actual}, can {'/'.join(ok_states)}"
    return None


def run_stage(ctx: Context, item: ChineseMediaQueueItem, stage: str) -> dict:
    """Chay MOT cong doan tren MOT muc va ghi ket qua. Day la cho DUY NHAT ghi
    `<stage>_state` / `attempts` / `last_error`."""
    field_name = STAGE_FIELD[stage]
    record: Dict[str, Any] = {"item_id": item.item_id, "stage": stage}

    unmet = unmet_requirement(item, stage)
    if unmet is not None:
        record.update(state=stage_state(item, stage),
                      note=f"chua du tien dieu kien: {unmet}",
                      skipped_by_orchestrator=True)
        return record

    if item.attempts >= ctx.max_attempts:
        record.update(state=stage_state(item, stage),
                      note=f"attempts={item.attempts} >= max {ctx.max_attempts}",
                      skipped_by_orchestrator=True)
        return record

    # Precheck: moi dieu kien kiem duoc RE deu phai xong TRUOC khi ghi RUNNING.
    # Chi doc, khong ghi — nen an toan ca trong `--dry-run`.
    try:
        pre = STAGE_PRECHECK[stage](ctx, item)
    except Exception as exc:                                    # noqa: BLE001
        pre = Outcome("FAILED", f"{type(exc).__name__}: {exc}")

    if pre is not None:
        if ctx.dry_run:
            record.update(state=pre.state, note=f"dry-run: {pre.note}",
                          blocked=pre.blocked)
            return record
        stale = _stale_claim(ctx, item, stage)
        if stale is not None:
            record.update(**stale)
            return record
        return _commit(ctx, item, stage, pre, record)

    if ctx.dry_run:
        # `--dry-run` la che do LAP KE HOACH, khong phai "chay that roi bo ket
        # qua". Neu goi ham cong doan o day, mot lan `--dry-run` van tot
        # 35-90 phut ASR hoac mot luot quota dich — roi vut di, vi khong duoc
        # phep ghi gi ca. Chi bao se lam gi.
        record.update(state=stage_state(item, stage),
                      note=f"dry-run: se chay cong doan {stage}",
                      would_run=True)
        return record

    stale = _stale_claim(ctx, item, stage)
    if stale is not None:
        record.update(**stale)
        return record

    ctx.store.update_queue_item(item.item_id, **{field_name: "RUNNING"})

    try:
        outcome = STAGE_FN[stage](ctx, item)
    except Exception as exc:                                    # noqa: BLE001
        outcome = Outcome("FAILED", f"{type(exc).__name__}: {exc}")

    return _commit(ctx, item, stage, outcome, record)


def _stale_claim(ctx: Context, item: ChineseMediaQueueItem,
                 stage: str) -> Optional[dict]:
    """Doc lai ngay truoc MOI lan ghi. Tra ve dict mo ta ly do bo qua, hoac
    None neu duoc phep ghi.

    Day KHONG phai compare-and-set that (Appwrite khong co cap nhat co dieu
    kien, va schema `content_queue` khong co truong lease) — no chi thu hep
    cua so. Xem "Gia dinh MOT nguoi ghi" o docstring dau tep.

    FAIL CLOSED: doc lai that bai thi BO QUA muc, khong ghi. Fail open o day
    la sai huong — no cho hai tien trinh cung chay dung vao luc phep kiem an
    toan vua hong."""
    try:
        fresh = ctx.store.get_queue_item(item.item_id)
    except Exception as exc:                                    # noqa: BLE001
        return {"state": stage_state(item, stage),
                "note": f"khong doc lai duoc muc truoc khi ghi: "
                        f"{type(exc).__name__}: {exc}",
                "skipped_by_orchestrator": True}
    if stage_state(fresh, stage) != stage_state(item, stage):
        return {"state": stage_state(fresh, stage),
                "note": "mot tien trinh khac vua doi trang thai cong doan nay",
                "skipped_by_orchestrator": True}
    return None


def _commit(ctx: Context, item: ChineseMediaQueueItem, stage: str,
            outcome: Outcome, record: dict) -> dict:
    """Ghi ket qua MOT cong doan. Cho DUY NHAT dung toi `attempts`/`last_error`."""
    updates: Dict[str, Any] = {STAGE_FIELD[stage]: outcome.state}
    updates.update(outcome.fields)

    # `attempts` la ngan sach cua CA MUC, khong phai cua tung cong doan — do
    # la hinh dang schema, khong doi duoc o day. Nen dem no la "so lan that
    # bai LIEN TIEP": mot cong doan xong thi dat lai ve 0. Neu khong, mot loi
    # ASR som cong voi mot loi dich muon se dung het ngan sach va giet mot muc
    # dang tien trien binh thuong.
    #
    # `last_error` cung la truong CUA CA MUC. Nen gan ten cong doan vao va chi
    # xoa khi CHINH cong doan do thanh cong — neu khong, viec danh dau
    # `render=SKIPPED` se xoa mat loi dich cua mot muc da het luot, de lai mot
    # muc chet ma khong con dau vet chan doan nao.
    if outcome.state == "FAILED":
        updates["attempts"] = item.attempts + 1
        updates["last_error"] = f"{stage}: {outcome.note}"[:1000]
    elif outcome.blocked:
        updates["last_error"] = f"{stage}: CHO: {outcome.note}"[:1000]
    else:
        # CHI `DONE` moi dat lai ngan sach — do la cong viec that su xong.
        # `SKIPPED` la mot quyet dinh chinh sach (vd cong quyen render); coi no
        # la tien bo se hoi sinh mai mai mot muc da chet han.
        if outcome.state == "DONE":
            updates["attempts"] = 0
        if item.last_error.startswith(f"{stage}: "):
            updates["last_error"] = ""

    ctx.store.update_queue_item(item.item_id, **updates)
    # Cap nhat ban sao trong bo nho de cong doan ke tiep trong CUNG mot lan
    # chay nhin thay trang thai moi (vd `transcript_key` vua sinh).
    for key, value in updates.items():
        if hasattr(item, key):
            setattr(item, key, value)

    record.update(state=outcome.state, note=outcome.note, blocked=outcome.blocked)
    return record


def process_item(ctx: Context, item: ChineseMediaQueueItem) -> dict:
    """Day MOT muc di xa nhat co the trong mot lan chay."""
    steps: List[dict] = []

    # Phan quyet ban quyen ap NGAY, khong cho duong day chay toi noi. Neu de
    # no lai cuoi hang, mot muc dang cho `--audio` se ket `render=PENDING` vo
    # thoi han va nhin nhu chinh sach chua he duoc ap — trong khi cau tra loi
    # da chac chan ngay tu dau.
    #
    # Ap cho MOI trang thai render chua phai SKIPPED (ke ca FAILED/DONE tu mot
    # lan chay cu, hoac RUNNING bo lai): phan quyet nay khong phu thuoc tien do
    # va cung khong phu thuoc `attempts`.
    verdict = rights_verdict(item)
    rights_settled = False
    if verdict is not None and item.render_state != "SKIPPED":
        record = {"item_id": item.item_id, "stage": "render"}
        if ctx.dry_run:
            record.update(state=verdict.state, note=f"dry-run: {verdict.note}",
                          blocked=verdict.blocked, dry_run=True)
        else:
            _commit(ctx, item, "render", verdict, record)
        steps.append(record)
        rights_settled = True

    for stage in STAGE_ORDER:
        if stage == "render" and rights_settled:
            # Da phan quyet o tren. Trong `--dry-run` muc trong bo nho khong
            # doi, nen khong chan o day thi vong lap se bao cao render lan hai.
            continue
        current = stage_state(item, stage)
        if current in ("DONE", "SKIPPED"):
            continue
        if current == "RUNNING":
            steps.append({
                "item_id": item.item_id, "stage": stage, "state": "RUNNING",
                "note": "dang chay o mot tien trinh khac; dung --reclaim-stale de thu hoi",
                "skipped_by_orchestrator": True,
            })
            break
        result = run_stage(ctx, item, stage)
        steps.append(result)
        if (result.get("skipped_by_orchestrator")
                or result["state"] not in ("DONE", "SKIPPED")):
            break
    return {"item_id": item.item_id, "title": item.title, "steps": steps}


#: Trang thai cua mot cong doan van con co the lam tiep.
#: `FAILED` PHAI co mat: khong co no, mot muc co cong doan cuoi cung that bai
#: (vd `draft=FAILED`) va moi cong doan khac da ket thuc se KHONG con cong doan
#: `PENDING` nao — hang doi khong bao gio chon lai no nua, du `attempts` van
#: con. Do la mot trang thai KHONG LOI RA, khong phai mot muc cho lau.
RETRYABLE_STATES = ("PENDING", "FAILED")


def collect_work(store, limit: int, max_attempts: int = 3,
                 max_pages: int = 10) -> List[ChineseMediaQueueItem]:
    """Muc con viec = con it nhat MOT cong doan `PENDING` hoac `FAILED` ma
    `attempts` chua het. Gom theo tung cong doan roi khu trung theo item_id
    (mot muc o nhieu cong doan cung luc la chuyen binh thuong).

    PHAN TRANG that su, khong phai lay du rong roi loc: muc het luot van nam
    trong ket qua truy van, nen neu chi lay mot trang thi mot dam muc chet o
    dau danh sach se lam ca hang doi chet doi — moi lan chay tra ve dung chung,
    loai het, roi ve tay khong."""
    seen: Dict[str, ChineseMediaQueueItem] = {}
    for stage in STAGE_ORDER:
        for state in RETRYABLE_STATES:
            offset = 0
            for _ in range(max_pages):
                if len(seen) >= limit:
                    return list(seen.values())[:limit]
                page = store.list_queue_items_by_state(
                    stage=STAGE_FIELD[stage], state=state,
                    limit=QUERY_PAGE_SIZE, offset=offset)
                if not page:
                    break
                for item in page:
                    if item.attempts >= max_attempts:
                        continue
                    seen.setdefault(item.item_id, item)
                    if len(seen) >= limit:
                        break
                if len(page) < QUERY_PAGE_SIZE:
                    break
                offset += QUERY_PAGE_SIZE
    return list(seen.values())[:limit]


def reclaim_stale(store, minutes: int, limit: int = 200,
                  dry_run: bool = False) -> List[dict]:
    """Mot muc ket o RUNNING sau khi tien trinh chet KHONG tu thoat ra duoc:
    schema khong co lease, nen dung `updated_at` lam moc tuoi. CHI chay khi
    duoc yeu cau tuong minh — tu dong thu hoi se cuop viec cua mot tien trinh
    dang thuc su chay."""
    cutoff = _now().timestamp() - minutes * 60
    reclaimed: List[dict] = []
    for stage in STAGE_ORDER:
        for item in store.list_queue_items_by_state(
                stage=STAGE_FIELD[stage], state="RUNNING", limit=limit):
            updated = _parse_iso(item.updated_at)
            if updated is None or updated.timestamp() > cutoff:
                continue
            if not dry_run:
                store.update_queue_item(item.item_id,
                                        **{STAGE_FIELD[stage]: "PENDING"})
            reclaimed.append({"item_id": item.item_id, "stage": stage,
                              "updated_at": item.updated_at,
                              "would_reclaim": dry_run})
    return reclaimed


def queue_status(store, limit: int = 500) -> dict:
    counts: Dict[str, Dict[str, int]] = {}
    for stage in STAGE_ORDER:
        counts[stage] = {
            state: len(store.list_queue_items_by_state(
                stage=STAGE_FIELD[stage], state=state, limit=limit))
            for state in ("PENDING", "RUNNING", "DONE", "SKIPPED", "FAILED")
        }
    return counts


def summarize(reports: List[dict]) -> dict:
    steps = [s for r in reports for s in r["steps"]]
    return {
        "items_examined": len(reports),
        # Mot buoc chi tinh la "da tien" khi no THAT SU duoc ghi: ban ghi cua
        # `--dry-run` va ban ghi bi bo qua deu khong dung toi hang doi.
        "stages_advanced": sum(1 for s in steps if s.get("state") in ("DONE", "SKIPPED")
                               and not s.get("skipped_by_orchestrator")
                               and not s.get("dry_run")),
        "stages_failed": sum(1 for s in steps if s.get("state") == "FAILED"),
        "stages_blocked_on_operator": sum(1 for s in steps if s.get("blocked")),
        "stages_would_run": sum(1 for s in steps if s.get("would_run")),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--item", default="", help="chi xu ly MOT item_id")
    ap.add_argument("--audio", default="",
                    help="tep media CUC BO cho --item (nguoi van hanh cung cap; "
                         "cong cu nay khong tu tai media)")
    ap.add_argument("--limit", type=int, default=10, help="so muc toi da moi lan chay")
    ap.add_argument("--dub", action="store_true", help="bat cong doan dub tieng Viet")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true",
                    help="khong ghi gi (khong Appwrite, khong R2, khong API)")
    ap.add_argument("--status", action="store_true",
                    help="chi in bang trang thai hang doi")
    ap.add_argument("--reclaim-stale", type=int, default=0, metavar="PHUT",
                    help="dat lai ve PENDING cac cong doan ket o RUNNING lau hon PHUT")
    args = ap.parse_args(argv)

    if args.audio and not args.item:
        print(json.dumps({"status": "FAIL",
                          "reason": "--audio chi co nghia khi di kem --item"}))
        return 2

    from server.config import load_settings
    from server.appwrite_store import AppwriteMetadataStore

    store = AppwriteMetadataStore(load_settings().appwrite)

    if args.status:
        print(json.dumps({"status": "PASS", "queue": queue_status(store)},
                         ensure_ascii=False, indent=2))
        return 0

    if args.reclaim_stale:
        reclaimed = reclaim_stale(store, args.reclaim_stale, dry_run=args.dry_run)
        print(json.dumps({"status": "PASS", "dry_run": args.dry_run,
                          "reclaimed": reclaimed},
                         ensure_ascii=False, indent=2))
        return 0

    import fanfic_credential_broker as broker

    token = "" if args.dry_run else (broker.fetch("FAS_HARVESTER_SERVICE_TOKEN") or "")

    ffmpeg = ""
    if args.dub:
        from desktop_app.output_manager import find_ffmpeg

        ffmpeg = find_ffmpeg(None) or ""

    ctx = Context(store=store, token=token, ffmpeg=ffmpeg, dub_enabled=args.dub,
                  whisper_model=args.whisper_model, dry_run=args.dry_run,
                  max_attempts=args.max_attempts)

    if args.item:
        items = [store.get_queue_item(args.item)]
        if args.audio:
            audio_path = Path(args.audio)
            if not audio_path.is_file():
                print(json.dumps({"status": "FAIL",
                                  "reason": f"khong co tep: {audio_path}"}))
                return 2
            ctx.audio[args.item] = audio_path
    else:
        items = collect_work(store, args.limit, args.max_attempts)

    reports = [process_item(ctx, item) for item in items]
    summary = summarize(reports)

    print(json.dumps({
        "status": "PASS" if summary["stages_failed"] == 0 else "PARTIAL",
        "dry_run": args.dry_run,
        **summary,
        "reports": reports,
    }, ensure_ascii=False, indent=2))
    return 0 if summary["stages_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
