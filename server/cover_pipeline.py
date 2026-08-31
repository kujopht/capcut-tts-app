"""
Giao diện và luồng xử lý tạo ảnh bìa tiểu thuyết (Cover Generation Job Interface).

Module này đóng vai trò hợp đồng (contract) và quản lý trạng thái công việc (job bookkeeping)
để sinh ảnh bìa từ siêu dữ liệu tiểu thuyết.

Tuân thủ nguyên tắc không phụ thuộc vào bất kỳ thư viện GPU/AI hoặc thư viện xử lý ảnh (Pillow)
nào ở giai đoạn này (tương tự như DriveArchiveBackend trong storage_backend.py).
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Literal, Optional, Protocol

import httpx

from server.character_identity import CharacterIdentityRegistry
from server.domain import (
    MediaAsset,
    MediaProcessingState,
    MediaType,
    StorageTier,
    new_id,
    now_iso,
)


@dataclass
class CoverGenerationRequest:
    """
    Yêu cầu sinh ảnh bìa với đầy đủ thông tin ngữ cảnh của tiểu thuyết.
    """

    novel_id: str
    fandom: str
    title: str
    summary: str
    #: Danh sach nhan vat DAY DU cua truyen - CHI la metadata/tham khao,
    #: KHONG con duoc dua thang vao prompt ve anh nua (xem CoverPromptBuilder:
    #: bia dong nguoi -> anh bia tro thanh "poster ensemble" dong duc, khong
    #: dung lam bia san xuat duoc). Dan dien vien HIEN THI tren bia dung
    #: primary_character/secondary_character/tertiary_character ben duoi.
    characters: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    mood: str = ""
    visual_style: str = ""
    #: Dan dien vien HIEN THI tren bia (khac voi `characters` metadata o tren).
    #: Rong = khong ve nhan vat cu the nao (bia phong canh/bieu tuong).
    primary_character: str = ""
    secondary_character: str = ""
    tertiary_character: str = ""
    #: So nhan vat toi da XUAT HIEN tren bia, tinh tu primary tro di. Mac
    #: dinh 2 (chi primary+secondary) de tranh bia dong nguoi - ngay ca khi
    #: tertiary_character duoc dien, no chi xuat hien khi gia tri nay >= 3.
    max_visible_characters: int = 2


class CoverProvider(Protocol):
    """
    Giao thức chuẩn cho các provider sinh ảnh bìa.
    """

    provider_name: str

    def generate(self, request: CoverGenerationRequest) -> bytes:
        """
        Sinh ảnh thô từ yêu cầu và trả về mảng bytes của ảnh.
        """
        ...


class NotConfiguredCoverProvider:
    """
    Provider mặc định khi chưa tích hợp hoặc cấu hình mô hình sinh ảnh bìa thực tế.
    Giữ đúng hợp đồng interface và từ chối thực thi với thông báo rõ ràng.
    """

    provider_name: str = "not_configured"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        raise NotImplementedError(
            "Cover generation model has not been chosen or deployed yet."
        )


class CoverProviderError(Exception):
    """Loi chung khi goi provider sinh anh bia that that bai (HTTP 500, timeout, v.v.)."""


class CoverPromptBuilder:
    """
    Xay dung prompt text cho model sinh anh bia (anime cover art).
    TAT DINH — cung input luon ra cung prompt, khong ngau nhien.
    KHONG bao gom ten tieu de thuan — model chi ve ART, application code
    chen tieu de qua overlay SVG (xem render_deterministic_overlay).

    Phong cach tag-oriented (booru-style, ngan gon) thay vi van xuoi dai —
    cac model anime (Illustrious/Animagine-class) bam theo tag chinh xac
    hon cau van tu nhien. Dan dien vien HIEN THI tren bia dung
    primary_character/secondary_character/(tertiary_character neu duoc
    phep boi max_visible_characters) — KHONG dung `characters[]` (metadata
    day du cua truyen) nua: dua thang toan bo characters[] vao prompt tung
    tao ra bia "poster ensemble" dong nguoi/nhan vat trung lap, khong dung
    lam bia san xuat duoc (bang chung that: ban Re:Zero dau tien).

    `identity_registry` (tuy chon, mac dinh None = hanh vi cu khong doi):
    tra ten nhan vat sang `CharacterVisualIdentity` that (toc/mat/trang
    phuc/dac diem — xem server/character_identity.py) — fix cho van de
    THAT: 3 candidate dau tien co bo cuc dung nhung Subaru/Anastasia tro
    thanh nhan vat anime CHUNG CHUNG, vi prompt chi co TEN, model khong
    "biet" ho la ai. Nhan vat CHUA co ho so (identity_registry.lookup tra
    None) van lui ve hanh vi CHI-TEN nhu truoc — khong chan tien trinh.

    CHE DO COMPACT (khi >= 2 nhan vat HIEN THI co `compact_visual_tags`):
    fix cho loi that tren Beam - prompt DAY DU (mo ta hoan chinh cho CA
    HAI nhan vat) dai ~980 ky tu nhung thuc te la 216 token CLIP, vuot
    gioi han cung 77 ("Token indices sequence length 216 > maximum 77" -
    log that tu Beam). Khi >= 2 nhan vat trong cast co san
    `compact_visual_tags`, build_prompt() tu dong chuyen sang phien ban
    RUT GON (ten + toi da 2 tag noi bat nhat/nhan vat, bo genre/mood/cau
    van dai) thay vi phien ban day du - KHONG bo hoan toan nhan dang
    (item 6: "Do not simply discard character identity"), chi giu lai
    PHAN QUAN TRONG NHAT. Nhan vat CHUA co compact_visual_tags (vd chi co
    1 nhan vat, hoac khong co identity_registry) van dung phien ban day
    du nhu truoc - KHONG doi hanh vi cho cac truong hop do.
    """

    @staticmethod
    def build_prompt(
        request: CoverGenerationRequest,
        identity_registry: Optional[CharacterIdentityRegistry] = None,
    ) -> str:
        cast = [
            c for c in (
                request.primary_character,
                request.secondary_character,
                request.tertiary_character,
            ) if c
        ][:max(0, request.max_visible_characters)]
        identities = [
            identity_registry.lookup(request.fandom, name) if identity_registry else None
            for name in cast
        ]

        count_tag = CoverPromptBuilder._build_count_tag(cast, identities)

        resolved_with_compact_tags = [
            i for i in identities if i and i.compact_visual_tags]
        if len(resolved_with_compact_tags) >= 2:
            return CoverPromptBuilder._build_compact_prompt(
                request, cast, identities, count_tag)

        parts: List[str] = ["light novel cover"]

        if request.fandom:
            parts.append(f"{request.fandom} fanart style")

        if count_tag:
            parts.append(count_tag)

        if cast:
            parts.append("clear focal hierarchy")
            parts.append(
                f"{CoverPromptBuilder._cast_block(cast[0], identities[0])} "
                f"in foreground, focal point")
            if len(cast) >= 2:
                parts.append(
                    f"{CoverPromptBuilder._cast_block(cast[1], identities[1])} "
                    f"positioned beside/behind {cast[0]}")
            if len(cast) >= 3:
                parts.append(
                    f"{CoverPromptBuilder._cast_block(cast[2], identities[2])} "
                    f"further back in the background")

        if request.mood:
            parts.append(f"{request.mood} mood")

        if request.genres:
            genres = ", ".join(request.genres)
            parts.append(f"{genres} genre")

        if request.visual_style:
            parts.append(request.visual_style)

        parts.append("cinematic fantasy background")
        parts.append("negative space for title")
        parts.append("detailed anime digital painting")
        parts.append("dynamic pose")
        parts.append("vibrant colors")
        parts.append("high quality")

        return ", ".join(parts)

    @staticmethod
    def _build_compact_prompt(
        request: CoverGenerationRequest, cast: List[str],
        identities: List[Optional[Any]], count_tag: str,
    ) -> str:
        """Phien ban RUT GON - xem build_prompt()'s own docstring "CHE DO
        COMPACT" cho ly do that. Chi giu: "light novel cover", fandom,
        count_tag, ten+toi da 2 tag noi bat/nhan vat, "negative space for
        title" (can cho overlay tieu de ung dung, khong phai chi tiet tuy
        chon), va 2 tag chat luong ngan gon - bo genre/mood/van xuoi dai/
        chi tiet uu tien thap (dung theo yeu cau: "Move/remove redundant
        prose, genre words, repeated descriptions, and low-priority
        details")."""
        parts: List[str] = ["light novel cover"]

        if request.fandom:
            parts.append(f"{request.fandom} fanart style")

        if count_tag:
            parts.append(count_tag)

        primary_descriptor = identities[0].to_compact_prompt_descriptor() if identities[0] else ""
        primary_block = f"{cast[0]}, {primary_descriptor}" if primary_descriptor else cast[0]
        parts.append(f"{primary_block}, foreground")

        if len(cast) >= 2:
            secondary_descriptor = (
                identities[1].to_compact_prompt_descriptor() if identities[1] else "")
            secondary_block = (
                f"{cast[1]}, {secondary_descriptor}" if secondary_descriptor else cast[1])
            parts.append(f"{secondary_block}, beside {cast[0]}")

        if len(cast) >= 3:
            tertiary_descriptor = (
                identities[2].to_compact_prompt_descriptor() if identities[2] else "")
            tertiary_block = (
                f"{cast[2]}, {tertiary_descriptor}" if tertiary_descriptor else cast[2])
            parts.append(f"{tertiary_block} in the background")

        parts.append("negative space for title")
        parts.append("detailed anime art, high quality")

        return ", ".join(parts)

    @staticmethod
    def _cast_block(name: str, identity: Optional[Any]) -> str:
        """Ten + (neu co ho so) tag mo ta hinh anh. Giu lai ten (khong chi
        dung mo ta) vi mot so model anime CO nhan biet tag ten nhan vat
        that (Danbooru-style) — mo ta la lop bao dam DU BIET TEN HAY
        KHONG, khong phai thay the ten."""
        if identity is None:
            return name
        descriptor = identity.to_prompt_descriptor()
        return f"{name}, {descriptor}" if descriptor else name

    @staticmethod
    def _build_count_tag(cast: List[str], identities: List[Optional[Any]]) -> str:
        """1boy/1girl/... khi TAT CA nhan vat HIEN THI co gender_presentation
        biet ro; lui ve solo/Npeople neu BAT KY ai chua biet (tranh tag
        dem sai/khong nhat quan khi tron ho so biet va chua biet)."""
        if not cast:
            return ""
        categories = [i.count_tag_category() if i else "" for i in identities]
        if all(categories):
            boys = categories.count("boy")
            girls = categories.count("girl")
            bits: List[str] = []
            if boys:
                bits.append(f"{boys}boy" if boys == 1 else f"{boys}boys")
            if girls:
                bits.append(f"{girls}girl" if girls == 1 else f"{girls}girls")
            return ", ".join(bits)
        if len(cast) == 1:
            return "solo"
        if len(cast) == 2:
            return "2people"
        return f"{len(cast)}people"

    @staticmethod
    def build_character_negative_traits(
        request: CoverGenerationRequest,
        identity_registry: Optional[CharacterIdentityRegistry] = None,
    ) -> List[str]:
        """Gop `negative_traits` tu ho so cua dan dien vien HIEN THI tren
        bia (visible cast) — CHUA duoc noi vao request HTTP that
        (HttpImageCoverProvider hien chi gui {"prompt": ...}), day la buoc
        TINH TOAN san sang cho buoc noi day tiep theo, khong phai loi
        thieu sot."""
        if identity_registry is None:
            return []
        cast = [
            c for c in (
                request.primary_character,
                request.secondary_character,
                request.tertiary_character,
            ) if c
        ][:max(0, request.max_visible_characters)]
        traits: List[str] = []
        for name in cast:
            identity = identity_registry.lookup(request.fandom, name)
            if identity:
                for trait in identity.negative_traits:
                    if trait not in traits:
                        traits.append(trait)
        return traits


def wrap_raster_as_overlayable_svg(
    png_bytes: bytes, *, width: int = 1024, height: int = 1536,
) -> bytes:
    """
    Cuon anh raster (PNG) vao mot tai lieu SVG de co the ap dung
    render_deterministic_overlay (SVG text injection) tren do.

    Phuong phap: data:image/png;base64,... trong the <image>.
    Khong can Pillow — toan bo la chuan SVG.
    """
    b64 = base64.b64encode(png_bytes).decode("ascii")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<image width="100%" height="100%" '
        f'href="data:image/png;base64,{b64}"/>'
        f'</svg>'
    )
    return svg.encode("utf-8")


class HttpImageCoverProvider:
    """
    Provider sinh anh bia that — goi endpoint self-hosted image generation
    (Illustrious/SDXL-class) qua HTTP.

    Ho tro hai kieu API chinh:
      - "a1111": Automatic1111 stable-diffusion-webui REST
        (POST /sdapi/v1/txt2img, response {"images": ["<base64>", ...]})
      - "simple": Custom REST, path CO THE CAU HINH qua `simple_path`
        (mac dinh "/generate" — GIU NGUYEN hanh vi cu cho moi provider
        "simple" hien co, response {"image_base64": "..."} hoac raw bytes)

    `simple_path` ton tai vi khong phai moi dich vu "simple" dung CUNG
    duong dan: mot Beam Cloud `@endpoint` (xem beam_apps/cover_illustrious_app.py)
    duoc goi bang POST THANG vao chinh URL deploy — KHONG co duong dan con
    "/generate" nao ca, URL deploy DA LA "endpoint" roi. Truoc ban va nay,
    class nay hardcode "/generate" cho MOI provider "simple", nen mot Beam
    endpoint that (deploy thanh cong) van tra 404 khi goi — day la loi tich
    hop THAT (khong phai loi GPU/model), phat hien qua chay benchmark that
    tren Cloud Shell. `simple_path=""` (chuoi rong) nghia la POST THANG vao
    goc URL deploy, khong noi them gi ca.

    Mau goc tu `_OpenAICompatFreeProvider` — dung httpx.Client, timeout
    dai, x loi typed (CoverProviderError) thay vi de lo httpx exception.
    """

    TIMEOUT_SECONDS: float = 120.0
    #: Duong dan mac dinh cho kieu "simple" — GIU NGUYEN de khong doi hanh
    #: vi cua moi provider "simple" hien co (vd cac test/deploy da viet
    #: truoc ban va nay). Beam va cac dich vu tuong tu truyen
    #: `simple_path=""` rieng qua constructor.
    DEFAULT_SIMPLE_PATH = "/generate"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        api_style: Literal["a1111", "simple"] = "a1111",
        simple_path: str = DEFAULT_SIMPLE_PATH,
        timeout_seconds: float = 120.0,
        client: Optional[httpx.Client] = None,
    ):
        self._api_style = api_style
        self._simple_path = simple_path
        self._timeout = timeout_seconds
        if client is not None:
            self._client = client
            if api_key:
                self._client.headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers: dict[str, str] = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            self._client = httpx.Client(
                base_url=base_url.rstrip("/"),
                headers=headers,
                timeout=self._timeout,
            )

    provider_name: str = "http_image"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        prompt = CoverPromptBuilder.build_prompt(request)

        try:
            if self._api_style == "a1111":
                return self._call_a1111(prompt)
            return self._call_simple(prompt)
        except httpx.HTTPError as exc:
            raise CoverProviderError(
                f"Loi goi dich vu sinh anh: {exc}") from exc

    def _call_a1111(self, prompt: str) -> bytes:
        payload = {
            "prompt": prompt,
            "steps": 28,
            "width": 1024,
            "height": 1536,
        }
        try:
            resp = self._client.post("/sdapi/v1/txt2img", json=payload)
        except httpx.HTTPError as exc:
            raise CoverProviderError(
                f"Loi goi dich vu sinh anh: {exc}") from exc

        if resp.status_code != 200:
            raise CoverProviderError(
                f"Dich vu sinh anh tra loi {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            raw_b64 = data["images"][0]
        except (KeyError, IndexError, ValueError) as exc:
            raise CoverProviderError(
                "Phan hoi dich vu sinh anh khong dung dinh dang.") from exc

        return base64.b64decode(raw_b64)

    def _call_simple(self, prompt: str) -> bytes:
        payload = {"prompt": prompt}
        try:
            resp = self._client.post(self._simple_path, json=payload)
        except httpx.HTTPError as exc:
            raise CoverProviderError(
                f"Loi goi dich vu sinh anh: {exc}") from exc

        if resp.status_code != 200:
            raise CoverProviderError(
                f"Dich vu sinh anh tra loi {resp.status_code}: {resp.text[:300]}")

        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                data = resp.json()
                return base64.b64decode(data["image_base64"])
            except (KeyError, ValueError) as exc:
                raise CoverProviderError(
                    "Phan hoi JSON khong co image_base64 hop le.") from exc

        return resp.content


#: Mau nen TAT DINH theo bang bam — cung fandom+mood LUON ra cung mau, khong
#: ngau nhien, khong can model. Bang mau ngan, de doc, KHONG phai bang tra
#: cuu day du — muc dich la phan biet truc quan cac truyen khac nhau tren
#: trang danh sach, khong phai mot he thong thiet ke.
_MAU_NEN = (
    "#3b3a63", "#5c3d5c", "#3d5c56", "#5c4a3d", "#3d4a5c", "#5c3d3d", "#3d5c4f",
)


class PlaceholderCoverProvider:
    """
    Anh bia TAM THOI khi CHUA chon model sinh anh that (mission: "Do NOT
    leave first real works without a visual asset... create deterministic
    placeholder/templated cover assets"). Sinh SVG (van ban thuan, KHONG
    can Pillow/thu vien anh nao) — nen mau tat dinh tu hash(fandom+mood),
    CHUA co tieu de: `CoverPipelineService.render_deterministic_overlay`
    chen tieu de sau, cung mot co che.

    CO CHU Y day KHONG PHAI "model sinh anh" — day la khung/nen trong, giu
    dung ranh gioi `CoverProvider` de sau nay thay bang provider that ma
    khong doi `CoverPipelineService`/HTTP route nao ca."""

    provider_name: str = "placeholder_svg"

    def generate(self, request: CoverGenerationRequest) -> bytes:
        seed = f"{request.fandom}|{request.mood}".encode("utf-8")
        mau = _MAU_NEN[int(hashlib.sha256(seed).hexdigest(), 16) % len(_MAU_NEN)]
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" '
            'viewBox="0 0 600 800">'
            f'<rect width="600" height="800" fill="{mau}"/>'
            '</svg>'
        )
        return svg.encode("utf-8")


class CoverJobStatus(str, Enum):
    """
    Trạng thái vòng đời của một công việc sinh ảnh bìa.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class CoverJob:
    """
    Bản ghi quản lý vòng đời của một tác vụ sinh ảnh bìa.
    """

    novel_id: str
    request: CoverGenerationRequest
    job_id: str = field(default_factory=lambda: new_id("cvj"))
    status: CoverJobStatus = CoverJobStatus.PENDING
    provider_name: str = ""
    media_asset_id: Optional[str] = None
    error_message: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


class CoverPipelineService:
    """
    Dịch vụ điều phối luồng sinh ảnh bìa và lưu trữ kết quả dưới dạng MediaAsset.
    """

    def __init__(self, media_asset_store: Any, provider: CoverProvider):
        self._media_asset_store = media_asset_store
        self._provider = provider

    def render_deterministic_overlay(self, base_image: bytes, title: str) -> bytes:
        """
        Ghi đè tiêu đề một cách tất định lên ảnh bìa gốc.

        Không phụ thuộc vào mô hình AI để render chữ nhằm tránh lỗi chính tả.

        SVG là trường hợp ĐẶC BIỆT: chèn một thẻ `<text>` vào ngay trước
        `</svg>` là thao tác chuỗi thuần tuý, không cần Pillow/thư viện ảnh
        nào — trình duyệt/trình xem tự render chữ đó khi hiển thị, đây vẫn
        là "code quyết định chữ nằm ở đâu", không phải model đoán. Với ảnh
        RASTER (PNG/JPEG chẳng hạn, từ một provider thật sau này), phương
        thức vẫn giữ nguyên hành vi cũ: trả ảnh gốc nếu tiêu đề rỗng, hoặc
        raise NotImplementedError vì việc đó cần quyết định thư viện ảnh
        (vd Pillow) chưa được đưa ra.
        """
        if not title:
            return base_image
        text_thap = base_image.lstrip()[:200].lower()
        if text_thap.startswith(b"<?xml") or text_thap.startswith(b"<svg"):
            return self._chen_tieu_de_vao_svg(base_image, title)
        raise NotImplementedError(
            "Text overlay rendering requires an image manipulation library decision (e.g. Pillow) which has not yet been made."
        )

    @staticmethod
    def _chen_tieu_de_vao_svg(svg_bytes: bytes, title: str) -> bytes:
        """Chen mot the `<text>` TAT DINH ngay truoc `</svg>` — escape XML
        that su (khong chi thay the '<'/'>' rieng le, con '&' truoc ca hai
        de khong tao thuc the XML sai)."""
        an_toan = (
            title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        the_van_ban = (
            '<text x="300" y="740" text-anchor="middle" '
            'font-family="sans-serif" font-size="32" fill="#ffffff">'
            f"{an_toan}</text>"
        )
        svg_text = svg_bytes.decode("utf-8")
        return svg_text.replace("</svg>", the_van_ban + "</svg>").encode("utf-8")

    def run_job(self, job: CoverJob) -> CoverJob:
        """
        Thực thi một tác vụ sinh ảnh bìa:
        1. Gọi provider sinh ảnh.
        2. Áp dụng overlay tiêu đề tất định.
        3. Tạo MediaAsset tương ứng trong kho lưu trữ.
        4. Cập nhật trạng thái DONE hoặc FAILED (kèm thông báo lỗi nếu có).
        """
        job.status = CoverJobStatus.RUNNING
        job.provider_name = (
            getattr(self._provider, "provider_name", "")
            or self._provider.__class__.__name__
        )
        job.updated_at = now_iso()

        try:
            raw_bytes = self._provider.generate(job.request)
            # Provider tra RASTER (PNG tu HttpImageCoverProvider that su) +
            # co tieu de can chen: render_deterministic_overlay chi biet chen
            # <text> vao SVG, nem NotImplementedError voi raster thuan (quyet
            # dinh thu vien anh nhu Pillow chua duoc dua ra). Cuon raster vao
            # mot SVG bao ngoai (wrap_raster_as_overlayable_svg) TRUOC —
            # khong can Pillow, ket qua van la SVG hop le de overlay chen
            # chu binh thuong. Chi ap dung khi CO tieu de: khong tieu de thi
            # giu nguyen dinh dang provider tra ve (vd PlaceholderCoverProvider
            # tra SVG, khong can cuon).
            overlay_input = raw_bytes
            if job.request.title:
                dau = raw_bytes.lstrip()[:5].lower()
                la_svg = dau.startswith(b"<?xml") or dau.startswith(b"<svg")
                if not la_svg:
                    overlay_input = wrap_raster_as_overlayable_svg(raw_bytes)
            final_bytes = self.render_deterministic_overlay(
                overlay_input, job.request.title
            )

            content_hash = hashlib.sha256(final_bytes).hexdigest()
            # Duoi tep THEO DUNG dinh dang byte that su tra ve — mot provider
            # SVG (vd `PlaceholderCoverProvider`) khong duoc dat ten `.png`,
            # se sai dinh dang khi mot client khac (hay chinh trinh duyet)
            # doc theo phan duoi.
            duoi = "svg" if final_bytes.lstrip()[:5].lower().startswith(b"<?xml") \
                or final_bytes.lstrip()[:4].lower().startswith(b"<svg") else "png"
            object_key = f"covers/{job.novel_id}/{job.job_id}.{duoi}"

            asset = MediaAsset(
                owner_id=job.novel_id,
                media_type=MediaType.IMAGE,
                storage_tier=StorageTier.HOT,
                object_key=object_key,
                content_hash=content_hash,
                source=job.provider_name or "cover_pipeline",
                size_bytes=len(final_bytes),
                processing_state=MediaProcessingState.READY,
            )
            created_asset = self._media_asset_store.create_asset(asset)
            job.media_asset_id = created_asset.asset_id
            job.status = CoverJobStatus.DONE
            job.error_message = ""
        except Exception as exc:
            job.status = CoverJobStatus.FAILED
            job.error_message = str(exc)
        finally:
            job.updated_at = now_iso()

        return job
