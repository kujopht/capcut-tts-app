"""
Chuan hoa ten fandom anime/manga/light-novel ve MOT dinh danh (`Fandom`).

Cung nguyen tac voi `server/scraper/site_registry.py`: mot bang HAT GIONG
(`_SEED_ALIASES`) cho cac fandom PHO BIEN, cong voi mot registry o BO NHO co
the DANG KY THEM tai runtime (`FandomRegistry.register`/`add_alias`) — danh
sach hat giong KHONG phai gioi han cung, mot ten CHUA biet duoc bao ro rang
qua `UnknownFandomError` de operator tu quyet dinh dang ky, khong bi am
tham gan vao mot fandom sai hoac bi bo qua.
"""
from __future__ import annotations

import threading
import unicodedata
from typing import Dict, List, Optional

from server.domain import Fandom, FandomMediaType

#: (canonical_name, media_type, [aliases...]) — fandom PHO BIEN duoc neu
#: trong mission brief, CONG alias thuong gap. Day la DIEM KHOI DAU, khong
#: phai toan bo vu tru fandom se ho tro — `FandomRegistry.register` dang ky
#: them fandom moi (bao gom fandom KHONG anime/manga/light-novel, du mission
#: hien tai chi nham anime/manga) tai runtime, giong `site_registry.py` hoc
#: domain moi qua `confirm_unknown_source`.
_SEED_FANDOMS = (
    ("Naruto", FandomMediaType.MANGA, ["Naruto Shippuden"]),
    ("One Piece", FandomMediaType.MANGA, []),
    ("Bleach", FandomMediaType.MANGA, []),
    ("Dragon Ball", FandomMediaType.MANGA, ["Dragon Ball Z", "Dragon Ball Super", "DBZ"]),
    ("Jujutsu Kaisen", FandomMediaType.MANGA, ["JJK"]),
    ("Demon Slayer", FandomMediaType.MANGA, ["Kimetsu no Yaiba"]),
    ("My Hero Academia", FandomMediaType.MANGA,
     ["Boku no Hero Academia", "BNHA", "MHA"]),
    ("Attack on Titan", FandomMediaType.MANGA, ["Shingeki no Kyojin", "AoT", "SNK"]),
    ("Re:Zero", FandomMediaType.LIGHT_NOVEL,
     ["Re:Zero kara Hajimeru Isekai Seikatsu", "Re Zero"]),
    ("Sword Art Online", FandomMediaType.LIGHT_NOVEL, ["SAO"]),
    ("Date A Live", FandomMediaType.LIGHT_NOVEL, []),
    ("High School DxD", FandomMediaType.LIGHT_NOVEL, ["Highschool DxD", "DxD"]),
)


class UnknownFandomError(Exception):
    """Ten fandom KHONG khop bat ky `canonical_name`/alias nao da dang ky.

    KHONG tu doan mot fandom gan giong nhat — bao ro de operator tu xac
    nhan dang ky moi (`FandomRegistry.register`) hoac gan alias
    (`FandomRegistry.add_alias`), cung nguyen tac voi
    `UnsupportedSiteError` cua `site_registry.py`."""


def _chuan_hoa_ten(raw: str) -> str:
    """So khop KHONG phan biet hoa/thuong, KHONG phan biet dau cach thua,
    va bo dau tieng Viet/dau phu am nhac (vd "Ðemon" ~ "Demon") — cac bien
    the go tay/OCR/nguon khac nhau thuong chi khac nhau o day."""
    normalized = unicodedata.normalize("NFKD", raw or "")
    without_marks = "".join(c for c in normalized if not unicodedata.combining(c))
    return " ".join(without_marks.lower().split())


class FandomRegistry:
    """Registry o BO NHO — MOT tien trinh, khong ben vung qua lan khoi
    dong lai (giong `MockScrapeRunStore`). Kho ben vung that (Appwrite) la
    mot lop rieng boc quanh registry nay sau, khong doi hop dong lop nay."""

    def __init__(self, *, seed: bool = True):
        self._lock = threading.Lock()
        self._fandoms: Dict[str, Fandom] = {}          # fandom_id -> Fandom
        self._alias_index: Dict[str, str] = {}         # ten da chuan hoa -> fandom_id
        if seed:
            for canonical_name, media_type, aliases in _SEED_FANDOMS:
                self.register(Fandom(
                    canonical_name=canonical_name, media_type=media_type,
                    aliases=list(aliases)))

    def register(self, fandom: Fandom) -> Fandom:
        """Dang ky mot `Fandom` moi, lap chi muc `canonical_name` + moi
        `aliases` da co san trong doi tuong truyen vao."""
        with self._lock:
            self._fandoms[fandom.fandom_id] = fandom
            self._alias_index[_chuan_hoa_ten(fandom.canonical_name)] = fandom.fandom_id
            for alias in fandom.aliases:
                self._alias_index[_chuan_hoa_ten(alias)] = fandom.fandom_id
            return fandom

    def add_alias(self, canonical_name: str, alias: str, *,
                  source_name: str = "") -> Fandom:
        """Gan THEM mot alias cho fandom da dang ky theo `canonical_name`.

        `source_name` (tuy chon): ten CHINH XAC nhu mot nguon cu the hien
        thi — ghi vao `Fandom.source_names` de doi soat sau, tach biet voi
        `aliases` (danh sach de KHOP, khong phai nhat ky nguon goc)."""
        with self._lock:
            fandom_id = self._alias_index.get(_chuan_hoa_ten(canonical_name))
            if fandom_id is None:
                raise UnknownFandomError(
                    f"Chua dang ky fandom {canonical_name!r} — goi `register()` truoc.")
            fandom = self._fandoms[fandom_id]
            if alias not in fandom.aliases:
                fandom.aliases.append(alias)
            if source_name and source_name not in fandom.source_names:
                fandom.source_names.append(source_name)
            self._alias_index[_chuan_hoa_ten(alias)] = fandom_id
            return fandom

    def lookup(self, raw_name: str) -> Optional[Fandom]:
        """Tra ve `Fandom` da khop, hoac `None` neu chua biet (KHONG nem
        loi — dung cho truong hop goi muon kiem tra truoc khi quyet dinh)."""
        with self._lock:
            fandom_id = self._alias_index.get(_chuan_hoa_ten(raw_name))
            return self._fandoms.get(fandom_id) if fandom_id else None

    def resolve(self, raw_name: str) -> Fandom:
        """Nhu `lookup` nhung NEM `UnknownFandomError` neu khong khop —
        dung khi nguon goi PHAI co mot fandom hop le de tiep tuc (vd truoc
        khi tao `Novel`), khong duoc am tham gan mot fandom "khac"/rong."""
        fandom = self.lookup(raw_name)
        if fandom is None:
            raise UnknownFandomError(
                f"Ten fandom chua biet: {raw_name!r} — can operator dang ky "
                f"qua `FandomRegistry.register()`/`add_alias()` truoc khi "
                f"phan loai noi dung nay.")
        return fandom

    def classify_many(self, raw_names: List[str]) -> Dict[str, List[str]]:
        """Phan loai MOT danh sach ten (vd danh sach fandom cua mot fic
        crossover) — tra ve `{"matched": [fandom_id, ...], "unmatched":
        [raw_name, ...]}`. KHONG nem loi: fic crossover thuong tron mot
        fandom da biet voi mot fandom (hoac original character tag) chua
        biet, va ta muon giu lai phan da khop thay vi loai bo ca fic."""
        matched: List[str] = []
        unmatched: List[str] = []
        for raw in raw_names:
            fandom = self.lookup(raw)
            if fandom is None:
                unmatched.append(raw)
            else:
                matched.append(fandom.fandom_id)
        return {"matched": matched, "unmatched": unmatched}

    def get(self, fandom_id: str) -> Optional[Fandom]:
        with self._lock:
            return self._fandoms.get(fandom_id)

    def list_all(self) -> List[Fandom]:
        with self._lock:
            return list(self._fandoms.values())
