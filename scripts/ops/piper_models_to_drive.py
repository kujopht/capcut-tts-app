"""Dua 25 model Piper (~1.5GB) tu `fanfic-worker-prod` len kho lanh Drive.

VI SAO CAN: do that ngay 2026-09-03 — bo model TON TAI DUY NHAT tren dia
boot cua `fanfic-worker-prod`. Khong co ban nao tren Drive, khong co ban nao
tren R2. Mat VM do = mat 25 giong doc, va mot trong so do
(`ngochuyennew` = "Ngoc Huyen (Moi)") dang duoc chao ban trong san pham.
Day dung mot loai van de voi "backup nam tren chinh VM no bao ve".

Va no chan viec dung AWS staging: bootstrap can 25 model co mat de kiem
duoc giong cuc bo.

    python -m scripts.ops.piper_models_to_drive          # keo ve + day len
    python -m scripts.ops.piper_models_to_drive --verify-only

CHI `rclone copy` — dung lai `scripts/rclone_archive_copy.py`, noi verb
`copy` duoc HARDCODE. Khong sync/move/delete.

MODEL KHONG PHAI BI MAT (la trong so TTS), nen khac voi ban backup Appwrite:
o day khong co van de credential. Nhung van KHONG day tu VM len Drive —
`rclone` khong co tren VM va khong nen cai.

CAU TRUC PHAI GIU NGUYEN:
    25 x <voice_key>.onnx        (~63.516.050 byte moi ban)
    MOT config.json dung chung
    25 SYMLINK <voice_key>.onnx.json -> config.json

`gcloud compute scp` KHONG giu symlink — no deref. Nen script nay KHONG copy
25 symlink; no chi mang ve 25 `.onnx` + `config.json`, roi ghi mot
`TAO_LAI_SYMLINK.sh` de dung lai dung cau truc o dau ben kia. Nho vay kho
lanh khong phai chua 25 ban sao giong nhau cua cung mot `config.json`.

`voice_id` = `piper:<voice_key>` da nam trong job cu VA gop phan sinh
`output_key` tren R2 -> ten tep KHONG duoc doi, bao gio cung vay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.rclone_archive_copy import rclone_copy, rclone_verify  # noqa: E402

DRIVE_MODELS_REMOTE = "fanfic-gdrive:FanficWorld/archive/infra/piper-models"
VM_NAME = "fanfic-worker-prod"
VM_ZONE = "asia-southeast1-b"
VM_MODELS = "/opt/fanfic-models/nghitts/piper-tts"
SO_ONNX_MONG_DOI = 25


def phan_giai(ten: str) -> str:
    """Tren Windows `gcloud` la `gcloud.cmd`; subprocess khong tu tim duoi."""
    p = shutil.which(ten)
    if p:
        return p
    for duoi in (".cmd", ".exe", ".bat"):
        p = shutil.which(ten + duoi)
        if p:
            return p
    return ten


def run(cmd: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess:
    cmd = [phan_giai(cmd[0])] + list(cmd[1:])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def sha256_file(p: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


TAO_LAI = """#!/usr/bin/env bash
# Dung lai cau truc THAT cua thu muc model Piper sau khi tai tu kho lanh.
#
# Kho lanh CO Y chi giu 25 tep .onnx + MOT config.json, khong giu 25 symlink
# (`gcloud compute scp` deref symlink, nen luu chung se thanh 25 ban sao
# giong nhau cua cung mot tep).
#
#     bash TAO_LAI_SYMLINK.sh /opt/fanfic-models/nghitts/piper-tts
set -euo pipefail
DICH="${1:-/opt/fanfic-models/nghitts/piper-tts}"
cd "$DICH"
[ -f config.json ] || { echo "LOI: thieu config.json trong $DICH" >&2; exit 2; }
n=0
for f in *.onnx; do
  [ -e "$f" ] || continue
  ln -sfn config.json "${f}.json"
  n=$((n+1))
done
echo "da tao lai $n symlink <voice_key>.onnx.json -> config.json"
ls -la | grep -c '\\.onnx\\.json ->' || true
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", required=True,
                    help="thu muc lam viec cuc bo (can ~1.5GB trong)")
    ap.add_argument("--verify-only", action="store_true",
                    help="chi doi soat ban da co tren Drive")
    a = ap.parse_args()

    work = Path(a.work_dir)
    local = work / "piper-tts"
    local.mkdir(parents=True, exist_ok=True)

    if not a.verify_only:
        print("=" * 70)
        print("  BUOC 1 — KEO model tu fanfic-worker-prod")
        print("=" * 70)
        # Chi `.onnx` + `config.json`. KHONG keo `*.onnx.json` (symlink).
        #
        # HAI loi goi rieng, khong gop: tren Windows `gcloud compute scp` di
        # qua PuTTY (`pscp`), va PuTTY KHONG nhan nhieu nguon tu xa trong
        # mot lan. Da do that:
        #   ERROR: (gcloud.compute.scp) Multiple remote sources not
        #   supported by PuTTY.
        for nguon in (f"{VM_MODELS}/*.onnx", f"{VM_MODELS}/config.json"):
            print(f"  keo {nguon} ...")
            p = run(["gcloud", "compute", "scp", f"--zone={VM_ZONE}",
                     f"{VM_NAME}:{nguon}", str(local)], timeout=7200)
            if p.returncode != 0:
                print(f"LOI keo ve (exit {p.returncode}):\n{p.stderr[-1200:]}")
                return 2

    onnx = sorted(local.glob("*.onnx"))
    cfg = local / "config.json"
    print(f"\n  .onnx keo ve   : {len(onnx)} / {SO_ONNX_MONG_DOI}")
    print(f"  config.json    : {'CO' if cfg.is_file() else 'THIEU'}")
    if len(onnx) != SO_ONNX_MONG_DOI or not cfg.is_file():
        print("DUNG LAI: chua du model, khong day len kho lanh ban thieu.")
        return 3

    print("\n" + "=" * 70)
    print("  BUOC 2 — MANIFEST + kiem giong bat buoc")
    print("=" * 70)
    noi_dung = []
    for f in onnx + [cfg]:
        noi_dung.append({"tep": f.name, "sha256": sha256_file(f),
                         "size_bytes": f.stat().st_size})
    ten = {f.stem for f in onnx}
    for k, nhan in (("ngochuyen", "Ngoc Huyen"),
                    ("ngochuyennew", "Ngoc Huyen (Moi)")):
        co = k in ten
        print(f"  {k:16} {'CO   ' if co else 'THIEU'} ({nhan})")
        if not co:
            print("DUNG LAI: thieu mot giong dang duoc chao ban.")
            return 3
    (local / "manifest.json").write_text(json.dumps({
        "nguon_vm": VM_NAME, "nguon_duong_dan": VM_MODELS,
        "so_onnx": len(onnx),
        "cau_truc_that_tren_vm": (
            "25 x <voice_key>.onnx + MOT config.json dung chung + 25 SYMLINK "
            "<voice_key>.onnx.json -> config.json"),
        "ghi_chu_symlink": (
            "Kho lanh KHONG giu 25 symlink (scp deref chung). Chay "
            "TAO_LAI_SYMLINK.sh sau khi tai ve de dung lai cau truc."),
        "bat_bien_ten_tep": (
            "voice_id = piper:<voice_key> da nam trong job cu VA gop phan "
            "sinh output_key tren R2 -> ten tep KHONG duoc doi"),
        "noi_dung": noi_dung,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (local / "TAO_LAI_SYMLINK.sh").write_text(TAO_LAI, encoding="utf-8")
    tong = sum(e["size_bytes"] for e in noi_dung)
    print(f"  tong           : {tong} byte ({tong / 2**30:.2f} GiB)")

    print("\n" + "=" * 70)
    print("  BUOC 3 — DAY len kho lanh Drive")
    print("=" * 70)
    cp = rclone_copy(str(local), DRIVE_MODELS_REMOTE,
                     rclone_bin=phan_giai("rclone"), timeout=14400)
    print(f"  exit_code: {cp['exit_code']}")
    if cp["exit_code"] != 0:
        print(f"  {cp['stderr_tail'][-500:]}")
        return 4

    print("\n" + "=" * 70)
    print("  BUOC 4 — DOI SOAT DOC LAP")
    print("=" * 70)
    vr = rclone_verify(str(local), DRIVE_MODELS_REMOTE,
                       rclone_bin=phan_giai("rclone"), timeout=3600)
    print(f"  rclone check --one-way exit: {vr['check_exit_code']}")
    try:
        sz = json.loads(vr["size"] or "{}")
        print(f"  tren Drive: {sz.get('count')} tep, {sz.get('bytes')} byte")
    except json.JSONDecodeError:
        pass
    ok = vr["check_exit_code"] == 0
    print("\n" + "=" * 70)
    print(f"  KET LUAN: {'PASS' if ok else 'FAIL'}")
    print("=" * 70)
    if ok:
        print(f"  Model gio co ban thu HAI, ngoai dia boot cua {VM_NAME}.")
        print(f"  Tai ve: rclone copy {DRIVE_MODELS_REMOTE} <dich> --checksum")
        print("  Roi:    bash TAO_LAI_SYMLINK.sh <dich>")
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
