# -*- coding: utf-8 -*-
"""KIỂM LIÊN TỤC (Continuity Audit) V0.7 — Router hiểu dự án này tới đâu?

Câu hỏi lớp này trả lời: *"Router có hiểu dự án này đủ để QUẢN nó chưa?"* — và
trả lời bằng số đo trên bằng chứng có thật, không bằng cảm giác.

LUẬT: **KHÔNG bao giờ báo điểm hoàn hảo cho tiện.** Một hạng mục không có bằng
chứng thì FAIL/PARTIAL và nói rõ thiếu gì. Một bảng điểm 100% giả làm người
dùng tin Router hiểu dự án trong khi nó không hiểu — đó là chế độ hỏng tệ nhất
mà cả V0.7 tồn tại để tránh.

Ba mức: `PASS` (có bằng chứng đủ) · `PARTIAL` (có, nhưng thiếu/chưa xác minh) ·
`FAIL` (không có). Kết luận: `YES` / `PARTIAL` / `NO`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center import vien_nang_du_an as VN

PASS, PARTIAL, FAIL = "PASS", "PARTIAL", "FAIL"

#: (khoá, nhãn, mục viên nang liên quan, BẮT BUỘC cho "sẵn sàng")
HANG_MUC: Tuple[Tuple[str, str, str, bool], ...] = (
    ("danh_tinh",     "Project identity",     "danh_tinh",          True),
    ("muc_tieu",      "Mission",              "muc_tieu",           True),
    ("kien_truc",     "Architecture",         "kien_truc",          True),
    ("production",    "Production topology",  "topo_production",    False),
    ("quyet_dinh",    "Critical decisions",   "quyet_dinh",         True),
    ("rang_buoc",     "Hard constraints",     "rang_buoc",          False),
    ("su_co",         "Known incidents",      "su_co",              False),
    ("issue_mo",      "Open issues",          "issue_mo",           False),
    ("roadmap",       "Roadmap",              "roadmap",            False),
    ("quan_sat",      "Live observability",   "tham_chieu_song",    True),
    ("lich_su",       "Historical coverage",  "lich_su_quan_trong", False),
    ("bang_chung",    "Evidence coverage",    "",                   True),
    ("tai_nguyen",    "Agent/provider avail", "tai_nguyen_agent",   True),
)

#: Ngưỡng phủ bằng chứng để hạng mục `bang_chung` đạt.
NGUONG_PHU = 0.75
#: Ngưỡng lịch sử: bao nhiêu dòng L0 thì coi là "có phủ lịch sử".
NGUONG_L0 = 200


@dataclass
class Hang:
    khoa: str
    nhan: str
    muc: str
    bat_buoc: bool
    ket_qua: str = FAIL
    ly_do: str = ""
    bang_chung: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"khoa": self.khoa, "nhan": self.nhan, "muc": self.muc,
                "bat_buoc": self.bat_buoc, "ket_qua": self.ket_qua,
                "ly_do": self.ly_do, "bang_chung": list(self.bang_chung)[:6]}


def _tu_muc(m: Optional[Dict]) -> Tuple[str, str, List[str]]:
    """Một mục viên nang -> (kết quả, lý do, bằng chứng)."""
    m = m or {}
    tt = m.get("trang_thai")
    bc = list(m.get("bang_chung") or [])
    if tt == VN.KHONG_RO:
        return FAIL, (m.get("ghi_chu") or "UNKNOWN — chưa có bằng chứng"), bc
    if tt == VN.CU:
        return PARTIAL, ("mục đã CŨ: " + (m.get("ghi_chu") or "")).strip(), bc
    gt = m.get("gia_tri")
    if isinstance(gt, (list, tuple)) and not gt:
        # Danh sach RONG co the la cau tra loi dung ("khong co issue nao").
        return PASS, (m.get("ghi_chu") or "rỗng — và đó là câu trả lời đúng"), bc
    if not bc:
        return PARTIAL, "có nội dung nhưng KHÔNG có bằng chứng lần về được", bc
    return PASS, f"{len(bc)} bằng chứng", bc


def kiem(cc, project_id: str, *, muc: Optional[Dict] = None) -> Dict:
    """Chạy kiểm liên tục. Không ném; nguồn hỏng thì hạng mục đó FAIL có lý do."""
    if muc is None:
        muc, _pb = VN.nap(cc, project_id)
    muc = muc or {}
    hangs: List[Hang] = []

    for khoa, nhan, mk, bb in HANG_MUC:
        h = Hang(khoa=khoa, nhan=nhan, muc=mk, bat_buoc=bb)
        if khoa == "bang_chung":
            co = [k for k in VN.KHOA_MUC
                  if (muc.get(k) or {}).get("trang_thai") in (VN.CO, VN.CU)]
            co_bc = [k for k in co if (muc.get(k) or {}).get("bang_chung")]
            phu = (len(co_bc) / len(VN.KHOA_MUC)) if VN.KHOA_MUC else 0.0
            h.ket_qua = (PASS if phu >= NGUONG_PHU
                         else (PARTIAL if phu >= 0.4 else FAIL))
            h.ly_do = (f"{len(co_bc)}/{len(VN.KHOA_MUC)} mục có bằng chứng "
                       f"({phu*100:.0f}%)")
        elif khoa == "lich_su":
            n = 0
            kc = getattr(cc, "ky_uc", None)
            if kc is not None:
                try:
                    n = int(((kc.thong_ke(project_id).get("dem") or {})
                             .get("su_kien")) or 0)
                except Exception:                           # noqa: BLE001
                    n = 0
            kq_m, ly_m, bc_m = _tu_muc(muc.get(mk))
            if n >= NGUONG_L0 and kq_m == PASS:
                h.ket_qua, h.ly_do = PASS, f"{n} dòng L0 + bối cảnh có bằng chứng"
            elif n >= NGUONG_L0:
                h.ket_qua, h.ly_do = PARTIAL, f"{n} dòng L0 nhưng {ly_m}"
            else:
                h.ket_qua, h.ly_do = FAIL, f"chỉ {n} dòng L0 (cần ≥ {NGUONG_L0})"
            h.bang_chung = bc_m
        elif khoa == "quan_sat":
            kq_m, ly_m, bc_m = _tu_muc(muc.get(mk))
            # CO cau hinh probe = PARTIAL, khong phai PASS: khai bao KHONG
            # dong nghia da do duoc. Chi khi co phep DO THAT gan day moi PASS.
            if kq_m == PASS:
                h.ket_qua, h.ly_do = PARTIAL, (
                    "đã khai provider quan sát; chưa xác minh bằng một phép đo "
                    "trong lần kiểm này")
                try:
                    ev = cc.store.su_kien(project_id=project_id, limit=200)
                    if any((e.get("kind") if isinstance(e, dict)
                            else getattr(e, "kind", "")) == "LIVE_PROBE"
                           for e in ev):
                        h.ket_qua = PASS
                        h.ly_do = "đã khai provider VÀ có phép đo sống trong sổ"
                except Exception:                           # noqa: BLE001
                    pass
            else:
                h.ket_qua, h.ly_do = kq_m, ly_m
            h.bang_chung = bc_m
        else:
            h.ket_qua, h.ly_do, h.bang_chung = _tu_muc(muc.get(mk))
        hangs.append(h)

    dat = sum(1 for h in hangs if h.ket_qua == PASS)
    mot_phan = sum(1 for h in hangs if h.ket_qua == PARTIAL)
    hong = [h for h in hangs if h.ket_qua == FAIL]
    bb_hong = [h for h in hangs if h.bat_buoc and h.ket_qua == FAIL]
    bb_mot_phan = [h for h in hangs if h.bat_buoc and h.ket_qua == PARTIAL]

    co = [k for k in VN.KHOA_MUC
          if (muc.get(k) or {}).get("trang_thai") in (VN.CO, VN.CU)]
    co_bc = [k for k in co if (muc.get(k) or {}).get("bang_chung")]
    phu = (len(co_bc) / len(VN.KHOA_MUC)) if VN.KHOA_MUC else 0.0

    if bb_hong:
        san_sang = "NO"
        vi_sao = ("thiếu hạng mục BẮT BUỘC: "
                  + ", ".join(h.nhan for h in bb_hong))
    elif hong or bb_mot_phan or mot_phan:
        san_sang = "PARTIAL"
        thieu = [h.nhan for h in hong] + [f"{h.nhan} (một phần)"
                                          for h in (bb_mot_phan + [
                                              x for x in hangs
                                              if x.ket_qua == PARTIAL
                                              and not x.bat_buoc])]
        vi_sao = "còn thiếu/chưa xác minh: " + ", ".join(dict.fromkeys(thieu))
    else:
        san_sang = "YES"
        vi_sao = "mọi hạng mục có bằng chứng đủ"

    return {"project_id": project_id, "hang": [h.to_dict() for h in hangs],
            "dat": dat, "mot_phan": mot_phan, "hong": len(hong),
            "tong": len(hangs),
            "phu_bang_chung": round(phu, 4),
            "phu_bang_chung_phan_tram": round(phu * 100),
            "san_sang": san_sang, "vi_sao": vi_sao,
            "so_muc_co": len(co), "so_muc": len(VN.KHOA_MUC)}


def bang_chu(kq: Dict) -> str:
    """Bảng CHỮ như mẫu Phần F — dùng cho CLI/nghiệm thu."""
    d = [f"{(kq.get('project_id') or '').upper()} — CONTINUITY AUDIT", ""]
    for h in kq.get("hang") or []:
        d.append(f"  {h['nhan']:<24} {h['ket_qua']:<8} {h['ly_do'][:70]}")
    d.append("")
    d.append(f"  Evidence coverage        {kq.get('phu_bang_chung_phan_tram')}%"
             f"  ({kq.get('so_muc_co')}/{kq.get('so_muc')} mục có nội dung)")
    d.append("")
    d.append(f"  READY FOR PRIMARY WORKSPACE: {kq.get('san_sang')}")
    if kq.get("vi_sao"):
        d.append(f"  ({kq['vi_sao']})")
    return "\n".join(d)
