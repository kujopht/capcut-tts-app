"""
Doi soat object audio trong kho voi ban ghi metadata.

MAC DINH CHI DOC. Che do xoa phai truyen co xac nhan ro rang, va truoc khi xoa
tung object thi KIEM TRA THAM CHIEU LAI mot lan nua.

Vi sao tach thanh module rieng thay vi de trong script: de test duoc tung phan
ma khong phai goi qua dong lenh, va de backend khong bao gio tu chay che do xoa.
Diem vao dong lenh o `scripts/reconcile_audio.py`.

BON LOAI object
---------------
`output_key` la TAT DINH: `audio/{owner_id}/{chapter_id}/{content_hash}.mp3`.

| Loai            | Nghia                                                       |
|-----------------|-------------------------------------------------------------|
| `da_tham_chieu` | co `audio_track.object_key` tro toi                         |
| `dang_xu_ly`    | khop output key cua job `pending`/`running` con lease hop le |
| `con_moi`       | `modified_at` nam trong thoi gian an han                     |
| `mo_coi`        | khong thuoc ba loai tren                                    |

Con mot chieu nguoc lai: `ban_ghi_thieu_file` — `audio_track` tro toi object
khong ton tai. Day la MAT DU LIEU, khong phai rac, nen cong cu chi BAO, tuyet
doi khong tu xoa ban ghi nao.

AN HAN
------
Object vua upload xong ma `create_track` chua kip ghi se trong nhu mo coi. Thoi
gian an han (mac dinh 24 gio) chan dung truong hop do. Khong co no thi cong cu
se xoa mat audio cua mot job dang chay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from server.domain import JobStatus

#: Object moi hon khoang nay thi khong bao gio bi coi la mo coi.
DEFAULT_GRACE_HOURS = 24

#: Chi doi soat trong pham vi nay. Khong quet ca bucket.
AUDIO_PREFIX = "audio/"


def expected_output_key(owner_id: str, chapter_id: str, content_hash: str) -> str:
    """
    Khoa object ma job se ghi ra.

    PHAI khop chinh xac cong thuc trong `main._run_job`. Lech mot ky tu la cong
    cu se coi audio cua job dang chay la mo coi — co test khoa lai dieu nay.
    """
    return f"{AUDIO_PREFIX}{owner_id}/{chapter_id}/{content_hash}.mp3"


@dataclass
class Report:
    """Ket qua mot luot doi soat. Khong chua secret nao."""

    che_do: str = "dry-run"
    an_han_gio: int = DEFAULT_GRACE_HOURS
    tong_object: int = 0
    da_tham_chieu: int = 0
    dang_xu_ly: List[str] = field(default_factory=list)
    con_moi: List[str] = field(default_factory=list)
    mo_coi: List[Dict[str, Any]] = field(default_factory=list)
    ban_ghi_thieu_file: List[Dict[str, str]] = field(default_factory=list)
    da_xoa: List[str] = field(default_factory=list)
    bo_qua_khi_xoa: List[Dict[str, str]] = field(default_factory=list)
    loi: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "che_do": self.che_do,
            "an_han_gio": self.an_han_gio,
            "tong_object": self.tong_object,
            "da_tham_chieu": self.da_tham_chieu,
            "dang_xu_ly": self.dang_xu_ly,
            "con_moi": self.con_moi,
            "mo_coi": self.mo_coi,
            "ban_ghi_thieu_file": self.ban_ghi_thieu_file,
            "da_xoa": self.da_xoa,
            "bo_qua_khi_xoa": self.bo_qua_khi_xoa,
            "loi": self.loi,
        }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _referenced_keys(store: Any) -> Set[str]:
    """Moi `object_key` dang duoc mot `audio_track` tro toi."""
    keys: Set[str] = set()
    for chapter in _all_chapters(store):
        for track in store.tracks_for_chapter(chapter.chapter_id):
            if track.object_key:
                keys.add(track.object_key)
    return keys


def _all_chapters(store: Any) -> Iterable[Any]:
    """
    Moi chuong cua moi nguoi dung.

    Khong co ham "liet ke moi chuong" trong Protocol — va co y khong them, vi
    mot ham nhu vay se la duong ro ri du lieu neu bi loi ra route. Thay vao do
    di qua tung truyen; `list_novels()` va `list_chapters()` deu da lat trang.
    """
    for novel in store.list_novels():
        for chapter in store.list_chapters(novel.novel_id):
            yield chapter


def _in_flight_keys(store: Any) -> Set[str]:
    """
    Khoa output cua cac job CHUA ket thuc va con lease hop le.

    Job `running` het lease KHONG nam o day: no se duoc worker recovery nhan lai,
    va neu no chay lai thi khoa output cung y nhu vay — nen object do van an toan
    nho thoi gian an han, khong phai nho danh sach nay.
    """
    keys: Set[str] = set()
    for status in (JobStatus.PENDING, JobStatus.RUNNING):
        try:
            jobs = store.list_jobs_by_status(status)
        except Exception:
            continue
        for job in jobs:
            if status is JobStatus.RUNNING and not job.lease_is_live():
                continue
            keys.add(expected_output_key(job.owner_id, job.chapter_id,
                                        job.content_hash))
            if job.output_key:
                keys.add(job.output_key)
    return keys


def scan(store: Any, storage: Any, *,
         grace_hours: int = DEFAULT_GRACE_HOURS) -> Report:
    """
    Doi soat CHI DOC. Khong xoa gi, khong tao presigned URL nao.

    Tra ve bao cao day du de doc bang mat hoac luu lai lam bang chung.
    """
    report = Report(che_do="dry-run", an_han_gio=grace_hours)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_hours)

    referenced = _referenced_keys(store)
    in_flight = _in_flight_keys(store)

    for obj in storage.list_objects(AUDIO_PREFIX):
        report.tong_object += 1
        if obj.key in referenced:
            report.da_tham_chieu += 1
            continue
        if obj.key in in_flight:
            report.dang_xu_ly.append(obj.key)
            continue
        modified = _parse_iso(obj.modified_at)
        if modified is not None and modified > cutoff:
            report.con_moi.append(obj.key)
            continue
        report.mo_coi.append({
            "key": obj.key,
            "size_bytes": obj.size_bytes,
            "modified_at": obj.modified_at,
        })

    # Chieu nguoc lai: ban ghi tro toi object khong con
    for chapter in _all_chapters(store):
        for track in store.tracks_for_chapter(chapter.chapter_id):
            if not track.object_key:
                continue
            try:
                if not storage.exists(track.object_key):
                    report.ban_ghi_thieu_file.append({
                        "track_id": track.track_id,
                        "chapter_id": track.chapter_id,
                        "object_key": track.object_key,
                    })
            except Exception as exc:
                report.loi.append({
                    "khi": f"kiem tra {track.object_key}",
                    "loi": type(exc).__name__,
                })
    return report


def purge(store: Any, storage: Any, *, confirm: bool = False,
          grace_hours: int = DEFAULT_GRACE_HOURS) -> Report:
    """
    Xoa cac object mo coi. CHI chay khi `confirm=True`.

    Truoc khi xoa TUNG object, kiem tra tham chieu LAI mot lan nua: giua luc quet
    va luc xoa co the vua co job hoan tat va tao track tro toi chinh khoa do.

    Loi khi xoa mot object KHONG lam mat bao cao cua ca luot: no duoc ghi vao
    `loi` va vong lap di tiep.
    """
    report = scan(store, storage, grace_hours=grace_hours)
    if not confirm:
        # Khong co co xac nhan thi day chi la mot lan quet, khong hon
        return report

    report.che_do = "delete"
    referenced = _referenced_keys(store)
    in_flight = _in_flight_keys(store)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_hours)

    for item in list(report.mo_coi):
        key = item["key"]
        # -- kiem tra lai, ba dieu kien doc lap ------------------------------
        if key in referenced:
            report.bo_qua_khi_xoa.append({"key": key, "vi_sao": "vua co ban ghi tro toi"})
            continue
        if key in in_flight:
            report.bo_qua_khi_xoa.append({"key": key, "vi_sao": "job dang xu ly"})
            continue
        modified = _parse_iso(item.get("modified_at"))
        if modified is not None and modified > cutoff:
            report.bo_qua_khi_xoa.append({"key": key, "vi_sao": "con trong thoi gian an han"})
            continue
        try:
            storage.delete(key)
            report.da_xoa.append(key)
        except Exception as exc:
            report.loi.append({"khi": f"xoa {key}", "loi": type(exc).__name__})
    return report
