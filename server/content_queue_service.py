"""Tang dich vu cho hang doi san xuat noi dung (`content_queue`).

Day la be mat WEB cua duong day ma `scripts/chinese_media_orchestrator.py`
tieu thu. Ranh gioi quan trong nhat, va la ly do tep nay ton tai thay vi goi
thang store tu route:

    WEB XEP VIEC VA QUAN LY VIEC. WEB KHONG BAO GIO CHAY VIEC.

Khong mot ham nao o day duoc phep khoi chay orchestrator — khong
`subprocess`, khong thread nen, khong task nen. Mot request "chay lai muc
nay" chi doi trang thai cong doan ve `PENDING`; tien trinh orchestrator DUY
NHAT se nhat no o lan quet ke tiep.

Ly do khong phai kien truc thuan tuy ma la mot rang buoc that: Appwrite khong
co cap nhat CO DIEU KIEN va schema `content_queue` chua co truong lease, nen
hai ban tieu thu chay cung luc co the cung gianh mot muc, cung chay ASR, va
ghi de ket qua cua nhau. Neu moi request web sinh mot tien trinh, so ban tieu
thu se bang so nguoi bam nut. Xem "Gia dinh MOT nguoi ghi" trong docstring cua
orchestrator.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from server.domain import ChineseMediaQueueItem, QUEUE_STAGE_STATES

#: Giu DONG BO voi `scripts/chinese_media_orchestrator.py::STAGE_ORDER`.
#: Khong import cheo: `server/` khong duoc phep phu thuoc vao `scripts/`.
STAGES = ("transcript", "translation", "subtitle", "dub", "draft", "render")

#: Chi hai trang thai nay duoc xep lai. `DONE` thi khong (se lam lai viec da
#: xong va sinh ban trung), `PENDING` thi vo nghia (dang cho san roi).
#: `SKIPPED` TUYET DOI khong — do la mot quyet dinh chinh sach, xem duoi.
REQUEUABLE_STATES = ("FAILED", "RUNNING")

#: Tuoi toi thieu cua mot cong doan `RUNNING` truoc khi web cho phep xep lai.
#: Xep lai mot cong doan dang thuc su chay se tao ra ban tieu thu thu hai cho
#: chinh muc do — dung dieu ma ca tep nay ton tai de ngan.
RUNNING_REQUEUE_MIN_AGE_MINUTES = 120


class QueueActionError(RuntimeError):
    """Hanh dong khong hop le — route dich thanh 409."""


def _overall(item: ChineseMediaQueueItem) -> str:
    """Mot nhan gon cho giao dien, dan xuat chu KHONG luu them truong nao."""
    states = [getattr(item, f"{s}_state") for s in STAGES]
    if any(s == "FAILED" for s in states):
        return "FAILED"
    if any(s == "RUNNING" for s in states):
        return "RUNNING"
    if all(s in ("DONE", "SKIPPED") for s in states):
        return "COMPLETE"
    return "PENDING"


def item_view(item: ChineseMediaQueueItem) -> Dict[str, Any]:
    return {
        "item_id": item.item_id,
        "source_id": item.source_id,
        "platform": item.platform,
        "title": item.title,
        "source_url": item.source_url,
        "rights_mode": item.rights_mode,
        "overall": _overall(item),
        "stages": {s: getattr(item, f"{s}_state") for s in STAGES},
        "novel_id": item.novel_id,
        "has_transcript_checkpoint": bool(item.transcript_key),
        "attempts": item.attempts,
        # `last_error` mang tien to ten cong doan (vd "translation: ..."), va
        # "CHO: " nghia la DANG DOI chu khong phai hong — giao dien phan biet
        # duoc hai thu do ma khong phai doan.
        "last_error": item.last_error,
        "waiting": item.last_error.split(": ", 1)[-1].startswith("CHO: ")
                   if item.last_error else False,
        "updated_at": item.updated_at,
    }


def _all_items(store, cap: int = 500) -> List[ChineseMediaQueueItem]:
    """Liet ke MOI muc dung MOT lan.

    Moi muc co dung mot `transcript_state`, nen quet het nam trang thai cua
    rieng truong do la mot phep phu kin va khong trung — khong can them
    phuong thuc store moi cho viec nay.
    """
    out: List[ChineseMediaQueueItem] = []
    seen = set()
    for state in QUEUE_STAGE_STATES:
        offset = 0
        while len(out) < cap:
            page = store.list_queue_items_by_state(
                stage="transcript_state", state=state, limit=100, offset=offset)
            if not page:
                break
            for it in page:
                if it.item_id not in seen:
                    seen.add(it.item_id)
                    out.append(it)
            if len(page) < 100:
                break
            offset += 100
    return out


def list_items(store, *, overall: str = "", limit: int = 50,
               offset: int = 0) -> Dict[str, Any]:
    items = _all_items(store)
    if overall:
        items = [i for i in items if _overall(i) == overall]
    items.sort(key=lambda i: i.updated_at, reverse=True)
    total = len(items)
    page = items[offset:offset + limit]
    return {"total": total, "limit": limit, "offset": offset,
            "items": [item_view(i) for i in page]}


def get_item(store, item_id: str) -> Dict[str, Any]:
    return {"item": item_view(store.get_queue_item(item_id))}


def summary(store) -> Dict[str, Any]:
    """Cung hinh dang ma `chinese_media_orchestrator --status` in ra, de mot
    man hinh quan tri va mot lan chay dong lenh khong bao gio ke hai cau
    chuyen khac nhau."""
    items = _all_items(store)
    counts = {s: {st: 0 for st in QUEUE_STAGE_STATES} for s in STAGES}
    for it in items:
        for s in STAGES:
            counts[s][getattr(it, f"{s}_state")] += 1
    overall_counts: Dict[str, int] = {}
    for it in items:
        key = _overall(it)
        overall_counts[key] = overall_counts.get(key, 0) + 1
    return {"total": len(items), "by_stage": counts, "by_overall": overall_counts}


def _minutes_since(iso_value: str) -> Optional[float]:
    """Tuoi cua `updated_at`, hoac None neu khong doc duoc dau thoi gian.

    Khong doc duoc thi coi nhu KHONG the doi tuoi — an toan hon la doan la no
    da cu roi cuop viec cua mot tien trinh dang song."""
    if not iso_value:
        return None
    try:
        parsed = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() / 60.0


def requeue_stage(store, item_id: str, stage: str, *,
                  actor_id: str) -> Dict[str, Any]:
    """Dat MOT cong doan ve `PENDING` de ban tieu thu nhat lai o lan quet sau.

    KHONG chay gi ca. Khong sinh tien trinh. Chi doi mot truong trang thai.
    """
    if stage not in STAGES:
        raise QueueActionError(f"Công đoạn không hợp lệ: {stage}")

    item = store.get_queue_item(item_id)
    current = getattr(item, f"{stage}_state")

    # CONG QUYEN — khong bao gio duoc di vong qua bang duong web.
    # `render` cua mot muc khong phai REHOST_ALLOWED da bi danh `SKIPPED` boi
    # chinh sach ban quyen. Cho phep xep lai no nghia la dung mot cu bam nut
    # de mo duong render cho noi dung chua co quyen phan phoi lai.
    if stage == "render" and item.rights_mode != "REHOST_ALLOWED":
        raise QueueActionError(
            f"Không thể xếp lại render: rights_mode={item.rights_mode} — "
            "không phân phối lại media gốc.")

    if current == "SKIPPED":
        raise QueueActionError(
            "Công đoạn đã được bỏ qua có chủ đích, không xếp lại được.")
    if current not in REQUEUABLE_STATES:
        raise QueueActionError(
            f"Chỉ xếp lại được công đoạn ở trạng thái "
            f"{'/'.join(REQUEUABLE_STATES)} — hiện tại là {current}.")

    if current == "RUNNING":
        age = _minutes_since(item.updated_at)
        if age is None or age < RUNNING_REQUEUE_MIN_AGE_MINUTES:
            shown = "không đọc được" if age is None else f"{age:.0f} phút trước"
            raise QueueActionError(
                f"Công đoạn đang chạy, cập nhật lần cuối {shown}. "
                f"Chờ đủ {RUNNING_REQUEUE_MIN_AGE_MINUTES} phút rồi xếp lại, "
                "để không cướp việc của tiến trình đang chạy thật.")

    updated = store.update_queue_item(
        item_id,
        **{f"{stage}_state": "PENDING",
           # Dat lai ngan sach that bai LIEN TIEP: mot lan xep lai co chu dich
           # cua con nguoi la mot khoi dau moi, khong phai lan thu thu N.
           "attempts": 0,
           "last_error": f"{stage}: CHO: đã xếp lại bởi {actor_id}"})
    return {"item": item_view(updated)}
