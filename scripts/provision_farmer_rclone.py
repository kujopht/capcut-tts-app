#!/usr/bin/env python3
"""Cai + cau hinh rclone tren may gat AWS — khong lo bi mat ra dau ca.

Cung khuon voi `push_harvester_token.py`, va vi cung mot ly do: tep cau hinh
rclone chua **refresh token OAuth cua Google Drive**. Do la mot bi mat that,
ngang hang voi mot mat khau — no doi duoc thanh quyen doc/ghi toan bo Drive.

    NGUON  : rclone.conf tren may nay, DUNG mot muc `[fanfic-gdrive]`
    DICH   : 13.212.224.218 : /var/lib/fanfic-farmer/rclone.conf (0600)
    KHONG  : khong dong toi worker-prod.env, khong doc muc remote nao khac,
             khong xoa gi tren Drive

## Vi sao `/var/lib/fanfic-farmer/` chu khong `/etc/fanfic-audio/`

Hai rang buoc cua unit systemd quyet dinh cho nay, khong phai so thich:

    ProtectHome=true   -> /home/fanfic khong ton tai voi dich vu. Duong mac
                          dinh cua rclone (~/.config/rclone) khong dung duoc.
    ProtectSystem=strict + ReadWritePaths=/var/lib/fanfic-farmer
                       -> /etc chi DOC. rclone GHI DE tep cau hinh moi lan no
                          lam moi access token; tren mot duong chi-doc no bao
                          loi moi lan chay, va neu Google xoay refresh token
                          thi ban luu tru chet am tham.

Nen tep cau hinh phai nam duoi duong duy nhat ma dich vu ghi duoc.
`RCLONE_CONFIG` trong farmer.env tro rclone toi do.

## Bi mat di duong nao

    rclone.conf cuc bo -> bo nho tien trinh nay -> stdin cua `ssh`
                       -> `cat` tren may AWS -> tep 0600 fanfic:fanfic

KHONG di qua argv (nen `ps` khong thay), bien moi truong, tep tam cuc bo,
stdout/stderr, log, git, hay ngu canh hoi thoai. Doan script chay tren may
AWS nam trong argv nhung KHONG chua bi mat — no doc tu stdin.

## Cai rclone bang apt, KHONG bang `curl | sudo bash`

Script cai dat chinh chu cua rclone bao nguoi dung dan mot URL vao mot shell
root. Kho Ubuntu thi da duoc ky va apt tu kiem chu ky — do la chuoi tin cay
co san tren may, khong phai mot chuoi tin cay moi dung len chi de cai mot
nhi phan. Ban 1.60 cu hon ban moi nhat; moi thu farmer dung (`copy`, `lsjson`,
`lsd`, `cat`) da on dinh tu rat lau truoc do.
"""
from __future__ import annotations

import argparse
import configparser
import io
import os
import subprocess
import sys
from pathlib import Path

#: GHIM. Khong co dong lenh nao doi duoc — mot cong cu "day cau hinh bat ky
#: di bat ky dau" la mot cong cu khac han.
ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
REMOTE_NAME = "fanfic-gdrive"
SVC_USER = "fanfic"
CONF_PATH = "/var/lib/fanfic-farmer/rclone.conf"
ENV_FILE = "/etc/fanfic-audio/farmer.env"

#: Goc SAN XUAT. Cay legacy `FanficWorld/archive` KHONG duoc dong toi.
PRODUCTION_ROOT = "FanficWorld/production"
LEGACY_ROOT = "FanficWorld/archive"


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


#: Buoc 1 — CAI. Khong mang bi mat nao.
_REMOTE_INSTALL = """
set -eu
if command -v rclone >/dev/null 2>&1; then
  echo "STEP-1 rclone=$(rclone version | head -1)"
else
  echo "STEP-1 cai rclone tu kho Ubuntu (da ky, apt tu kiem)"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq rclone >/dev/null
  echo "STEP-1 rclone=$(rclone version | head -1)"
fi
"""

#: Buoc 2 — GHI CAU HINH. Doc bi mat tu STDIN; khong bao gio in no.
#: `worker-prod.env` khong xuat hien o day — no khong duoc mo.
_REMOTE_WRITE = f"""
set -eu
umask 077
C={CONF_PATH}
T="$C.new.$$"
install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$T"
cat > "$T"
if ! grep -q '^\\[{REMOTE_NAME}\\]' "$T"; then
  rm -f "$T"; echo "RESULT=NO_REMOTE_SECTION"; exit 2
fi
mv -f "$T" "$C"
chown {SVC_USER}:{SVC_USER} "$C"
chmod 600 "$C"

# farmer.env: chi SO HUU khoa RCLONE_CONFIG, giu nguyen moi dong khac. Ghi
# tep-sang-tep nen khong dong nao di qua mot bien shell.
E={ENV_FILE}
if [ -f "$E" ]; then
  TE="$E.new.$$"
  install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$TE"
  grep -v '^RCLONE_CONFIG=' "$E" > "$TE" || true
  printf 'RCLONE_CONFIG=%s\\n' '{CONF_PATH}' >> "$TE"
  mv -f "$TE" "$E"
  chown {SVC_USER}:{SVC_USER} "$E"; chmod 600 "$E"
fi
echo "RESULT=CONFIG_WRITTEN conf=$(stat -c '%U:%G %a' "$C") env=$(stat -c '%U:%G %a' "$E")"
"""

#: Buoc 3 — KHU HOI. Chay DUOI DANH TINH `fanfic`, vi day la danh tinh that
#: su se luu tru; chung minh voi `ubuntu` thi khong chung minh duoc gi.
#:
#: Tep tham do duoc GHI DE moi lan chu khong xoa: `drive_archive` la
#: chi-COPY, va mot cong cu van hanh biet xoa se lam ro rang bat bien do
#: thanh mot loi hua thay vi mot tinh chat.
_REMOTE_VERIFY = f"""
set -eu
export RCLONE_CONFIG={CONF_PATH}
R="rclone --config {CONF_PATH}"
echo "STEP-3 kiem ket noi"
$R lsd {REMOTE_NAME}: --max-depth 1 >/dev/null && echo "STEP-3 remote OK"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
printf 'farmer round-trip %s\\n' "$STAMP" > "$TMP/_healthcheck.txt"

echo "STEP-4 ghi len {PRODUCTION_ROOT}/_healthcheck/"
$R copy "$TMP/_healthcheck.txt" "{REMOTE_NAME}:{PRODUCTION_ROOT}/_healthcheck" --checksum

echo "STEP-5 doc nguoc ve"
GOT=$($R cat "{REMOTE_NAME}:{PRODUCTION_ROOT}/_healthcheck/_healthcheck.txt")
if [ "$GOT" = "farmer round-trip $STAMP" ]; then
  echo "RESULT=ROUNDTRIP_OK stamp=$STAMP"
else
  echo "RESULT=ROUNDTRIP_MISMATCH"; exit 3
fi

echo "STEP-6 cay legacy VAN NGUYEN (chi doc, khong ghi)"
$R lsd "{REMOTE_NAME}:{LEGACY_ROOT}" --max-depth 1 2>/dev/null | wc -l \
  | sed 's/^/LEGACY_SUBDIRS=/'
echo "STEP-7 goc san xuat"
$R lsd "{REMOTE_NAME}:{PRODUCTION_ROOT}" --max-depth 1 2>/dev/null || true
"""


def _ssh(key: str, script: str, *, as_root: bool, stdin: str = None,
         timeout: int = 900):
    lenh = (f"sudo -n bash -c {_shquote(script)}" if as_root
            # `sudo -n -u fanfic`: chung minh duoi DUNG danh tinh se luu tru.
            else f"sudo -n -u {SVC_USER} bash -c {_shquote(script)}")
    return subprocess.run(
        ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
         f"{ALLOWED_USER}@{ALLOWED_HOST}", lenh],
        input=stdin, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")


def doc_muc_remote(duong_dan: Path) -> str:
    """Trich DUNG mot muc `[fanfic-gdrive]`. Khong bao gio tra ve ca tep.

    Tep rclone.conf cuc bo con co `hainam-drive` va co the con nua. Day ca tep
    di la day nhung bi mat khong lien quan sang mot may khac — mot cong cu chi
    duoc mang dung thu no can.
    """
    cp = configparser.RawConfigParser()
    cp.read_string(duong_dan.read_text(encoding="utf-8"))
    if REMOTE_NAME not in cp.sections():
        raise KeyError(f"khong thay muc [{REMOTE_NAME}] trong {duong_dan}")
    ra = io.StringIO()
    ra.write(f"[{REMOTE_NAME}]\n")
    for k, v in cp.items(REMOTE_NAME):
        ra.write(f"{k} = {v}\n")
    return ra.getvalue()


def tim_config() -> Path:
    for p in (os.environ.get("RCLONE_CONFIG"),
              Path(os.environ.get("APPDATA", "")) / "rclone" / "rclone.conf",
              Path.home() / ".config" / "rclone" / "rclone.conf",
              Path.home() / ".rclone.conf"):
        if p and Path(p).is_file():
            return Path(p)
    raise FileNotFoundError("khong tim thay rclone.conf tren may nay")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="chi kiem doc duoc cau hinh cuc bo — KHONG ket noi")
    ap.add_argument("--verify-only", action="store_true",
                    help="BO QUA cai dat va ghi cau hinh; chi chay khu hoi")
    args = ap.parse_args(argv)

    if not args.verify_only:
        conf = tim_config()
        try:
            muc = doc_muc_remote(conf)
        except (KeyError, Exception) as exc:                    # noqa: BLE001
            print(f"RESULT=LOCAL_CONFIG_ERROR {type(exc).__name__}: {exc}")
            return 2

        # Bang chung DUY NHAT ve bi mat duoc phep in: no co that, va dai bao
        # nhieu. KHONG in noi dung, khong in token, khong in ca client_id.
        print(f"RESULT=LOCAL_SECTION_LOADED remote={REMOTE_NAME} "
              f"bytes={len(muc)} keys={muc.count(chr(10)) - 1}")
        if args.dry_run:
            print("RESULT=DRY_RUN_OK (khong ket noi, khong ghi)")
            return 0

        p = _ssh(args.ssh_key, _REMOTE_INSTALL, as_root=True)
        print((p.stdout or "").rstrip())
        if p.returncode != 0:
            print(f"RESULT=INSTALL_FAILED exit={p.returncode} "
                  f"stderr={(p.stderr or '')[-500:]}")
            return p.returncode

        p = _ssh(args.ssh_key, _REMOTE_WRITE, as_root=True, stdin=muc)
        del muc
        print((p.stdout or "").rstrip())
        if p.returncode != 0:
            # stderr cua ssh/sudo khong chua bi mat (bi mat chi di qua stdin).
            print(f"RESULT=WRITE_FAILED exit={p.returncode} "
                  f"stderr={(p.stderr or '')[-500:]}")
            return p.returncode

    p = _ssh(args.ssh_key, _REMOTE_VERIFY, as_root=False)
    print((p.stdout or "").rstrip())
    if p.returncode != 0:
        print(f"RESULT=VERIFY_FAILED exit={p.returncode} "
              f"stderr={(p.stderr or '')[-800:]}")
        return p.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
