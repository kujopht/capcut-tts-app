"""
Chia van ban dai thanh nhieu phan de khong gui mot request qua lon.

Quy tac uu tien (tu tren xuong):
1. Ranh gioi doan van (dong trong).
2. Ranh gioi cau (. ! ? ... va cac dau cau tieng Viet/CJK).
3. Ranh gioi menh de (, ; :) roi tiep den khoang trang giua tu.

KHONG BAO GIO cat giua mot tu. Truong hop duy nhat phai cat cung la khi ban
than mot "tu" dai hon gioi han (vi du chuoi khong co khoang trang) — luc do
moi cat theo ky tu, va viec nay duoc ghi ro trong ket qua.
"""

from __future__ import annotations

import re
from typing import List

from desktop_app.models import DEFAULT_CHUNK_CHARS, MAX_CHUNK_CHARS, MIN_CHUNK_CHARS

#: Ket thuc cau: dau cau + khoang trang, hoac dau cau + dong moi
_SENTENCE_END = re.compile(r"(?<=[.!?…。！？])[\s ]+")

#: Ranh gioi doan van: mot hoac nhieu dong trong
_PARAGRAPH_SPLIT = re.compile(r"\n[ \t]*\n+")

#: Ranh gioi menh de
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:—–])[\s ]+")


def normalize_chunk_size(value: int | None) -> int:
    """Ep gioi han chunk vao khoang cho phep."""
    try:
        size = int(value if value is not None else DEFAULT_CHUNK_CHARS)
    except (TypeError, ValueError):
        return DEFAULT_CHUNK_CHARS
    return max(MIN_CHUNK_CHARS, min(MAX_CHUNK_CHARS, size))


def _split_keep_words(text: str, limit: int) -> List[str]:
    """
    Cat mot khoi text dai hon `limit` tai ranh gioi cau -> menh de -> khoang trang.
    Chi cat giua ky tu khi khong con ranh gioi nao (tu don qua dai).
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    for splitter in (_SENTENCE_END, _CLAUSE_SPLIT):
        pieces = [p.strip() for p in splitter.split(text) if p.strip()]
        if len(pieces) > 1:
            return _pack(pieces, limit, separator=" ")

    # Khong co dau cau: gop theo tu (khoang trang)
    words = [w for w in re.split(r"[\s ]+", text) if w]
    if len(words) > 1:
        return _pack(words, limit, separator=" ")

    # Mot "tu" duy nhat dai hon limit: bat buoc cat theo ky tu
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _pack(pieces: List[str], limit: int, separator: str = " ") -> List[str]:
    """
    Gom cac manh lien tiep vao chung mot chunk cho den khi gan day `limit`.
    Manh nao tu no da qua dai thi de quy cat nho tiep.
    """
    chunks: List[str] = []
    current = ""

    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue

        if len(piece) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_keep_words(piece, limit))
            continue

        candidate = f"{current}{separator}{piece}" if current else piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece

    if current:
        chunks.append(current)
    return chunks


def chunk_text(text: str, limit: int = DEFAULT_CHUNK_CHARS) -> List[str]:
    """
    Chia `text` thanh danh sach phan, moi phan toi da `limit` ky tu.

    Van ban ngan hon `limit` tra ve danh sach 1 phan tu (khong chia).
    Van ban rong tra ve danh sach rong.
    """
    limit = normalize_chunk_size(limit)
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    if not paragraphs:
        return []

    # Gop cac doan lai; doan nao qua dai thi chia theo cau
    return _pack(paragraphs, limit, separator="\n\n")


def estimate_part_count(text: str, limit: int = DEFAULT_CHUNK_CHARS) -> int:
    """So phan du kien — dung cho bang file truoc khi chay."""
    return len(chunk_text(text, limit))


def split_display_segments(text: str) -> List[str]:
    """
    Chia MOT phan tong hop (dau ra cua `chunk_text`) thanh cac doan HIEN THI
    nho hon — doan van, roi cau — cho phu de dong bo (web V4, Phan 2G).

    KHAC voi `chunk_text`: ham do chia theo GIOI HAN KY TU de gui TTS; ham nay
    chia theo RANH GIOI NGON NGU de hien thi, khong quan tam gioi han do dai —
    mot phan 2000 ky tu co the ra vai chuc doan hien thi ngan.

    KHONG dùng cho TTS — chi dùng để hiển thị phụ đề đồng bộ với thời lượng đã
    đo được của phần cha (xem `server/transcript.py::build_transcript`).
    """
    text = (text or "").strip()
    if not text:
        return []
    doan_van = [p.strip() for p in _PARAGRAPH_SPLIT.split(text) if p.strip()]
    ra: List[str] = []
    for doan in doan_van:
        cau = [c.strip() for c in _SENTENCE_END.split(doan) if c.strip()]
        ra.extend(cau if len(cau) > 1 else [doan])
    return ra
