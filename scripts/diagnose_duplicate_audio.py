#!/usr/bin/env python
"""
Bao cao cac ban audio TRUNG LAP cua mot chuong. CHI DOC, khong xoa gi.

VI SAO CAN: `/library` liet ke tung TtsJob `completed` thanh mot dong. Mot
chuong co N job hoan tat thi hien N dong trong y het nhau, va nguoi dung khong
co cach nao biet chung khac nhau o dau — hay co khac nhau khong.

Truoc khi xoa bat cu thu gi, phai tra loi duoc: hai dong do la HAI BAN GHI
THUA cua cung mot ket qua, hay la HAI KET QUA THAT SU KHAC NHAU (khac giong,
khac ban noi dung, khac toc do)? Hai truong hop can hai cach xu ly khac han,
va script nay chi lam mot viec: noi ro chung khac nhau o dau.

    python scripts/diagnose_duplicate_audio.py
    python scripts/diagnose_duplicate_audio.py --user <user_id>
    python scripts/diagnose_duplicate_audio.py --json bao-cao.json

Cau hinh doc tu bien moi truong nhu backend (`FAS_ENV_FILE` tro toi tep .env
muon dung). KHONG BAO GIO in secret: khong in API key, khong in session token,
khong in URL da ky.

TUYET DOI KHONG XOA. Script nay khong co duong ghi nao.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.config import get_settings          # noqa: E402
from server.adapters import build_metadata_store  # noqa: E402
from server.domain import JobStatus             # noqa: E402


def rut_gon(s: str, n: int = 12) -> str:
    """Dau van tay chi de DOI CHIEU, khong can day du va khong nen day du."""
    s = s or ""
    return s if len(s) <= n else f"{s[:n]}…"


def phan_loai(nhom: List[Any]) -> str:
    """
    Vi sao nhom nay co nhieu hon mot ban?

    Day la cau tra loi quan trong nhat cua ca bao cao: no quyet dinh viec don
    dep la an toan hay la mat du lieu.
    """
    hashes = {j.content_hash for j in nhom}
    voices = {j.voice_id for j in nhom}
    rates = {j.rate for j in nhom}

    if len(hashes) == 1:
        # Cung dau van tay = cung noi dung + cung giong + cung thiet lap.
        # Dung ra idempotency phai chan duoc — day la truong hop DANG NGO nhat.
        return "TRUNG HOAN TOAN (cùng fingerprint — lẽ ra idempotency phải chặn)"
    ly_do = []
    if len(voices) > 1:
        ly_do.append(f"{len(voices)} giọng khác nhau")
    if len(rates) > 1:
        ly_do.append(f"{len(rates)} tốc độ khác nhau")
    if not ly_do:
        # Khac hash ma cung giong+toc do => noi dung chuong da doi giua cac lan.
        ly_do.append("nội dung chương đã sửa giữa các lần tạo")
    return "KHÁC NHAU THẬT: " + ", ".join(ly_do)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default="", help="chỉ xét một user_id")
    ap.add_argument("--json", dest="tep_json", default="",
                    help="ghi báo cáo ra tệp JSON")
    ap.add_argument("--all", action="store_true",
                    help="in cả chương chỉ có một bản (mặc định chỉ in nhóm nghi ngờ)")
    args = ap.parse_args()

    settings = get_settings()
    store = build_metadata_store(settings)
    print(f"Môi trường : {settings.environment}")
    print(f"Kho dữ liệu: {settings.data_backend}")
    print()

    if not args.user:
        print("Cần --user <user_id>: kho không có đường liệt kê toàn bộ người dùng.")
        print("Lấy user_id từ `/api/auth/me` của tài khoản cần xét.")
        return 2

    jobs = store.list_jobs(args.user)
    xong = [j for j in jobs if j.status == JobStatus.COMPLETED]
    print(f"Tổng số job     : {len(jobs)}")
    print(f"Job hoàn tất    : {len(xong)}")

    theo_chuong: Dict[str, List[Any]] = defaultdict(list)
    for j in xong:
        theo_chuong[j.chapter_id].append(j)

    nghi_ngo = {c: v for c, v in theo_chuong.items() if len(v) > 1}
    print(f"Chương có audio : {len(theo_chuong)}")
    print(f"Chương >1 bản   : {len(nghi_ngo)}")
    print()

    bao_cao: List[Dict[str, Any]] = []
    can_in = theo_chuong if args.all else nghi_ngo
    for chapter_id, nhom in sorted(can_in.items(),
                                   key=lambda kv: -len(kv[1])):
        try:
            chuong = store.get_chapter(chapter_id)
            tieu_de = chuong.title
        except Exception:
            tieu_de = "(không đọc được chương — có thể đã xoá)"

        loai = phan_loai(nhom) if len(nhom) > 1 else "chỉ một bản"
        print(f"── {tieu_de}")
        print(f"   chapter_id : {chapter_id}")
        print(f"   số bản     : {len(nhom)}   → {loai}")

        muc: Dict[str, Any] = {
            "chapter_id": chapter_id, "title": tieu_de,
            "so_ban": len(nhom), "phan_loai": loai, "jobs": [],
        }
        for j in sorted(nhom, key=lambda x: x.created_at):
            # `output_key` la khoa object trong R2. In ra la an toan: no khong
            # phai URL da ky va khong tai duoc neu khong co credential.
            print(f"     · job {j.job_id}  {j.status.value:9} "
                  f"hash={rut_gon(j.content_hash)}  voice={j.voice_id}  "
                  f"rate={j.rate}  chunk={j.chunk_chars}  {j.created_at}")
            print(f"       object: {j.output_key or '(không có)'}")
            muc["jobs"].append({
                "job_id": j.job_id, "status": j.status.value,
                "content_hash": j.content_hash, "voice_id": j.voice_id,
                "rate": j.rate, "chunk_chars": j.chunk_chars,
                "created_at": j.created_at, "output_key": j.output_key,
            })

        # AudioTrack: mot ban ghi metadata rieng, TIM-HOAC-TAO theo
        # (chapter_id, content_hash). Neu so track it hon so job thi cac job do
        # dung CHUNG mot track — tuc la khong co object thua trong R2.
        try:
            tracks = store.tracks_for_chapter(chapter_id)
            print(f"   AudioTrack : {len(tracks)}")
            for t in tracks:
                print(f"     · track {t.track_id}  object={t.object_key}  "
                      f"{t.size_bytes} B  {t.created_at}")
            muc["tracks"] = [{"track_id": t.track_id, "object_key": t.object_key,
                              "size_bytes": t.size_bytes,
                              "created_at": t.created_at} for t in tracks]
        except Exception as exc:
            print(f"   AudioTrack : (không đọc được: {type(exc).__name__})")
            muc["tracks"] = None

        # Object R2 RIENG BIET: cac `output_key` khac nhau. Trung khoa thi chi
        # la mot object, va do la thiet ke — khoa tat dinh theo content_hash.
        khoa = {j.output_key for j in nhom if j.output_key}
        print(f"   object R2 riêng biệt: {len(khoa)}")
        muc["so_object_rieng_biet"] = len(khoa)
        print()
        bao_cao.append(muc)

    if args.tep_json:
        with open(args.tep_json, "w", encoding="utf-8") as f:
            json.dump(bao_cao, f, ensure_ascii=False, indent=2)
        print(f"Đã ghi báo cáo JSON: {args.tep_json}")

    print()
    print("KHÔNG XOÁ GÌ. Script này chỉ đọc.")
    print("Xem cột 'phân loại' trước khi quyết định: 'KHÁC NHAU THẬT' nghĩa là")
    print("xoá sẽ mất một bản audio người dùng có thể đang cần.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
