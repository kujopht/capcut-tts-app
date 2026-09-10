"""MẶT TIỀN provider ngoài — cái webapi/engine gọi; cái agent và giao diện thấy.

Quy tắc của mặt tiền này (Part D2 — "agent nhận khả năng, không nhận credential"):

  * Đầu vào duy nhất mang giá trị credential là `them_tai_khoan(..., gia_tri)`.
    Giá trị đi thẳng vào `KhoBiMat`, hàm trả `TaiKhoan.to_dict()` (chỉ có
    `credential_ref`), và biến cục bộ bị xoá trước khi hàm trả.
  * Mọi đầu ra là dict đã sạch; sự kiện ghi vào sổ Control Center chỉ mang
    alias/ref/mã HTTP — và đi qua bộ lọc bí mật một lần nữa cho chắc.
  * `dang_ky_vao_fabric` đưa provider ngoài vào sổ định tuyến ở trạng thái
    `dispatchable=False`: `Scheduler.explain` thấy nó, giải thích được vì sao
    không chọn, nhưng KHÔNG một đường tự động nào giao việc cho một API trả
    tiền mà người vận hành chưa bật. Bật AUTO là "bước tiếp theo", có chủ ý.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from scripts.control_center.memory.bi_mat import loc as _loc
from scripts.control_center.providers.adapter import (AdapterOpenAICompat, HttpClient,
                                                      KetQuaThu)
from scripts.control_center.providers.be import BeTaiKhoan
from scripts.control_center.providers.kho_bi_mat import (KhoBiMat, KhoBiMatKhongSan,
                                                         KhongCoBiMat, kiem_gia_tri,
                                                         mo_kho_bi_mat, sinh_ref)
from scripts.control_center.providers.preset import (NANG_LUC_KHAI_BAO, danh_sach,
                                                     preset)
from scripts.control_center.providers.so import (ModelNgoai, Provider, SoProvider,
                                                 TaiKhoan)

#: Chinh sach dinh tuyen V0.6.1 cho provider ngoai — KHONG cau hinh duoc o UI.
AUTO_ROUTING = False
LY_DO_AUTO = ("Provider ngoài được đăng ký vào fabric ở trạng thái KHÔNG nhận dispatch: "
              "bộ lập lịch thấy và giải thích được, nhưng không tự giao việc cho một API "
              "trả tiền. Định tuyến thủ công qua 'Hỏi thử'. Bật AUTO là bước tiếp theo, "
              "cần adapter thực thi + ngân sách chi tiêu tường minh.")


class LoiDichVuProvider(ValueError):
    pass


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:40] or "x"


def _kiem_base_url(u: str) -> str:
    u = (u or "").strip().rstrip("/")
    if not u:
        raise LoiDichVuProvider("thiếu base_url")
    p = urlsplit(u)
    if p.username or p.password:
        raise LoiDichVuProvider("base_url không được chứa user:pass@")
    if p.query or p.fragment:
        raise LoiDichVuProvider("base_url không được có ?query hay #fragment")
    host = (p.hostname or "").lower()
    if p.scheme == "https" and host:
        return u
    if p.scheme == "http" and host in ("127.0.0.1", "localhost", "::1"):
        return u                       # chi cho kiem thu/cuc bo
    raise LoiDichVuProvider("base_url phải là https:// (http chỉ cho 127.0.0.1/localhost)")


class DichVuProvider:
    def __init__(self, store, root: Path, *, kho_bi_mat: Optional[KhoBiMat] = None,
                 http: Optional[HttpClient] = None, so: Optional[SoProvider] = None,
                 sau_khi_doi=None):
        self.store = store
        self.root = Path(root)
        self.kho = kho_bi_mat or mo_kho_bi_mat()
        self.so = so or SoProvider(root=self.root)
        self.http = http
        #: Goi SAU moi thay doi so (them/xoa/bat-tat/thu ket noi) — engine dung
        #: no de dong bo fabric DANG SONG. Nghiem thu EXE bat loi that: fabric
        #: dung truoc (Leader mo phien), provider them sau -> runtime EXT_* chi
        #: xuat hien sau khi khoi dong lai.
        self.sau_khi_doi = sau_khi_doi
        self._khoa = threading.RLock()

    def _da_doi(self) -> None:
        if self.sau_khi_doi is None:
            return
        try:
            self.sau_khi_doi()
        except Exception:                                   # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self.so.close()
        except Exception:                                   # noqa: BLE001
            pass

    # -- su kien (da loc) -------------------------------------------------------

    def _su_kien(self, kind: str, detail: str, *, project_id: str = "",
                 level: str = "INFO", meta: Optional[Dict] = None) -> None:
        if self.store is None:
            return
        try:
            self.store.ghi_su_kien(kind, project_id=project_id, level=level,
                                   detail=_loc(detail)[0][:400],
                                   meta={k: (_loc(v)[0] if isinstance(v, str) else v)
                                         for k, v in (meta or {}).items()})
        except Exception:                                   # noqa: BLE001
            pass

    # -- doc -----------------------------------------------------------------------

    def trang_thai(self) -> Dict[str, Any]:
        pvs = self.so.providers()
        return {
            "kho_bi_mat": self.kho.mo_ta(),
            "presets": danh_sach(),
            "providers": [p.to_dict() for p in pvs],
            "tai_khoan": [t.to_dict() for t in self.so.tai_khoan_tat_ca()],
            "models": {p.provider_id: [m.to_dict() for m in self.so.models_cua(p.provider_id)]
                       for p in pvs},
            "be": {p.provider_id: BeTaiKhoan(self.so, p.provider_id).tom_tat() for p in pvs},
            "chinh_sach": {"auto_routing": AUTO_ROUTING, "ly_do": LY_DO_AUTO},
        }

    # -- provider ------------------------------------------------------------------

    def them_provider(self, provider_id: str, preset_ma: str, *, base_url: str = "",
                      ten: str = "") -> Dict:
        pr = preset(preset_ma)
        base = _kiem_base_url(base_url or pr.base_url_mac_dinh)
        with self._khoa:
            p = self.so.luu_provider(Provider(provider_id=provider_id, preset=pr.ma,
                                              ten=(ten or pr.ten)[:80], base_url=base))
            for m in pr.models_goi_y:
                if not any(x.model_id == m for x in self.so.models_cua(p.provider_id)):
                    self.so.luu_model(ModelNgoai(provider_id=p.provider_id, model_id=m,
                                                 nang_luc=NANG_LUC_KHAI_BAO, nguon="preset"))
        self._su_kien("PROVIDER_ADDED", f"provider {p.provider_id} (preset {pr.ma}) → {base}")
        self._da_doi()
        return p.to_dict()

    def xoa_provider(self, provider_id: str, *, xac_nhan: bool = False) -> Dict:
        if not xac_nhan:
            raise LoiDichVuProvider("xoá provider là thao tác phá huỷ — cần xac_nhan=true")
        with self._khoa:
            refs = self.so.xoa_provider(provider_id)
            da_xoa = sum(1 for r in refs if self.kho.xoa(r))
        self._su_kien("PROVIDER_REMOVED", f"provider {provider_id}: xoá {len(refs)} tài khoản, "
                                          f"{da_xoa} credential khỏi kho", level="WARNING")
        self._da_doi()
        return {"provider_id": provider_id, "tai_khoan_da_xoa": len(refs),
                "credential_da_xoa": da_xoa}

    # -- tai khoan -------------------------------------------------------------------

    def them_tai_khoan(self, provider_id: str, alias: str, gia_tri, *,
                       project_id: str = "") -> Dict:
        p = self.so.provider(provider_id)
        if p is None:
            raise LoiDichVuProvider(f"không có provider {provider_id!r}")
        ok_kho, ct = self.kho.san()
        if not ok_kho:
            raise KhoBiMatKhongSan(f"không có kho bí mật an toàn: {ct}")
        v = kiem_gia_tri(gia_tri)
        del gia_tri
        ref = sinh_ref(provider_id, alias)
        with self._khoa:
            self.kho.luu(ref, v)
            del v
            t = TaiKhoan(account_id=f"{provider_id}:{_slug(alias)}", provider_id=provider_id,
                         alias=alias, credential_ref=ref)
            try:
                self.so.luu_tai_khoan(t)
            except Exception:
                self.kho.xoa(ref)
                raise
        self._su_kien("PROVIDER_ACCOUNT_ADDED",
                      f"{provider_id}/{alias}: credential_ref {ref} (giá trị nằm ở kho "
                      f"{self.kho.kieu}, không ở sổ)", project_id=project_id,
                      meta={"provider_id": provider_id, "alias": alias, "credential_ref": ref})
        self._da_doi()
        return t.to_dict()

    def xoa_tai_khoan(self, account_id: str, *, xac_nhan: bool = False) -> Dict:
        if not xac_nhan:
            raise LoiDichVuProvider("xoá tài khoản là thao tác phá huỷ — cần xac_nhan=true")
        with self._khoa:
            ref = self.so.xoa_tai_khoan(account_id)
            da_xoa = bool(ref and self.kho.xoa(ref))
        if ref is None:
            raise LoiDichVuProvider(f"không có tài khoản {account_id!r}")
        self._su_kien("PROVIDER_ACCOUNT_REMOVED", f"{account_id}: credential_ref {ref} "
                                                  f"{'đã' if da_xoa else 'không'} xoá khỏi kho",
                      level="WARNING")
        self._da_doi()
        return {"account_id": account_id, "credential_ref": ref, "credential_da_xoa": da_xoa}

    def bat_tat_tai_khoan(self, account_id: str, bat: bool) -> Dict:
        t = self.so.cap_nhat_tai_khoan(account_id, bat=bool(bat))
        if t is None:
            raise LoiDichVuProvider(f"không có tài khoản {account_id!r}")
        self._su_kien("PROVIDER_ACCOUNT_TOGGLED", f"{account_id}: {'bật' if bat else 'tắt'}")
        self._da_doi()
        return t.to_dict()

    # -- thu ket noi / hoi thu ---------------------------------------------------------

    def _adapter(self, t: TaiKhoan):
        p = self.so.provider(t.provider_id)
        if p is None:
            raise LoiDichVuProvider(f"tài khoản {t.account_id} trỏ provider không còn")
        return AdapterOpenAICompat(p, preset(p.preset), http=self.http), p

    def thu_ket_noi(self, account_id: str, *, project_id: str = "",
                    timeout: float = 15.0) -> Dict:
        t = self.so.tai_khoan(account_id)
        if t is None:
            raise LoiDichVuProvider(f"không có tài khoản {account_id!r}")
        ad, p = self._adapter(t)
        be = BeTaiKhoan(self.so, p.provider_id)
        try:
            bm = self.kho.lay(t.credential_ref)
        except KhongCoBiMat:
            kq = KetQuaThu(ok=False, chi_tiet=f"credential_ref {t.credential_ref} không còn "
                                              f"trong kho {self.kho.kieu} — xoá và thêm lại "
                                              f"tài khoản", ts=time.time())
            t2 = be.ket_thuc(account_id, ok=False, chi_tiet=kq.chi_tiet) or t
            self._su_kien("PROVIDER_TEST_FAILED", f"{p.provider_id}/{t.alias}: {kq.chi_tiet}",
                          project_id=project_id, level="WARNING")
            return {"tai_khoan": t2.to_dict(), "ket_qua": kq.to_dict()}
        be.bat_dau(account_id)
        kq = ad.thu_ket_noi(bm, timeout=timeout)
        t2 = be.ket_thuc(account_id, ok=kq.ok, chi_tiet=kq.chi_tiet) or t
        if kq.ok and kq.cach == "models" and kq.models:
            with self._khoa:
                self.so.xoa_models(p.provider_id, nguon="probed")
                for m in kq.models[:200]:
                    self.so.luu_model(ModelNgoai(provider_id=p.provider_id, model_id=m,
                                                 nang_luc=NANG_LUC_KHAI_BAO, nguon="probed"))
        self._su_kien("PROVIDER_TEST_OK" if kq.ok else "PROVIDER_TEST_FAILED",
                      f"{p.provider_id}/{t.alias}: {kq.chi_tiet}", project_id=project_id,
                      level="INFO" if kq.ok else "WARNING",
                      meta={"account_id": account_id, "ma_http": kq.ma_http, "cach": kq.cach})
        self._da_doi()
        return {"tai_khoan": t2.to_dict(), "ket_qua": kq.to_dict()}

    def hoi_thu(self, account_id: str, *, model: str, cau: str, project_id: str = "",
                max_tokens: int = 128, timeout: float = 60.0) -> Dict:
        """ĐỊNH TUYẾN THỦ CÔNG — người bấm, một lượt, có ghi sự kiện."""
        t = self.so.tai_khoan(account_id)
        if t is None:
            raise LoiDichVuProvider(f"không có tài khoản {account_id!r}")
        if not t.bat:
            raise LoiDichVuProvider("tài khoản đang tắt")
        if t.dang_cooldown():
            raise LoiDichVuProvider("tài khoản đang cooldown sau nhiều lần hỏng")
        ad, p = self._adapter(t)
        bm = self.kho.lay(t.credential_ref)
        be = BeTaiKhoan(self.so, p.provider_id)
        be.bat_dau(account_id)
        kq = ad.hoi(bm, model=model, cau=cau, max_tokens=max_tokens, timeout=timeout)
        be.ket_thuc(account_id, ok=kq.ok, chi_tiet=kq.chi_tiet or "hỏi thử OK")
        self._su_kien("PROVIDER_MANUAL_CALL",
                      f"{p.provider_id}/{t.alias} model {model}: "
                      f"{'OK' if kq.ok else 'HỎNG'} {kq.chi_tiet}"[:300],
                      project_id=project_id, level="INFO" if kq.ok else "WARNING",
                      meta={"account_id": account_id, "model": model, "usage": kq.usage})
        return kq.to_dict()

    # -- dinh tuyen (Part E, toi thieu) ----------------------------------------------------

    def dang_ky_vao_fabric(self, fabric) -> Dict:
        """Đưa provider/tài khoản/model ngoài vào fabric — KHÔNG nhận dispatch.

        Runtime `EXT_<provider>_<alias>`, `auth_profile = credential-ref:<ref>`
        (nhãn chỉ chỗ, không phải giá trị), `dispatchable=False`. Model của
        provider vào `fabric.models` với năng lực KHAI BÁO. Hỏng ở bước
        `validate` thì gỡ hết phần vừa thêm — fabric không bao giờ ở trạng
        thái nửa chừng.
        """
        from scripts.router_v4 import fabric_config as FC
        from scripts.router_v4.runtime import RuntimeStatus
        them_rt: List[str] = []
        them_md: List[str] = []
        mong_rt: set = set()
        mong_md: set = set()
        loi = ""
        try:
            for p in self.so.providers():
                if not p.bat:
                    continue
                nhom = f"{p.provider_id}_api"
                fabric.pool_groups.add(nhom)
                mods = [m for m in self.so.models_cua(p.provider_id, chi_bat=True)]
                ids: List[str] = []
                for m in mods:
                    mid = f"{p.provider_id}/{m.model_id}"
                    ids.append(mid)
                    mong_md.add(mid)
                    if mid in fabric.models:
                        continue
                    fabric.add_model(FC._model_tu_dict({
                        "model_id": mid, "model_family": p.provider_id,
                        "provider": p.provider_id, "quota_pool": nhom,
                        "reasoning": "medium", "provider_model": m.model_id,
                        "premium_tier": int(m.bac or 1),
                        "capabilities": list(m.nang_luc or NANG_LUC_KHAI_BAO),
                        "capability_source": {c: "declared" for c in
                                              (m.nang_luc or NANG_LUC_KHAI_BAO)},
                        "benchmark_profile": 0.5, "latency_profile": 30.0,
                        "reliability": 0.8, "cost_profile": 0.7,
                        "notes": f"provider ngoài {p.provider_id} · nguồn {m.nguon} · "
                                 f"CHƯA ĐO"}))
                    them_md.append(mid)
                for t in self.so.tai_khoan_cua(p.provider_id):
                    rid = f"EXT_{p.provider_id}_{_slug(t.alias)}".upper().replace("-", "_")
                    mong_rt.add(rid)
                    if rid in fabric.runtimes:
                        r = fabric.runtimes[rid]
                    else:
                        r = FC._runtime_tu_dict({
                            "runtime_id": rid, "provider": p.provider_id,
                            "account_id": t.account_id,
                            "auth_profile": f"credential-ref:{t.credential_ref}",
                            "transport": "http-openai", "concurrency": 1,
                            "supported_models": ids, "dispatchable": False,
                            "notes": "provider ngoài — không nhận dispatch (V0.6.1)"})
                        fabric.add_runtime(r)
                        them_rt.append(rid)
                    r.dispatchable = False
                    r.supported_models = tuple(ids)
                    if not t.bat:
                        r.needs_provisioning = "tài khoản đang tắt"
                        r.status = RuntimeStatus.OFFLINE
                    elif t.lan_thu_ok:
                        r.needs_provisioning = ""
                        r.status = RuntimeStatus.IDLE
                        r.last_seen = t.lan_thu_ts
                        r.health_detail = t.lan_thu_chi_tiet[:200]
                    else:
                        r.needs_provisioning = "chưa thử kết nối thành công"
                        r.status = RuntimeStatus.OFFLINE
                        r.health_detail = t.lan_thu_chi_tiet[:200]
            # Tai khoan/provider da bi xoa -> go runtime/model EXT tuong ung.
            # Chi cham nhung gi CHINH ta dat vao (tien to EXT_ / model co "/"
            # va provider khong con trong so); khong bao gio cham khe AG.
            bo_rt = [rid for rid in fabric.runtimes
                     if rid.startswith("EXT_") and rid not in mong_rt]
            for rid in bo_rt:
                fabric.runtimes.pop(rid, None)
            bo_md = [mid for mid, m in fabric.models.items()
                     if "/" in mid and mid not in mong_md
                     and str(getattr(m, "notes", "")).startswith("provider ngoài")]
            for mid in bo_md:
                fabric.models.pop(mid, None)
            fabric.validate()
        except Exception as exc:                            # noqa: BLE001
            loi = f"{type(exc).__name__}: {exc}"[:300]
            for rid in them_rt:
                fabric.runtimes.pop(rid, None)
            for mid in them_md:
                fabric.models.pop(mid, None)
            them_rt, them_md, bo_rt, bo_md = [], [], [], []
        return {"runtimes": them_rt, "models": them_md, "da_go": bo_rt + bo_md, "loi": loi}
