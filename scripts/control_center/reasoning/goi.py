"""GỌI MỘT VAI trên placement đã chọn — V0.8.

Tách khỏi `dinh_tuyen.py` có chủ đích: **quyết định** phải kiểm được tất định
mà không cần một tiến trình model nào, còn **thực thi** thì không. Cùng ranh
giới `Scheduler` / `Executor` của Router V4, và nhờ nó toàn bộ bài kiểm định
tuyến v0.8 chạy với `BoGoiGia`.

BA ĐƯỜNG THẬT, và mỗi đường đã có sẵn trong kho — không viết lại cái nào:

    antigravity  một tiến trình `agy` ẤM, KHÔNG worktree, KHÔNG quyền ghi.
                 Cùng khuôn `leader.PhienLeader` (nó chính là tệp nguồn cho
                 `PhienVai` ở đây), vì lý do khởi động nguội cũng như nhau:
                 đo được ~8s cho một lần mở lạnh, và một vai suy luận có thể
                 được gọi hai lượt liền nhau.
    codex        `codex exec -m <model đã ghim>` một lượt, qua `find_codex()`.
                 GHIM MODEL LÀ BẮT BUỘC — thiếu `-m` thì CLI chạy model mặc
                 định của chính nó, và mặc định đó đổi được ở phía nhà cung
                 cấp sau một lần `codex update` (đo 2026-09-09: mặc định trên
                 máy này là `gpt-5.6-sol`, cùng bản CLI phơi ra `gpt-6-astra`).
    provider ngoài  `providers.dich_vu.hoi_thu` — OpenAI-compatible, credential
                 ở Windows Credential Manager, giá trị KHÔNG BAO GIỜ vào
                 SQLite/ký ức/log/nhắc nhở.

KHÔNG NỚI QUYỀN, KHÔNG NGOẠI LỆ. `allow_edits=False`,
`dangerously_skip_permissions=False`, không thư mục phụ, không workspace. Một
vai suy luận không có việc gì phải chạm tệp — và `agy --print` sẽ tự chối
công cụ đó rồi trả về rỗng, nên nới quyền cũng không mua được gì ngoài rủi ro.

RÀO NÀY LÀ MỘT BÀI KIỂM, KHÔNG PHẢI MỘT LỜI HỨA:
`test_control_center_core.TestRaoAnToanTinh` đọc AST của MỌI tệp trong gói
`control_center` và bắt lỗi nếu tên cờ bỏ-qua-quyền xuất hiện như một chuỗi
trong mã CHẠY. Tệp này nằm trong phạm vi quét đó — nên nó cố ý KHÔNG khai một
hằng số liệt kê các cờ ấy: chính hằng số đó sẽ làm bài kiểm đỏ (đã xảy ra
thật khi viết tệp này, và đó là bằng chứng rào còn sống).
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Protocol, Tuple

from scripts.control_center.reasoning.dinh_tuyen import ChonVai
from scripts.control_center.reasoning.vai import VaiTro

@dataclass
class LuotVai:
    """Một lượt gọi vai. Thuần dữ liệu — `hoi_dong.py` phân loại hỏng từ nó."""

    ok: bool = False
    van_ban: str = ""
    loi: str = ""
    giay: float = 0.0
    ma_thoat: Optional[int] = None
    #: `True` khi tiến trình chạy nhưng không nói gì. Đây là tín hiệu RIÊNG:
    #: xem `that_bai.phan_loai_that_bai` — rỗng là RUNTIME, không phải VIEC.
    rong: bool = False
    provider: str = ""
    model_id: str = ""

    def to_dict(self) -> Dict:
        return {"ok": self.ok, "giay": round(self.giay, 2),
                "ma_thoat": self.ma_thoat, "rong": self.rong,
                "loi": self.loi[:400], "provider": self.provider,
                "model_id": self.model_id, "byte": len(self.van_ban)}


class BoGoi(Protocol):
    """Hợp đồng gọi một vai. Hai hiện thực: `BoGoiThat` và `BoGoiGia`."""

    def goi(self, chon: ChonVai, nhac_nho: str, *,
            han_giay: float) -> LuotVai: ...

    def dong(self) -> None: ...


# ------------------------------------------------------------------ phien vai --

class PhienVai:
    """Một tiến trình `agy` ẤM cho MỘT (runtime, model), dùng cho vai suy luận.

    Vì sao không dùng lại `leader.PhienLeader`: nó ghim `model=MODEL_LEADER`
    làm mặc định, ghim `runtime_id="AG01"`, và nó chặn MỌI model bậc cao cấp
    ở hàm khởi tạo — đúng cho Leader (nó chạy ở mọi tin nhắn, kể cả câu
    chào), nhưng sai cho Strategist, nơi bậc cao cấp là một khả năng hợp lệ
    ĐÃ đi qua bốn rào ở `dinh_tuyen._xet_astra`.

    Rào giữ nguyên ở đây: không quyền ghi, không worktree, không cờ nới quyền.
    """

    def __init__(self, *, model: str, runtime_id: str,
                 turn_timeout: float = 300.0):
        self.model = model
        self.runtime_id = runtime_id
        self.turn_timeout = turn_timeout
        self.start_error = ""
        self._w = None
        self._khoa = threading.RLock()

    @property
    def song(self) -> bool:
        from scripts.router_v3.warm_pool import WarmState
        return self._w is not None and self._w.state is not WarmState.FAILED

    def mo(self) -> bool:
        with self._khoa:
            return True if self.song else self._mo_that()

    def _mo_that(self) -> bool:
        import os

        from scripts.router_v3.warm_pool import RecyclePolicy, WarmAgyWorker
        from scripts.router_v4.antigravity_launcher import (
            KhoaLauncher, SESSIONS_DIR, acc_cua, profile_ton_tai, switch)

        self.start_error = ""
        acc = acc_cua(self.runtime_id) or self.runtime_id
        if not profile_ton_tai(acc):
            self.start_error = f"chưa lưu profile {acc}"
            return False
        sess = SESSIONS_DIR / acc
        try:
            sess.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.start_error = f"không dựng được thư mục phiên: {exc}"
            return False
        env = dict(os.environ)
        env["USERPROFILE"] = str(sess)
        env["HOME"] = str(sess)
        try:
            with KhoaLauncher():
                ok, ct = switch(acc)
                if not ok:
                    self.start_error = f"switch {acc} hỏng: {ct}"
                    return False
                w = WarmAgyWorker(
                    f"VAI-{self.runtime_id}-{self.model}", model=self.model,
                    workspace=None, cwd=str(sess), allow_edits=False,
                    dangerously_skip_permissions=False,
                    policy=RecyclePolicy(), turn_timeout=self.turn_timeout,
                    env=env)
                if not w.start():
                    self.start_error = (getattr(w, "start_error", "")
                                        or "agy không khởi động được")
                    try:
                        w.close()
                    except Exception:                       # noqa: BLE001
                        pass
                    return False
                self._w = w
        except TimeoutError:
            self.start_error = "quá hạn chờ khoá launcher"
            return False
        return True

    def hoi(self, nhac_nho: str) -> LuotVai:
        """Một lượt. KHÔNG ném — trả `LuotVai` để bên gọi phân loại hỏng."""
        t0 = time.perf_counter()
        with self._khoa:
            if not self.song and not self.mo():
                return LuotVai(ok=False, loi=self.start_error
                               or "không mở được phiên vai",
                               giay=round(time.perf_counter() - t0, 2),
                               model_id=self.model, provider="antigravity")
            t = self._w.send(nhac_nho, family=self.runtime_id)
            giay = round(time.perf_counter() - t0, 2)
            van = (t.response or "").strip()
            if not t.ok or not van:
                duoi = (getattr(self._w, "stderr_tail", "") or "").strip()
                return LuotVai(
                    ok=False, van_ban=van,
                    loi=(t.error or "").strip() or (duoi[-300:] if duoi else ""),
                    giay=giay, rong=not van, model_id=self.model,
                    provider="antigravity")
            return LuotVai(ok=True, van_ban=van, giay=giay,
                           model_id=self.model, provider="antigravity")

    def dong(self) -> None:
        with self._khoa:
            if self._w is not None:
                try:
                    self._w.close()
                except Exception:                           # noqa: BLE001
                    pass
                self._w = None


# ------------------------------------------------------------------ bo goi --

class BoGoiThat:
    """Gọi vai thật, dispatch theo `provider` của placement.

    Giữ các phiên ấm theo `(runtime, model)`: hai lượt Strategist liền nhau
    không phải trả lại 8 giây khởi động nguội. `dong()` đóng tất cả và nó
    được gọi từ `ControlCenter.shutdown()`.
    """

    def __init__(self, *, providers=None, tim_codex: Optional[Callable] = None):
        #: `providers.dich_vu.DichVuProvider` cho nhà cung cấp NGOÀI. `None`
        #: = chưa bật; đường đó trả lỗi rõ thay vì im lặng bỏ vai.
        self.providers = providers
        self._tim_codex = tim_codex
        self._phien: Dict[str, PhienVai] = {}
        self._khoa = threading.RLock()

    # -- antigravity --------------------------------------------------------

    def _phien_ag(self, chon: ChonVai, han_giay: float) -> PhienVai:
        khoa = f"{chon.runtime_id}/{chon.model_id}"
        with self._khoa:
            ph = self._phien.get(khoa)
            if ph is None:
                ph = PhienVai(model=chon.model_id, runtime_id=chon.runtime_id,
                              turn_timeout=han_giay)
                self._phien[khoa] = ph
            return ph

    # -- codex --------------------------------------------------------------

    def _goi_codex(self, chon: ChonVai, nhac_nho: str, *,
                   han_giay: float, ten_gui: str) -> LuotVai:
        from scripts.router_v3.pool.adapters import find_codex
        from scripts.router_v3.policy import la_hinh_dang_bao_mat
        from scripts.router_v3.tien_trinh import an_cua_so

        t0 = time.perf_counter()
        # HINH DANG BAO MAT -> KHONG goi Codex. Bang chung 2026-08-28: Codex
        # tra ket qua RONG kem "flagged for possible cybersecurity risk".
        # Chan o day (som) thay vi de no chay roi hong: mot lan hong that van
        # tieu mot luot va vai chuc giay.
        if la_hinh_dang_bao_mat(nhac_nho):
            return LuotVai(
                ok=False, loi="codex_security_shaped_refusal",
                giay=round(time.perf_counter() - t0, 2),
                provider="codex", model_id=chon.model_id)
        if not ten_gui:
            return LuotVai(
                ok=False, loi="no_model_pinned",
                giay=round(time.perf_counter() - t0, 2),
                provider="codex", model_id=chon.model_id)
        exe = (self._tim_codex or find_codex)()
        if not exe:
            return LuotVai(ok=False, loi="worker_unavailable: không tìm thấy codex",
                           giay=round(time.perf_counter() - t0, 2),
                           provider="codex", model_id=chon.model_id)
        argv = [exe, "exec", "--skip-git-repo-check", "-m", ten_gui,
                "--color", "never", "-"]
        try:
            p = subprocess.run(argv, input=nhac_nho, capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=han_giay, **an_cua_so())
        except subprocess.TimeoutExpired:
            return LuotVai(ok=False, loi=f"timeout sau {han_giay}s",
                           giay=round(time.perf_counter() - t0, 2),
                           provider="codex", model_id=chon.model_id)
        except OSError as exc:
            return LuotVai(ok=False, loi=f"spawn_failed: {exc}"[:300],
                           giay=round(time.perf_counter() - t0, 2),
                           provider="codex", model_id=chon.model_id)
        giay = round(time.perf_counter() - t0, 2)
        van = (p.stdout or "").strip()
        if p.returncode != 0 and not van:
            return LuotVai(ok=False, loi=f"exit_{p.returncode}: "
                           + (p.stderr or "")[-300:], giay=giay,
                           ma_thoat=p.returncode, rong=True,
                           provider="codex", model_id=chon.model_id)
        if not van:
            return LuotVai(ok=False, loi=(p.stderr or "")[-300:], giay=giay,
                           ma_thoat=p.returncode, rong=True,
                           provider="codex", model_id=chon.model_id)
        return LuotVai(ok=True, van_ban=van, giay=giay,
                       ma_thoat=p.returncode, provider="codex",
                       model_id=chon.model_id)

    # -- provider ngoai -----------------------------------------------------

    def _goi_ngoai(self, chon: ChonVai, nhac_nho: str, *,
                   han_giay: float) -> LuotVai:
        t0 = time.perf_counter()
        if self.providers is None:
            return LuotVai(
                ok=False,
                loi=(f"provider {chon.provider!r} cần dịch vụ provider ngoài, "
                     f"nhưng nó chưa bật trong phiên này"),
                giay=round(time.perf_counter() - t0, 2),
                provider=chon.provider, model_id=chon.model_id)
        try:
            kq = self.providers.hoi_vai(
                provider_id=chon.provider, model=chon.model_id,
                cau=nhac_nho, han_giay=han_giay)
        except AttributeError:
            return LuotVai(
                ok=False,
                loi=(f"dịch vụ provider không có đường gọi vai "
                     f"(`hoi_vai`) — provider {chon.provider!r} chưa dùng "
                     f"được cho vai suy luận"),
                giay=round(time.perf_counter() - t0, 2),
                provider=chon.provider, model_id=chon.model_id)
        except Exception as exc:                            # noqa: BLE001
            return LuotVai(ok=False, loi=f"{type(exc).__name__}: {exc}"[:300],
                           giay=round(time.perf_counter() - t0, 2),
                           provider=chon.provider, model_id=chon.model_id)
        van = str((kq or {}).get("van_ban") or "").strip()
        giay = round(time.perf_counter() - t0, 2)
        if not van:
            return LuotVai(ok=False, loi=str((kq or {}).get("loi") or ""),
                           giay=giay, rong=True, provider=chon.provider,
                           model_id=chon.model_id)
        return LuotVai(ok=True, van_ban=van, giay=giay,
                       provider=chon.provider, model_id=chon.model_id)

    # -- cong vao -----------------------------------------------------------

    def goi(self, chon: ChonVai, nhac_nho: str, *,
            han_giay: float, ten_gui_nha_cung_cap: str = "") -> LuotVai:
        if not chon.co_cho:
            return LuotVai(ok=False, loi="placement rỗng — không gọi được",
                           provider=chon.provider, model_id=chon.model_id)
        pv = (chon.provider or "").lower()
        if pv == "antigravity":
            return self._phien_ag(chon, han_giay).hoi(nhac_nho)
        if pv == "codex":
            return self._goi_codex(chon, nhac_nho, han_giay=han_giay,
                                   ten_gui=ten_gui_nha_cung_cap)
        if pv == "claude":
            # CLAUDE_LEAD la phien dieu phoi, `dispatchable=False`. Bo lap
            # lich da loai no; dong nay la lop thu hai, va no noi ro VI SAO
            # thay vi tra mot loi chung.
            return LuotVai(
                ok=False,
                loi=("runtime Claude là phiên điều phối, không nhận dispatch "
                     "— không gọi vai qua nó"),
                provider=pv, model_id=chon.model_id)
        return self._goi_ngoai(chon, nhac_nho, han_giay=han_giay)

    def dong(self) -> None:
        with self._khoa:
            for ph in list(self._phien.values()):
                ph.dong()
            self._phien.clear()


@dataclass
class BoGoiGia:
    """Bộ gọi GIẢ cho bài kiểm và cho nghiệm thu tất định.

    `kich_ban` là `{vai: [LuotVai, …]}` — mỗi lần gọi lấy phần tử kế tiếp.
    Hết kịch bản thì trả một lượt HỎNG có lý do rõ, KHÔNG lặp lại phần tử
    cuối: lặp lại sẽ làm một bài kiểm về trần thử lại vẫn "xanh" khi trần đã
    vỡ.
    """

    kich_ban: Dict[VaiTro, List[LuotVai]] = field(default_factory=dict)
    da_goi: List[Tuple[VaiTro, str, str]] = field(default_factory=list)
    nhac_nho_da_nhan: Dict[VaiTro, List[str]] = field(default_factory=dict)

    def goi(self, chon: ChonVai, nhac_nho: str, *, han_giay: float = 0.0,
            ten_gui_nha_cung_cap: str = "") -> LuotVai:
        self.da_goi.append((chon.vai, chon.runtime_id, chon.model_id))
        self.nhac_nho_da_nhan.setdefault(chon.vai, []).append(nhac_nho)
        con = self.kich_ban.get(chon.vai) or []
        if not con:
            return LuotVai(ok=False,
                           loi=f"BoGoiGia: hết kịch bản cho vai {chon.vai.value}",
                           provider=chon.provider, model_id=chon.model_id)
        lv = con.pop(0)
        lv.provider = lv.provider or chon.provider
        lv.model_id = lv.model_id or chon.model_id
        return lv

    def dong(self) -> None:
        return None
