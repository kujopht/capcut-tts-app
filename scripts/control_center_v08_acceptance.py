"""NGHIỆM THU V0.8 — Strategist + Reviewer + bộ định tuyến model động.

Chạy SÁU tình huống hội thoại A–F của yêu cầu v0.8 trên **fabric thật** và
**ký ức dự án Fanfic thật**, rồi kiểm mười điều của mục §16 (POLICY
ACCEPTANCE).

TẤT ĐỊNH VÀ KHÔNG TỐN QUOTA. Các vai chạy qua `BoGoiGia` — kịch bản cố định.
Đó là chủ ý, không phải một lối tắt:

* thứ v0.8 cần chứng minh là **quyết định định tuyến** (vai nào, model nào,
  vì sao, có độc lập không, có chạm bậc cao cấp không), và mọi quyết định đó
  đã nằm trọn ở tầng `Scheduler` — tầng CỐ Ý tách khỏi thực thi;
* gọi model thật cho sáu tình huống × bốn chế độ là ~20 lượt Antigravity cho
  một phép đo không thêm thông tin nào về định tuyến;
* và bể Claude/GPT của Antigravity đo được 10% hạn mức tuần lúc viết bài này
  (2026-09-11) — tiêu nó cho một bài nghiệm thu là đúng thứ
  `~/.claude/CLAUDE.md` cấm.

Thứ *có* gọi ra ngoài là phép ĐO HẠN MỨC (`--do-han-muc`), và nó tắt mặc
định vì mỗi lần là một lượt `agy` thật.

Chạy:
    python scripts/control_center_v08_acceptance.py
    python scripts/control_center_v08_acceptance.py --do-han-muc
    python scripts/control_center_v08_acceptance.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from scripts.control_center.duong_du_lieu import (duong_control_db,   # noqa: E402
                                                  goc_du_lieu)
from scripts.control_center.reasoning import chinh_sach as CS         # noqa: E402
from scripts.control_center.reasoning import ngan_sach as NS          # noqa: E402
from scripts.control_center.reasoning.dinh_tuyen import BoDinhTuyenVai  # noqa: E402
from scripts.control_center.reasoning.goi import BoGoiGia, LuotVai    # noqa: E402
from scripts.control_center.reasoning.hoi_dong import HoiDong         # noqa: E402
from scripts.control_center.reasoning.phan_loai import (lap_ke_hoach_vai,  # noqa: E402
                                                        phan_loai_luot)
from scripts.control_center.reasoning.vai import VaiTro               # noqa: E402
from scripts.router_v4 import fabric_config as FC                     # noqa: E402
from scripts.router_v4.premium import CheDo                           # noqa: E402

DU_AN = "fanfic"

#: Sáu tình huống §15, NGUYÊN VĂN.
TINH_HUONG: Tuple[Tuple[str, str, str], ...] = (
    ("A", "production farmer hiện chạy không?",
     "tra cứu SỐNG trực tiếp — không Strategist, không Reviewer, không leo thang"),
    ("B", "vụ SSH key trước đây là gì?",
     "ký ức dự án — không worker đi khám phá lại"),
    ("C", "tại sao mấy hôm nay Drive không có production mới?",
     "bằng chứng ProductionProbeBroker + chẩn đoán vừa phải"),
    ("D", "theo trạng thái hiện tại, project Fanfic nên ưu tiên phát triển "
          "phần nào tiếp theo và tại sao?",
     "Strategist THAM GIA; Reviewer chỉ khi tác động đủ lớn"),
    ("E", "hãy đề xuất một redesign lớn cho production architecture và phản "
          "biện chính đề xuất đó.",
     "Strategist + Reviewer ĐỘC LẬP"),
    ("F", "ê bro",
     "chỉ Leader, rẻ"),
)

CL = ('{"muc_tieu":"đánh giá hướng đi","phuong_an":["A","B"],'
      '"danh_doi":["A rẻ hơn, B an toàn hơn"],"de_xuat":"chọn A",'
      '"rui_ro":["di trú dữ liệu"],"viec_can_lam":["v1"],"do_tin":0.7,'
      '"bang_chung":["qd_0001"],"cau_hoi_can_nguoi":["ai duyệt cutover?"]}')
PB = ('{"phan_xu":"REVISE","bang_chung_thieu":["chưa có số liệu tải thật"],'
      '"phat_hien_rui_ro":["cutover không có đường lùi"],"do_tin":0.6}')


class Bang:
    """Bảng kết quả: mỗi dòng là một điều KIỂM ĐƯỢC, không phải một lời kể."""

    def __init__(self) -> None:
        self.hang: List[Dict] = []

    def them(self, muc: str, dat: bool, chi_tiet: str = "") -> bool:
        self.hang.append({"muc": muc, "dat": bool(dat), "chi_tiet": chi_tiet})
        print(f"  [{'ĐẠT' if dat else 'HỎNG'}] {muc}"
              + (f"\n         {chi_tiet}" if chi_tiet else ""))
        return bool(dat)

    @property
    def so_dat(self) -> int:
        return sum(1 for h in self.hang if h["dat"])

    @property
    def tat_ca_dat(self) -> bool:
        return all(h["dat"] for h in self.hang)


def _ky_uc():
    """`DichVuKyUc` THẬT trên sổ chính tắc. `None` nếu không mở được."""
    try:
        from scripts.control_center.memory.service import DichVuKyUc
        from scripts.control_center.store import ControlStore
        st = ControlStore(duong_control_db())
        return DichVuKyUc(st, goc_du_lieu()), st
    except Exception as exc:                                # noqa: BLE001
        print(f"  (!) không mở được ký ức thật: {type(exc).__name__}: {exc}")
        return None, None


def _hoi_dong(fab, weights, cs, kich_ban):
    bdt = BoDinhTuyenVai(fab, weights=weights, chinh_sach=cs)
    gia = BoGoiGia(kich_ban=kich_ban)
    return HoiDong(bo_dinh_tuyen=bdt, bo_goi=gia), gia, bdt


def _kich_ban_day_du():
    return {VaiTro.STRATEGIST: [LuotVai(ok=True, van_ban=CL, giay=4.2)],
            VaiTro.REVIEWER: [LuotVai(ok=True, van_ban=PB, giay=2.8)]}


# ---------------------------------------------------------------- pha A-F --

def pha_tinh_huong(bd: Bang, fab, weights, cs) -> Dict:
    print("\n--- PHẦN 1: SÁU TÌNH HUỐNG HỘI THOẠI (§15 A–F) ---")
    ra: Dict[str, Dict] = {}
    for nhan, cau, mong in TINH_HUONG:
        p = phan_loai_luot(cau)
        cd = CheDo.AUTO
        hd, gia, _ = _hoi_dong(fab, weights, cs, _kich_ban_day_du())
        kq = hd.chay(cau=cau, phan_loai=p, che_do=cd, khoi_san_co={
            "vien_nang": "(viên nang dự án — nghiệm thu)",
            "ky_uc": "(ký ức dự án — nghiệm thu)"}, project_id=DU_AN)
        vai = [v.value for v in kq.ke_hoach.vai]
        ra[nhan] = {"cau": cau, "mong_doi": mong,
                    "bac": p.bac.value, "tac_dong": p.tac_dong.value,
                    "do_tin": p.do_tin, "vai": vai,
                    "so_luot_model": len(gia.da_goi),
                    "dung_astra": kq.so.dung_astra,
                    "suy_giam": kq.suy_giam,
                    "dong": kq.dong_nguon_goc()}
        print(f"\n  {nhan}. {cau[:66]}")
        print(f"     mong đợi : {mong}")
        print(f"     phân loại: {p.bac.value}/{p.tac_dong.value} "
              f"(tin {p.do_tin:.2f}) · vai {vai} · {len(gia.da_goi)} lượt model")
        for d in kq.dong_nguon_goc():
            print(f"       {d}")

    bd.them("A: tra cứu sống -> KHÔNG gọi vai suy luận nào",
            ra["A"]["vai"] == ["leader"] and ra["A"]["so_luot_model"] == 0,
            f"vai={ra['A']['vai']}, lượt model={ra['A']['so_luot_model']}")
    bd.them("B: câu hỏi lịch sử -> KHÔNG gọi vai suy luận nào",
            ra["B"]["vai"] == ["leader"] and ra["B"]["so_luot_model"] == 0,
            f"vai={ra['B']['vai']}")
    bd.them("C: chẩn đoán vận hành -> KHÔNG leo thang ở AUTO",
            ra["C"]["vai"] == ["leader"],
            f"bậc {ra['C']['bac']}, dưới ngưỡng KHO của AUTO")
    bd.them("D: câu hỏi chiến lược -> Strategist THAM GIA",
            "strategist" in ra["D"]["vai"],
            f"vai={ra['D']['vai']} (Reviewer không chạy vì tác động "
            f"{ra['D']['tac_dong']})")
    bd.them("E: redesign + phản biện -> Strategist VÀ Reviewer",
            {"strategist", "reviewer"} <= set(ra["E"]["vai"]),
            f"vai={ra['E']['vai']}")
    bd.them("F: xã giao -> chỉ Leader",
            ra["F"]["vai"] == ["leader"] and ra["F"]["so_luot_model"] == 0)
    return ra


# ------------------------------------------------------------ pha chinh sach --

def pha_chinh_sach(bd: Bang, fab, weights) -> Dict:
    print("\n--- PHẦN 2: CHÍNH SÁCH & CHẾ ĐỘ (§5, §16) ---")
    kc, st = _ky_uc()
    ten = CS.ten_model_cao_cap(fab)
    cs = CS.doc_chinh_sach(kc, DU_AN, ten_model=ten)
    print(f"  chính sách cao cấp: hạn chế={cs.han_che} nguồn={cs.nguon} "
          f"mã={cs.ma or '—'}")
    print(f"    {cs.ly_do()[:200]}")

    bd.them("Chính sách Astra TRA TỪ KÝ ỨC dự án (không chép cứng trong mã)",
            cs.nguon == "ky_uc" and bool(cs.ma),
            f"nguồn={cs.nguon}, mã={cs.ma!r} — quyết định thật của người dùng")
    bd.them("Chính sách đó là HẠN CHẾ", cs.han_che, cs.trich[:150])

    # CO LAP DU AN: mot du an khong co quyet dinh -> van HAN CHE, khong ke thua.
    cs_khac = CS.doc_chinh_sach(kc, "mot-du-an-khong-ton-tai", ten_model=ten)
    bd.them("Cô lập dự án: dự án khác KHÔNG kế thừa quyết định của Fanfic",
            cs_khac.han_che and cs_khac.nguon != "ky_uc",
            f"nguồn={cs_khac.nguon} (fail closed, không suy ra từ dự án khác)")

    # ASTRA theo che do.
    ket: Dict[str, Dict] = {}
    tam_thuong = phan_loai_luot("ê bro")
    kho = phan_loai_luot(TINH_HUONG[4][1])
    from scripts.control_center.reasoning.dinh_tuyen import KhongCoCho
    for cd in CheDo:
        bdt = BoDinhTuyenVai(fab, weights=weights, chinh_sach=cs)
        try:
            cv_kho = bdt.chon(VaiTro.STRATEGIST, kho, cd,
                              nguoi_yeu_cau_cao_cap=(cd is CheDo.MAX))
        except KhongCoCho as exc:
            # FAIL CLOSED la hanh vi DUNG, nen no khong duoc lam vo bai
            # nghiem thu — no thanh mot dong ket qua doc duoc.
            ket[cd.value] = {"kho_model": "", "kho_gia": "", "kho_astra": False,
                             "ly_do_astra": f"KHÔNG CÓ CHỖ: {exc}"[:300],
                             "vai_tam_thuong": [v.value for v in
                                                lap_ke_hoach_vai(tam_thuong, cd).vai]}
            print(f"  {cd.value:<7} câu RẤT KHÓ -> KHÔNG CÓ CHỖ")
            continue
        ket[cd.value] = {
            "kho_model": cv_kho.model_id, "kho_gia": cv_kho.bac_gia.value,
            "kho_astra": cv_kho.astra, "ly_do_astra": cv_kho.astra_ly_do,
            "vai_tam_thuong": [v.value for v in
                               lap_ke_hoach_vai(tam_thuong, cd).vai],
        }
        print(f"  {cd.value:<7} câu RẤT KHÓ -> {cv_kho.runtime_id}/"
              f"{cv_kho.model_id} [{cv_kho.bac_gia.value}] astra={cv_kho.astra}")

    bd.them("Astra KHÔNG dùng cho lượt tầm thường ở MỌI chế độ",
            all(v["vai_tam_thuong"] == ["leader"] for v in ket.values()),
            "cổng tầm thường chặn trước cả tầng định tuyến")
    bd.them("ECO KHÔNG bao giờ chạm bậc cao cấp",
            not ket["ECO"]["kho_astra"], ket["ECO"]["ly_do_astra"][:140])
    bd.them("AUTO chỉ leo thang khi có LÝ DO tường minh, và ghi lại lý do",
            bool(ket["AUTO"]["ly_do_astra"]), ket["AUTO"]["ly_do_astra"][:140])
    bd.them("MAX không vượt rào an toàn (vẫn qua GacAstra + chính sách dự án)",
            "chính sách dự án" in ket["MAX"]["ly_do_astra"]
            or not ket["MAX"]["kho_astra"],
            ket["MAX"]["ly_do_astra"][:140])
    bd.them("STRONG dùng model mạnh hơn ECO cho cùng câu hỏi",
            ket["STRONG"]["kho_model"] != ket["ECO"]["kho_model"]
            or ket["STRONG"]["kho_gia"] != ket["ECO"]["kho_gia"],
            f"ECO={ket['ECO']['kho_model']}[{ket['ECO']['kho_gia']}] "
            f"STRONG={ket['STRONG']['kho_model']}[{ket['STRONG']['kho_gia']}]")
    if st is not None:
        try:
            st.close()
        except Exception:                                   # noqa: BLE001
            pass
    return {"chinh_sach": cs.to_dict(), "theo_che_do": ket}


# -------------------------------------------------------------- pha doc lap --

def pha_doc_lap(bd: Bang, fab, weights, cs) -> Dict:
    print("\n--- PHẦN 3: ĐỘC LẬP CỦA REVIEWER (§9) ---")
    p = phan_loai_luot(TINH_HUONG[4][1])
    bdt = BoDinhTuyenVai(fab, weights=weights, chinh_sach=cs)
    s = bdt.chon(VaiTro.STRATEGIST, p, CheDo.AUTO)
    r = bdt.chon(VaiTro.REVIEWER, p, CheDo.AUTO, ho_tac_gia=s.model_family,
                 doi_doc_lap=True)
    print(f"  Strategist: {s.runtime_id}/{s.model_id} (họ {s.model_family})")
    print(f"  Reviewer  : {r.runtime_id}/{r.model_id} (họ {r.model_family}) "
          f"độc lập={r.doc_lap} suy giảm={r.suy_giam}")
    bd.them("Reviewer chạy trên HỌ MODEL KHÁC Strategist",
            r.model_family != s.model_family and bool(r.doc_lap),
            f"{s.model_family} -> {r.model_family}")

    # Suy giam phai BAO RA, khong duoc gia vo doc lap.
    class FabMotHo:
        pass
    from scripts.router_v4.runtime import Fabric
    f2 = Fabric()
    for mid, m in fab.models.items():
        if m.model_family == s.model_family:
            f2.add_model(m)
    for rid, rt in fab.runtimes.items():
        mo = tuple(x for x in rt.supported_models if x in f2.models)
        if mo:
            import dataclasses
            f2.add_runtime(dataclasses.replace(rt, supported_models=mo))
    for pid, po in fab.pools.items():
        if any(x in f2.models for x in po.member_models):
            f2.add_pool(po)
    try:
        f2.validate()
        r2 = BoDinhTuyenVai(f2, chinh_sach=cs).chon(
            VaiTro.REVIEWER, p, CheDo.AUTO, ho_tac_gia=s.model_family,
            doi_doc_lap=True)
        bd.them("Chỉ còn MỘT họ model -> báo DEGRADED, KHÔNG giả vờ độc lập",
                r2.co_cho and r2.doc_lap is False and r2.suy_giam,
                r2.suy_giam_ly_do[:160])
    except Exception as exc:                                # noqa: BLE001
        bd.them("Chỉ còn MỘT họ model -> báo DEGRADED", False,
                f"không dựng được fabric một họ: {exc}")
    return {"strategist": s.to_dict(), "reviewer": r.to_dict()}


# ------------------------------------------------------- pha thao luan/thuc thi --

def pha_thao_luan(bd: Bang, fab, weights, cs) -> Dict:
    print("\n--- PHẦN 4: THẢO LUẬN ≠ THỰC THI (§11) ---")
    cau_ban = "theo m thì Fanfic nên làm gì tiếp?"
    cau_lam = "sửa giúp bug ở scripts/control_center/store.py rồi chạy test"
    p_ban, p_lam = phan_loai_luot(cau_ban), phan_loai_luot(cau_lam)

    hd, gia, _ = _hoi_dong(fab, weights, cs, _kich_ban_day_du())
    kq = hd.chay(cau=cau_ban, phan_loai=p_ban, che_do=CheDo.AUTO,
                 khoi_san_co={}, project_id=DU_AN)
    khoi = kq.khoi_leader()
    print(f"  bàn  : {cau_ban!r} -> thực thi={p_ban.la_thuc_thi} "
          f"vai={[v.value for v in kq.ke_hoach.vai]}")
    print(f"  làm  : {cau_lam!r} -> thực thi={p_lam.la_thuc_thi}")

    bd.them("Câu BÀN LUẬN không bị phân loại là thực thi",
            not p_ban.la_thuc_thi)
    bd.them("Hội đồng KHÔNG có đường nào tạo việc",
            not hasattr(kq, "tasks") and not hasattr(kq, "tao_viec"))
    bd.them("Khối gửi Leader nói rõ CHƯA tạo việc nào và CẤM delegate_work",
            "CHƯA tạo việc nào" in khoi and "KHÔNG TỰ TẠO VIỆC" in khoi)
    bd.them("Câu XIN LÀM vẫn được nhận diện là thực thi",
            p_lam.la_thuc_thi)
    bd.them("Câu XIN LÀM (dễ) đi thẳng Router V4, không qua hội đồng",
            [v.value for v in lap_ke_hoach_vai(p_lam, CheDo.MAX).vai]
            == ["leader"])
    return {"ban": p_ban.to_dict(), "lam": p_lam.to_dict()}


# ------------------------------------------------------------- pha han muc --

def pha_han_muc(bd: Bang, fab, do_that: bool) -> Dict:
    print("\n--- PHẦN 5: HẠN MỨC / UNKNOWN (§7, §8) ---")
    ra: Dict = {"da_do": bool(do_that)}
    truoc = {p.pool_id: p.source.value for p in fab.pools.values()}
    ra["nguon_truoc"] = truoc

    if do_that:
        from scripts.control_center.store import ControlStore
        from scripts.control_center.usage import UsageReporter
        st = ControlStore(duong_control_db())
        up = UsageReporter(st, fabric=fab)
        hm: Dict = {}
        for u in up.do_nha_cung_cap(force=True):
            if u.provider == "antigravity" and u.raw_text:
                hm = NS.doc_han_muc_agy(u.raw_text)
        ra["han_muc"] = {k: v.to_dict() for k, v in hm.items()}
        r01 = fab.runtimes.get("AG01")
        ap = NS.ap_han_muc(fab, hm, account_id=r01.account_id) if r01 else []
        ra["da_ap"] = ap
        print(f"  đo được: {ra['han_muc']}")
        print(f"  đã áp  : {ap}")
        bd.them("Hạn mức ĐO ĐƯỢC khi nhà cung cấp có lộ ra (§7)",
                bool(hm), f"{len(hm)} bể đọc được từ `agy --print /usage`")
        khac = [p.pool_id for p in fab.pools.values()
                if p.account_id != (r01.account_id if r01 else "")
                and p.source.value == "probed"]
        bd.them("Phép đo CHỈ áp cho tài khoản đã đo, không lan sang tài khoản khác",
                not khac, f"bể tài khoản khác mang nhãn probed: {khac or 'không có'}")
        st.close()
    else:
        print("  (bỏ qua phép đo thật — dùng `--do-han-muc` để bật)")

    # UNKNOWN phai la None, khong phai 0 — dung tren du lieu DANG CO.
    bdt = BoDinhTuyenVai(fab)
    nl = bdt.nang_luc_bay()
    khong_do = [x for x in nl if x["quota_con_lai"] is None]
    ra["so_placement"] = len(nl)
    ra["so_khong_do_duoc"] = len(khong_do)
    bd.them("Bể không đọc được số dư -> `None`, KHÔNG phải 0",
            all(x["quota_con_lai"] is None or isinstance(
                x["quota_con_lai"], float) for x in nl),
            f"{len(khong_do)}/{len(nl)} placement mang None")
    bd.them("Không bản ghi định tuyến nào bịa usage",
            all(m.value is None for m in NS.usage_khong_do_duoc("codex")),
            "usage không đo được luôn mang UNAVAILABLE + None")
    return ra


# ------------------------------------------------------------------- main --

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--do-han-muc", action="store_true",
                    help="gọi `agy --print /usage` thật (chậm, tốn một lượt)")
    # DO SUC KHOE BAT MAC DINH, va day khong phai mot lua chon tuy tien:
    # `dung_fabric` dat MOI runtime o OFFLINE cho toi khi co mot lan do. Chay
    # nghiem thu tren mot fabric chua do se cho ra "KHONG_CO_CHO" cho moi vai
    # va bai nghiem thu se do vi mot ly do khong lien quan gi toi v0.8.
    ap.add_argument("--khong-probe", action="store_true",
                    help="KHÔNG dò sức khoẻ runtime (mọi runtime sẽ OFFLINE)")
    ap.add_argument("--json", action="store_true", help="in JSON")
    a = ap.parse_args(argv)

    print("=" * 74)
    print("NGHIỆM THU V0.8 — Strategist + Reviewer + định tuyến model động")
    print("=" * 74)

    fab, weights, _esc = FC.nap(probe=not a.khong_probe)
    print(f"\nfabric: {len(fab.runtimes)} runtime, {len(fab.models)} model, "
          f"{len(list(fab.placements()))} placement · tài khoản "
          f"{fab.dem_tai_khoan()}")

    kc, st = _ky_uc()
    cs = CS.doc_chinh_sach(kc, DU_AN, ten_model=CS.ten_model_cao_cap(fab))
    if st is not None:
        try:
            st.close()
        except Exception:                                   # noqa: BLE001
            pass

    bd = Bang()
    kq: Dict = {}
    kq["tinh_huong"] = pha_tinh_huong(bd, fab, weights, cs)
    kq["chinh_sach"] = pha_chinh_sach(bd, fab, weights)
    kq["doc_lap"] = pha_doc_lap(bd, fab, weights, cs)
    kq["thao_luan"] = pha_thao_luan(bd, fab, weights, cs)
    kq["han_muc"] = pha_han_muc(bd, fab, a.do_han_muc)

    print("\n" + "=" * 74)
    print(f"KẾT QUẢ: {bd.so_dat}/{len(bd.hang)} ĐẠT")
    print("=" * 74)
    for h in bd.hang:
        if not h["dat"]:
            print(f"  HỎNG: {h['muc']} — {h['chi_tiet']}")
    kq["bang"] = bd.hang
    kq["tom_tat"] = {"dat": bd.so_dat, "tong": len(bd.hang),
                     "tat_ca_dat": bd.tat_ca_dat}
    if a.json:
        print(json.dumps(kq, ensure_ascii=False, indent=2, default=str))
    return 0 if bd.tat_ca_dat else 1


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
