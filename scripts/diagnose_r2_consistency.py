#!/usr/bin/env python3
"""
Chan doan do tre/mat nhat quan cua R2: PUT bao thanh cong nhung HEAD/GET
ngay sau do lai bao khong ton tai (`NoSuchKey`).

    python -m scripts.diagnose_r2_consistency --api https://fas-staging-api.onrender.com

Tao MOT chuong + MOT job TTS dung-mot-lan qua chinh API dang chay (khong
dung boto3/credential R2 truc tiep — script nay khong bao gio can va khong
bao gio doc R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY). Ghi lai:

    - dinh danh bucket KHONG BI MAT: chi ho cua presigned URL (vi du
      `<account>.r2.cloudflarestorage.com`), KHONG BAO GIO ca URL day du —
      query string cua URL ky san chua chu ky/thoi han, va (o mot so cau
      hinh boto3) co the lo ten bucket qua duong dan; script CHI giu phan
      host, cat toan bo phan con lai truoc khi ghi vao bao cao.
    - object key (KHONG bi mat — suy tu owner_id/chapter_id/content_hash,
      cung cong khai nhu chinh $id cua tai nguyen).
    - ket qua PUT: suy tu trang thai job (`completed` => PUT khong nem loi,
      dung bat bien trong `main._run_job`: "THU TU BAT BUOC: synthesize ->
      upload -> create_track -> luu completed").
    - ket qua HEAD/GET NGAY sau khi job hoan tat: xin MOT URL ky moi qua
      `GET /api/audio/{id}/url` roi GET THANG no. `GET /api/audio/{id}`
      (khong /url) KHONG dung duoc cho viec nay — voi kho R2 no chi
      307-redirect sang URL ky (xem `main.stream_audio`), nhanh
      `storage.get()` server-side la `# pragma: no cover`, chi chay voi
      kho cuc bo. URL bi VUT BO ngay sau khi doc status code.
    - CHUOI HEAD/GET lap lai voi backoff ngan (moi lan xin URL ky MOI, vi
      URL cu co the het han), de phan biet "mat vinh vien" voi "do tre
      truyen ba/lifecycle tuc thi roi moi bien mat".
    - Tin hieu THU HAI, hoan toan doc lap: khi xoa fixture, cascade xoa
      chuong goi `storage.exists()` (boto3 `head_object` server-side, KHONG
      qua URL ky) truoc khi xoa — so `objects` bi xoa server bao ra la mot
      phep kiem tra ton tai THAT SU, khac co che voi URL ky o tren.

Don sach fixture cua chinh no o cuoi (xoa truyen dung mot lan, ke ca khi
kiem tra that bai giua chung).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


@dataclass
class LanThu:
    """Mot lan kiem tra HEAD/GET, ghi lai ĐỘ TRỄ ke tu khi job hoan tat."""

    lan: int
    do_tre_giay: float
    http_status: Optional[int]
    doc_duoc: bool


@dataclass
class BaoCao:
    bucket_host: str = ""          # CHI host, khong bao gio ca URL
    object_key: str = ""
    put_thanh_cong: Optional[bool] = None
    head_ngay_lap_tuc: Optional[LanThu] = None
    chuoi_head_sau_do: List[LanThu] = field(default_factory=list)
    ket_luan: str = ""
    fixture_da_don: bool = False
    #: Tin hieu THU HAI, doc lap voi HEAD/GET qua URL ky: server tu kiem tra
    #: `storage.exists()` (boto3 `head_object`, KHONG qua URL ky) khi xoa
    #: truyen — xem `server/main.py::_xoa_chuong_va_lien_quan`. 0 dong y voi
    #: ket luan "object da mat" bang mot co che hoan toan khac.
    objects_xoa_server_side: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        def _lan_thu(x: Optional[LanThu]) -> Optional[Dict[str, Any]]:
            if x is None:
                return None
            return {"lan": x.lan, "do_tre_giay": round(x.do_tre_giay, 2),
                    "http_status": x.http_status, "doc_duoc": x.doc_duoc}

        return {
            "bucket_host": self.bucket_host,
            "object_key": self.object_key,
            "put_thanh_cong": self.put_thanh_cong,
            "head_ngay_lap_tuc": _lan_thu(self.head_ngay_lap_tuc),
            "chuoi_head_sau_do": [_lan_thu(x) for x in self.chuoi_head_sau_do],
            "objects_xoa_server_side": self.objects_xoa_server_side,
            "ket_luan": self.ket_luan,
            "fixture_da_don": self.fixture_da_don,
        }


def _goi(client: httpx.Client, method: str, path: str,
         payload: Optional[Dict[str, Any]] = None,
         token: Optional[str] = None) -> tuple[int, Dict[str, Any]]:
    headers = {"User-Agent": _UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = client.request(method, path, json=payload, headers=headers)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {}


def _rut_gon_host(url: str) -> str:
    """CHI host cua URL ky san. Khong bao gio tra ve path/query — do la noi
    chua chu ky va (tuy cau hinh) co the mang ten bucket."""
    try:
        return urllib.parse.urlsplit(url).netloc
    except Exception:
        return "(khong doc duoc host)"


def chay(api: str, *, job_timeout: float, so_lan_head_lap_lai: int,
        khoang_cach_giay: float) -> BaoCao:
    bao_cao = BaoCao()
    # Goi Free cua Render ngu sau 15 phut khong traffic — lan goi dau danh
    # thuc co the mat toi ~100s (xem deploy/render.free.yaml).
    client = httpx.Client(timeout=120.0, trust_env=False, base_url=api)

    email = f"r2diag-{uuid.uuid4().hex[:10]}@fanficdev.invalid"
    password = "Aa1!" + uuid.uuid4().hex[:10]
    try:
        ma, r = _goi(client, "POST", "/api/auth/register",
                    {"email": email, "password": password, "display_name": "r2diag"})
    except httpx.TimeoutException:
        bao_cao.ket_luan = "backend khong phan hoi trong thoi gian danh thuc — thu lai sau"
        return bao_cao
    if ma != 201:
        bao_cao.ket_luan = f"khong dang ky duoc tai khoan chan doan: HTTP {ma}"
        return bao_cao
    tok = r.get("token") or r.get("access_token")

    ma, r = _goi(client, "POST", "/api/novels",
                {"title": "[R2-DIAG] chan doan do tre R2", "description": "disposable"}, tok)
    if ma not in (200, 201):
        bao_cao.ket_luan = f"khong tao duoc truyen chan doan: HTTP {ma}"
        return bao_cao
    nid = r["novel"]["novel_id"]

    try:
        ma, r = _goi(client, "POST", "/api/chapters",
                    {"novel_id": nid, "title": "c1",
                     "content": "Chan doan do tre R2. " * 100, "order_index": 0}, tok)
        if ma not in (200, 201):
            bao_cao.ket_luan = f"khong tao duoc chuong chan doan: HTTP {ma}"
            return bao_cao
        cid = r["chapter"]["chapter_id"]

        ma, r = _goi(client, "POST", "/api/jobs",
                    {"chapter_id": cid, "voice_id": "edge:vi-VN-HoaiMyNeural"}, tok)
        if ma not in (200, 201, 202):
            bao_cao.ket_luan = f"khong tao duoc job chan doan: HTTP {ma}"
            return bao_cao
        jid = r["job"]["job_id"]

        han_chot = time.monotonic() + job_timeout
        trang_thai = None
        while time.monotonic() < han_chot:
            ma, r = _goi(client, "GET", f"/api/jobs/{jid}", None, tok)
            trang_thai = r.get("job", {}).get("status")
            if trang_thai in ("completed", "failed"):
                break
            time.sleep(3)

        bao_cao.put_thanh_cong = (trang_thai == "completed")
        if trang_thai != "completed":
            bao_cao.ket_luan = f"job khong hoan tat (trang thai={trang_thai}) — khong chan doan duoc PUT/HEAD"
            return bao_cao

        job = r.get("job", {})
        owner_id = job.get("owner_id", "")
        content_hash = job.get("content_hash", "")
        bao_cao.object_key = f"audio/{owner_id}/{cid}/{content_hash}.mp3"

        # `/api/audio/{id}` CHI 307-redirect sang URL ky (xem
        # `main.stream_audio` — nhanh `storage.get()` server-side la
        # `# pragma: no cover`, chi chay duoc voi kho cuc bo, khong bao gio
        # voi R2). Nen phep kiem THAT phai xin MOT URL ky moi moi lan roi tu
        # GET thang no — dung y het duong di trinh duyet that su dung. URL
        # bi VUT BO ngay sau khi doc status code, khong bao gio ghi lai.
        def _xin_va_kiem(lan: int, t0: float) -> LanThu:
            ma_url, r_url = _goi(client, "GET", f"/api/audio/{cid}/url", None, tok)
            url = r_url.get("url") if ma_url == 200 else None
            if not url:
                return LanThu(lan=lan, do_tre_giay=time.monotonic() - t0,
                              http_status=ma_url, doc_duoc=False)
            if not bao_cao.bucket_host:
                bao_cao.bucket_host = _rut_gon_host(url)
            try:
                with httpx.Client(timeout=30.0, trust_env=False) as r2_client:
                    resp = r2_client.get(url)
                    ma_r2 = resp.status_code
                    resp.read()  # xa het than de dong ket noi gon gang
            except httpx.HTTPError:
                ma_r2 = None
            return LanThu(lan=lan, do_tre_giay=time.monotonic() - t0,
                          http_status=ma_r2, doc_duoc=(ma_r2 == 200))

        t0 = time.monotonic()
        bao_cao.head_ngay_lap_tuc = _xin_va_kiem(0, t0)

        for i in range(1, so_lan_head_lap_lai + 1):
            time.sleep(khoang_cach_giay)
            bao_cao.chuoi_head_sau_do.append(_xin_va_kiem(i, t0))

        tat_ca = [bao_cao.head_ngay_lap_tuc] + bao_cao.chuoi_head_sau_do
        if all(x.doc_duoc for x in tat_ca):
            bao_cao.ket_luan = "DOC DUOC o moi lan thu — khong tai hien duoc su co lan nay"
        elif not any(x.doc_duoc for x in tat_ca):
            bao_cao.ket_luan = ("MAT NGAY TU LAN DAU va KHONG BAO GIO xuat hien lai trong "
                               f"{tat_ca[-1].do_tre_giay:.1f}s — khop voi 'object bien mat "
                               "tuc thi', khong phai do tre truyen ba thong thuong")
        else:
            bao_cao.ket_luan = ("KHONG NHAT QUAN giua cac lan thu — co dau hieu do tre "
                               "truyen ba/cache thay vi mat han")
        return bao_cao
    finally:
        _, xoa = _goi(client, "DELETE", f"/api/novels/{nid}", None, tok)
        bao_cao.fixture_da_don = bool(xoa.get("deleted"))
        removed = xoa.get("removed") or {}
        bao_cao.objects_xoa_server_side = removed.get("objects")
        client.close()


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", required=True, help="URL goc cua backend can chan doan")
    p.add_argument("--job-timeout", type=float, default=180.0)
    p.add_argument("--retries", type=int, default=5,
                   help="so lan HEAD/GET lap lai sau lan dau, cach nhau --interval giay")
    p.add_argument("--interval", type=float, default=3.0)
    p.add_argument("--json", help="ghi bao cao ra file JSON")
    a = p.parse_args(argv)

    bao_cao = chay(a.api, job_timeout=a.job_timeout,
                   so_lan_head_lap_lai=a.retries, khoang_cach_giay=a.interval)

    print(f"bucket_host        : {bao_cao.bucket_host or '(khong lay duoc)'}")
    print(f"object_key         : {bao_cao.object_key or '(khong co)'}")
    print(f"put_thanh_cong     : {bao_cao.put_thanh_cong}")
    if bao_cao.head_ngay_lap_tuc:
        x = bao_cao.head_ngay_lap_tuc
        print(f"HEAD ngay lap tuc  : +{x.do_tre_giay:.2f}s  HTTP {x.http_status}  doc_duoc={x.doc_duoc}")
    for x in bao_cao.chuoi_head_sau_do:
        print(f"HEAD lan {x.lan}          : +{x.do_tre_giay:.2f}s  HTTP {x.http_status}  doc_duoc={x.doc_duoc}")
    print(f"objects_xoa_server_side : {bao_cao.objects_xoa_server_side}"
          "  (kiem tra doc lap qua storage.exists() server-side luc xoa)")
    print(f"fixture_da_don     : {bao_cao.fixture_da_don}")
    print(f"\nket luan: {bao_cao.ket_luan}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(bao_cao.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\nDa ghi bao cao: {a.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
