"""Production Naming Standards for Router V4 Content Factory.

Provides standard naming for production folders and web CMS:
1. Human-readable full Vietnamese with accents:
   `[Fandom] Tiêu Đề Có Dấu Đầy Đủ - Chương 01` (or `Tập 01`, `Phần 01`)
   Ví dụ:
     - `[Naruto] Đêm Nghịch Mệnh - Huyết Đồng Tái Thế - Chương 01`
     - `[Anime] Đợi Gió Đợi Ánh Sáng - Tập 01`
     - `[Naruto] Đệ Tử Orochimaru - Phần 01`
     - `[One Piece] Đại Chiến Tân Thế Giới - Tập 05`

2. URL-safe slug for SEO links:
   `naruto-dem-nghich-menh-c01`
"""

import re
import unicodedata
from typing import Optional


# Vietnamese diacritics mapping dictionary for URL slugs
VI_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'Ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd',
    'À': 'a', 'Á': 'a', 'Ả': 'a', 'Ã': 'a', 'Ạ': 'a',
    'Ă': 'a', 'Ằ': 'a', 'Ắ': 'a', 'Ẳ': 'a', 'Ẵ': 'a', 'Ặ': 'a',
    'Â': 'a', 'Ầ': 'a', 'Ấ': 'a', 'Ẩ': 'a', 'Ẫ': 'a', 'Ậ': 'a',
    'È': 'e', 'É': 'e', 'Ẻ': 'e', 'Ẽ': 'e', 'Ẹ': 'e',
    'Ê': 'e', 'Ề': 'e', 'Ế': 'e', 'Ể': 'e', 'Ễ': 'e', 'Ệ': 'e',
    'Ì': 'i', 'Í': 'i', 'Ỉ': 'i', 'Ĩ': 'i', 'Ị': 'i',
    'Ò': 'o', 'Ó': 'o', 'Ỏ': 'o', 'Õ': 'o', 'Ọ': 'o',
    'Ô': 'o', 'Ồ': 'o', 'Ố': 'o', 'Ổ': 'o', 'Ỗ': 'o', 'Ộ': 'o',
    'Ơ': 'o', 'Ờ': 'o', 'Ớ': 'o', 'Ở': 'o', 'Ỡ': 'o', 'Ợ': 'o',
    'Ù': 'u', 'Ú': 'u', 'Ủ': 'u', 'Ũ': 'u', 'Ụ': 'u',
    'Ư': 'u', 'Ừ': 'u', 'Ứ': 'u', 'Ử': 'u', 'Ữ': 'u', 'Ự': 'u',
    'Ỳ': 'y', 'Ý': 'y', 'Ỷ': 'y', 'Ỹ': 'y', 'Ỵ': 'y',
    'Đ': 'd',
}


def vietnamese_to_ascii(text: str) -> str:
    """Converts Vietnamese string to pure ASCII unaccented text."""
    if not text:
        return ""
    res = "".join(VI_MAP.get(c, c) for c in text)
    res = unicodedata.normalize("NFKD", res)
    res = "".join(c for c in res if not unicodedata.combining(c))
    return res


def extract_part_info(text: str) -> dict:
    """Extracts chapter, episode, or part number from text.
    
    Returns:
      {
        "type": "Chương" | "Tập" | "Phần",
        "num": int,
        "label_vi": "Chương 01" | "Tập 01" | "Phần 01",
        "code": "c01" | "ep01" | "p01"
      }
    """
    # Check chapter: chương, chuong, chap, chapter, c
    m_ch = re.search(r"\b(?:chương|chuong|chap|chapter|c)\s*(\d+)\b", text, re.IGNORECASE)
    if m_ch:
        num = int(m_ch.group(1))
        return {"type": "Chương", "num": num, "label_vi": f"Chương {num:02d}", "code": f"c{num:02d}"}

    # Check episode: tập, tap, tiết, tiet, ep, episode
    m_ep = re.search(r"\b(?:tập|tap|tiết|tiet|ep|episode)\s*(\d+)\b", text, re.IGNORECASE)
    if m_ep:
        num = int(m_ep.group(1))
        return {"type": "Tập", "num": num, "label_vi": f"Tập {num:02d}", "code": f"ep{num:02d}"}

    # Check part: phần, phan, part, p
    m_pt = re.search(r"\b(?:phần|phan|part|p)\s*(\d+)\b", text, re.IGNORECASE)
    if m_pt:
        num = int(m_pt.group(1))
        return {"type": "Phần", "num": num, "label_vi": f"Phần {num:02d}", "code": f"p{num:02d}"}

    return {}


def sanitize_windows_name(name: str) -> str:
    """Removes invalid Windows filesystem characters while preserving Vietnamese diacritics."""
    # Replace illegal filesystem chars (: / \ | * ? " < >) with clean dash or space
    s = re.sub(r'[\/\\:\*?\"<>\|]', ' - ', name)
    s = re.sub(r"[\'\"`#]", '', s)
    s = re.sub(r'\s*-\s*', ' - ', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip(' -.')


def clean_title_for_display(title: str, fandom: str = "") -> str:
    """Cleans title text for human-readable display with full Vietnamese diacritics."""
    t = title.strip()
    # If title starts with "[Fandom]" or "Fandom:", remove the prefix to avoid repetition
    fandom_clean = fandom.strip("[] ").lower()
    t = re.sub(rf"^\[?{re.escape(fandom_clean)}\]?\s*[:\-|–—]?\s*", "", t, flags=re.IGNORECASE)

    # Remove existing chapter/part labels from the middle of the title
    t = re.sub(r"\b(?:chương|chuong|chap|chapter|tập|tap|tiết|tiet|phần|phan|part|ep|episode)\s*\d+\b", "", t, flags=re.IGNORECASE)
    
    # Remove file extensions or technical suffixes if present
    t = re.sub(r"\.(?:mp3|mp4|mkv|wav|txt|html|htm)$", "", t, flags=re.IGNORECASE)
    # Remove common video noise: FULL HD, Vietsub, Thuyết Minh
    t = re.sub(r"\b(?:FULL(?:\s*HD)?|VIETSUB|THUYẾT MINH|AUDIOBOOK)\b", "", t, flags=re.IGNORECASE)

    return sanitize_windows_name(t)


def make_production_name(
    fandom: str,
    title: str,
    part_num: Optional[int] = None,
    default_part_type: str = "Chương",
) -> str:
    """Generates standardized, full-accent Vietnamese production folder name.
    
    Format: `[Fandom] Tiêu Đề Có Dấu Đầy Đủ - Chương 01`
    
    Examples:
      - `[Naruto] Đêm Nghịch Mệnh - Huyết Đồng Tái Thế - Chương 01`
      - `[Anime] Đợi Gió Đợi Ánh Sáng - Tập 01`
      - `[Naruto] Đệ Tử Orochimaru - Phần 01`
    """
    clean_fandom = sanitize_windows_name(fandom.strip("[] ")).strip() or "Đồng Nhân"
    clean_fandom = re.sub(r'[\/\\]', ' & ', clean_fandom).strip()
    fandom_tag = f"[{clean_fandom}]"
    part_info = extract_part_info(title)

    if part_num is not None:
        part_label = f"{default_part_type} {part_num:02d}"
    elif part_info:
        part_label = part_info["label_vi"]
    else:
        part_label = f"{default_part_type} 01"

    clean_t = clean_title_for_display(title, fandom=fandom)
    if not clean_t:
        clean_t = "Tác Phẩm"

    return f"{fandom_tag} {clean_t} - {part_label}"


STOP_WORDS = {
    "audiobook", "audio", "fanfic", "dong", "nhan", "truyen", "full", "hd",
    "vietsub", "thuyet", "minh", "tieng", "viet", "ban", "dich", "doc",
    "video", "animation", "anime", "novel", "official", "hay", "nhat"
}


def make_production_slug(
    fandom: str,
    title: str,
    part: Optional[str] = None,
    default_part_type: str = "c",
) -> str:
    """Generates ASCII URL slug for SEO routing on fanfic.world."""
    f = vietnamese_to_ascii(fandom).lower().strip()
    f = re.sub(r"[^a-z0-9]", "", f)[:15] or "fanfic"

    # Extract part code
    part_info = extract_part_info(title)
    code = part or (part_info.get("code") if part_info else f"{default_part_type}01")

    # Clean words
    ascii_t = vietnamese_to_ascii(title).lower()
    ascii_t = re.sub(r"['’]", "", ascii_t)
    chunks = [c.strip() for c in re.split(r"[:\-|–—]", ascii_t) if c.strip()]
    chosen = chunks[0] if chunks else ascii_t
    if len(chosen.split()) <= 1 and len(chunks) > 1:
        chosen = chunks[1]

    words = re.findall(r"[a-z0-9]+", chosen)
    filtered = [w for w in words if w not in STOP_WORDS] or words
    short_slug = "-".join(filtered[:4]) or "story"

    if short_slug.startswith(f + "-"):
        short_slug = short_slug[len(f) + 1:]

    return f"{f}-{short_slug}-{code}"
