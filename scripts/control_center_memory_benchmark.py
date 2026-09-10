#!/usr/bin/env python3
"""Benchmark lịch sử dài cho ký ức V0.6 — số ĐO, không phải số ước.

CÂU HỎI DUY NHẤT CẦN TRẢ LỜI BẰNG SỐ: lịch sử thô có thể lớn hơn một cửa
sổ ngữ cảnh nhiều lần, mà gói ngữ cảnh vẫn nằm dưới trần?

    python scripts/control_center_memory_benchmark.py                # 200k
    python scripts/control_center_memory_benchmark.py --so 50000
    python scripts/control_center_memory_benchmark.py --giu          # giữ thư mục

In ra: thời gian nạp, kích thước sổ/blob/chỉ mục, độ trễ tìm (nóng/lạnh),
kích thước gói ngữ cảnh ở 4 ngân sách, và tỉ lệ gói/lịch sử. Không gọi
LLM, không mạng. Thư mục tạm bị xoá khi xong trừ khi `--giu`.
"""
from __future__ import annotations

import argparse
import io
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)
GOC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GOC))

from scripts.control_center.memory.goi_ngu_canh import BoMayNguCanh, NganSach  # noqa: E402
from scripts.control_center.memory.model import (KyUc, LoaiKyUc, SuKien,  # noqa: E402
                                                 uoc_token)
from scripts.control_center.memory.provider import LocalMemoryProvider  # noqa: E402

TU = ("farmer", "AWS", "Appwrite", "R2", "worker", "TTS", "pipeline", "Cloudflare",
      "Next.js", "FastAPI", "worktree", "agent", "khoá", "SSH", "tệp", "cấu hình",
      "kho", "lưu trữ", "legacy", "chỉ đọc", "migrate", "render", "audio", "giọng",
      "chương", "truyện", "hàng đợi", "lỗi", "thử lại", "kiểm định", "đóng gói", "EXE")


def cau_ngau_nhien(rng: random.Random, i: int) -> str:
    n = rng.randint(60, 140)
    tu = [rng.choice(TU) for _ in range(n)]
    return f"Sự kiện {i}: " + " ".join(tu)


def mb(b: int) -> str:
    return f"{b / 1048576:.1f} MB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", type=int, default=200_000)
    ap.add_argument("--giu", action="store_true")
    a = ap.parse_args(argv)
    goc = Path(tempfile.mkdtemp(prefix="cc-membench-"))
    print(f"# benchmark ký ức V0.6 — {a.so:,} sự kiện — {goc}")
    p = LocalMemoryProvider(goc, "bench")
    ok, che_do = p.san_sang()
    print(f"# sổ: {p.kho.path.name} · chế độ tìm: {che_do}")
    rng = random.Random(6)

    # -- nap ----------------------------------------------------------------
    t0 = time.perf_counter()
    kim = rng.sample(range(a.so), 20)         # 20 "kim" de tim lai
    byte_tho = 0
    lo = 2000
    for dau in range(0, a.so, lo):
        with p.kho.giao_dich():
            for i in range(dau, min(a.so, dau + lo)):
                van = cau_ngau_nhien(rng, i)
                if i in kim:
                    van += f" KIM-{i}-canonical-fanficappwrite"
                byte_tho += len(van.encode("utf-8"))
                p.ghi_su_kien(SuKien(loai="chat_user", ts=time.time() - (a.so - i),
                                     tom_tat=van, nguon="bench"))
        if dau % 20000 == 0 and dau:
            print(f"  … {dau:,} ({time.perf_counter() - t0:.0f}s)")
    # Mot lop ky uc L1 tren do (1 moi 50 su kien) de goi ngu canh co gi ma chon.
    for i in range(0, a.so, 50):
        p.luu_ky_uc(KyUc(loai=LoaiKyUc.EPISODIC, quan_trong=rng.randint(1, 9),
                         tieu_de=f"tóm tắt {i}", noi_dung=cau_ngau_nhien(rng, i)[:400],
                         ts_su_kien=time.time() - (a.so - i)))
    t_nap = time.perf_counter() - t0
    p.kho.toi_uu()
    p.kho._c().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print(f"nạp            : {t_nap:.1f}s ({a.so / t_nap:,.0f} sự kiện/s) · "
          f"văn bản thô {mb(byte_tho)}")

    # -- dung luong -----------------------------------------------------------
    tk = p.thong_ke()
    b = tk["byte"]
    print(f"đếm            : {tk['dem']['su_kien']:,} sự kiện · {tk['dem']['ky_uc']:,} ký ức")
    print(f"tệp sổ         : {mb(b['tep_db'])} (= {b['tep_db'] / max(1, byte_tho):.2f}× văn bản thô)")
    print(f"  lịch sử thô  : {mb(b['lich_su_tho'])}")
    print(f"  chỉ mục FTS  : {mb(b['chi_muc'])}")
    print(f"  có cấu trúc  : {mb(b['co_cau_truc'])}")
    print(f"  blob (dedup) : {mb(b['bang_chung'])} · {tk['so_blob']} tệp")
    print(f"tổng trên đĩa  : {mb(b['tong'])}")

    # -- tim ------------------------------------------------------------------
    def do(f, lan=5):
        ts = []
        for _ in range(lan):
            t = time.perf_counter(); f(); ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        return ts[0], ts[len(ts) // 2]
    k0 = kim[3]
    l1, m1 = do(lambda: p.tim_su_kien(f"KIM-{k0}-canonical", limit=5))
    kq = p.tim_su_kien(f"KIM-{k0}-canonical", limit=5)
    print(f"tìm kim (L0)   : lạnh {l1:.1f}ms · trung vị {m1:.1f}ms · "
          f"{'ĐÚNG' if kq and f'KIM-{k0}' in kq[0].tom_tat else 'SAI'}")
    l2, m2 = do(lambda: p.tim("khoá SSH tệp cấu hình", limit=60))
    print(f"tìm ký ức (L1) : lạnh {l2:.1f}ms · trung vị {m2:.1f}ms · "
          f"{len(p.tim('khoá SSH tệp cấu hình', limit=60))} ứng viên")
    l3, m3 = do(lambda: p.tim_su_kien("farmer", limit=10))
    print(f"từ phổ biến    : lạnh {l3:.1f}ms · trung vị {m3:.1f}ms  (bm25 trên từ có ở ~mọi dòng)")

    # -- goi ngu canh --------------------------------------------------------
    print("gói ngữ cảnh   : (trần → đo)  — phải luôn ≤ trần, độc lập kích thước sổ")
    for tong in (800, 1500, 2500, 5000):
        t = time.perf_counter()
        g = BoMayNguCanh(p, NganSach(tong=tong)).dung("khoá SSH canonical tệp cấu hình")
        ms = (time.perf_counter() - t) * 1000
        tl = uoc_token(g.render()) / max(1, byte_tho / 2.5)
        print(f"  {tong:>5} → {g.token_uoc:>5} token · {len(g.chon)} chọn · {g.bo_qua} bỏ qua"
              f" · {ms:.0f}ms · gói/lịch-sử = {tl:.2e}"
              f" {'OK' if g.token_uoc <= tong else 'VƯỢT'}")
    print(f"cửa sổ 200K token ≈ {mb(int(200_000 * 2.5))} văn bản; lịch sử thô ở đây = "
          f"{byte_tho / (200_000 * 2.5):.1f}× cửa sổ đó")

    p.close()
    if a.giu:
        print(f"# giữ thư mục: {goc}")
    else:
        shutil.rmtree(goc, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
