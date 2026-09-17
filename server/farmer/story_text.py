"""
Structured text acquisition, deterministic chapter splitting, and preflight validation.

Module nay giai quyet 3 van de goc cua Fanfic Farmer:
1. Structured Text Acquisition: Khong lam sup (collapse) cac chuong cua FanFicFare
   thanh mot chuoi vo danh; giu nguyen ranh gioi chuong goc va tieu de goc.
2. Deterministic Chapter Splitting: Cat cac chuong vuot FAS_MAX_CHAPTER_CHARS
   theo thu tu uu tien doan -> dong -> cau -> tu -> ky tu, khong mat chu, khong dao thu tu.
3. Preflight Validation: Kiem tra toan bo ke hoach xuat ban truoc khi goi
   POST /api/novels, tranh tuyet doi truyen mo coi (novel khong co chuong).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.story_limits import DEFAULT_MAX_CHAPTER_CHARS, get_max_chapter_chars

# --- Ma loi Preflight on dinh ---
PRODUCTION_TEXT_EMPTY = "PRODUCTION_TEXT_EMPTY"
PRODUCTION_TEXT_PREPARE_FAILED = "PRODUCTION_TEXT_PREPARE_FAILED"
PRODUCTION_CHAPTER_LIMIT_INVALID = "PRODUCTION_CHAPTER_LIMIT_INVALID"


class PreflightError(Exception):
    """Loi kiem tra dieu kien xuat ban truoc khi cham vao bat ky API nao."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass
class SourceChapter:
    """Mot chuong thu thap duoc tu nguon goc."""
    title: str
    content: str
    order_index: int = 1


@dataclass
class FetchedStoryText:
    """Dai dien mien cho van ban thu thap duoc tu nguon."""
    review_text: str
    chapters: List[SourceChapter]
    source_is_structured: bool = False

    @classmethod
    def from_plain_text(cls, text: str, title: str = "") -> "FetchedStoryText":
        """Tao tu van ban tho (generic HTTP), coi nhu 1 chuong logic ban dau."""
        content = (text or "")
        ch = SourceChapter(title=title or "Chương 1", content=content, order_index=1)
        return cls(review_text=content, chapters=[ch], source_is_structured=False)

    @classmethod
    def from_source_chapters(cls, chapters: Sequence[SourceChapter],
                             review_text: Optional[str] = None) -> "FetchedStoryText":
        """Tao tu danh sach chuong co cau truc (vd FanFicFare)."""
        valid = [c for c in chapters if (c.content or "").strip()]
        if review_text is None:
            review_text = "\n\n".join(c.content for c in valid)
        return cls(review_text=review_text, chapters=valid, source_is_structured=True)


@dataclass
class PreparedChapter:
    """Mot chuong da chuan hoa va san sang xuat ban (<= FAS_MAX_CHAPTER_CHARS)."""
    title: str
    content: str
    order_index: int
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash and self.content:
            self.content_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class PreparedStoryPlan:
    """Ke hoach xuat ban hoan chinh cho mot tac pham."""
    chapters: List[PreparedChapter]
    total_chars: int
    review_text: str
    is_structured: bool = False


_SENTENCE_RE = re.compile(r'[.!?…。！？]["\'”’)]?[\s]+')
_SPACE_RE = re.compile(r'\s+')
_NHIEU_DONG_TRONG = re.compile(r"\n{3,}")
_CUOI_DONG = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_text(raw: str) -> str:
    """Chuan hoa van ban NFC, bo khoang trang thua cuoi dong."""
    s = unicodedata.normalize("NFC", raw or "").replace("\r\n", "\n").replace("\r", "\n")
    s = _CUOI_DONG.sub("", s)
    s = _NHIEU_DONG_TRONG.sub("\n\n", s).strip()
    return s + "\n" if s else ""


def split_chapter_content(content: str, max_chars: int) -> List[str]:
    """
    Cat mot chuong dai thanh cac phan <= max_chars theo thu tu uu tien:
      1. Ranh gioi doan van (\\n\\n)
      2. Ranh gioi dong don (\\n)
      3. Ranh gioi cau (. ! ? ...)
      4. Khoang trang ( )
      5. Cat ky tu cung (fallback)

    Bao dam tuyet doi:
      - len(chunk) <= max_chars voi moi chunk
      - ''.join(chunks) == content (khong mat chu nao)
      - Thu tu giu nguyen
    """
    if max_chars <= 0:
        raise PreflightError(PRODUCTION_CHAPTER_LIMIT_INVALID, f"Gioi han ky tu chuong phai > 0, nhan duoc: {max_chars}")
    if not content:
        return []
    if len(content) <= max_chars:
        return [content]

    chunks: List[str] = []
    start = 0
    total_len = len(content)

    while start < total_len:
        remaining = total_len - start
        if remaining <= max_chars:
            chunks.append(content[start:])
            break

        window_end = start + max_chars
        cut: Optional[int] = None

        # 1. Ranh gioi doan van: \n\n
        p_idx = content.rfind("\n\n", start, window_end)
        if p_idx != -1 and (p_idx + 2) > start:
            cut = p_idx + 2

        # 2. Ranh gioi dong don: \n
        if cut is None:
            n_idx = content.rfind("\n", start, window_end)
            if n_idx != -1 and (n_idx + 1) > start:
                cut = n_idx + 1

        # 3. Ranh gioi cau
        if cut is None:
            window_text = content[start:window_end]
            matches = list(_SENTENCE_RE.finditer(window_text))
            if matches:
                last_m = matches[-1]
                if last_m.end() > 0 and (start + last_m.end()) > start:
                    cut = start + last_m.end()

        # 4. Khoang trang
        if cut is None:
            window_text = content[start:window_end]
            matches = list(_SPACE_RE.finditer(window_text))
            if matches:
                last_m = matches[-1]
                if last_m.end() > 0 and (start + last_m.end()) > start:
                    cut = start + last_m.end()

        # 5. Fallback: cat cung tai window_end
        if cut is None or cut <= start:
            cut = window_end

        chunks.append(content[start:cut])
        start = cut

    return chunks


def prepare_story_plan(
    fetched: FetchedStoryText,
    title: str = "",
    max_chars: Optional[int] = None,
) -> PreparedStoryPlan:
    """
    Kiem tra preflight va chuan bi ke hoach xuat ban cac chuong.

    Nem PreflightError neu:
    - Van ban rong (PRODUCTION_TEXT_EMPTY)
    - Gioi han ky tu <= 0 (PRODUCTION_CHAPTER_LIMIT_INVALID)
    - Khong chuong nao con lai sau chuan hoa (PRODUCTION_TEXT_PREPARE_FAILED)
    """
    limit = max_chars if max_chars is not None else get_max_chapter_chars()
    if limit <= 0:
        raise PreflightError(
            PRODUCTION_CHAPTER_LIMIT_INVALID,
            f"Giới hạn ký tự chương không hợp lệ: {limit}",
        )

    if not fetched or not (fetched.review_text or "").strip():
        raise PreflightError(
            PRODUCTION_TEXT_EMPTY,
            "Nội dung truyện rỗng, không thể xuất bản novel",
        )

    valid_source_chapters = [
        c for c in fetched.chapters if (c.content or "").strip()
    ]
    if not valid_source_chapters:
        raise PreflightError(
            PRODUCTION_TEXT_EMPTY,
            "Không có chương nào có nội dung trong tác phẩm",
        )

    prepared: List[PreparedChapter] = []
    order_idx = 1

    for src_ch in valid_source_chapters:
        norm_content = normalize_text(src_ch.content)
        if not norm_content.strip():
            continue

        base_title = (src_ch.title or title or f"Chương {order_idx}").strip()

        if len(norm_content) <= limit:
            prepared.append(
                PreparedChapter(
                    title=base_title,
                    content=norm_content,
                    order_index=order_idx,
                )
            )
            order_idx += 1
        else:
            pieces = split_chapter_content(norm_content, limit)
            total_pieces = len(pieces)
            for sub_idx, piece in enumerate(pieces, 1):
                sub_title = f"{base_title} ({sub_idx}/{total_pieces})"
                prepared.append(
                    PreparedChapter(
                        title=sub_title,
                        content=piece,
                        order_index=order_idx,
                    )
                )
                order_idx += 1

    if not prepared:
        raise PreflightError(
            PRODUCTION_TEXT_PREPARE_FAILED,
            "Chuẩn bị chương thất bại: không có chương hợp lệ sau khi chuẩn hoá",
        )

    total_chars = sum(len(p.content) for p in prepared)
    return PreparedStoryPlan(
        chapters=prepared,
        total_chars=total_chars,
        review_text=fetched.review_text,
        is_structured=fetched.source_is_structured,
    )


def verify_served_novel(
    novel_data: Dict[str, Any],
    plan: PreparedStoryPlan,
    max_chars: Optional[int] = None,
    raise_on_error: bool = True,
) -> Tuple[bool, str]:
    """
    Xac minh mot novel doc tu GET /api/novels/{id} co phuc vu DAY DU va DUNG
    ke hoach da duoc duyet hay khong.
    """
    def _fail(msg: str) -> Tuple[bool, str]:
        if raise_on_error:
            raise PreflightError(PRODUCTION_TEXT_PREPARE_FAILED, msg)
        return False, msg

    limit = max_chars if max_chars is not None else get_max_chapter_chars()
    nid = (novel_data or {}).get("novel_id") or ((novel_data or {}).get("novel") or {}).get("novel_id")
    if not novel_data or not nid:
        return _fail("Novel không tồn tại hoặc dữ liệu rỗng")

    chapters = sorted(
        novel_data.get("chapters") or [],
        key=lambda c: c.get("order_index", 0),
    )

    expected_count = len(plan.chapters)
    actual_count = len(chapters)

    if actual_count != expected_count:
        return _fail(f"Số lượng chương không khớp: mong đợi {expected_count}, thực tế có {actual_count}")

    if actual_count == 0:
        return _fail("Novel không có chương nào (zero chapters)")

    for idx, (exp, act) in enumerate(zip(plan.chapters, chapters), 1):
        act_order = act.get("order_index")
        if act_order != exp.order_index:
            return _fail(f"Thứ tự chương {idx} sai: mong đợi {exp.order_index}, thực tế {act_order}")

        act_content = act.get("content", "")
        if not act_content.strip():
            return _fail(f"Chương {idx} ({exp.title}) có nội dung rỗng")

        if len(act_content) > limit:
            return _fail(f"Chương {idx} ({exp.title}) vượt giới hạn ký tự: {len(act_content)} > {limit}")

        act_hash = hashlib.sha256(act_content.encode("utf-8")).hexdigest()
        if exp.content_hash and act_hash != exp.content_hash:
            norm_act = normalize_text(act_content)
            norm_exp = normalize_text(exp.content)
            if norm_act != norm_exp:
                return _fail(f"Nội dung chương {idx} ({exp.title}) không khớp bản gốc đã chuẩn bị")

    return True, ""
