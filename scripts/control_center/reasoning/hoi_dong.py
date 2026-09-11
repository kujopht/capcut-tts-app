"""HỘI ĐỒNG — chạy các vai suy luận rồi giao KẾT QUẢ cho Leader tổng hợp (V0.8).

Đây là chỗ bảy mảnh nối vào nhau, và thứ tự nối không tuỳ ý:

    phan_loai   -> lượt này khó/tác động tới đâu, và có phải thực thi không
    ke_hoach    -> vai nào chạy (cổng tầm thường chặn ở đây)
    chinh_sach  -> model cao cấp có được phép theo QUYẾT ĐỊNH của dự án
    dinh_tuyen  -> vai nào lên (runtime, model) nào, độc lập hay suy giảm
    ngu_canh    -> mỗi vai nhận gói CÓ TRẦN, có kê khai
    goi         -> chạy thật (hoặc `BoGoiGia` trong bài kiểm)
    hop_dong    -> đọc đầu ra theo lược đồ; FAIL CLOSED ở phán xử
    that_bai    -> hỏng thì phân loại và thử lại CÓ TRẦN

HAI TÍNH CHẤT PHẢI GIỮ, và cả hai đều là yêu cầu tường minh của v0.8:

**§11 — THẢO LUẬN KHÔNG PHẢI THỰC THI.** `KetQuaHoiDong` KHÔNG có đường nào
tạo việc. Nó trả về một khối văn bản cho nhắc nhở của Leader và một bản ghi
định tuyến. `viec_can_lam` của Strategist đi vào khối đó dưới nhãn "CHƯA tạo
việc nào", và `LUAT_HOI_DONG` nói thẳng với Leader rằng một đề xuất không
phải một yêu cầu của người dùng. Việc chỉ sinh ra khi `engine._chat` thấy
`delegate_work` — và Leader chỉ được trả `delegate_work` khi người dùng xin
làm.

**§9 — KHÔNG GIẢ VỜ ĐỘC LẬP.** Reviewer chạy cùng họ model với Strategist
thì `suy_giam=True`, khối gửi Leader mang một dòng `(!)` tường minh, và giao
diện hiện DEGRADED. Thà nói "lượt này không có phản biện độc lập" còn hơn
trình một bản tự đọc lại như một bản phản biện.

MẤT HỘI ĐỒNG KHÔNG ĐƯỢC LÀM MẤT CÂU TRẢ LỜI. Mọi đường hỏng ở đây đều kết
thúc bằng "Leader trả lời một mình, và biết là mình đang thiếu gì" — cùng
nguyên tắc `engine._leader_quyet_dinh` đã dựng cho V0.3: mất Leader thì mất
sự tiện, không được mất khả năng giao việc.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.control_center.reasoning import hop_dong as HD
from scripts.control_center.reasoning import ngu_canh as NC
from scripts.control_center.reasoning.chinh_sach import ChinhSachCaoCap
from scripts.control_center.reasoning.dinh_tuyen import (BoDinhTuyenVai,
                                                         ChonVai, KhongCoCho)
from scripts.control_center.reasoning.ngan_sach import (BanGhiDinhTuyen,
                                                        SoDinhTuyen)
from scripts.control_center.reasoning.phan_loai import (KeHoachVai, PhanLoai,
                                                        lap_ke_hoach_vai)
from scripts.control_center.reasoning.that_bai import (ChinhSachThuLai,
                                                       HanhDong, LoaiThatBai,
                                                       phan_loai_that_bai)
from scripts.control_center.reasoning.vai import VaiTro, ho_so
from scripts.router_v4.premium import CheDo


#: Luật đi kèm khối HỘI ĐỒNG trong nhắc nhở của Leader. Có mặt ở MỌI lượt có
#: khối — cùng lý do `leader.LUAT_KY_UC` phải đi kèm khối ký ức ở mọi lượt:
#: một khối trơn tru, cụ thể, KHÔNG có luật nào, sẽ được đọc như sự thật.
LUAT_HOI_DONG = """\
KẾT QUẢ HỘI ĐỒNG SUY LUẬN — đọc trước khi trả lời:

Lượt này Router đã gọi thêm vai suy luận sâu. Khối bên dưới là ĐẦU RA CỦA
CHÚNG, và bạn là người TỔNG HỢP.

* **Đề xuất của Strategist KHÔNG phải quyết định.** Nó là kiến nghị của một
  model. Thẩm quyền là của NGƯỜI DÙNG. Đừng viết "chúng ta đã quyết"; hãy
  viết "hướng tôi khuyên là…, vì…" và nêu thứ cần người dùng chốt.
* **KHÔNG TỰ TẠO VIỆC.** Mục "Việc sẽ cần" là danh sách việc SẼ CẦN NẾU người
  dùng đồng ý — lượt này chưa có việc nào được tạo, và bạn KHÔNG được trả
  `delegate_work` chỉ vì Strategist liệt kê ra việc. Chỉ uỷ thác khi chính
  người dùng xin làm. Hãy MỜI họ: "muốn tôi triển khai phần nào thì nói".
* **Phán xử của Reviewer phải hiện ra trong câu trả lời.** `REVISE` hay
  `REJECT` thì nói rõ Reviewer không đồng ý ở đâu — đừng chỉ trình bày đề
  xuất như thể nó đã qua kiểm. `ACCEPT` thì nói ngắn là đã được soi và không
  ai tìm thấy lỗ hổng.
* **Có dòng `(!) ĐỘ ĐỘC LẬP SUY GIẢM` thì phải nói ra.** Nghĩa là bản phản
  biện do CÙNG họ model với bản chiến lược viết — một lần tự đọc lại. Người
  dùng cần biết mức bảo đảm họ đang nhận.
* **Đừng dán lại nguyên khối.** Tổng hợp thành câu trả lời bằng ngôn ngữ của
  người dùng: hướng khuyên, vì sao, rủi ro, thứ cần họ chốt. Khối này là
  biên bản nội bộ, không phải câu trả lời."""


@dataclass
class NguonGocVai:
    """Nguồn gốc định tuyến của MỘT vai trong lượt này — thứ §12 hiển thị."""

    vai: VaiTro
    trang_thai: str = "CHUA_CHAY"        # OK | HONG | BO_QUA | KHONG_CO_CHO
    chon: Optional[ChonVai] = None
    ban_ghi: Optional[BanGhiDinhTuyen] = None
    ke_khai: Dict = field(default_factory=dict)
    loai_that_bai: str = ""
    ghi_chu: str = ""
    so_lan: int = 0

    def to_dict(self) -> Dict:
        return {"vai": self.vai.value, "trang_thai": self.trang_thai,
                "chon": self.chon.to_dict() if self.chon else None,
                "ban_ghi": self.ban_ghi.to_dict() if self.ban_ghi else None,
                "ngu_canh": dict(self.ke_khai),
                "loai_that_bai": self.loai_that_bai,
                "ghi_chu": self.ghi_chu, "so_lan": self.so_lan}


@dataclass
class KetQuaHoiDong:
    """Thứ `engine` nhận lại. KHÔNG có đường nào ở đây tạo việc (§11)."""

    phan_loai: PhanLoai
    ke_hoach: KeHoachVai
    chinh_sach: Optional[ChinhSachCaoCap] = None
    chien_luoc: Optional[HD.BanChienLuoc] = None
    phan_bien: Optional[HD.BanPhanBien] = None
    nguon_goc: List[NguonGocVai] = field(default_factory=list)
    so: SoDinhTuyen = field(default_factory=SoDinhTuyen)
    loi: List[str] = field(default_factory=list)
    giay: float = 0.0

    @property
    def da_chay(self) -> bool:
        """Có vai suy luận nào THẬT SỰ chạy và trả về thứ dùng được không."""
        return bool(self.chien_luoc or self.phan_bien)

    @property
    def suy_giam(self) -> bool:
        return self.so.suy_giam or bool(self.loi)

    def khoi_leader(self) -> str:
        """Khối cho nhắc nhở Leader, hoặc `""` khi không vai nào chạy.

        Rỗng là một câu trả lời hợp lệ và nó QUAN TRỌNG: một lượt tầm thường
        phải không thêm một token nào vào nhắc nhở của Leader, nếu không cái
        rẻ nhất trong hệ thống sẽ đắt lên theo mọi lượt.
        """
        if not self.da_chay and not self.loi:
            return ""
        d = [LUAT_HOI_DONG, ""]
        if self.chien_luoc is not None:
            d += [self.chien_luoc.to_khoi_leader(), ""]
        if self.phan_bien is not None:
            ng = next((n for n in self.nguon_goc if n.vai is VaiTro.REVIEWER),
                      None)
            dl = ng.chon.doc_lap if (ng and ng.chon) else None
            nguon = ""
            if ng and ng.chon and ng.chon.co_cho:
                nguon = f"{ng.chon.provider}/{ng.chon.model_id}"
            d += [self.phan_bien.to_khoi_leader(doc_lap=dl, nguon=nguon), ""]
        if self.loi:
            d += ["THIẾU SÓT CỦA HỘI ĐỒNG LƯỢT NÀY (nói ra nếu nó ảnh hưởng "
                  "mức bảo đảm bạn đưa cho người dùng):"]
            d += [f"  - {x}" for x in self.loi[:5]]
            d.append("")
        return "\n".join(d)

    def dong_nguon_goc(self) -> List[str]:
        """Bản in GỌN cho giao diện §12 — vai · model · lý do · trạng thái."""
        ra = [f"{self.ke_hoach.che_do.value}  "
              f"[{self.phan_loai.bac.value}/{self.phan_loai.tac_dong.value}]  "
              f"{self.ke_hoach.ly_do}"]
        for n in self.nguon_goc:
            if n.ban_ghi is not None:
                ra.append(n.ban_ghi.dong_gon())
            elif n.chon is not None and n.chon.co_cho:
                ra.append(f"{n.vai.nhan:<11} {n.chon.provider}/"
                          f"{n.chon.model_id}  {n.trang_thai}")
            else:
                ra.append(f"{n.vai.nhan:<11} —  {n.trang_thai}"
                          + (f" ({n.ghi_chu})" if n.ghi_chu else ""))
        if self.chinh_sach is not None:
            ra.append(f"Cao cấp     {'DÙNG' if self.so.dung_astra else 'không dùng'}"
                      f" — {self.chinh_sach.ly_do()[:120]}")
        return ra

    def to_dict(self) -> Dict:
        return {"phan_loai": self.phan_loai.to_dict(),
                "ke_hoach": self.ke_hoach.to_dict(),
                "chinh_sach": (self.chinh_sach.to_dict()
                               if self.chinh_sach else None),
                "chien_luoc": (self.chien_luoc.to_dict()
                               if self.chien_luoc else None),
                "phan_bien": (self.phan_bien.to_dict()
                              if self.phan_bien else None),
                "nguon_goc": [n.to_dict() for n in self.nguon_goc],
                "so": self.so.to_dict(), "loi": list(self.loi),
                "da_chay": self.da_chay, "suy_giam": self.suy_giam,
                "giay": round(self.giay, 2),
                "dong_nguon_goc": self.dong_nguon_goc()}


class HoiDong:
    """Chạy các vai suy luận cho MỘT lượt hội thoại."""

    def __init__(self, *, bo_dinh_tuyen: BoDinhTuyenVai, bo_goi,
                 ghi_su_kien: Optional[Callable[..., Any]] = None):
        self.bo_dinh_tuyen = bo_dinh_tuyen
        self.bo_goi = bo_goi
        self._ghi = ghi_su_kien

    def _sk(self, kind: str, **kw) -> None:
        if self._ghi is None:
            return
        try:
            self._ghi(kind, **kw)
        except Exception:                                   # noqa: BLE001
            pass

    # -- mot vai -------------------------------------------------------------

    def _chay_vai(self, vai: VaiTro, *, p: PhanLoai, che_do: CheDo,
                  khoi_san_co: Dict[str, str], nguon_khoi: Dict[str, str],
                  huong_dan: str, doc: Callable[[str], Any],
                  thu_lai: ChinhSachThuLai, so: SoDinhTuyen,
                  ho_tac_gia: str = "", doi_doc_lap: bool = False,
                  nguoi_yeu_cau_cao_cap: bool = False,
                  project_id: str = "",
                  chinh_sach: Optional[ChinhSachCaoCap] = None
                  ) -> Tuple[Optional[Any], NguonGocVai]:
        """Định tuyến + gọi + đọc MỘT vai, có thử lại trong trần.

        Trả `(bản đã đọc hoặc None, nguồn gốc)`. Không ném: một vai hỏng là
        một thiếu sót được ghi lại, không phải một lượt chat bị vỡ.
        """
        ng = NguonGocVai(vai=vai)
        h = ho_so(vai)
        model_manh_da_hong = False

        while True:
            con, vi_sao = thu_lai.con_cho_goi(vai)
            if not con:
                ng.trang_thai = "HONG" if ng.so_lan else "BO_QUA"
                ng.ghi_chu = vi_sao
                return None, ng

            try:
                chon = self.bo_dinh_tuyen.chon(
                    vai, p, che_do, ho_tac_gia=ho_tac_gia,
                    doi_doc_lap=doi_doc_lap,
                    nguoi_yeu_cau_cao_cap=nguoi_yeu_cau_cao_cap,
                    model_manh_da_hong=model_manh_da_hong,
                    loai_tru_placement=thu_lai.loai_tru(vai),
                    chinh_sach=chinh_sach)
            except KhongCoCho as exc:
                ng.trang_thai = "KHONG_CO_CHO"
                ng.ghi_chu = str(exc)[:400]
                self._sk("REASONING_NO_PLACEMENT", project_id=project_id,
                         level="WARNING",
                         detail=f"{vai.value}: {str(exc)[:300]}")
                return None, ng
            ng.chon = chon

            goi_kem = dict(khoi_san_co)
            goi = NC.dung_goi(vai, khoi_san_co=goi_kem, nguon=nguon_khoi,
                              huong_dan=huong_dan,
                              tran_token=h.tran_token_ngu_canh)
            ng.ke_khai = goi.ke_khai()

            ten_gui = ""
            try:
                m = self.bo_dinh_tuyen.fabric.models.get(chon.model_id)
                ten_gui = getattr(m, "ten_gui_nha_cung_cap", "") or ""
            except Exception:                               # noqa: BLE001
                ten_gui = ""

            thu_lai.ghi_goi(vai)
            ng.so_lan += 1
            lv = self.bo_goi.goi(chon, goi.render(), han_giay=h.han_giay,
                                 ten_gui_nha_cung_cap=ten_gui)

            ban = None
            loi_doc = ""
            if lv.ok:
                try:
                    ban = doc(lv.van_ban)
                except HD.HopDongLoi as exc:
                    loi_doc = str(exc)[:300]
                except Exception as exc:                    # noqa: BLE001
                    loi_doc = f"{type(exc).__name__}: {exc}"[:300]

            bg = so.them(BanGhiDinhTuyen(
                vai=vai, provider=chon.provider, runtime_id=chon.runtime_id,
                model_id=chon.model_id, model_family=chon.model_family,
                che_do=che_do, bac_gia=chon.bac_gia, bac_kho=p.bac,
                ly_do=chon.ly_do, thanh_cong=bool(ban is not None),
                giay=lv.giay or None, doc_lap=chon.doc_lap,
                suy_giam=chon.suy_giam, astra=chon.astra,
                astra_ly_do=chon.astra_ly_do,
                loai_that_bai=""))
            ng.ban_ghi = bg

            if ban is not None:
                ng.trang_thai = "OK"
                self._sk("REASONING_ROLE_OK", project_id=project_id,
                         detail=f"{vai.value} @ {chon.runtime_id}/{chon.model_id} "
                                f"({lv.giay:.1f}s)",
                         meta={"vai": vai.value, "placement": chon.runtime_id
                               + "/" + chon.model_id, "giay": lv.giay,
                               "doc_lap": chon.doc_lap,
                               "astra": chon.astra})
                return ban, ng

            loai, vi_sao_loai = phan_loai_that_bai(
                loi=lv.loi, van_ban=("" if lv.ok else lv.van_ban),
                ma_thoat=lv.ma_thoat, rong=lv.rong,
                doc_duoc=not bool(loi_doc))
            bg.loai_that_bai = loai.value
            ng.loai_that_bai = loai.value
            ng.ghi_chu = (loi_doc or lv.loi or vi_sao_loai)[:400]
            self._sk("REASONING_ROLE_FAIL", project_id=project_id,
                     level="WARNING",
                     detail=f"{vai.value} @ {chon.runtime_id}/{chon.model_id}: "
                            f"{loai.value} — {ng.ghi_chu[:200]}",
                     meta={"vai": vai.value, "loai": loai.value})

            hd, ly_hd = thu_lai.quyet_dinh(
                vai, loai, placement=f"{chon.runtime_id}/{chon.model_id}")
            if hd is HanhDong.DUNG:
                ng.trang_thai = "HONG"
                ng.ghi_chu = f"{ng.ghi_chu} | {ly_hd}"[:400]
                return None, ng
            if hd is HanhDong.DINH_TUYEN_LAI and loai is LoaiThatBai.RUNTIME:
                # Mot model manh vua hong that -> day la mot LY DO LEO THANG
                # hop le theo `premium.LyDoLeoThang.MODEL_MANH_DA_HONG`. No
                # KHONG tu dong mo cua Astra: bon rao o `_xet_astra` van
                # phai qua het.
                model_manh_da_hong = True
            # THU_LAI_CUNG_CHO: vong lap chay lai, `loai_tru` khong doi nen
            # bo lap lich chon lai dung cho do.

    # -- toan hoi dong -------------------------------------------------------

    def chay(self, *, cau: str, phan_loai: PhanLoai, che_do: CheDo,
             khoi_san_co: Dict[str, str],
             nguon_khoi: Optional[Dict[str, str]] = None,
             chinh_sach: Optional[ChinhSachCaoCap] = None,
             project_id: str = "",
             thu_lai: Optional[ChinhSachThuLai] = None) -> KetQuaHoiDong:
        """Chạy hội đồng cho một lượt. KHÔNG tạo việc, KHÔNG chạm kho (§11/§19).

        `khoi_san_co` là các khối ngữ cảnh engine đã dựng (viên nang, ký ức,
        trạng thái sống, bằng chứng vận hành, …). Hội đồng KHÔNG tự đi dựng
        chúng: engine đã dựng cho Leader rồi, và dựng lần thứ hai sẽ chạy lại
        ~6 lệnh `git` cùng một probe SSH cho cùng một lượt.
        """
        t0 = time.perf_counter()
        kh = lap_ke_hoach_vai(phan_loai, che_do)
        kq = KetQuaHoiDong(phan_loai=phan_loai, ke_hoach=kh,
                           chinh_sach=chinh_sach,
                           so=SoDinhTuyen(project_id=project_id, che_do=che_do))
        if not kh.co_strategist:
            # Khong vai nao chay. Ghi mot su kien de mot lan KHONG leo thang
            # cung giai thich duoc — im lang la cach mot tinh nang tot bien
            # thanh mot tinh nang khong ai tin.
            self._sk("REASONING_SKIPPED", project_id=project_id,
                     detail=f"{che_do.value}: {kh.ly_do[:200]}",
                     meta={"phan_loai": phan_loai.to_dict(),
                           "ke_hoach": kh.to_dict()})
            kq.giay = time.perf_counter() - t0
            return kq

        tl = thu_lai or ChinhSachThuLai()
        nguon_khoi = dict(nguon_khoi or {})
        khoi = dict(khoi_san_co or {})
        khoi.setdefault("yeu_cau_nguoi_dung", cau or "")

        # -- STRATEGIST --
        bcl, ng_s = self._chay_vai(
            VaiTro.STRATEGIST, p=phan_loai, che_do=che_do, khoi_san_co=khoi,
            nguon_khoi=nguon_khoi, huong_dan=HD.NHAC_STRATEGIST,
            doc=HD.doc_ban_chien_luoc, thu_lai=tl, so=kq.so,
            nguoi_yeu_cau_cao_cap=(che_do is CheDo.MAX),
            project_id=project_id, chinh_sach=chinh_sach)
        kq.nguon_goc.append(ng_s)
        kq.chien_luoc = bcl
        if bcl is None:
            kq.loi.append(
                f"vai STRATEGIST không chạy được ({ng_s.trang_thai}"
                + (f": {ng_s.loai_that_bai}" if ng_s.loai_that_bai else "")
                + f") — {ng_s.ghi_chu[:200]}")

        # -- REVIEWER --
        if kh.co_reviewer:
            if bcl is None:
                # KHONG goi Reviewer khi khong co gi de soi. Goi no de "co
                # cho day du" la tieu mot luot model cho mot lan doc mot
                # khoi rong.
                ng_r = NguonGocVai(vai=VaiTro.REVIEWER, trang_thai="BO_QUA",
                                   ghi_chu="không có bản chiến lược nào để soi")
                kq.nguon_goc.append(ng_r)
                kq.loi.append("vai REVIEWER bị bỏ qua: không có bản chiến "
                              "lược nào để phản biện")
            else:
                khoi_r = dict(khoi)
                khoi_r["ban_chien_luoc"] = bcl.to_khoi_leader()
                nguon_r = dict(nguon_khoi)
                nguon_r["ban_chien_luoc"] = (
                    f"vai STRATEGIST trên "
                    f"{ng_s.chon.provider}/{ng_s.chon.model_id}"
                    if ng_s.chon and ng_s.chon.co_cho else "vai STRATEGIST")
                ho = (ng_s.chon.model_family if ng_s.chon else "")
                bpb, ng_r = self._chay_vai(
                    VaiTro.REVIEWER, p=phan_loai, che_do=che_do,
                    khoi_san_co=khoi_r, nguon_khoi=nguon_r,
                    huong_dan=HD.NHAC_REVIEWER, doc=HD.doc_ban_phan_bien,
                    thu_lai=tl, so=kq.so, ho_tac_gia=ho, doi_doc_lap=True,
                    nguoi_yeu_cau_cao_cap=False, project_id=project_id,
                    chinh_sach=chinh_sach)
                kq.nguon_goc.append(ng_r)
                kq.phan_bien = bpb
                if bpb is None:
                    kq.loi.append(
                        f"vai REVIEWER không chạy được ({ng_r.trang_thai}"
                        + (f": {ng_r.loai_that_bai}" if ng_r.loai_that_bai else "")
                        + ") — lượt này KHÔNG có phản biện độc lập")
                elif ng_r.chon is not None and ng_r.chon.suy_giam:
                    kq.loi.append(
                        "ĐỘ ĐỘC LẬP SUY GIẢM: " + ng_r.chon.suy_giam_ly_do)

        kq.giay = time.perf_counter() - t0
        self._sk("REASONING_COUNCIL", project_id=project_id,
                 level="WARNING" if kq.suy_giam else "INFO",
                 detail=(f"{che_do.value} {phan_loai.bac.value}/"
                         f"{phan_loai.tac_dong.value}: "
                         + ", ".join(f"{n.vai.value}={n.trang_thai}"
                                     for n in kq.nguon_goc)
                         + f" ({kq.giay:.1f}s)"),
                 meta={"ket_qua": {k: v for k, v in kq.to_dict().items()
                                   if k in ("phan_loai", "ke_hoach", "so",
                                            "loi", "suy_giam")}})
        return kq
