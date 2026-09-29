"""Vendor mot tap con cua Icons8 Line Awesome (kieu "solid") thanh du lieu path
TypeScript, khong tai qua CDN, khong them dependency runtime.

CACH CHAY LAI (khi can them/doi icon):

    1. Tai goi ve mot thu muc tam:
       npm pack line-awesome --pack-destination <thu_muc_tam>
    2. Giai nen:
       tar -xzf <thu_muc_tam>/line-awesome-<phien_ban>.tgz -C <thu_muc_tam>
    3. Chay script nay, tro --src-dir vao thu muc `svg` da giai nen:

       python scripts/icons/vendor_line_awesome.py \
           --src-dir <thu_muc_tam>/package/svg \
           --out web/src/components/icons/lineAwesome.generated.ts \
           --license-out web/src/components/icons/LINE_AWESOME_LICENSE.md \
           --license-src <thu_muc_tam>/package/LICENSE.md

Script CHI doc svg/LICENSE.md tu --src-dir/--license-src — khong tai mang,
khong ghi gi ngoai hai duong --out/--license-out.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

# concept (IconName) -> ten tep nguon (khong duoi .svg) trong package/svg cua
# line-awesome. TAT CA deu la kieu "solid" (mot duong dan day, mot mau) de
# dong bo mot phong cach duy nhat.
ICON_MAP: dict[str, str] = {
    "home": "home-solid",
    "community": "users-solid",
    "library": "landmark-solid",
    "studio": "pen-nib-solid",
    "search": "search-solid",
    "notification": "bell-solid",
    "message": "comment-dots-solid",
    "profile": "user-circle-solid",
    "settings": "cog-solid",
    "admin": "user-shield-solid",
    "audio": "headphones-solid",
    "book": "book-solid",
    "image": "image-solid",
    "upload": "upload-solid",
    "download": "download-solid",
    "play": "play-solid",
    "pause": "pause-solid",
    "like": "heart-solid",
    "comment": "comment-solid",
    "share": "share-solid",
    "report": "flag-solid",
    "block": "ban-solid",
    "mute": "bell-slash-solid",
    "game": "gamepad-solid",
    "trophy": "trophy-solid",
    "leaderboard": "list-ol-solid",
    "level": "layer-group-solid",
    "ai": "robot-solid",
    "support": "life-ring-solid",
    "sticker": "sticky-note-solid",
    "emoji": "smile-solid",
    "close": "times-solid",
    "send": "paper-plane-solid",
    "stop": "stop-solid",
    "refresh": "sync-solid",
    "history": "history-solid",
    "plus": "plus-solid",
    "menu": "bars-solid",
    "chevron-down": "chevron-down-solid",
    "chevron-left": "chevron-left-solid",
    "external-link": "external-link-alt-solid",
    "trash": "trash-alt-solid",
    "spark": "magic-solid",
}

VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')
PATH_D_RE = re.compile(r'<path\s[^>]*\bd="([^"]+)"')

HEADER = """/**
 * TU DONG SINH — KHONG SUA TAY.
 *
 * Sinh boi `scripts/icons/vendor_line_awesome.py` tu goi npm `line-awesome`
 * (Icons8 Line Awesome, kieu "solid"). Chi vendor DUONG DAN (path data) can
 * dung — khong tai font/CDN, khong them dependency runtime. Giay phep: xem
 * `LINE_AWESOME_LICENSE.md` canh tep nay (MIT / Icons8 Good Boy License).
 *
 * Them icon moi: sua ICON_MAP trong script roi chay lai no.
 */

export interface DuLieuIcon {
  viewBox: string;
  path: string;
}

"""


def doc_icon(src_dir: Path, ten_tep: str) -> DuLieuIcon:
    noi_dung = (src_dir / f"{ten_tep}.svg").read_text(encoding="utf-8")
    vb = VIEWBOX_RE.search(noi_dung)
    d = PATH_D_RE.search(noi_dung)
    if not vb or not d:
        raise ValueError(f"Khong doc duoc viewBox/path tu {ten_tep}.svg")
    return DuLieuIcon(viewBox=vb.group(1), path=d.group(1))


class DuLieuIcon:
    def __init__(self, viewBox: str, path: str) -> None:
        self.viewBox = viewBox
        self.path = path


def sinh_ts(du_lieu: dict[str, "DuLieuIcon"]) -> str:
    ten_union = " | ".join(f'"{ten}"' for ten in du_lieu)
    dong_bang = []
    for ten, ic in du_lieu.items():
        d_thoat = ic.path.replace("\\", "\\\\").replace('"', '\\"')
        dong_bang.append(
            f'  "{ten}": {{ viewBox: "{ic.viewBox}", path: "{d_thoat}" }},'
        )
    return (
        HEADER
        + f"export type IconName = {ten_union};\n\n"
        + "export const LINE_AWESOME_ICONS: Record<IconName, DuLieuIcon> = {\n"
        + "\n".join(dong_bang)
        + "\n};\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src-dir", required=True, type=Path, help="Thu muc svg/ da giai nen tu goi line-awesome")
    ap.add_argument("--out", required=True, type=Path, help="Duong ghi module .ts sinh ra")
    ap.add_argument("--license-out", type=Path, default=None, help="Duong ghi ban sao giay phep")
    ap.add_argument("--license-src", type=Path, default=None, help="Duong doc LICENSE.md nguon (package/LICENSE.md)")
    args = ap.parse_args()

    if not args.src_dir.is_dir():
        raise SystemExit(f"Khong thay thu muc --src-dir: {args.src_dir}")

    du_lieu: dict[str, DuLieuIcon] = {}
    thieu: list[str] = []
    for ten, ten_tep in ICON_MAP.items():
        try:
            du_lieu[ten] = doc_icon(args.src_dir, ten_tep)
        except FileNotFoundError:
            thieu.append(f"{ten} -> {ten_tep}.svg")
    if thieu:
        raise SystemExit("Thieu tep nguon cho: " + ", ".join(thieu))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sinh_ts(du_lieu), encoding="utf-8", newline="\n")
    print(f"Da ghi {len(du_lieu)} icon vao {args.out}")

    if args.license_out and args.license_src:
        if not args.license_src.is_file():
            raise SystemExit(f"Khong thay --license-src: {args.license_src}")
        noi_dung = args.license_src.read_text(encoding="utf-8")
        tieu_de = (
            "<!-- Sao chep tu goi npm `line-awesome` (Icons8 Line Awesome). "
            "Xem `scripts/icons/vendor_line_awesome.py`. -->\n\n"
        )
        args.license_out.write_text(tieu_de + noi_dung, encoding="utf-8", newline="\n")
        print(f"Da ghi giay phep vao {args.license_out}")


if __name__ == "__main__":
    main()
