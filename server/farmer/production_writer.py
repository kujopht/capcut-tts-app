"""Ghi mot tac pham da duyet vao BO CUC CHINH TAC — R2 truoc, Drive sau.

Module nay la thu con THIEU sau dot ra soat du dieu kien: `canonical.py`,
`artwork.py` va `drive_archive.py` deu da co va deu da qua kiem thu, nhung
KHONG cai nao duoc goi tu `loop.py`. Chung duoc xay xong roi de do. Day la
cho chung duoc noi vao duong chay that.

## Thu tu, va vi sao dung thu tu do

    van ban -> anh -> manifest -> guong Drive -> cong READY

R2 (duong PHUC VU) duoc ghi TRUOC Drive (ban GUONG). Nguoc lai se co luc mot
tac pham nam tren ban luu tru ma khong ai doc duoc no. Va manifest duoc ghi
SAU cac hien vat no mo ta: mot manifest noi ve mot tep chua ton tai la mot
manifest noi doi.

`manifest.json` duoc ghi HAI noi — trong thu muc tac pham (de doc cung cho
voi noi dung) va duoi `manifests/<work_id>.json` (de LIET KE duoc ma khong
phai quet ca cay). Cung mot noi dung; noi thu hai la mot chi muc.

## Drive hong KHONG lam hong gi

`archive_file` chi COPY va khong bao gio nem. Hong thi manifest ghi
`ARCHIVE_PENDING` va tac pham VAN hop le tren duong phuc vu — dung nhu
`drive_archive` da hua. Cong READY khong hoi Drive.

## Model khong dat ten cho bat cu thu gi

Sieu du lieu da chuan hoa cua Gemini/Antigravity di vao `normalized` trong
manifest. Duong dan thi den tu `canonical.work_id()` + `canonical.slug()` —
ca hai chi phu thuoc (thung, URL). Xem docstring cua `canonical.py`.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from server.farmer import artwork, canonical, drive_archive
from server.farmer.canonical import (
    ARTIFACT_AUDIO_VI, ARTIFACT_BACKGROUND, ARTIFACT_COVER, ARTIFACT_MANIFEST,
    ARTIFACT_TEXT, MANIFESTS, PRODUCTION_ROOT, WorkManifest, canonical_dir,
    holding_dir, work_id as tinh_work_id,
)

#: Ghi mot tep len R2. Cung chu ky voi `R2StorageAdapter.put`.
PutObject = Callable[[str, bytes, str], Any]

_NHIEU_DONG_TRONG = re.compile(r"\n{3,}")
_CUOI_DONG = re.compile(r"[ \t]+$", re.MULTILINE)


class ProductionWriteError(RuntimeError):
    """Khong ghi duoc duong PHUC VU. Day la loi that — khac Drive hong."""


def normalize_text(raw: str) -> str:
    """Chuan hoa van ban — TAT DINH, thuan ma, khong model nao trong duong di.

    Bon phep, khong hon: NFC, bo khoang trang cuoi dong, gop tu ba dong trong
    tro len xuong hai, va bao dam mot ky tu xuong dong o cuoi. Chung deu dao
    nguoc duoc ve mat y nghia va deu khong lam mat noi dung — ban goc van nam
    nguyen trong `source.hashes` de doi chieu.
    """
    s = unicodedata.normalize("NFC", raw or "").replace("\r\n", "\n").replace("\r", "\n")
    s = _CUOI_DONG.sub("", s)
    s = _NHIEU_DONG_TRONG.sub("\n\n", s).strip()
    return s + "\n" if s else ""


def _rel(duong_dan_chinh_tac: str) -> str:
    """Duong dan tuong doi so voi goc san xuat — cai ma Drive can."""
    tien_to = PRODUCTION_ROOT + "/"
    return (duong_dan_chinh_tac[len(tien_to):]
            if duong_dan_chinh_tac.startswith(tien_to) else duong_dan_chinh_tac)


@dataclass
class WriteOutcome:
    """Ket qua ghi MOT tac pham."""
    work_id: str
    canonical_dir: str
    manifest: WorkManifest
    ready: bool = False
    archive_status: str = ""
    #: Ly do CHUA READY. Rong khi da READY. Day la truong nguoi van hanh doc.
    blocked_reason: str = ""
    artifacts_written: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"work_id": self.work_id, "canonical_dir": self.canonical_dir,
                "ready": self.ready, "archive_status": self.archive_status,
                "blocked_reason": self.blocked_reason,
                "artifacts": list(self.artifacts_written)}


class ProductionWriter:
    """Ghi bo hien vat chinh tac. Moi phu thuoc duoc TIEM VAO de kiem thu
    duoc ma khong can R2, ffmpeg hay rclone."""

    def __init__(self, *, put_object: PutObject,
                 get_object: Optional[Callable[[str], bytes]] = None,
                 download_object: Optional[Callable[[str, Path], Any]] = None,
                 generate_artwork: Optional[Callable[[str], Any]] = None,
                 archive_file: Optional[Callable[..., Any]] = None,
                 mirror_to_drive: bool = True):
        self._put = put_object
        #: Chi can cho `attach_audio` (doc lai manifest cu de BO SUNG thay vi
        #: ghi de). Duong ghi chinh khong bao gio doc lai gi, nen no tuy chon.
        self._get = get_object
        #: Tai mot object XUONG DIA. Rieng khoi `get_object` (tra `bytes`) vi
        #: ban mp3 co the vai tram MB va dich vu chay duoi `MemoryMax=1G`.
        self._download = download_object
        self._art = generate_artwork or artwork.generate
        self._archive = archive_file or drive_archive.archive_file
        self._mirror = mirror_to_drive

    def manifest_for(self, bucket: str, url: str):
        """Manifest cua mot tac pham, hoac None. Duong doc, khong ghi gi."""
        return self.read_manifest(canonical_dir(bucket, url))

    def work_complete(self, bucket: str, url: str) -> bool:
        """Tac pham nay DA XONG chua — do bang HIEN VAT, khong bang ban ghi.

        Day la dinh nghia "da gat roi" dung dan, va no thay cho phep kiem cu
        ("co ban ghi novel chua"). Su khac biet khong hoc thuat chut nao:

            Mot tac pham co novel nhung khong co manifest la mot tac pham
            DANG DO. Phep kiem cu goi no la "xong", nen no khong bao gio
            duoc thu lai — mot lan hong o giua duong bien thanh vinh vien.

        Da xay ra HAI lan tren may san xuat: bon tac pham fanfiction that,
        deu da qua cong danh gia, deu tao novel va xep TTS, roi dung o buoc
        bia va bi khoa lai mai mai vi novel cua chinh chung lam chung "trung
        lap" voi chinh minh.

        Fail closed: khong doc duoc thi coi la CHUA xong. Doan "chac xong roi"
        se lang le bo qua mot tac pham that; doan nguoc lai chi ton mot vong
        lam lai, va buoc xuat ban da biet dung lai ban nhap cu.
        """
        if self._get is None:
            return False
        try:
            man = WorkManifest.from_dict(json.loads(
                self._get(f"{canonical_dir(bucket, url)}/{ARTIFACT_MANIFEST}")))
        except Exception:                                       # noqa: BLE001
            return False
        return bool(man.ready)

    # -- duong chinh --------------------------------------------------------
    def write_approved(self, *, bucket: str, url: str, title: str, body: str,
                       verdict: Any, novel_id: str = "",
                       tts_job_id: str = "",
                       source_meta: Optional[Dict[str, Any]] = None
                       ) -> WriteOutcome:
        """Ghi mot tac pham DA DUOC DUYET. Nem `ProductionWriteError` khi
        duong phuc vu hong — mot tac pham thieu van ban khong phai tac pham."""
        wid = tinh_work_id(bucket, url)
        thu_muc = canonical_dir(bucket, url)
        man = self._manifest(
            wid=wid, thu_muc=thu_muc, bucket=bucket, url=url, title=title,
            body=body, verdict=verdict, decision=canonical.DECISION_APPROVE,
            novel_id=novel_id, tts_job_id=tts_job_id, source_meta=source_meta)

        da_ghi: List[str] = []
        cuc_bo: Dict[str, bytes] = {}

        # 1. Van ban da chuan hoa. Hong o day = hong that: khong co gi de doc.
        van_ban = normalize_text(body).encode("utf-8")
        try:
            self._put(f"{thu_muc}/{ARTIFACT_TEXT}", van_ban, "text/plain; charset=utf-8")
        except Exception as exc:                                # noqa: BLE001
            raise ProductionWriteError(
                f"khong ghi duoc {ARTIFACT_TEXT} cho {wid}: "
                f"{type(exc).__name__}: {exc}") from exc
        man.artifacts[ARTIFACT_TEXT] = f"{thu_muc}/{ARTIFACT_TEXT}"
        cuc_bo[ARTIFACT_TEXT] = van_ban
        da_ghi.append(ARTIFACT_TEXT)

        # 2. Anh bia + anh nen. Hong o day KHONG nem: tac pham van ton tai,
        #    no chi khong qua duoc cong READY va se duoc thu lai vong sau.
        chan = ""
        try:
            bia, nen = self._art(wid)
            for ten, du_lieu in ((ARTIFACT_COVER, bia), (ARTIFACT_BACKGROUND, nen)):
                self._put(f"{thu_muc}/{ten}", du_lieu, "image/webp")
                man.artifacts[ten] = f"{thu_muc}/{ten}"
                cuc_bo[ten] = du_lieu
                da_ghi.append(ten)
        except Exception as exc:                                # noqa: BLE001
            chan = f"thieu tranh bia: {type(exc).__name__}: {exc}"[:300]

        # 3. Guong Drive — TRUOC khi ghi manifest, de manifest noi dung su
        #    that ve trang thai luu tru thay vi mot du doan.
        self._da_guong: List[str] = []
        ket_qua_luu = self._mirror_files(bucket, url, cuc_bo)
        man.archive_state = ket_qua_luu.status
        man.archive_path = ket_qua_luu.remote_path
        man.archived_artifacts = list(self._da_guong)

        # 4. Manifest — SAU cung, vi no mo ta moi thu tren.
        man.decision = canonical.DECISION_APPROVE
        san_sang = man.publishable()
        man.ready = san_sang
        self._write_manifest(man, thu_muc)
        da_ghi.append(ARTIFACT_MANIFEST)

        if not chan and not san_sang:
            chan = ("thieu " + ", ".join(man.missing_required_artwork()))
        return WriteOutcome(
            work_id=wid, canonical_dir=thu_muc, manifest=man, ready=san_sang,
            archive_status=ket_qua_luu.status, blocked_reason=chan,
            artifacts_written=da_ghi)

    def write_holding(self, *, bucket: str, url: str, title: str, body: str,
                      verdict: Any,
                      source_meta: Optional[Dict[str, Any]] = None
                      ) -> WriteOutcome:
        """Ghi ban an cho mot tac pham KHONG duoc duyet.

        Chi manifest, khong van ban va khong tranh: mot tac pham bi cach ly
        khong duoc ton dung luong san xuat, nhung ban an cua no phai tim lai
        duoc — neu khong, mot lan xem lai bang tay se khong biet vi sao.
        """
        quyet_dinh = getattr(verdict, "decision", "") or canonical.DECISION_REJECT
        wid = tinh_work_id(bucket, url)
        thu_muc = holding_dir(quyet_dinh, bucket, url)
        man = self._manifest(
            wid=wid, thu_muc=thu_muc, bucket=bucket, url=url, title=title,
            body=body, verdict=verdict, decision=quyet_dinh,
            source_meta=source_meta)
        man.archive_state = drive_archive.ARCHIVE_DISABLED
        self._write_manifest(man, thu_muc)
        return WriteOutcome(
            work_id=wid, canonical_dir=thu_muc, manifest=man, ready=False,
            blocked_reason=f"quyet dinh: {quyet_dinh}",
            artifacts_written=[ARTIFACT_MANIFEST])

    def audio_archived(self, man: WorkManifest) -> bool:
        """Ban mp3 da co ban sao ben vung chua.

        KHAC voi "da gan vao manifest": mot khoa R2 nam trong `artifacts` chi
        noi rang tep co tren duong PHUC VU. Gop hai cau hoi lam mot chinh la
        ly do bon tac pham dau tien co manifest ghi audio ma tren Drive khong
        he co tep mp3 nao.
        """
        return ARTIFACT_AUDIO_VI in (man.archived_artifacts or [])

    def attach_audio(self, *, bucket: str, url: str, object_key: str) -> str:
        """Gan ban audio vao manifest VA guong len Drive.

        Tach rieng vi TTS chay BAT DONG BO tren Cloud Run: khoanh khac tac
        pham duoc duyet va khoanh khac co tep mp3 khong bao gio la mot.

        Idempotent va chay tiep duoc — tra ve mot trong:

            "KHONG_CO_MANIFEST" | "DA_DAY_DU" | "DA_GAN" | "DA_GUONG"
            | "GUONG_HOAN"

        Goi lai khi da day du la mot lan doc, khong phai mot lan ghi. Con khi
        `artifacts` da co audio ma Drive thi chua, no lam NOT phan con thieu —
        do la duong sua cho nhung tac pham da gan audio truoc khi buoc guong
        ton tai.
        """
        thu_muc = canonical_dir(bucket, url)
        man = self.read_manifest(thu_muc)
        if man is None:
            return "KHONG_CO_MANIFEST"

        da_gan = man.artifacts.get(ARTIFACT_AUDIO_VI) == object_key
        if da_gan and self.audio_archived(man):
            return "DA_DAY_DU"

        man.artifacts[ARTIFACT_AUDIO_VI] = object_key
        ket_qua = self._mirror_audio(man, thu_muc, object_key)
        self._write_manifest(man, thu_muc)
        if ket_qua is None:
            return "DA_GAN"
        return "DA_GUONG" if ket_qua else "GUONG_HOAN"

    def _mirror_audio(self, man: WorkManifest, thu_muc: str,
                      object_key: str) -> Optional[bool]:
        """Tai mp3 tu R2 xuong dia roi COPY len Drive.

        `None` = khong thu (guong tat, hoac khong co duong tai). `True`/`False`
        = da thu va thanh cong/that bai.

        Tai XUONG DIA chu khong vao RAM: dich vu chay duoi `MemoryMax=1G` va
        mot track dai co the vai tram MB — `get()` se lam no bi giet chu khong
        chi cham.
        """
        if not self._mirror or self._download is None:
            return None
        duoi = Path(object_key).suffix or ".mp3"
        try:
            with tempfile.TemporaryDirectory(prefix="farmer-audio-") as tmp:
                tep = Path(tmp) / (Path(ARTIFACT_AUDIO_VI).stem + duoi)
                self._download(object_key, tep)
                ket_qua = self._archive(
                    tep, work_key=f"{_rel(thu_muc)}/audio")
        except Exception as exc:                                # noqa: BLE001
            man.archive_state = drive_archive.ARCHIVE_PENDING
            return False
        if ket_qua.status != drive_archive.ARCHIVE_DONE:
            man.archive_state = drive_archive.ARCHIVE_PENDING
            return False
        if ARTIFACT_AUDIO_VI not in man.archived_artifacts:
            man.archived_artifacts.append(ARTIFACT_AUDIO_VI)
        return True

    # -- ben trong ----------------------------------------------------------
    def _manifest(self, *, wid: str, thu_muc: str, bucket: str, url: str,
                  title: str, body: str, verdict: Any, decision: str,
                  novel_id: str = "", tts_job_id: str = "",
                  source_meta: Optional[Dict[str, Any]] = None) -> WorkManifest:
        """Ban goc KHONG bao gio bi ghi de bang ban chuan hoa — xem
        `WorkManifest`."""
        raw = dict(source_meta or {})
        # `_disabled` la co dieu khien cua tep nguon, khong phai su that ve
        # tac pham. Giu lai se lam mot lan doc sau nay hieu nham.
        raw.pop("_disabled", None)
        g = lambda ten, mac_dinh="": getattr(verdict, ten, mac_dinh)  # noqa: E731
        return WorkManifest(
            work_id=wid, bucket=bucket, canonical_dir=thu_muc,
            decision=decision,
            source_url=url, source_title=title,
            source_provider_id=str(raw.get("provider_id", "")),
            source_hashes={
                "body_sha256": hashlib.sha256(
                    (body or "").encode("utf-8")).hexdigest(),
                "normalized_sha256": hashlib.sha256(
                    normalize_text(body).encode("utf-8")).hexdigest(),
            },
            source_metadata_raw=raw,
            canonical_title=g("canonical_title") or title,
            display_title=g("display_title") or title,
            fandom=g("fandom"), category=g("category"), author=g("author"),
            language=g("language"), content_type=g("content_type"),
            completeness=g("completeness"),
            quality_score=int(g("score", 0) or 0),
            tags=[str(t) for t in (g("tags", ()) or ())],
            decision_reason=" | ".join(str(r) for r in (g("reasons", ()) or ()))[:500],
            novel_id=novel_id, tts_job_id=tts_job_id,
            review_model=g("model"),
        )

    def _write_manifest(self, man: WorkManifest, thu_muc: str) -> None:
        du_lieu = json.dumps(man.as_dict(), ensure_ascii=False,
                             indent=2, sort_keys=True).encode("utf-8")
        try:
            self._put(f"{thu_muc}/{ARTIFACT_MANIFEST}", du_lieu,
                      "application/json")
            # Chi muc phang — de liet ke duoc tac pham ma khong phai quet cay.
            self._put(f"{PRODUCTION_ROOT}/{MANIFESTS}/{man.work_id}.json",
                      du_lieu, "application/json")
        except Exception as exc:                                # noqa: BLE001
            raise ProductionWriteError(
                f"khong ghi duoc manifest cho {man.work_id}: "
                f"{type(exc).__name__}: {exc}") from exc

    def read_manifest(self, thu_muc: str) -> Optional[WorkManifest]:
        doc = self._get
        if doc is None:
            return None
        try:
            return WorkManifest.from_dict(
                json.loads(doc(f"{thu_muc}/{ARTIFACT_MANIFEST}")))
        except Exception:                                       # noqa: BLE001
            return None

    def _mirror_files(self, bucket: str, url: str,
                      noi_dung: Dict[str, bytes]):
        """Guong len Drive. KHONG BAO GIO nem: mot su co Drive la thong tin,
        khong phai loi san xuat."""
        if not self._mirror or not noi_dung:
            return drive_archive.ArchiveOutcome(
                drive_archive.ARCHIVE_DISABLED,
                detail="guong Drive tat cho lan ghi nay")
        goc_tuong_doi = _rel(canonical_dir(bucket, url))
        cuoi = drive_archive.ArchiveOutcome(drive_archive.ARCHIVE_PENDING)
        self._da_guong = []
        try:
            with tempfile.TemporaryDirectory(prefix="farmer-arc-") as tmp:
                for ten, du_lieu in noi_dung.items():
                    tep = Path(tmp) / Path(ten).name
                    tep.write_bytes(du_lieu)
                    thu_muc_con = str(Path(ten).parent).replace("\\", "/")
                    khoa = (f"{goc_tuong_doi}/{thu_muc_con}"
                            if thu_muc_con not in (".", "") else goc_tuong_doi)
                    cuoi = self._archive(tep, work_key=khoa)
                    if cuoi.status != drive_archive.ARCHIVE_DONE:
                        # Mot tep hong thi ca bo la CHUA xong — bao dung su
                        # that thay vi bao xong vi tep cuoi tinh co thanh cong.
                        return cuoi
                    self._da_guong.append(ten)
        except Exception as exc:                                # noqa: BLE001
            return drive_archive.ArchiveOutcome(
                drive_archive.ARCHIVE_PENDING,
                detail=f"{type(exc).__name__}: {exc}"[:300])
        return cuoi
