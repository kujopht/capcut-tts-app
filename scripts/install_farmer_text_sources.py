#!/usr/bin/env python3
"""Doc/ghi tep nguon truyen chu cua farmer tren may gat AWS.

    MAY  : 13.212.224.218
    TEP  : /etc/fanfic-audio/farmer-text-sources.json  (0640 fanfic:fanfic)

Tep nay CO Y nam ngoai kho ma. Mot danh sach nguon nhung cung trong ma nghia
la moi lan them mot nguon la mot lan deploy — xem `__main__._text_discovery`.

## THEM chu khong DE LEN

`--merge` giu lai moi muc dang co va chi them nhung URL chua co. Mot tep
nguon co the da duoc nguoi van hanh sua bang tay giua hai lan chay; ghi de
mu quang se lang le vut bo cong do. Trung lap duoc xet theo URL da chuan hoa
chu khong theo chuoi tho, nen mot dau `/` thua khong tao ra muc thu hai.

Khong co bi mat nao trong tep nay, nen no khong can duong stdin nhu
`push_harvester_token.py` — nhung no van duoc ghi nguyen to (tep tam +
`mv`) de farmer khong bao gio doc trung mot tep dang viet do dang.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
SVC_USER = "fanfic"
DEST = "/etc/fanfic-audio/farmer-text-sources.json"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


_READ = f"""
set -eu
if [ -f {DEST} ]; then cat {DEST}; else echo '{{"sources": []}}'; fi
"""


def _write(noi_dung: str) -> str:
    return f"""
set -eu
umask 077
T={DEST}.new.$$
install -o {SVC_USER} -g {SVC_USER} -m 640 /dev/null "$T"
cat > "$T" <<'JSON_EOF'
{noi_dung}
JSON_EOF
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$T"
mv -f "$T" {DEST}
chown {SVC_USER}:{SVC_USER} {DEST}
chmod 640 {DEST}
echo "RESULT=WRITTEN $(stat -c '%U:%G %a %s' {DEST})"
"""


def _ssh(key: str, script: str, timeout: int = 300):
    return subprocess.run(
        ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{ALLOWED_USER}@{ALLOWED_HOST}",
         f"sudo -n bash -c {_shquote(script)}"],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")


def _chuan(url: str) -> str:
    try:
        from server.scraper.contract import canonicalize_url
        return canonicalize_url(url)
    except Exception:                                           # noqa: BLE001
        return (url or "").strip().rstrip("/")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--show", action="store_true", help="chi doc, khong ghi")
    ap.add_argument("--merge", help="tep JSON cuc bo can hop vao")
    ap.add_argument("--disable", action="append", default=[],
                    help="dat `_disabled` cho mot URL dang co (lap lai duoc). "
                         "TAT chu khong XOA: mot muc bi xoa se mat ca ly do no "
                         "tung o day, va vong sau co the them lai chinh no.")
    args = ap.parse_args(argv)

    p = _ssh(args.ssh_key, _READ)
    if p.returncode != 0:
        print(f"RESULT=READ_FAILED exit={p.returncode} "
              f"stderr={(p.stderr or '')[-400:]}")
        return p.returncode
    try:
        hien_co = json.loads((p.stdout or "").strip() or '{"sources": []}')
    except ValueError as exc:
        print(f"RESULT=REMOTE_JSON_INVALID {exc}")
        return 3

    muc = list(hien_co.get("sources") or [])
    print(f"RESULT=CURRENT count={len(muc)}")
    for s in muc:
        co = " [TAT]" if s.get("_disabled") else ""
        print(f"  {s.get('url','?')}{co}")

    if args.show or (not args.merge and not args.disable):
        return 0

    da_co = {_chuan(s.get("url", "")) for s in muc}
    moi = 0
    if args.merge:
        them = json.loads(Path(args.merge).read_text(encoding="utf-8"))
        for s in (them.get("sources") or []):
            if _chuan(s.get("url", "")) in da_co:
                continue
            muc.append(s)
            da_co.add(_chuan(s.get("url", "")))
            moi += 1

    tat = {_chuan(u) for u in args.disable}
    da_tat = 0
    for s in muc:
        if _chuan(s.get("url", "")) in tat and not s.get("_disabled"):
            s["_disabled"] = True
            da_tat += 1

    noi_dung = json.dumps({"sources": muc}, ensure_ascii=False, indent=2)
    if "JSON_EOF" in noi_dung:
        # Dau ket thuc heredoc xuat hien trong du lieu se cat doan script.
        print("RESULT=REFUSED noi dung chua JSON_EOF")
        return 4

    p = _ssh(args.ssh_key, _write(noi_dung))
    print((p.stdout or "").rstrip())
    if p.returncode != 0:
        print(f"RESULT=WRITE_FAILED exit={p.returncode} "
              f"stderr={(p.stderr or '')[-400:]}")
        return p.returncode
    print(f"RESULT=MERGED added={moi} disabled={da_tat} total={len(muc)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
