"""
Bieu dien nhan dang HINH ANH nhan vat (`CharacterVisualIdentity`) — PROVIDER-
TRUNG LAP, khong gan voi bat ky mo hinh sinh anh cu the nao (Illustrious,
SDXL, LoRA, IP-Adapter, hay bat ky provider tuong lai nao khac).

VI SAO CAN FILE NAY: bia Re:Zero dau tien (that, tren Beam that) co bo cuc
dung (2 nguoi, dung phan cap tien canh/hau canh, khong con dong nguoi —
xem CoverPromptBuilder trong cover_pipeline.py), nhung Subaru va Anastasia
tro thanh nhan vat anime CHUNG CHUNG — model khong "biet" ho la ai chi tu
ten. Fix la MO TA HINH ANH cu the (toc/mat/trang phuc/dac diem), khong
phai hardcode chuoi prompt trong Beam endpoint (cover_illustrious_app.py
van chi nhan `prompt: str` bat ky — khong doi) — nhan dang thuoc ve
METADATA fandom/nhan vat co the tai su dung, o day va trong
CoverPromptBuilder.build_prompt(), giong nguyen tac cua
`server/fandom_registry.py`.

CHUA gan LoRA/reference-image that (`lora_reference_id`/
`reference_asset_url` la truong DU PHONG, hien khong duoc bat ky code nao
doc/goi) — thiet ke de cam vao sau ma khong doi schema, khong phai vi da
tich hop.
"""
from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def _normalize_name(raw: str) -> str:
    """So khop khong phan biet hoa/thuong, khong phan biet dau cach thua,
    bo dau — cung nguyen tac voi `fandom_registry.py::_chuan_hoa_ten`,
    nhung KHONG import tu do de module nay khong phu thuoc fandom_registry
    (provider-trung-lap, dung doc lap duoc)."""
    normalized = unicodedata.normalize("NFKD", raw or "")
    without_marks = "".join(c for c in normalized if not unicodedata.combining(c))
    return " ".join(without_marks.lower().split())


@dataclass
class CharacterVisualIdentity:
    """
    Nhan dang HINH ANH cua MOT nhan vat, doc lap voi provider sinh anh.

    `gender_presentation`: chuoi tu do ("male"/"female"/...) — dung de
    suy ra tag dem nguoi (1boy/1girl, xem `count_tag_category()`); de
    trong = khong biet, CoverPromptBuilder se lui ve tag chung
    (solo/2people/...).

    `negative_traits`: dac diem KHONG nen xuat hien / hay bi nham lan —
    duoc TINH (`CoverPromptBuilder.build_character_negative_traits`) NHUNG
    CHUA duoc noi vao request HTTP that (HttpImageCoverProvider hien chi
    gui {"prompt": ...}) — day la buoc noi day du tiep theo, khong phai
    loi thieu sot cua ban nay.
    """

    canonical_name: str
    fandom: str
    aliases: List[str] = field(default_factory=list)
    gender_presentation: str = ""
    hair_description: str = ""
    eye_description: str = ""
    outfit_description: str = ""
    distinctive_traits: List[str] = field(default_factory=list)
    negative_traits: List[str] = field(default_factory=list)
    #: Du phong cho co che dieu kien hoa hinh anh trong tuong lai (LoRA
    #: weight/ID, hoac anh tham chieu cho IP-Adapter-style conditioning).
    #: KHONG code nao doc 2 truong nay ngay bay gio.
    lora_reference_id: str = ""
    reference_asset_url: str = ""
    #: Nguon goc cac mo ta o tren — bat buoc VE MAT QUY UOC (khong ep bang
    #: code) de nhan dang co the doi soat lai duoc, khong phai doan.
    source_provenance: str = ""

    def count_tag_category(self) -> str:
        """"boy"/"girl" neu `gender_presentation` biet ro, nguoc lai
        chuoi rong (chua biet — caller lui ve tag dem chung)."""
        gp = self.gender_presentation.strip().lower()
        if gp in ("male", "man", "boy"):
            return "boy"
        if gp in ("female", "woman", "girl"):
            return "girl"
        return ""

    def to_prompt_descriptor(self) -> str:
        """Chuoi tag mo ta hinh anh (toc, mat, trang phuc, dac diem rieng)
        — DUNG lam noi dung PROMPT DUONG (positive), khong bao gom ten."""
        parts: List[str] = []
        if self.hair_description:
            parts.append(self.hair_description)
        if self.eye_description:
            parts.append(self.eye_description)
        if self.outfit_description:
            parts.append(self.outfit_description)
        parts.extend(self.distinctive_traits)
        return ", ".join(parts)


#: Ho so HAT GIONG — cung nguyen tac voi `fandom_registry._SEED_FANDOMS`:
#: DIEM KHOI DAU cho cac nhan vat da xuat hien trong mission, khong phai
#: toan bo vu tru nhan vat. Nguon: rezero.fandom.com (Re:Zero Wiki, Fandom)
#: + doi chieu Otapedia/Tokyo Otaku Mode, tra cuu that qua WebSearch
#: 2026-08-31 — khong doan tu tri nho huan luyen.
_SEED_CHARACTERS: Tuple[CharacterVisualIdentity, ...] = (
    CharacterVisualIdentity(
        canonical_name="Natsuki Subaru",
        fandom="Re:Zero",
        aliases=["Subaru Natsuki", "Subaru"],
        gender_presentation="male",
        hair_description="short messy black hair, swept back and unkempt",
        eye_description="sharp dark brown eyes with an intense gaze",
        outfit_description=(
            "black tracksuit jacket zipped up with stand-up collar over a "
            "black t-shirt, deep-grey tracksuit pants with an orange "
            "stripe down the side, black sneakers with orange laces"
        ),
        distinctive_traits=["athletic build", "determined expression"],
        negative_traits=["blonde hair", "glasses", "formal suit"],
        source_provenance=(
            "rezero.fandom.com/wiki/Natsuki_Subaru "
            "(cross-checked otakumode.com/otapedia, 2026-08-31)"
        ),
    ),
    CharacterVisualIdentity(
        canonical_name="Anastasia Hoshin",
        fandom="Re:Zero",
        aliases=["Anastasia", "Hoshin Anastasia"],
        gender_presentation="female",
        hair_description="long wavy purple hair reaching her hips",
        eye_description="blue-green eyes, gentle relaxed expression",
        outfit_description=(
            "form-fitting ankle-length long-sleeved white dress, tall "
            "white fluffy fur ushanka-style hat, white scarf, white "
            "high-heeled boots with pale pink soles"
        ),
        distinctive_traits=[
            "yellow star-shaped hairpin", "small teal pendant necklace",
            "petite doll-like figure",
        ],
        negative_traits=["short hair", "armor", "modern clothing"],
        source_provenance=(
            "rezero.fandom.com/wiki/Anastasia_Hoshin "
            "(cross-checked otakumode.com/otapedia, 2026-08-31)"
        ),
    ),
)


class CharacterIdentityRegistry:
    """Registry o BO NHO — mot tien trinh, khong ben vung qua lan khoi
    dong lai, cung nguyen tac voi `FandomRegistry`. Khoa tra cuu la
    (fandom, ten) da chuan hoa de tranh nham nhan vat trung ten khac
    fandom."""

    def __init__(self, *, seed: bool = True):
        self._lock = threading.Lock()
        self._identities: Dict[str, CharacterVisualIdentity] = {}
        self._alias_index: Dict[Tuple[str, str], str] = {}
        if seed:
            for identity in _SEED_CHARACTERS:
                self.register(identity)

    def _key(self, identity: CharacterVisualIdentity) -> str:
        return f"{_normalize_name(identity.fandom)}::{_normalize_name(identity.canonical_name)}"

    def register(self, identity: CharacterVisualIdentity) -> CharacterVisualIdentity:
        with self._lock:
            key = self._key(identity)
            self._identities[key] = identity
            fandom_norm = _normalize_name(identity.fandom)
            self._alias_index[(fandom_norm, _normalize_name(identity.canonical_name))] = key
            for alias in identity.aliases:
                self._alias_index[(fandom_norm, _normalize_name(alias))] = key
            return identity

    def lookup(self, fandom: str, raw_name: str) -> Optional[CharacterVisualIdentity]:
        """Tra ve `CharacterVisualIdentity` da khop trong DUNG fandom, hoac
        `None` neu chua biet (KHONG nem loi — CoverPromptBuilder lui ve
        hanh vi chi-co-ten khi khong tim thay, khong chan tien trinh sinh
        bia cho nhan vat CHUA co ho so)."""
        with self._lock:
            key = self._alias_index.get(
                (_normalize_name(fandom), _normalize_name(raw_name)))
            return self._identities.get(key) if key else None

    def list_all(self) -> List[CharacterVisualIdentity]:
        with self._lock:
            return list(self._identities.values())
