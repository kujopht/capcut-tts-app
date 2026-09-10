# -*- coding: utf-8 -*-
"""CLI di trú kho dữ liệu Router về GỐC CHÍNH TẮC.

    python scripts/router_cc_di_tru.py                 # KHÁM PHÁ + XEM TRƯỚC (không ghi)
    python scripts/router_cc_di_tru.py --chay           # ghi thật (tự sao lưu đích trước)
    python scripts/router_cc_di_tru.py --chay --dat-moc # + đặt mốc DA_DI_TRU vào sổ cũ
    python scripts/router_cc_di_tru.py --goc <dir>      # đích khác (bài kiểm)
    python scripts/router_cc_di_tru.py --chi-du-an fanfic

Mặc định là XEM TRƯỚC: không ghi một byte nào vào đích. Không quét cả máy —
chỉ kho nguồn + các `dist-*` cạnh nó (xem `di_tru.ung_vien_mac_dinh`).
KHÔNG xoá sổ cũ bao giờ.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOC_MA = Path(__file__).resolve().parents[1]
if str(GOC_MA) not in sys.path:
    sys.path.insert(0, str(GOC_MA))

from scripts.control_center import di_tru as DT                       # noqa: E402
from scripts.control_center.duong_du_lieu import mo_ta                # noqa: E402


def ghi(s: str = "") -> None:
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--goc", default="", help="gốc dữ liệu ĐÍCH (mặc định: chính tắc)")
    ap.add_argument("--kho-nguon", default="", help="kho nguồn để tìm dist-* (mặc định: kho này)")
    ap.add_argument("--chay", action="store_true", help="GHI THẬT (mặc định chỉ xem trước)")
    ap.add_argument("--dat-moc", action="store_true",
                    help="sau khi ghi, đặt mốc DA_DI_TRU.json vào các sổ cũ")
    ap.add_argument("--chi-du-an", default="", help="chỉ di trú các project_id này (phẩy)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass

    dich = a.goc or None
    chi = [x.strip() for x in a.chi_du_an.split(",") if x.strip()] or None

    mt = mo_ta(dich)
    ghi("=" * 78)
    ghi("DI TRÚ KHO DỮ LIỆU ROUTER -> GỐC CHÍNH TẮC")
    ghi(f"  đích            : {mt['goc']}")
    ghi(f"  là chính tắc    : {mt['la_chinh_tac']}  (chính tắc: {mt['chinh_tac']})")
    ghi(f"  phiên bản kho   : trên đĩa {mt['phien_ban_kho']} · mã hiểu {mt['phien_ban_ma']}")
    ghi(f"  đích đã có data : {mt['co_du_lieu']}")
    ghi("=" * 78)

    nguon = DT.kham_pha(kho_nguon=Path(a.kho_nguon) if a.kho_nguon else None)
    ghi(f"\nKHÁM PHÁ — {len(nguon)} gốc ứng viên (tường minh, KHÔNG quét máy):")
    for n in nguon:
        cd = "có" if n.control_db else "KHÔNG"
        ghi(f"  [{'hợp lệ' if n.hop_le else 'bỏ   '}] {n.nhan}")
        ghi(f"       {n.goc}")
        ghi(f"       control.db={cd} · dự án={list(n.du_an)} · quyển={len(n.sach)} "
            f"· su_kien={n.tong_su_kien} · ky_uc={n.tong_ky_uc}")
        for s in n.sach:
            ghi(f"         - {s.ns} pid={s.project_id or '(không quy được)'} "
                f"{ {k: v for k, v in s.dem.items() if v} }")
        if n.ly_do:
            ghi(f"       lý do: {n.ly_do}")

    bc = DT.di_tru(dich, nguon=nguon, thu_kho=not a.chay, chi_du_an=chi)
    ghi("\n" + ("GHI THẬT" if a.chay else "XEM TRƯỚC (không ghi gì)"))
    ghi(f"  sao lưu : {bc.get('sao_luu') or '(xem trước)'}")
    g = bc.get("gieo") or {}
    ghi(f"  gieo    : {g.get('gieo')} {('từ ' + str(g.get('tu'))) if g.get('tu') else g.get('ly_do','')}")
    for x in bc.get("gop", []):
        if x.get("bo_qua"):
            ghi(f"  gộp     : {x.get('nguon')} {x.get('ns')} -> BỎ QUA ({x['bo_qua']})")
        else:
            ghi(f"  gộp     : {x.get('nguon')} {x.get('ns')} pid={x.get('project_id')} -> "
                + " ".join(f"{k}={v}" for k, v in x.items()
                           if k not in ("nguon", "ns", "project_id", "goc") and v))
    if bc.get("tong"):
        ghi(f"  TỔNG    : " + " ".join(f"{k}={v}" for k, v in sorted(bc["tong"].items()) if v))
    if bc.get("ly_do"):
        ghi(f"  ghi chú : {bc['ly_do']}")

    if a.chay and a.dat_moc:
        for n in nguon:
            if n.hop_le and Path(n.goc).resolve() != Path(bc["dich"]).resolve():
                p = DT.dat_moc_da_di_tru(n, dich, bao_cao=bc)
                ghi(f"  mốc     : {p}")

    if a.json:
        ghi(json.dumps(bc, ensure_ascii=False, indent=1))
    ghi("=" * 78)
    if not a.chay:
        ghi("Chưa ghi gì. Chạy lại với `--chay` để di trú thật (tự sao lưu đích).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
