"""Nạp fabric từ cấu hình — Router V4.

MỌI thứ đặc thù nhà cung cấp sống trong `config/fabric.json`, không rải rác
trong mã. Thêm một tài khoản hay một model là sửa một tệp dữ liệu.

DÒ SỨC KHOẺ LÀ THẬT, KHÔNG PHẢI GIẢ ĐỊNH. `nap(probe=True)` hỏi từng
provider xem nó có thật sự dùng được không, và một runtime không dò được sẽ
vào `OFFLINE` kèm lý do — chứ không im lặng nằm ở `IDLE` rồi hỏng lúc giao
việc.

KHÔNG BAO GIỜ ĐỌC CREDENTIAL: `auth_profile` chỉ là NHÃN CHỈ CHỖ. Việc dò
sức khoẻ hỏi CLI "anh còn đăng nhập không" và chỉ đọc câu trả lời có/không
— không đọc token, không sao chép hồ sơ, không xoay tài khoản.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.router_v4.capabilities import Reasoning
from scripts.router_v4.runtime import (Fabric, FabricError, ModelCapability,
                                       QuotaPool, RuntimeStatus, Source,
                                       WorkerRuntime)
from scripts.router_v4.scheduler import Weights
from scripts.router_v4.modes import EscalationPolicy

AG_SLOTS: Tuple[str, ...] = tuple(f"AG{i:02d}" for i in range(1, 9))

#: Cong cu DOI TAI KHOAN bang cach ghi de credential store. Cau hinh cham
#: toi bat ky mau nao trong so nay bi TU CHOI — cung bat bien voi
#: `router_v3/pool/identity.py`, lap lai o day vi V4 nap cau hinh RIENG va
#: mot rao chi ton tai o tang duoi thi tang tren di vong qua duoc.
_MAU_XOAY_TAI_KHOAN = (
    re.compile(r"agy_profile\.py", re.I),
    re.compile(r"\bacc\.cmd\b", re.I),
    re.compile(r"\bCredWrite", re.I),
    re.compile(r"\bCredDelete", re.I),
    re.compile(r"saved_profiles", re.I),
    re.compile(r"gemini:antigravity", re.I),
)


def duong_mac_dinh() -> Path:
    return Path(__file__).resolve().parent / "config" / "fabric.json"


def duong_ghi_de(root: Optional[Path] = None) -> Path:
    """Cấu hình GHI ĐÈ theo kho, nếu có. Cho phép một kho chỉnh trọng số/
    runtime mà không sửa tệp mặc định đi kèm mã."""
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "v4" / "fabric.json"


def assert_khong_xoay_tai_khoan(*van_ban: str) -> None:
    for t in van_ban:
        for mau in _MAU_XOAY_TAI_KHOAN:
            if mau.search(t or ""):
                raise FabricError(
                    f"cấu hình chạm tới công cụ XOAY TÀI KHOẢN (mẫu "
                    f"{mau.pattern!r}) — TỪ CHỐI. Mỗi runtime phải có hồ sơ "
                    f"xác thực RIÊNG; sao chép blob credential giữa các danh "
                    f"tính bị cấm (mission #8).")


def _thay_bien(s: str) -> str:
    """`${USERNAME}` -> tên tài khoản Windows hiện tại.

    Chỉ thay các biến môi trường VÔ HẠI liên quan tới danh tính hồ sơ. Cố ý
    không mở rộng tuỳ ý: một cấu hình thay được `${...}` bất kỳ sẽ đọc được
    biến môi trường chứa bí mật rồi ghi nó vào một nhãn công khai.
    """
    CHO_PHEP = ("USERNAME", "COMPUTERNAME")
    def _th(m):
        ten = m.group(1)
        if ten not in CHO_PHEP:
            raise FabricError(
                f"cấu hình dùng ${{{ten}}} — chỉ cho phép {list(CHO_PHEP)}. "
                f"Mở rộng biến tuỳ ý có thể kéo bí mật từ môi trường vào một "
                f"nhãn công khai.")
        return os.environ.get(ten, "unknown")
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", _th, s)


def _doc_json(p: Path) -> Dict:
    tho = p.read_text(encoding="utf-8")
    assert_khong_xoay_tai_khoan(tho)
    try:
        d = json.loads(tho)
    except json.JSONDecodeError as exc:
        raise FabricError(f"{p}: JSON hỏng — {exc}") from exc
    if not isinstance(d, dict):
        raise FabricError(f"{p}: cần một đối tượng JSON")
    return d


def doc_cau_hinh(*, root: Optional[Path] = None,
                 path: Optional[Path] = None) -> Dict:
    d = _doc_json(Path(path) if path else duong_mac_dinh())
    if path is None:
        ghi_de = duong_ghi_de(root)
        if ghi_de.exists():
            d.update(_doc_json(ghi_de))
    return d


def _model_tu_dict(d: Dict) -> ModelCapability:
    return ModelCapability(
        model_id=str(d["model_id"]), model_family=str(d.get("model_family") or ""),
        provider=str(d.get("provider") or ""),
        capabilities=frozenset(d.get("capabilities") or ()),
        capability_source={k: Source(v) for k, v in
                           (d.get("capability_source") or {}).items()},
        quota_pool=str(d.get("quota_pool") or ""),
        reasoning=Reasoning(str(d.get("reasoning") or "medium")),
        benchmark_profile=float(d.get("benchmark_profile", 0.5)),
        latency_profile=float(d.get("latency_profile", 30.0)),
        reliability=float(d.get("reliability", 0.9)),
        cost_profile=float(d.get("cost_profile", 0.5)),
        notes=str(d.get("notes") or ""))


def _runtime_tu_dict(d: Dict) -> WorkerRuntime:
    return WorkerRuntime(
        runtime_id=str(d["runtime_id"]), provider=str(d.get("provider") or ""),
        account_id=str(d.get("account_id") or ""),
        auth_profile=_thay_bien(str(d.get("auth_profile") or "")),
        supported_models=tuple(d.get("supported_models") or ()),
        concurrency=int(d.get("concurrency") or 1),
        needs_provisioning=str(d.get("needs_provisioning") or ""),
        transport=str(d.get("transport") or "native"),
        host=str(d.get("host") or "127.0.0.1"),
        port=int(d.get("port") or 0),
        workspace=str(d.get("workspace") or ""),
        dispatchable=bool(d.get("dispatchable", True)),
        notes=str(d.get("notes") or ""))


def dung_fabric(cfg: Dict) -> Fabric:
    """Dựng fabric từ cấu hình. KHÔNG chạm mạng — dò sức khoẻ là bước riêng."""
    f = Fabric()

    for m in cfg.get("models") or []:
        f.add_model(_model_tu_dict(m))

    runtimes = [_runtime_tu_dict(r) for r in (cfg.get("runtimes") or [])]

    # AG03..AG08 sinh tu mau. Chung CO MAT (de bang dieu khien thay, va de
    # cap phat chi la viec van hanh) nhung deu CHUA cap phat.
    mau = cfg.get("ag_slot_template")
    co_san = {r.runtime_id for r in runtimes}
    if mau:
        for slot in AG_SLOTS:
            if slot in co_san:
                continue
            runtimes.append(_runtime_tu_dict({
                "runtime_id": slot,
                "provider": mau.get("provider", "antigravity"),
                "account_id": f"ag-account-{slot[2:]}",
                "auth_profile": f"windows-user:{slot}",
                "transport": mau.get("transport", "bridge"),
                "concurrency": mau.get("concurrency", 1),
                "supported_models": mau.get("supported_models") or [],
                "needs_provisioning": str(
                    mau.get("needs_provisioning") or "").replace("{slot}", slot),
            }))
    # Khe AG nao da co profile launcher tren DIA thi KHONG con "chua cap
    # phat" nua — bang chung la tep, khong phai cau hinh. Nguoc lai, khe
    # khong co profile van giu ly do cap phat cua no.
    # KHONG bao boc bang `except Exception: pass`. Da vap that: ban dau
    # doan nay dung `pathlib.Path` trong khi module chi import `Path`, va
    # `NameError` bi chinh cai `except` do NUOT — 7 khe launcher am tham
    # khong duoc dang ky, bang dieu khien van bao OFFLINE, va khong co
    # mot dong loi nao. Chi bat ImportError (launcher vang mat la truong
    # hop HOP LE tren may khac); moi loi khac phai noi ra.
    try:
        from scripts.router_v4.antigravity_launcher import (
            ACC_CUA_RUNTIME, SESSIONS_DIR, profile_ton_tai)
    except ImportError:
        ACC_CUA_RUNTIME, SESSIONS_DIR, profile_ton_tai = {}, None, None
    # Doi chieu phai la HAI CHIEU. Ban dau doan nay chi XOA
    # `needs_provisioning` khi thay profile, khong bao gio DAT lai khi khong
    # thay — nen AG01 (khai `needs_provisioning: null` tinh trong
    # fabric.json, tu thoi no la tai khoan duy nhat) bao `provisioned=True`
    # tren MOI may, ke ca may khong co `acc1.bin` nao. Do dung la "worker
    # gia": mot khe bao san sang ma khong co MOT bang chung nao.
    #
    # Da do that, khong phai suy luan: CI Linux (run 33760902870) do 3 bai
    # — `test_trang_thai_khe_AG_khop_voi_THUC_TE_tren_dia`,
    # `test_dem_tai_khoan_khong_thoi_phong`,
    # `test_khe_co_profile_thi_dung_transport_launcher` — deu cung mot goc:
    # "AG01: khong co acc1.bin" nhung `provisioned` van True. Tren may nguoi
    # van hanh ba bai do DAT vi `acc1.bin` co that, nen loi an duoc rat lau.
    #
    # `provisioned` = `not needs_provisioning`, va no chan ca
    # `trang_thai_hien_tai()` (-> OFFLINE) lan `dem_tai_khoan()`. Nen mot
    # cho sua nay dong ca ba bai.
    if profile_ton_tai is not None:
        for r in runtimes:
            acc = ACC_CUA_RUNTIME.get(r.runtime_id)
            if not acc or r.provider != 'antigravity':
                continue
            if profile_ton_tai(acc):
                r.transport = 'launcher'
                r.auth_profile = f'agy-launcher:{acc}'
                r.needs_provisioning = ''
                r.workspace = str(Path(SESSIONS_DIR) / acc)
            elif not r.needs_provisioning:
                # Khong co bang chung tren dia -> KHONG duoc khai la da cap
                # phat. Chi ghi de khi cau hinh de trong: AG02..AG08 da co
                # ly do cap phat rieng, cu the hon, phai giu nguyen.
                r.needs_provisioning = (
                    f"Chua co ho so launcher {acc}.bin tren dia. Chay "
                    f"scripts/migrate_agy_profiles_dpapi.py de ma hoa ho so "
                    f"agy san co, hoac dang nhap Antigravity mot lan trong "
                    f"phien Windows cua khe {r.runtime_id} roi luu ho so."
                )

    for r in runtimes:
        f.add_runtime(r)

    # Be quota: mot ban RIENG cho moi (tai khoan x mau be). Quota gan voi
    # TAI KHOAN — hai tai khoan Antigravity co hai be Gemini doc lap, va
    # gop chung lam mot be se lam mot tai khoan het quota keo ca hai xuong.
    mau_be = {str(t["pool_id"]): t for t in (cfg.get("quota_pool_templates") or [])}
    # Khai bao NHOM truoc khi tao be that: `Fabric.validate` chap nhan mot
    # model tro toi mot nhom da khai ke ca khi chua tai khoan nao tao be
    # thuoc nhom do (vd model chi chay tren runtime chua cap phat).
    f.pool_groups |= set(mau_be)
    f.pool_groups |= {m.quota_pool for m in f.models.values() if m.quota_pool}
    theo_model = {m.model_id: m for m in f.models.values()}
    da_tao = set()
    for r in f.runtimes.values():
        for mid in r.supported_models:
            m = theo_model.get(mid)
            if m is None or not m.quota_pool:
                continue
            pid = f"{r.account_id}:{m.quota_pool}"
            if pid in da_tao:
                continue
            t = mau_be.get(m.quota_pool, {})
            thanh_vien = frozenset(
                x for x in r.supported_models
                if theo_model.get(x) and theo_model[x].quota_pool == m.quota_pool)
            f.add_pool(QuotaPool(
                pool_id=pid, account_id=r.account_id,
                member_models=thanh_vien,
                rolling_window_seconds=float(
                    t.get("rolling_window_seconds") or 18000.0),
                source=Source(str(t.get("source") or "unknown")),
                note=str(t.get("note") or "")))
            da_tao.add(pid)

    f.validate()
    return f


# ---------------------------------------------------------------------------
# Do suc khoe THAT
# ---------------------------------------------------------------------------

def do_suc_khoe(f: Fabric, *, now: Optional[float] = None) -> Fabric:
    """Hỏi từng provider xem nó THẬT SỰ dùng được không.

    Mỗi nhánh dưới đây gọi một lệnh/endpoint có thật. Không nhánh nào đoán:
    một runtime không chứng minh được là sống thì vào `OFFLINE` kèm lý do
    đọc được, để người vận hành biết phải làm gì.
    """
    curr = time.time() if now is None else now
    for r in f.runtimes.values():
        r.last_seen = curr
        if not r.provisioned:
            r.status = RuntimeStatus.OFFLINE
            continue
        try:
            song, chi_tiet = _dò_mot(r)
        except Exception as exc:                          # noqa: BLE001
            song, chi_tiet = False, f"{type(exc).__name__}: {exc}"[:180]
        r.status = RuntimeStatus.IDLE if song else RuntimeStatus.OFFLINE
        r.health_detail = chi_tiet[:200]
    return f


def _dò_mot(r: WorkerRuntime) -> Tuple[bool, str]:
    if r.provider == "claude":
        return True, "phiên Claude đang chạy"
    if r.provider == "antigravity":
        if r.transport == "launcher":
            # Khe di qua launcher da-tai-khoan CO SAN. "Song" = co profile
            # da luu tren DIA, khong phai co ten trong cau hinh.
            from scripts.router_v4.antigravity_launcher import (
                LAUNCHER, acc_cua, profile_ton_tai)
            if not LAUNCHER.is_file():
                return False, f"thiếu launcher {LAUNCHER.name}"
            acc = acc_cua(r.runtime_id)
            if not acc:
                return False, f"không có ánh xạ acc cho {r.runtime_id}"
            if not profile_ton_tai(acc):
                return False, (f"chưa lưu profile {acc} — chạy `acc login "
                               f"{acc[3:]}` một lần trong phiên người dùng")
            return True, f"launcher, profile {acc} đã lưu"
        if r.transport == "native":
            from scripts.router_v3.native_worker import find_agy
            exe = find_agy()
            return (bool(exe), "agy sẵn sàng" if exe else "không tìm thấy agy")
        # bridge: chi song khi co ban ghi ghep VA co ai nghe cong do.
        from scripts.router_v3 import worker_identity
        dt = worker_identity.doc(r.runtime_id)
        if dt is None:
            return False, "chưa ghép cầu nối (chưa có danh tính đã lưu)"
        return _cong_song(r.host, r.port or dt["port"])
    if r.provider == "opencode":
        song, ct = _cong_song(r.host, r.port or 4096)
        if not song:
            return False, ct
        from scripts.router_v3.opencode_adapter import OpenCodeAdapter
        bc = OpenCodeAdapter(r.runtime_id, host=r.host, port=r.port or 4096).health()
        from scripts.router_v3.registry import Health
        return bc.state is Health.HEALTHY, bc.detail or "opencode serve"
    if r.provider == "codex":
        from scripts.router_v3.pool.adapters import CodexAdapter
        from scripts.router_v3.registry import Health
        bc = CodexAdapter(r.runtime_id).health()
        return bc.state is Health.HEALTHY, bc.detail
    return False, f"provider lạ {r.provider!r}"


def _cong_song(host: str, port: int) -> Tuple[bool, str]:
    import socket
    if not port:
        return False, "chưa có cổng"
    s = socket.socket()
    s.settimeout(2.0)
    try:
        s.connect((host, port))
        return True, f"cổng {port} đang nghe"
    except OSError as exc:
        return False, f"cổng {port} không có ai nghe ({type(exc).__name__})"
    finally:
        s.close()


def nap(*, root: Optional[Path] = None, path: Optional[Path] = None,
        probe: bool = True) -> Tuple[Fabric, Weights, EscalationPolicy]:
    cfg = doc_cau_hinh(root=root, path=path)
    f = dung_fabric(cfg)
    if probe:
        do_suc_khoe(f)
    return f, Weights.from_dict(cfg.get("weights")), \
        EscalationPolicy.from_dict(cfg.get("escalation"))
