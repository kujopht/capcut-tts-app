"""Cover Generator Engine: Professional Artwork & Background Creation for Fanfic Works.

Supports 16:9 Landscape (ảnh ngang) high-definition (1920x1080) artwork across all 3 branches:
1. Branch 1 (Audiobook YouTube): Clean YouTube watermark, crop letterbox, apply cinematic gradient & overlay fantasy typography.
2. Branch 2 (Truyện TTS Novel): Beam Cloud GPU (Animagine XL 4.0) 16:9 anime illustrations with glowing fantasy titles & chapter badges.
3. Branch 3 (Phim AI Animation): Native video thumbnail/frame with deep scrim to eliminate legacy subtitles, overlaying Vietnamese fantasy title & episode badge.
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    Image = None  # type: ignore

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")


# Fantasy & Cinematic Fonts
FONT_FANTASY = PROJECT_ROOT / "scripts" / "content_factory" / "fonts" / "Philosopher-Bold.ttf"
FONT_CINZEL = PROJECT_ROOT / "scripts" / "content_factory" / "fonts" / "Cinzel.ttf"
FONT_CONSTANTIA_BOLD = "C:/Windows/Fonts/constanb.ttf"
FONT_GEORGIA_BOLD = "C:/Windows/Fonts/georgiab.ttf"
FONT_CAMBRIA_BOLD = "C:/Windows/Fonts/cambriab.ttf"
FONT_SEGOE_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_ARIAL_BOLD = "C:/Windows/Fonts/arialbd.ttf"


def get_fantasy_font(size: int, prefer_cinzel: bool = False) -> ImageFont.FreeTypeFont:
    """Loads specialized fantasy novel fonts with full Vietnamese diacritics support."""
    candidates = []
    if prefer_cinzel and FONT_CINZEL.exists():
        candidates.append(str(FONT_CINZEL))
    if FONT_FANTASY.exists():
        candidates.append(str(FONT_FANTASY))
    candidates.extend([
        FONT_CONSTANTIA_BOLD,
        FONT_GEORGIA_BOLD,
        FONT_CAMBRIA_BOLD,
        FONT_SEGOE_BOLD,
        FONT_ARIAL_BOLD,
        "arial.ttf",
    ])
    for cand in candidates:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_fantasy_glowing_text(
    canvas: Image.Image,
    text: str,
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    glow_color: Tuple[int, int, int, int] = (255, 180, 40, 200),
    text_color: Tuple[int, int, int] = (255, 235, 150),
    glow_radius: int = 10,
    outline_color: Tuple[int, int, int, int] = (20, 15, 10, 220),
) -> Image.Image:
    """Renders radiant glowing text with deep 3D shadow and crisp outline."""
    # 1. Soft Radiant Glow
    glow_mask = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow_mask)
    g_draw.text((x, y), text, font=font, fill=glow_color)
    blurred_glow = glow_mask.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    canvas = Image.alpha_composite(canvas, blurred_glow)

    # 2. Deep 3D Shadow
    s_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(s_layer)
    s_draw.text((x + 4, y + 4), text, font=font, fill=(0, 0, 0, 240))
    canvas = Image.alpha_composite(canvas, s_layer)

    # 3. Fine Dark Outline
    t_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(t_layer)
    for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]:
        t_draw.text((x + ox, y + oy), text, font=font, fill=outline_color)
    t_draw.text((x, y), text, font=font, fill=text_color)
    canvas = Image.alpha_composite(canvas, t_layer)
    return canvas


def clean_youtube_watermark(source_image: Image.Image) -> Image.Image:
    """Cleans YouTube thumbnails: crops letterboxing, zooms to cut out edge logos & numbers."""
    img = source_image.convert("RGB")

    # 1. Detect & remove black letterbox bars if numpy is available
    if np is not None:
        arr = np.array(img)
        row_means = arr.mean(axis=(1, 2))
        valid_rows = np.where(row_means > 14)[0]
        if len(valid_rows) > 0:
            ymin, ymax = valid_rows[0], valid_rows[-1]
            if ymax - ymin > int(img.height * 0.6):
                img = img.crop((0, ymin, img.width, ymax))

    # 2. Smart center zoom (crop 18% top text, 8% bottom watermark, 8% sides)
    cw, ch = img.size
    crop_x1 = int(cw * 0.08)
    crop_x2 = int(cw * 0.92)
    crop_y1 = int(ch * 0.18)
    crop_y2 = int(ch * 0.92)
    img_focal = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
    return img_focal


def download_remote_cover(cover_url: str, dest_path: Path) -> bool:
    """Downloads a high-resolution cover image using curl.exe."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "curl.exe", "-s", "-L", "--max-time", "15",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        cover_url,
        "-o", str(dest_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
        if dest_path.exists() and dest_path.stat().st_size > 1000:
            return True
    except Exception as exc:
        print(f"[CoverGen] Cảnh báo tải ảnh bìa từ {cover_url} thất bại: {exc}")
    return False


GENERIC_COVER_TAGS = {"FANFIC", "ĐỒNG NHÂN", "AUDIO", "TRUYỆN AUDIO", "AUDIOBOOK", "SÁCH NÓI", "TIỂU THUYẾT", "LIGHT NOVEL"}


def split_title_smart(title: str, max_line1_len: int = 26) -> Tuple[str, str]:
    """Logically splits a title into Primary Series Title (Line 1) and Subtitle/Arc/Chapter (Line 2).
    
    Prevents awkward word cutoffs and strips out redundant episode suffixes since they are
    already displayed prominently in the top-right episode badge.
    """
    t = re.sub(r"^\[.*?\]\s*", "", title).strip()
    t = re.sub(r"[\s\-_–—]+(Phần|Tập|Chương)\s*\d+.*$", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"\s*\((Phần|Tập|Chương)\s*\d+.*\)$", "", t, flags=re.IGNORECASE).strip()

    # Strip leading generic words
    for gt in list(GENERIC_COVER_TAGS):
        t = re.sub(r"^" + gt + r"[\s\-_:–|]+", "", t, flags=re.IGNORECASE).strip()

    if ":" in t:
        p1, p2 = t.split(":", 1)
        p1, p2 = p1.strip(), p2.strip()
        if p1.upper() not in GENERIC_COVER_TAGS and 0 < len(p1.split()) <= 5 and len(p2.split()) >= 1:
            return p1.upper(), p2

    for sep in [" - ", " – ", " — "]:
        if sep in t:
            parts = [p.strip() for p in t.split(sep) if p.strip()]
            valid = [p for p in parts if p.upper() not in GENERIC_COVER_TAGS]
            if len(valid) >= 2:
                p1, p2 = valid[0], " ".join(valid[1:])
                if len(p1.split()) <= 8:
                    return p1.upper(), p2

    words = t.split()
    if len(words) <= 5:
        return t.upper(), ""

    cur = []
    line1 = ""
    for w in words:
        if len(" ".join(cur + [w])) <= max_line1_len or len(cur) < 3:
            cur.append(w)
        else:
            line1 = " ".join(cur)
            break
    if not line1:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
    else:
        line2 = " ".join(words[len(cur):])
    return line1.upper(), line2


def build_character_centric_prompt(
    title: str,
    fandom: str = "",
    summary: str = "",
    part_label: str = "",
) -> str:
    """Builds optimized character-centric anime illustration prompts for Animagine XL 4.0.
    
    Guarantees prominent, dynamic anime characters (protagonist), action poses,
    powers/auras, and unique artwork variations per episode/chapter.
    """
    text_ctx = f"{fandom} {title} {summary} {part_label}".lower()
    base_prefix = "masterpiece, best quality, newest, cinematic lighting, dramatic angle, anime key visual, 8k wallpaper"

    # Check part / chapter number for dynamic pose variations
    is_part_2 = any(k in (part_label.lower() + " " + title.lower()) for k in ["phần 02", "phần 2", "chương 02", "chương 2", "tập 02", "tập 2", "p02", "c02"])

    # 1. Dragon Ball / Super Saiyan crossover (e.g. One Piece x Dragon Ball)
    if any(k in text_ctx for k in ["saiyan", "dragon ball", "siêu saiyan", "goku", "kamehameha"]):
        if is_part_2:
            return (
                f"{base_prefix}, 1boy, super saiyan 2, spiky glowing golden hair, fierce cyan eyes, "
                "golden ki aura, glowing energy sphere in hand, preparing energy blast, black pirate coat, "
                "dynamic action angle, night stormy ocean, dark clouds, lightning, cinematic anime CG"
            )
        else:
            return (
                f"{base_prefix}, 1boy, super saiyan, spiky glowing golden hair, turquoise eyes, "
                "golden aura, energy crackle, muscular build, open black pirate captain coat, "
                "standing on pirate ship deck, stormy sea, lightning, dramatic action pose"
            )

    # 2. One Piece / Doctor / Medical Devil Fruit (Tế Bào / Bác Sĩ)
    if any(k in text_ctx for k in ["bác sĩ", "y sư", "tế bào", "chữa trị", "thuốc", "doctor"]):
        return (
            f"{base_prefix}, 1boy, young handsome doctor pirate, dark slicked hair, sharp glowing cyan eyes, "
            "long dark pirate coat with silver trim, glowing turquoise and golden biological cellular aura around hands, "
            "holding surgical blade infused with devil fruit energy, confident smirk, pirate deck at night"
        )

    # 2b. Kaido Son / Oni Prince / Beast Pirates / World King
    if any(k in text_ctx for k in ["kaido", "bách thú", "vua thế giới", "thần long", "con trai kaido", "oni"]):
        if is_part_2:
            return (
                f"{base_prefix}, 1boy, powerful oni dragon warrior prince, demonic horns on head, "
                "intense glowing crimson eyes, dark azure dragon scales covering arm, roaring azure dragon spirit behind him, "
                "spiked kanabo club surrounded by black and red conqueror lightning haki, fiery ruins of onigashima, stormy night, epic key visual"
            )
        else:
            return (
                f"{base_prefix}, 1boy, young handsome oni warrior prince, horns on head, wild dark hair, "
                "sharp glowing amber eyes, muscular build, dark fur-trimmed cloak, spiked kanabo club resting on shoulder with red lightning haki crackles, "
                "confident domineering smirk, skull fortress onigashima background, stormy sky with lightning"
            )

    # 3. One Piece / Vice Captain Rocks / Swordsman / Conqueror Haki
    if any(k in text_ctx for k in ["one piece", "hải tặc", "rocks", "phó thuyền trưởng", "kiếm hào", "tứ hoàng", "haki", "trảm"]):
        if is_part_2:
            return (
                f"{base_prefix}, 1boy, pirate swordsman, black pirate captain coat with gold trim, "
                "intense battle expression, dual katanas coated in dark purple and crimson conqueror haki lightning, "
                "leaping sword slash, shattered warship masts, ocean vortex, dynamic perspective"
            )
        else:
            return (
                f"{base_prefix}, 1boy, young badass pirate vice-captain, dark messy hair, sharp glowing crimson eyes, "
                "black coat with gold epaulets, holding katana with dark purple lightning armament haki, "
                "confident grin, dramatic action stance, fiery ruined battleship deck, sparks and smoke"
            )

    # 4. Naruto / Mokuton (Wood Release) / Jiraiya Disciple
    if any(k in text_ctx for k in ["mộc độn", "jiraiya", "thụ giới", "senju"]):
        if is_part_2:
            return (
                f"{base_prefix}, 1boy, young shinobi prodigy, green glowing chakra aura, "
                "summoning giant wooden dragon jutsu, dynamic action jumping pose, intense battle gaze, "
                "wood release blooming branches, shattered rocks, dark storm forest"
            )
        else:
            return (
                f"{base_prefix}, 1boy, young prodigy shinobi, leaf village headband, spiky dark brown hair, "
                "glowing emerald green chakra aura, wood release jutsu, wooden branches and roots sprouting from ground, "
                "fierce determined eyes, ninja combat stance, konoha forest background"
            )

    # 5. Naruto / Uchiha / Sharingan / Ninja general
    if any(k in text_ctx for k in ["naruto", "hỏa ảnh", "uchiha", "sharingan", "luân hồi", "ninja", "shinobi", "làng lá"]):
        return (
            f"{base_prefix}, 1boy, young uchiha shinobi, glowing red sharingan eyes, black hair, "
            "high-collar navy shinobi clothes, blue chidori lightning aura in hand, dramatic night stance, "
            "ruined konoha rooftops, crimson moon"
        )

    # 6. Jujutsu Kaisen / Cursed Energy
    if any(k in text_ctx for k in ["jujutsu", "chú thuật", "sukuna", "gojo", "chú lực", "nguyền hồn"]):
        return (
            f"{base_prefix}, 1boy, jujutsu sorcerer, black high-collar uniform, glowing violet cursed energy aura around fists, "
            "fierce intense eyes, dynamic martial arts combat pose, nocturnal shibuya cityscape with shattered glass and neon lights"
        )

    # 7. Bleach / Shinigami
    if any(k in text_ctx for k in ["bleach", "tử thần", "shinigami", "trảm hồn", "bankai"]):
        return (
            f"{base_prefix}, 1boy, soul reaper shinigami, black shihakusho robe fluttering, "
            "wielding glowing katana zanpakuto, blue spiritual pressure reiatsu erupting, intense gaze, gothic celestial ruins under crescent moon"
        )

    # 8a. Supernatural Comedy / Glasses / Ghost Rules (Cận Thị Nghìn Độ / Quy Tắc Quái Đàm / Linh Dị)
    if any(k in text_ctx for k in ["cận thị", "quái đàm", "linh dị", "hài kịch", "hài hước", "sa điêu", "kính cận", "ghost", "quỷ dị"]):
        return (
            f"{base_prefix}, 1boy, handsome quirky anime high school boy with round eyeglasses, one lens comically cracked, "
            "funny confident clueless smile, neat school uniform, surrounded by translucent cute funny shadowy ghost spirits, "
            "eerie illuminated night school hallway with lanterns, vibrant comedic supernatural anime key visual, cinematic lighting"
        )

    # 8b. Blind Girl in Noble Boy's School / Yandere / Elite Academy (Giả Mù Ở Trường Nam Sinh)
    if any(k in text_ctx for k in ["giả mù", "mù", "blind", "bệnh kiều", "yandere", "nam hiệu", "trường nam sinh", "quý tộc", "thiếu gia", "tài phiệt"]):
        return (
            f"{base_prefix}, 1girl, stunningly beautiful anime heroine, porcelain skin, long silky dark hair, "
            "delicate black silk blindfold covering eyes, elegant elite academy uniform with gold filigree, regal dignified posture, "
            "two handsome aristocratic young men in tailored suits gazing at her with intense devotion and obsession, "
            "luxurious grand academy ballroom, opulent crystal chandelier, dramatic romantic lighting, otome visual novel CG"
        )

    # 8c. Sweet Youth / Childhood Friends / Sweet Romance (Điềm Điềm Tiểu Tuyết / Thanh xuân vườn trường)
    if any(k in text_ctx for k in ["tiểu tuyết", "điềm điềm", "thanh mai", "trúc mã", "ngọt sủng", "ngọt ngào", "thanh xuân", "lãng mạn", "tình cảm", "school romance", "đồng cư"]):
        return (
            f"{base_prefix}, 1girl, 1boy, breathtakingly cute anime girl with long silky chestnut hair, sweet shy smile, "
            "soft pink blush, beside handsome gentle high school boy with affectionate gaze, matching modern school uniforms, "
            "walking together under falling pink cherry blossom petals, warm golden sunlight, romantic emotional atmosphere, shoujo manga anime key visual"
        )

    # 8d. Ancient Chinese Palace / Court Romance / Imperial Lord (Kinh Hồng Nhập Mộng / Cổ đại)
    if any(k in text_ctx for k in ["cổ đại", "quyền thần", "trưởng huynh", "từ hôn", "tra nam", "kinh hồng", "hoàng đế", "vương gia", "cung đình", "hầu phủ", "hanfu"]):
        return (
            f"{base_prefix}, 1girl, 1man, breathtakingly gorgeous noble lady in flowing crimson and gold embroidered ancient Chinese hanfu silk robes, "
            "delicate jade hairpins, next to handsome imposing imperial minister with long tied black hair in dark dragon robes, "
            "royal palace courtyard with blooming red plum blossoms, romantic historical Chinese anime visual novel CG"
        )

    # 8e. Modern Urban Romance / Wealthy Family Recognition (亲子鉴定 / Nhận thân / Hào môn)
    if any(k in text_ctx for k in ["phó gia", "nhận thân", "thế gia", "tổng tài", "hào môn", "đô thị", "phú hào"]):
        return (
            f"{base_prefix}, 1girl, delicate beautiful anime heroine with long wavy hair, elegant white modern dress, "
            "gentle emotional expression, handsome protective wealthy CEO brother beside her, modern high-end penthouse balcony, "
            "glittering city skyline night view, emotional family romance anime visual novel CG"
        )

    # 9. Generic Fantasy / Isekai
    return (
        f"{base_prefix}, 1boy, fantasy anime protagonist hero, glowing magical blade, "
        "arcane runes floating, flowing adventurer cloak, heroic battle stance, floating crystal fantasy citadel background, dramatic sunset lighting"
    )


# Backward-compatible wrapper
def build_anime_prompt_for_novel(title: str, fandom: str, summary: str = "", part_label: str = "") -> str:
    return build_character_centric_prompt(title=title, fandom=fandom, summary=summary, part_label=part_label)


def generate_anime_art_via_beam(
    prompt: str,
    output_path: Path,
    negative_prompt: str = "worst quality, low quality, blurry, deformed, bad anatomy, bad hands, extra limbs, text, watermark, logo, duplicate, cropped",
    width: int = 1216,
    height: int = 832,
    seed: Optional[int] = None,
) -> bool:
    """Generates serverless 16:9 anime illustration using Beam Cloud GPU (Animagine XL)."""
    if seed is None:
        seed = random.randint(1000, 99999999)
    try:
        from server.openmontage_worker.image_provider import BeamAnimagineProvider
        provider = BeamAnimagineProvider()
        provider.URL = "https://cover-illustrious-fe39340-v11.app.beam.cloud"
        print(f"[CoverGen] Đang sinh ảnh bìa Anime qua Beam Cloud GPU (Seed: {seed}, Prompt: '{prompt[:55]}...')...")
        res = provider.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            seed=seed,
            width=width,
            height=height,
        )
        if res.png_bytes:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(res.png_bytes)
            print(f"[CoverGen] ✅ Beam Cloud sinh ảnh thành công ({len(res.png_bytes)} bytes trong {res.wall_seconds:.1f}s)")
            return True
    except Exception as exc:
        print(f"[CoverGen] Beam Cloud không khả dụng, dùng fallback procedural: {exc}")
    return False


def generate_landscape_fanfic_cover(
    title: str,
    author: str = "Fanfic.World Studio",
    fandom: str = "Fanfic",
    chapter_label: str = "",
    output_path: Path | str = "cover.jpg",
    base_art_path: Optional[Path | str] = None,
    base_art_url: Optional[str] = None,
    use_beam_ai: bool = True,
    width: int = 1920,
    height: int = 1080,
    voice_name: str = "Cô Gái Hoạt Ngôn (CapCut)",
    summary: str = "",
    series_art_dir: Optional[Path | str] = None,
) -> Path:
    """Generates a 16:9 Landscape Cover with Fantasy Typography for Branch 2 (Truyện TTS).

    series_art_dir: thư mục cấp series (cha của tất cả chương) để lưu/tái dùng base_art.png chung.
    Nếu series_art_dir có base_art.png → tất cả chương của bộ dùng cùng 1 artwork.
    Nếu chưa có → sinh 1 lần từ Beam Cloud và lưu vào đó.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Priority: series_art_dir > chapter dir > explicit base_art_path
    series_art_candidate: Optional[Path] = None
    if series_art_dir:
        series_dir_p = Path(series_art_dir)
        series_dir_p.mkdir(parents=True, exist_ok=True)
        series_art_candidate = series_dir_p / "base_art.png"

    base_art_candidate = output_path.parent / "base_art.png"

    local_art: Optional[Path] = None

    # 1. Explicit path provided
    if base_art_path and Path(base_art_path).exists() and Path(base_art_path).resolve() != output_path.resolve():
        local_art = Path(base_art_path)
    # 2. Series-level shared art (preferred — same image for all chapters)
    elif series_art_candidate and series_art_candidate.exists():
        local_art = series_art_candidate
    # 3. Chapter-level cached art (backward compat)
    elif base_art_candidate.exists():
        local_art = base_art_candidate
    # 4. Remote URL download
    elif base_art_url:
        temp_art = output_path.parent / "_temp_raw_cover.jpg"
        if download_remote_cover(base_art_url, temp_art):
            local_art = temp_art

    # 5. Generate new art via Beam Cloud — save to series dir if available
    if not local_art and use_beam_ai:
        save_to = series_art_candidate if series_art_candidate else base_art_candidate
        prompt = build_character_centric_prompt(title, fandom, summary=summary, part_label="")
        if generate_anime_art_via_beam(prompt, save_to, width=1216, height=832):
            local_art = save_to

    if local_art and local_art.exists():
        try:
            base_img = Image.open(local_art).convert("RGB")
        except Exception:
            base_img = Image.new("RGB", (width, height), (18, 22, 34))
    else:
        base_img = Image.new("RGB", (width, height), (18, 22, 34))

    # Scale to fill 1920x1080
    bw, bh = base_img.size
    scale = max(width / bw, height / bh)
    new_w, new_h = int(bw * scale), int(bh * scale)
    base_img = base_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    img = base_img.crop((left, top, left + width, top + height)).convert("RGBA")

    # Bottom deep cinematic gradient scrim
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    scrim_start = int(height * 0.48)
    for y in range(scrim_start, height):
        ratio = (y - scrim_start) / (height - scrim_start)
        alpha = int(250 * (ratio ** 1.3))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    # Top scrim for badge contrast
    for y in range(0, 150):
        alpha = int(140 * ((150 - y) / 150))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    img = Image.alpha_composite(img, overlay)

    f_title = get_fantasy_font(72)
    f_sub = get_fantasy_font(42)
    f_badge = get_fantasy_font(28)
    f_author = get_fantasy_font(26)

    draw = ImageDraw.Draw(img)

    # Top-Left Fandom Pill Badge
    fandom_clean = (fandom or "FANFIC NOVEL").upper()
    if not fandom_clean.endswith("FANFIC") and not fandom_clean.endswith("NOVEL") and " x " not in fandom_clean:
        fandom_clean = f"{fandom_clean} FANFIC"
    tb = draw.textbbox((0, 0), fandom_clean, font=f_badge)
    bw_badge = tb[2] - tb[0] + 60
    bx, by = 60, 50
    draw.rounded_rectangle([(bx, by), (bx + bw_badge, by + 55)], radius=12, fill=(15, 18, 26, 230), outline=(212, 175, 55), width=2)
    draw.polygon([(bx + 20, by + 27), (bx + 25, by + 22), (bx + 30, by + 27), (bx + 25, by + 32)], fill=(255, 215, 0))
    draw.text((bx + 38, by + 12), fandom_clean, fill=(255, 230, 140), font=f_badge)
    draw.polygon([(bx + bw_badge - 25, by + 27), (bx + bw_badge - 20, by + 22), (bx + bw_badge - 15, by + 27), (bx + bw_badge - 20, by + 32)], fill=(255, 215, 0))

    # Top-Right Chapter Badge
    if chapter_label:
        chap_clean = chapter_label.upper()
        tb_c = draw.textbbox((0, 0), chap_clean, font=f_badge)
        cw_badge = tb_c[2] - tb_c[0] + 60
        cx = width - cw_badge - 60
        draw.rounded_rectangle([(cx, by), (width - 60, by + 55)], radius=12, fill=(185, 28, 38, 240), outline=(255, 215, 0), width=2)
        draw.text((cx + 30, by + 12), chap_clean, fill=(255, 255, 255), font=f_badge)

    # Format Title into Primary + Subtitle lines using smart splitting
    line1, line2 = split_title_smart(title)
    cur_y = 690 if line2 else 760
    img = render_fantasy_glowing_text(img, line1, f_title, 80, cur_y, glow_color=(255, 175, 35, 220), text_color=(255, 235, 140))
    cur_y += 85
    if line2:
        img = render_fantasy_glowing_text(img, line2, f_sub, 80, cur_y, glow_color=(80, 210, 255, 180), text_color=(240, 248, 255))
        cur_y += 65

    # Gold Divider
    d_draw = ImageDraw.Draw(img)
    d_draw.line([(80, cur_y + 8), (480, cur_y + 8)], fill=(212, 175, 55), width=2)
    d_draw.polygon([(490, cur_y + 8), (496, cur_y + 2), (502, cur_y + 8), (496, cur_y + 14)], fill=(255, 215, 0))
    d_draw.line([(512, cur_y + 8), (920, cur_y + 8)], fill=(212, 175, 55), width=2)

    # Author & Branding
    meta_txt = f"Tác giả: {author or 'Fanfic.World Studio'}   •   Giọng đọc: {voice_name}"
    d_draw.text((80, cur_y + 25), meta_txt, fill=(210, 220, 235), font=f_author)

    final_res = img.convert("RGB")
    final_res.save(output_path, quality=95)
    return output_path


def generate_landscape_animation_cover(
    video_cover_path: Path | str,
    title: str,
    episode_label: str = "TRỌN BỘ FULL HD",
    caption_line: str = "",
    output_path: Path | str = "cover.jpg",
    fandom: str = "Anime",
    use_beam_ai: bool = True,
    width: int = 1920,
    height: int = 1080,
    summary: str = "",
    series_art_dir: Optional[Path | str] = None,
) -> Path:
    """Generates 16:9 Landscape Cover for Branch 3 (Phim AI).

    series_art_dir: thư mục cấp series để lưu/tái dùng base_art.png chung cho tất cả tập.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    src_p = Path(video_cover_path)

    series_art_candidate: Optional[Path] = None
    if series_art_dir:
        series_dir_p = Path(series_art_dir)
        series_dir_p.mkdir(parents=True, exist_ok=True)
        series_art_candidate = series_dir_p / "base_art.png"

    base_art_candidate = output_path.parent / "base_art.png"

    base_img: Optional[Image.Image] = None

    # 1. Series-level shared art
    if series_art_candidate and series_art_candidate.exists():
        try:
            base_img = Image.open(series_art_candidate).convert("RGB")
        except Exception:
            base_img = None

    # 2. Chapter-level cached art (backward compat)
    if base_img is None and base_art_candidate.exists():
        try:
            base_img = Image.open(base_art_candidate).convert("RGB")
        except Exception:
            base_img = None

    # 3. Generate via Beam Cloud — save to series dir; prompt omits episode label
    if base_img is None and use_beam_ai:
        save_to = series_art_candidate if series_art_candidate else base_art_candidate
        prompt = build_character_centric_prompt(title, fandom, summary=summary, part_label="")
        if generate_anime_art_via_beam(prompt, save_to, width=1216, height=832):
            try:
                base_img = Image.open(save_to).convert("RGB")
            except Exception:
                base_img = None

    # 4. Fallback to source video frame / thumbnail
    if base_img is None:
        if src_p.exists() and src_p.resolve() != output_path.resolve():
            try:
                base_img = Image.open(src_p).convert("RGB")
            except Exception:
                base_img = Image.new("RGB", (width, height), (15, 20, 30))
        else:
            base_img = Image.new("RGB", (width, height), (15, 20, 30))

    base_img = base_img.resize((width, height), Image.Resampling.LANCZOS)
    img_rgba = base_img.convert("RGBA")

    # Bottom deep gradient scrim
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    scrim_start = int(height * 0.50)
    scrim_solid = int(height * 0.72)
    for y in range(scrim_start, height):
        if y >= scrim_solid:
            alpha = 255
        else:
            ratio = (y - scrim_start) / (scrim_solid - scrim_start)
            alpha = int(255 * (ratio ** 1.6))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    # Top scrim
    for y in range(0, 150):
        alpha = int(140 * ((150 - y) / 150))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    img_rgba = Image.alpha_composite(img_rgba, overlay)

    f_title = get_fantasy_font(72)
    f_sub = get_fantasy_font(44)
    f_badge = get_fantasy_font(28)
    f_meta = get_fantasy_font(26)

    draw = ImageDraw.Draw(img_rgba)

    # Top Left Badge
    badge_txt = (fandom or "PHIM HOẠT HÌNH ANIME").upper()
    if not badge_txt.endswith("ANIME"):
        badge_txt = f"{badge_txt} ANIME"
    tb = draw.textbbox((0, 0), badge_txt, font=f_badge)
    bw = tb[2] - tb[0] + 60
    draw.rounded_rectangle([(60, 50), (60 + bw, 105)], radius=12, fill=(15, 18, 26, 230), outline=(212, 175, 55), width=2)
    draw.polygon([(82, 77), (87, 72), (92, 77), (87, 82)], fill=(255, 215, 0))
    draw.text((102, 62), badge_txt, fill=(255, 230, 140), font=f_badge)
    draw.polygon([(60 + bw - 30, 77), (60 + bw - 25, 72), (60 + bw - 20, 77), (60 + bw - 25, 82)], fill=(255, 215, 0))

    # Top Right Episode Badge
    ep_txt = (episode_label or "TRỌN BỘ FULL HD").upper()
    tb_ep = draw.textbbox((0, 0), ep_txt, font=f_badge)
    ew = tb_ep[2] - tb_ep[0] + 60
    draw.rounded_rectangle([(width - ew - 60, 50), (width - 60, 105)], radius=12, fill=(20, 120, 220, 240), outline=(255, 255, 255), width=2)
    draw.text((width - ew - 60 + 30, 62), ep_txt, fill=(255, 255, 255), font=f_badge)

    line1, line2 = split_title_smart(title)
    if not line2 and caption_line:
        line2 = caption_line

    cur_y = 700 if line2 else 770
    img_rgba = render_fantasy_glowing_text(img_rgba, line1, f_title, 80, cur_y, glow_color=(255, 175, 35, 220), text_color=(255, 235, 140))
    cur_y += 85
    if line2:
        img_rgba = render_fantasy_glowing_text(img_rgba, line2, f_sub, 80, cur_y, glow_color=(80, 210, 255, 180), text_color=(240, 248, 255))
        cur_y += 65

    # Gold Divider & Metadata
    d_draw = ImageDraw.Draw(img_rgba)
    d_draw.line([(80, cur_y + 8), (480, cur_y + 8)], fill=(212, 175, 55), width=2)
    d_draw.polygon([(490, cur_y + 8), (496, cur_y + 2), (502, cur_y + 8), (496, cur_y + 14)], fill=(255, 215, 0))
    d_draw.line([(512, cur_y + 8), (920, cur_y + 8)], fill=(212, 175, 55), width=2)

    meta_txt = "Vietsub Chuẩn Khẩu Hình   •   Lồng Tiếng AI Đa Giọng (Nam / Nữ)   •   Fanfic.World"
    d_draw.text((80, cur_y + 25), meta_txt, fill=(210, 220, 235), font=f_meta)

    out_res = img_rgba.convert("RGB")
    out_res.save(output_path, quality=95)
    return output_path


def generate_landscape_audio_cover(
    youtube_cover_path: Path | str,
    title: str,
    fandom: str = "Audiobook",
    episode_label: str = "Tập 01",
    author: str = "Fanfic.World",
    output_path: Path | str = "cover.jpg",
    use_beam_ai: bool = True,
    width: int = 1920,
    height: int = 1080,
    summary: str = "",
    series_art_dir: Optional[Path | str] = None,
) -> Path:
    """Generates 16:9 Landscape Cover for Branch 1 (Audio YouTube).

    series_art_dir: thư mục cấp series để lưu/tái dùng base_art.png chung cho tất cả tập.
    Lần đầu → sinh art từ Beam Cloud (prompt KHÔNG có episode label để art mang tính series).
    Các tập sau → reuse cùng artwork, chỉ thay badge PHẦN/TẬP.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    src_p = Path(youtube_cover_path)

    # Determine series-level art path (preferred) vs chapter-level fallback
    series_art_candidate: Optional[Path] = None
    if series_art_dir:
        series_dir_p = Path(series_art_dir)
        series_dir_p.mkdir(parents=True, exist_ok=True)
        series_art_candidate = series_dir_p / "base_art.png"

    base_art_candidate = output_path.parent / "base_art.png"

    base_img: Optional[Image.Image] = None

    # 1. Series-level shared art (same artwork across all episodes)
    if series_art_candidate and series_art_candidate.exists():
        try:
            base_img = Image.open(series_art_candidate).convert("RGB")
        except Exception:
            base_img = None

    # 2. Chapter-level cached art (backward compat)
    if base_img is None and base_art_candidate.exists():
        try:
            base_img = Image.open(base_art_candidate).convert("RGB")
        except Exception:
            base_img = None

    # 3. Generate via Beam Cloud — save to series dir (retry up to 3 times)
    if base_img is None and use_beam_ai:
        save_to = series_art_candidate if series_art_candidate else base_art_candidate
        prompt = build_character_centric_prompt(title, fandom, summary=summary, part_label="")
        print(f"[CoverGen] Đang sinh ảnh nhân vật 16:9 Beam Cloud cho Audio: '{title[:45]}...'")
        for attempt in range(1, 4):
            if generate_anime_art_via_beam(prompt, save_to, width=1216, height=832):
                try:
                    base_img = Image.open(save_to).convert("RGB")
                    print(f"[CoverGen] [OK] Đã tạo xong ảnh bìa nhân vật Beam Cloud (lần thử {attempt})!")
                    break
                except Exception:
                    base_img = None
            if attempt < 3:
                time.sleep(2.0)

    # 4. Fallback: Aesthetic Dark Fantasy Gradient canvas (NEVER use raw YouTube thumbnail)
    if base_img is None:
        base_img = Image.new("RGB", (width, height), (18, 22, 34))

    cleaned_img = base_img.resize((width, height), Image.Resampling.LANCZOS)
    img_rgba = cleaned_img.convert("RGBA")

    # Bottom deep gradient scrim
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    scrim_start = int(height * 0.48)
    for y in range(scrim_start, height):
        ratio = (y - scrim_start) / (height - scrim_start)
        alpha = int(250 * (ratio ** 1.3))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    # Top scrim
    for y in range(0, 150):
        alpha = int(140 * ((150 - y) / 150))
        ov_draw.line([(0, y), (width, y)], fill=(8, 10, 16, alpha))

    img_rgba = Image.alpha_composite(img_rgba, overlay)

    f_title = get_fantasy_font(72)
    f_sub = get_fantasy_font(42)
    f_badge = get_fantasy_font(28)
    f_author = get_fantasy_font(26)

    draw = ImageDraw.Draw(img_rgba)

    # Top-Left Fandom Pill
    f_txt = (fandom or "AUDIOBOOK FANFIC").upper()
    tb = draw.textbbox((0, 0), f_txt, font=f_badge)
    bw = tb[2] - tb[0] + 60
    draw.rounded_rectangle([(60, 50), (60 + bw, 105)], radius=12, fill=(15, 18, 26, 230), outline=(212, 175, 55), width=2)
    draw.polygon([(82, 77), (87, 72), (92, 77), (87, 82)], fill=(255, 215, 0))
    draw.text((102, 62), f_txt, fill=(255, 230, 140), font=f_badge)
    draw.polygon([(60 + bw - 30, 77), (60 + bw - 25, 72), (60 + bw - 20, 77), (60 + bw - 25, 82)], fill=(255, 215, 0))

    # Top-Right Episode Badge
    ep_txt = (episode_label or "TẬP 01").upper()
    tb_ep = draw.textbbox((0, 0), ep_txt, font=f_badge)
    ew = tb_ep[2] - tb_ep[0] + 60
    draw.rounded_rectangle([(width - ew - 60, 50), (width - 60, 105)], radius=12, fill=(185, 28, 38, 240), outline=(255, 215, 0), width=2)
    draw.text((width - ew - 60 + 30, 62), ep_txt, fill=(255, 255, 255), font=f_badge)

    line1, line2 = split_title_smart(title)
    cur_y = 690 if line2 else 760
    img_rgba = render_fantasy_glowing_text(img_rgba, line1, f_title, 80, cur_y, glow_color=(255, 175, 35, 220), text_color=(255, 235, 140))
    cur_y += 85
    if line2:
        img_rgba = render_fantasy_glowing_text(img_rgba, line2, f_sub, 80, cur_y, glow_color=(80, 210, 255, 180), text_color=(240, 248, 255))
        cur_y += 65

    # Divider & Metadata
    d_draw = ImageDraw.Draw(img_rgba)
    d_draw.line([(80, cur_y + 8), (480, cur_y + 8)], fill=(212, 175, 55), width=2)
    d_draw.polygon([(490, cur_y + 8), (496, cur_y + 2), (502, cur_y + 8), (496, cur_y + 14)], fill=(255, 215, 0))
    d_draw.line([(512, cur_y + 8), (920, cur_y + 8)], fill=(212, 175, 55), width=2)

    author_txt = f"Bản quyền nội dung: {author or 'Fanfic.World'}   •   Audiobook Trọn Bộ Chất Lượng Cao"
    d_draw.text((80, cur_y + 25), author_txt, fill=(200, 215, 235), font=f_author)

    out_res = img_rgba.convert("RGB")
    out_res.save(output_path, quality=95)
    return output_path


# Backward compatible alias for novel covers
generate_novel_cover = generate_landscape_fanfic_cover
