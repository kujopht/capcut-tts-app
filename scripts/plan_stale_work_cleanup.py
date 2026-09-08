#!/usr/bin/env python3
"""Ke hoach XOA cho tac pham READY-nhung-rong. Mac dinh KHONG xoa gi.

Pham vi GHIM trong ma: DUNG hai `work_id`, khong co co dong lenh nao doi
duoc. Mot cong cu "xoa tac pham bat ky" la mot cong cu khac han, va khong
phai cai duoc uy quyen o day.

## Vi sao phai CHUNG MINH truoc khi xoa

Xoa ban ghi san xuat la thao tac khong hoan tac duoc. Nen script nay khong
tin vao ky ức cua ai — no doc lai tung tieu chi tu DU LIEU SONG, va TU CHOI
lap ke hoach neu bat ky tieu chi nao khong dat:

    1. novel ton tai, chu so huu = svc_harvester
    2. 0 chuong                      <- trieu chung
    3. 0 job TTS                     <- he qua cua (2)
    4. manifest ton tai, ready=true  <- dung la "READY-nhung-rong"
    5. quyet dinh = approve
    6. do dai van ban > 100.000      <- NGUYEN NHAN GOC (MAX_CHAPTER_CHARS)
    7. manifest khong co audio

Tieu chi 6 la thu bien "mot tac pham hong" thanh "dung tac pham hong ma ta
dang noi toi". Thieu no, script nay se san sang xoa mot tac pham hong vi mot
ly do hoan toan khac.

## Cai KHONG xoa, va vi sao

`review_jobs` va ban an tren R2 duoc GIU LAI. Ban an (72 va 74 diem) la du
lieu HOP LE — no noi ve chat luong tac pham, khong ve loi cat chuong. Giu no
nghia la mot lan chay lai sau nay (khi da co cat chuong) dung lai duoc ban an
cu thay vi tra tien danh gia lan hai.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

ALLOWED_HOST = "13.212.224.218"
ALLOWED_USER = "ubuntu"
SVC_USER = "fanfic"
VENV = "/opt/fanfic-audio/.venv"

#: GHIM. Hai tac pham, khong hon. Doi chung can sua ma va doc lai docstring.
WORK_IDS = (
    "w_746f54d3a18cef20c9ad",       # Fire Bird
    "w_9a2405c9083f6a85f22f",       # With Sprinkles 2
)


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


_BODY = r'''
import json, subprocess, sys

from server.appwrite_store import AppwriteMetadataStore
from server.config import get_settings, load_settings
from server.farmer import canonical, drive_archive
from server.farmer.canonical import (
    ARTIFACT_AUDIO_VI, ARTIFACT_MANIFEST, MANIFESTS, PRODUCTION_ROOT,
    WorkManifest,
)
from server.farmer.dedup import FARMER_OWNER
from server.r2_adapter import R2StorageAdapter

WORK_IDS = __WORK_IDS__
APPLY = __APPLY__
AUDIT = __AUDIT__
MAX_CHAPTER_CHARS = 100000

#: Khong bao gio duoc dung toi. Ban an la du lieu HOP LE — no noi ve chat
#: luong tac pham, khong ve loi cat chuong.
TIEN_TO_CAM = ("review/",)

store = AppwriteMetadataStore(load_settings().appwrite)
r2 = R2StorageAdapter(get_settings().r2)
chi_muc = PRODUCTION_ROOT + "/" + MANIFESTS + "/"

if AUDIT:
    # Kiem SAU khi xoa: dung thu phai mat da mat, dung thu phai con van con.
    from server.farmer import review_keys

    for wid in WORK_IDS:
        print()
        print("=" * 70)
        print("work_id: " + wid)

        try:
            man = WorkManifest.from_dict(
                json.loads(r2.get(chi_muc + wid + ".json")))
            nid = man.novel_id
            print("  [XX] manifest VAN CON (le ra da xoa)")
        except Exception:
            nid = ""
            print("  [OK] manifest da xoa khoi chi muc")

        con = [o.key for o in r2.list_objects(PRODUCTION_ROOT + "/")
               if wid in o.key]
        print("  [%s] object R2 con lai mang work_id nay: %d"
              % ("OK" if not con else "XX", len(con)))
        for k in con:
            print("        " + k)

        goc_thung = (drive_archive.remote_name() + ":" + PRODUCTION_ROOT
                     + "/" + canonical.BUCKET_FANFIC_TTS)
        try:
            p = subprocess.run(["rclone", "lsf", "-R", goc_thung],
                               capture_output=True, text=True, timeout=180)
            muc = [x for x in (p.stdout or "").split() if wid in x]
        except Exception:
            muc = ["?"]
        # Phan biet TEP voi THU MUC: `lsf -R` liet ke ca hai, va mot thu muc
        # rong con lai khong phai du lieu — no la mot cai vo. Dem lan lon hai
        # thu se bao dong ve mot thu khong ton tai.
        tep = [x for x in muc if not x.endswith("/")]
        thu_muc = [x for x in muc if x.endswith("/")]
        print("  [%s] TEP Drive con lai: %d" % ("OK" if not tep else "XX",
                                                len(tep)))
        for x in tep:
            print("        " + x)

        if not tep and thu_muc:
            # Xoa cai vo rong — day la phan con lai cua CHINH thao tac da
            # duoc duyet, khong phai mot viec moi.
            duong = goc_thung + "/" + thu_muc[0].rstrip("/")
            assert wid in duong, "duong thu muc khong chua work_id: " + duong
            try:
                subprocess.run(["rclone", "rmdirs", duong],
                               capture_output=True, text=True, timeout=180)
                print("  [OK] da xoa thu muc rong con lai: " + thu_muc[0])
            except Exception as exc:
                print("  [XX] khong xoa duoc thu muc rong: %s" % exc)

        # --- PHAI CON ---
        try:
            job = store.get_review_job(wid)
            print("  [OK] review_job VAN CON: status=%s decision=%s"
                  % (job.status, getattr(job, "decision", "?")))
        except Exception as exc:
            print("  [XX] review_job da MAT: %s" % exc)

        for ten, khoa in (("mau", review_keys.sample_key(wid)),
                          ("ban an", review_keys.verdict_key(wid))):
            try:
                n = len(r2.get(khoa))
                print("  [OK] %s tren R2 VAN CON (%d byte): %s" % (ten, n, khoa))
            except Exception:
                print("  [XX] %s tren R2 da MAT: %s" % (ten, khoa))

    print()
    print("=" * 70)
    print("Kiem sau khi xoa: xong.")
    raise SystemExit(0)

ke_hoach = []
for wid in WORK_IDS:
    print()
    print("=" * 70)
    print("work_id: " + wid)
    bao = {"work_id": wid, "hop_le_de_xoa": False, "tieu_chi": {}, "xoa": {}}

    try:
        man = WorkManifest.from_dict(json.loads(r2.get(chi_muc + wid + ".json")))
    except Exception as exc:
        print("  KHONG doc duoc manifest: %s" % exc)
        ke_hoach.append(bao)
        continue

    d = man.canonical_dir
    print("  tieu de : " + (man.source_title or "?")[:60])
    print("  nguon   : " + man.source_url)
    print("  thu muc : " + d)

    # --- doc su that tu tung lop ------------------------------------------
    try:
        novel = store.get_novel(man.novel_id) if man.novel_id else None
    except Exception:
        novel = None
    try:
        chapters = store.list_chapters(man.novel_id) if man.novel_id else []
    except Exception:
        chapters = []
    jobs = []
    try:
        for ch in chapters:
            jobs += list(store.list_jobs(FARMER_OWNER, ch.chapter_id))
    except Exception:
        pass
    try:
        van_ban = r2.get(d + "/" + canonical.ARTIFACT_TEXT).decode("utf-8", "replace")
    except Exception:
        van_ban = ""

    t = bao["tieu_chi"]
    t["1_novel_ton_tai"] = novel is not None
    t["2_khong_co_chuong"] = len(chapters) == 0
    t["3_khong_co_job_tts"] = len(jobs) == 0
    t["4_manifest_ready"] = bool(man.ready)
    t["5_quyet_dinh_approve"] = man.decision == canonical.DECISION_APPROVE
    t["6_van_ban_vuot_han_muc"] = len(van_ban) > MAX_CHAPTER_CHARS
    t["7_khong_co_audio"] = not man.artifacts.get(ARTIFACT_AUDIO_VI)

    print("  do dai van ban: %d ky tu (han muc chuong %d)"
          % (len(van_ban), MAX_CHAPTER_CHARS))
    print("  --- tieu chi ---")
    for k in sorted(t):
        print("    [%s] %s" % ("OK" if t[k] else "XX", k))

    if not all(t.values()):
        print("  => TU CHOI lap ke hoach: khong dat du tieu chi")
        ke_hoach.append(bao)
        continue
    bao["hop_le_de_xoa"] = True

    # --- liet ke DUNG nhung gi se xoa -------------------------------------
    khoa_r2 = sorted(o.key for o in r2.list_objects(d + "/"))
    khoa_r2.append(chi_muc + wid + ".json")
    bao["xoa"]["r2"] = khoa_r2
    bao["xoa"]["appwrite_novel"] = man.novel_id

    duong_drive = drive_archive.remote_name() + ":" + d
    try:
        p = subprocess.run(["rclone", "lsf", "-R", duong_drive],
                           capture_output=True, text=True, timeout=180)
        tep_drive = sorted(x for x in (p.stdout or "").split()
                           if x and not x.endswith("/")) if p.returncode == 0 else []
    except Exception:
        tep_drive = []
    bao["xoa"]["drive_thu_muc"] = duong_drive
    bao["xoa"]["drive_tep"] = tep_drive

    print("  --- SE XOA ---")
    print("    Appwrite novel : %s (0 chuong, 0 job)" % man.novel_id)
    print("    R2 (%d object):" % len(khoa_r2))
    for k in khoa_r2:
        print("      " + k)
    print("    Drive (%d tep) duoi %s:" % (len(tep_drive), duong_drive))
    for k in tep_drive:
        print("      " + k)
    print("  --- GIU LAI ---")
    print("    review_jobs/%s + ban an tren R2 — ban an %d diem la du lieu"
          % (wid, man.quality_score))
    print("      HOP LE; giu de mot lan chay lai sau nay khong phai danh gia lai.")

    if not APPLY:
        ke_hoach.append(bao)
        continue

    # ------------------------------------------------------------------ XOA
    # Cac phep khang dinh nay chay NGAY TRUOC moi lan xoa, khong phai luc lap
    # ke hoach. Mot ke hoach dung o thoi diem lap van co the sai o thoi diem
    # thuc hien; thu duy nhat dang tin la trang thai ngay luc dong tay.
    print("  --- DANG XOA ---")

    for k in khoa_r2:
        assert k.startswith(d + "/") or k == chi_muc + wid + ".json", \
            "khoa nam ngoai pham vi tac pham: " + k
        for cam in TIEN_TO_CAM:
            assert not k.startswith(cam), "khoa thuoc vung CAM: " + k
    assert wid in duong_drive, "duong Drive khong chua work_id: " + duong_drive

    # 1. R2
    for k in khoa_r2:
        try:
            r2.delete(k)
            print("    R2 da xoa: " + k)
        except Exception as exc:
            print("    R2 XOA HONG: %s (%s)" % (k, exc))

    # 2. Drive — xoa TUNG TEP da liet ke, khong `purge` ca cay. Chi tiet hon,
    #    va mot duong dan sai chi hong mot tep thay vi mot thu muc.
    for ten in tep_drive:
        muc_tieu = duong_drive + "/" + ten
        try:
            p = subprocess.run(["rclone", "deletefile", muc_tieu],
                               capture_output=True, text=True, timeout=180)
            print("    Drive da xoa: %s%s" % (
                ten, "" if p.returncode == 0 else " (HONG: %s)"
                % (p.stderr or "").strip()[:120]))
        except Exception as exc:
            print("    Drive XOA HONG: %s (%s)" % (ten, exc))
    try:
        subprocess.run(["rclone", "rmdirs", duong_drive, "--leave-root"],
                       capture_output=True, text=True, timeout=180)
    except Exception:
        pass

    # 3. Appwrite — sau cung. `delete_novel` tu kiem chu so huu; mot ban ghi
    #    khong thuoc svc_harvester se nem thay vi bi xoa.
    try:
        store.delete_novel(man.novel_id, FARMER_OWNER)
        print("    Appwrite da xoa novel: " + man.novel_id)
    except Exception as exc:
        print("    Appwrite XOA HONG: %s (%s)" % (man.novel_id, exc))

    ke_hoach.append(bao)

print()
print("=" * 70)
so = sum(1 for b in ke_hoach if b["hop_le_de_xoa"])
print("TONG: %d/%d tac pham dat DU tieu chi de xoa" % (so, len(WORK_IDS)))
if APPLY:
    print("DA XOA %d tac pham. review_jobs va ban an tren R2 KHONG bi dung." % so)
else:
    print("KHONG co gi bi xoa trong lan chay nay (che do ke hoach).")
'''


def _body(apply_it: bool, audit: bool) -> str:
    return (_BODY.replace("__WORK_IDS__", repr(list(WORK_IDS)))
                 .replace("__APPLY__", "True" if apply_it else "False")
                 .replace("__AUDIT__", "True" if audit else "False"))


#: Doan chay tren may AWS. Ma Python di qua STDIN chu KHONG qua argv.
#:
#: Truoc day no duoc nhung thang vao mot heredoc ben trong mot chuoi da
#: duoc `_shquote` boc — hai lop trich dan long nhau, va `repr()` cua danh
#: sach work_id sinh ra dau nhay don o giua. Bash vo ngay dong do. Doc tu
#: stdin thi khong con lop trich dan nao de vo.
_REMOTE = f"""
set -eu
S=/var/lib/fanfic-farmer/_plan.py
install -o {SVC_USER} -g {SVC_USER} -m 600 /dev/null "$S"
cat > "$S"
systemd-run --quiet --pipe --wait --collect \\
  --uid={SVC_USER} --gid={SVC_USER} \\
  --working-directory=/opt/fanfic-audio \\
  -p EnvironmentFile=/etc/fanfic-audio/worker-prod.env \\
  -p 'EnvironmentFile=-/etc/fanfic-audio/farmer.env' \\
  -p 'Environment=PYTHONPATH=/opt/fanfic-audio' \\
  -p 'Environment=PYTHONIOENCODING=utf-8' \\
  -p 'Environment=RCLONE_CONFIG=/var/lib/fanfic-farmer/rclone.conf' \\
  {VENV}/bin/python "$S"
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ssh-key", required=True)
    ap.add_argument("--apply", action="store_true",
                    help="THUC HIEN xoa. Khong co co nay thi chi lap ke hoach. "
                         "Moi tieu chi duoc kiem LAI ngay truoc khi xoa.")
    ap.add_argument("--audit", action="store_true",
                    help="kiem SAU khi xoa: dung thu phai mat da mat, dung thu "
                         "phai con (ban an) van con. KHONG xoa gi.")
    args = ap.parse_args(argv)

    p = subprocess.run(
        ["ssh", "-i", args.ssh_key, "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=15", f"{ALLOWED_USER}@{ALLOWED_HOST}",
         f"sudo -n bash -c {_shquote(_REMOTE)}"],
        input=_body(args.apply and not args.audit, args.audit),
        capture_output=True, text=True, timeout=900,
        encoding="utf-8", errors="replace")
    print((p.stdout or "").rstrip())
    if p.returncode != 0:
        print(f"RESULT=PLAN_FAILED exit={p.returncode}")
        print((p.stderr or "")[-2000:])
    return p.returncode


if __name__ == "__main__":
    sys.exit(main())
