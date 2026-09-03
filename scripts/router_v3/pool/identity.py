"""Danh tính worker CỐ ĐỊNH — Bể worker tự trị, Phase 1.

BÀI TOÁN THẬT (đo được trên máy này 2026-09-03, không phải giả định):

`agy` KHÔNG giữ phiên đăng nhập trong thư mục cấu hình. Phép đo:

    HOME=<thư mục rỗng hoàn toàn> agy models   ->  VẪN xác thực thành công

Thư mục `.gemini` mới được tạo ra trong HOME giả, nhưng lượt gọi vẫn lấy
được danh sách model từ máy chủ. Vậy credential nằm ở **Windows Credential
Manager**, mục `gemini:antigravity` — MỘT mục duy nhất, dùng chung cho MỌI
tiến trình của MỘT tài khoản Windows.

Hệ quả không thể lách được:

    một tài khoản Windows  ==  một Credential Manager  ==  MỘT tài khoản
    Antigravity tại một thời điểm

Nên **danh tính cố định = hồ sơ Windows riêng**. Không có biến môi trường,
cờ dòng lệnh, hay thư mục cấu hình nào tạo ra được hai danh tính song song
trong cùng một hồ sơ Windows.

VÌ SAO ĐIỀU NÀY QUAN TRỌNG HƠN MỘT CHI TIẾT KỸ THUẬT:

Trên máy này có sẵn `C:\\Users\\nguye\\agy-profiles\\agy_profile.py` (gọi qua
`acc.cmd`) đọc blob credential của mục `gemini:antigravity`, lưu ra tệp
`.bin`, rồi GHI ĐÈ mục đó bằng blob của tài khoản khác để "chuyển tài khoản".
Đó chính xác là thứ mission CẤM:

    - "never dynamically switches accounts"
    - "never copies auth cookies/tokens between identities"
    - "Do NOT implement login rotation or automated account switching"

Bể worker này **không gọi, không nhập, không phụ thuộc** công cụ đó, và
`assert_khong_xoay_tai_khoan()` dưới đây TỪ CHỐI khởi động nếu cấu hình cố
lôi nó vào. Một khe không có hồ sơ Windows riêng thì báo `OFFLINE` kèm lý do
`needs_provisioning` — KHÔNG mượn tạm credential của khe khác.

RANH GIỚI CREDENTIAL (giữ nguyên bất biến của `registry.py`): module này chỉ
đọc/ghi **nhãn chỉ chỗ** (`auth_realm`), không bao giờ đọc credential.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from scripts.router_v3.registry import (CAPABILITIES, ExecutionType, Health,
                                        WorkerSpec)

#: Khe Antigravity cố định. Trùng với `registry.AG_SLOTS` — giữ ở đây một
#: bản để module này dùng được độc lập khi chỉ kiểm cấu hình.
AG_SLOTS: Tuple[str, ...] = tuple(f"AG{i:02d}" for i in range(1, 9))


class IdentityError(RuntimeError):
    """Cấu hình danh tính sai. LUÔN ném lúc nạp, không bao giờ lúc chạy —
    một bể worker chạy được nửa chừng rồi mới lộ ra hai khe dùng chung một
    tài khoản là loại lỗi chỉ thấy khi đã gửi việc đi rồi."""


#: Công cụ ĐỔI TÀI KHOẢN bằng cách ghi đè credential store. Tên tệp/lệnh
#: khớp bất kỳ mẫu nào dưới đây bị TỪ CHỐI xuất hiện trong cấu hình bể.
#: Đây là danh sách CỤ THỂ những thứ có thật trên máy này, không phải một
#: bộ lọc chung chung — một bộ lọc chung chung sẽ chặn nhầm việc hợp lệ.
_MAU_XOAY_TAI_KHOAN = (
    re.compile(r"agy_profile\.py", re.I),
    re.compile(r"\bacc\.cmd\b", re.I),
    re.compile(r"\bCredWrite", re.I),
    re.compile(r"\bCredDelete", re.I),
    re.compile(r"saved_profiles", re.I),
    re.compile(r"gemini:antigravity", re.I),
)


def assert_khong_xoay_tai_khoan(*van_ban: str) -> None:
    """Từ chối bất kỳ cấu hình nào kéo công cụ xoay tài khoản vào bể.

    Kiểm ở CỔNG VÀO chứ không dựa vào lời hứa trong tài liệu: quy tắc "không
    xoay tài khoản" chỉ có giá trị khi có thứ gì đó thực sự chặn được nó.
    """
    for t in van_ban:
        for mau in _MAU_XOAY_TAI_KHOAN:
            if mau.search(t or ""):
                raise IdentityError(
                    f"cấu hình chạm tới công cụ XOAY TÀI KHOẢN (mẫu "
                    f"{mau.pattern!r}) — TỪ CHỐI. Mỗi khe phải có hồ sơ "
                    f"Windows/phiên xác thực RIÊNG; sao chép blob credential "
                    f"giữa các danh tính bị cấm (xem docstring module).")


class Transport(str, Enum):
    """Cách Router nói chuyện với danh tính này.

    KHÔNG trùng `worker_adapter.TransportKind`: cái kia mô tả *giao thức*
    (ACP/HTTP/CLI/bridge) để chọn khi tích hợp provider mới; cái này mô tả
    *ranh giới hệ điều hành* — thứ quyết định danh tính có tách được không.
    """

    #: Tiến trình con do Router sinh, DÙNG CHUNG credential của tài khoản
    #: Windows đang chạy Router. Chỉ đúng MỘT khe được dùng cách này.
    NATIVE = "native"
    #: Cầu nối localhost tới một phiên đã xác thực trong hồ sơ Windows KHÁC.
    #: Đây là cách DUY NHẤT có thêm danh tính Antigravity thật.
    BRIDGE = "bridge"
    #: Server HTTP thường trực đã tự xác thực (opencode serve).
    HTTP = "http"
    #: CLI headless tự giữ phiên riêng (codex).
    CLI = "cli"


@dataclass(frozen=True)
class Identity:
    """MỘT danh tính worker cố định. Không bao giờ đổi tài khoản.

    `auth_realm` là bất biến trung tâm: nó nói phiên đăng nhập NẰM Ở ĐÂU.
    Hai danh tính Antigravity có cùng `auth_realm` nghĩa là chúng dùng CHUNG
    một Credential Manager — tức là cùng một tài khoản đội hai tên, không
    phải hai danh tính. `validate_pool()` từ chối chuyện đó.
    """

    worker_id: str
    provider: str
    transport: Transport
    auth_realm: str
    model: str = ""
    capabilities: FrozenSet[str] = frozenset()
    max_concurrent: int = 1
    trusted_for_high_risk: bool = False
    pool: str = ""
    workspace: str = ""
    #: Chỉ với `Transport.BRIDGE`/`HTTP`: nơi nghe. KHÔNG chứa token —
    #: token đọc từ `worker_identity.py`/tệp ghép lúc kết nối, không lưu ở đây.
    host: str = "127.0.0.1"
    port: int = 0
    #: Lý do khe này chưa dùng được, nếu chưa. Rỗng = đã cấp phát xong.
    needs_provisioning: str = ""
    notes: str = ""

    # -- Khe TÀI KHOẢN hay LÀN chạy trên một khe? --------------------------
    # Phân biệt này là thứ giữ cho mọi con số báo cáo về sau trung thực.
    #
    # `account_slot=True`  : một TÀI KHOẢN riêng (AG01..AG08, OPENCODE01,
    #                        CODEX01). Đếm được vào "số tài khoản".
    # `account_slot=False` : một LÀN chạy model khác TRÊN tài khoản của khe
    #                        `lane_of`. Chạy song song được, nhưng KHÔNG
    #                        phải tài khoản thứ hai và KHÔNG được đếm như
    #                        vậy — dùng chung quota, dùng chung credential.
    #
    # Không có cặp cờ này thì "8 worker" và "8 tài khoản" trông giống hệt
    # nhau trong mọi bảng điều khiển, và đó đúng là chỗ dễ tự lừa nhất.
    account_slot: bool = True
    lane_of: str = ""

    @property
    def provisioned(self) -> bool:
        return not self.needs_provisioning

    def validate(self) -> None:
        if not self.worker_id.strip():
            raise IdentityError("danh tính thiếu worker_id")
        la = set(self.capabilities) - CAPABILITIES
        if la:
            raise IdentityError(f"{self.worker_id}: năng lực lạ {sorted(la)}")
        if self.max_concurrent < 1:
            raise IdentityError(f"{self.worker_id}: max_concurrent phải >= 1")
        if not self.auth_realm.strip():
            raise IdentityError(
                f"{self.worker_id}: thiếu `auth_realm` — không có nhãn chỉ chỗ "
                f"phiên đăng nhập thì bất biến 'một danh tính = một tài khoản' "
                f"không kiểm được bằng máy, và cả bể mất ý nghĩa.")
        if self.transport in (Transport.BRIDGE, Transport.HTTP) and not self.port:
            if self.provisioned:
                raise IdentityError(
                    f"{self.worker_id}: transport {self.transport.value} cần "
                    f"`port`. Khe chưa có cổng phải khai `needs_provisioning`.")
        if not self.account_slot and not self.lane_of:
            raise IdentityError(
                f"{self.worker_id}: là LÀN (account_slot=False) nhưng không "
                f"khai `lane_of`. Một làn phải nói rõ nó chạy trên tài khoản "
                f"của khe nào — nếu không, nó sẽ được đếm nhầm thành một tài "
                f"khoản riêng ở mọi bảng báo cáo.")
        if self.account_slot and self.lane_of:
            raise IdentityError(
                f"{self.worker_id}: khai vừa là khe tài khoản vừa là làn của "
                f"{self.lane_of!r} — chọn một.")
        assert_khong_xoay_tai_khoan(self.auth_realm, self.notes, self.workspace)

    def to_spec(self) -> WorkerSpec:
        """Đổi sang `WorkerSpec` cho `WorkerRegistry` — KHÔNG dựng lớp sổ
        đăng ký thứ hai. Bể chỉ thêm khái niệm DANH TÍNH lên trên sổ đã có."""
        return WorkerSpec(
            worker_id=self.worker_id,
            provider_family=self.provider,
            execution_type=(ExecutionType.NATIVE_LEAD
                            if self.provider == "claude"
                            else ExecutionType.LOCAL_CLI),
            pool=self.pool or self.provider.upper(),
            capabilities=frozenset(self.capabilities),
            trusted_for_high_risk=self.trusted_for_high_risk,
            max_concurrent=self.max_concurrent,
            notes=self.notes,
            model=self.model,
            workspace=self.workspace,
            auth_realm=self.auth_realm)


def validate_pool(danh_sach: Sequence[Identity]) -> None:
    """Kiểm bất biến TOÀN BỂ. Ném `IdentityError` nếu sai.

    Bất biến khó nhất và cũng là lý do module này tồn tại: **hai danh tính
    Antigravity KHÔNG được dùng chung `auth_realm`**. Trên Windows một hồ sơ
    người dùng = một Credential Manager = một tài khoản Antigravity; hai khe
    trỏ cùng chỗ nghĩa là để chạy được chúng phải LUÂN PHIÊN ghi đè credential
    — đúng thứ mission cấm. Bắt ở đây, lúc nạp cấu hình, là cách duy nhất
    ngăn nó lọt vào lúc chạy dưới dạng "sao worker này trả lời như tài khoản
    kia".
    """
    thay: Dict[str, str] = {}
    for d in danh_sach:
        d.validate()
        if d.worker_id in thay:
            raise IdentityError(f"trùng worker_id: {d.worker_id!r}")
        thay[d.worker_id] = d.auth_realm

    theo_realm: Dict[str, List[str]] = {}
    for d in danh_sach:
        # Khe CHƯA cấp phát chưa chiếm realm nào cả — chúng khai một realm
        # dự kiến ("windows-user:AG05") để tài liệu hoá đích đến, và hai khe
        # chưa cấp phát không thể "đụng nhau" vì không khe nào chạy.
        if not d.provisioned or not d.account_slot:
            continue
        theo_realm.setdefault(d.auth_realm, []).append(d.worker_id)

    for realm, ids in sorted(theo_realm.items()):
        if len(ids) > 1:
            raise IdentityError(
                f"{len(ids)} KHE TÀI KHOẢN cùng auth_realm {realm!r}: "
                f"{sorted(ids)}. Trên Windows đó là MỘT Credential Manager, "
                f"tức MỘT tài khoản — chạy cả hai đòi luân phiên ghi đè "
                f"credential, thứ bể này cấm. Cấp một hồ sơ Windows riêng cho "
                f"mỗi khe, để khe thừa ở trạng thái needs_provisioning, hoặc "
                f"khai nó là LÀN (account_slot=False, lane_of=...) nếu nó "
                f"thật sự chạy trên cùng tài khoản.")

    # Mot LAN phai tro toi mot khe co that VA dung CHINH realm cua khe do.
    # Neu khong ep dieu nay, `account_slot=False` tro thanh cai cua sau: khai
    # bat ky realm nao cung lot, va bat bien "mot khe = mot tai khoan" mat
    # hieu luc vi chi can doi mot co la vong kiem tren bo qua.
    theo_id = {d.worker_id: d for d in danh_sach}
    for d in danh_sach:
        if d.account_slot:
            continue
        chu = theo_id.get(d.lane_of)
        if chu is None:
            raise IdentityError(
                f"{d.worker_id}: lane_of={d.lane_of!r} không tồn tại trong bể.")
        if not chu.account_slot:
            raise IdentityError(
                f"{d.worker_id}: lane_of trỏ tới {chu.worker_id!r} vốn cũng là "
                f"một làn — làn phải trỏ thẳng tới KHE TÀI KHOẢN.")
        if chu.auth_realm != d.auth_realm:
            raise IdentityError(
                f"{d.worker_id}: khai là làn của {chu.worker_id!r} nhưng "
                f"auth_realm khác ({d.auth_realm!r} vs {chu.auth_realm!r}). "
                f"Một làn chạy trên ĐÚNG credential của khe nó thuộc về; "
                f"realm khác nghĩa là nó là một tài khoản thứ hai đang giả "
                f"làm làn.")


def dem_tai_khoan(danh_sach: Sequence[Identity]) -> Dict[str, int]:
    """Đếm TÀI KHOẢN thật (không phải worker) theo nhà cung cấp.

    Tồn tại để không ai — kể cả chính bộ điều phối lúc viết báo cáo — nhầm
    "6 worker chạy song song" thành "6 tài khoản".
    """
    ra: Dict[str, int] = {}
    for d in danh_sach:
        if d.account_slot and d.provisioned:
            ra[d.provider] = ra.get(d.provider, 0) + 1
    return ra


# ---------------------------------------------------------------------------
# Cấu hình mặc định — phản ánh thứ THẬT SỰ có trên máy này
# ---------------------------------------------------------------------------

_NANG_LUC_CODING = frozenset({"recon", "implement", "tests", "frontend",
                              "review", "integration"})
_NANG_LUC_NHE = frozenset({"recon", "tests", "implement"})
_NANG_LUC_REVIEW = frozenset({"review", "recon", "implement"})


def duong_cau_hinh(root: Optional[Path] = None) -> Path:
    goc = Path(root) if root else Path.cwd()
    return goc / ".router" / "pool" / "identities.json"


def mac_dinh() -> List[Identity]:
    """Bể mặc định. AG01 là khe DUY NHẤT chạy native được — nó dùng chính
    Credential Manager của tài khoản Windows đang chạy Router.

    AG02 đã có hồ sơ Windows riêng (`C:\\Users\\AG02`) nên khai transport
    BRIDGE; nó chỉ READY khi người dùng AG02 tự đăng nhập và chạy
    `run_bridge.py` trong phiên của họ.

    AG03..AG08 CHƯA có hồ sơ Windows nào — khai `needs_provisioning` kèm
    đúng việc phải làm, thay vì giả vờ chúng sẵn sàng.
    """
    windows_user = os.environ.get("USERNAME") or "unknown"
    ds: List[Identity] = [
        Identity(
            worker_id="AG01", provider="antigravity", transport=Transport.NATIVE,
            auth_realm=f"windows-user:{windows_user}",
            model="gemini-3.8-flash-high", pool="GEMINI_FLASH_HIGH",
            capabilities=_NANG_LUC_CODING, max_concurrent=3,
            notes="tài khoản Antigravity của hồ sơ Windows đang chạy Router"),
        Identity(
            worker_id="AG02", provider="antigravity", transport=Transport.BRIDGE,
            auth_realm="windows-user:AG02",
            model="gemini-3.8-flash-high", pool="GEMINI_FLASH_HIGH",
            capabilities=_NANG_LUC_CODING, max_concurrent=1,
            needs_provisioning=(
                "hồ sơ Windows AG02 ĐÃ tồn tại nhưng cầu nối chưa chạy — "
                "đăng nhập vào phiên AG02 rồi chạy: python -m "
                "scripts.router_v3.run_bridge --worker-id AG02"),
            notes="hồ sơ Windows riêng, credential riêng"),
    ]
    for slot in AG_SLOTS[2:]:
        ds.append(Identity(
            worker_id=slot, provider="antigravity", transport=Transport.BRIDGE,
            auth_realm=f"windows-user:{slot}",
            model="gemini-3.8-flash-high", pool="GEMINI_FLASH_HIGH",
            capabilities=_NANG_LUC_CODING, max_concurrent=1,
            needs_provisioning=(
                f"chưa có hồ sơ Windows {slot}. Danh tính cố định đòi một "
                f"Credential Manager riêng: tạo tài khoản Windows {slot}, "
                f"đăng nhập một lần vào Antigravity bằng tài khoản Google "
                f"riêng của khe, rồi chạy run_bridge.py trong phiên đó. "
                f"KHÔNG dùng công cụ đổi tài khoản — xem docstring module."),
            notes="khe dự phòng, chưa cấp phát"))

    # Cac model KHAC trong CUNG tai khoan AG01 — khai la LAN, khong phai khe
    # tai khoan. Chung chay song song that va co nang luc khac nhau (mission
    # doi dinh tuyen theo nang luc: viec co hoc di model re, review bao mat
    # di Claude Opus), nhung chung DUNG CHUNG credential va quota cua AG01.
    ds += [
        Identity(
            worker_id="AG01_MED", provider="antigravity",
            transport=Transport.NATIVE, account_slot=False, lane_of="AG01",
            auth_realm=f"windows-user:{windows_user}",
            model="gemini-3.8-flash-medium", pool="GEMINI_FLASH_MEDIUM",
            capabilities=_NANG_LUC_NHE, max_concurrent=2,
            notes="LÀN trên tài khoản AG01, model rẻ hơn — cơ học/test/docs"),
        Identity(
            worker_id="AG_OPUS", provider="antigravity",
            transport=Transport.NATIVE, account_slot=False, lane_of="AG01",
            auth_realm=f"windows-user:{windows_user}",
            model="claude-opus-4-6-thinking", pool="ANTIGRAVITY_CLAUDE_OPUS",
            capabilities=frozenset({"security_review", "architecture", "review"}),
            trusted_for_high_risk=True, max_concurrent=1,
            notes="LÀN trên tài khoản AG01, model Claude Opus — review bảo mật"),
        Identity(
            worker_id="AG_GPTOSS", provider="antigravity",
            transport=Transport.NATIVE, account_slot=False, lane_of="AG01",
            auth_realm=f"windows-user:{windows_user}",
            model="gpt-oss-120b-medium", pool="ANTIGRAVITY_GPT_OSS",
            capabilities=frozenset({"challenger", "review", "recon"}),
            max_concurrent=1,
            notes="LÀN trên tài khoản AG01, ý kiến phản biện khác họ model"),
        Identity(
            worker_id="OPENCODE01", provider="opencode",
            transport=Transport.HTTP, auth_realm="opencode-server:127.0.0.1:4096",
            port=4096, pool="OPENCODE",
            capabilities=_NANG_LUC_REVIEW, max_concurrent=1,
            notes="opencode serve — tài khoản OpenCode riêng"),
        Identity(
            worker_id="CODEX01", provider="codex", transport=Transport.CLI,
            auth_realm="codex-cli:default", pool="CODEX",
            capabilities=frozenset({"review", "implement"}), max_concurrent=1,
            notes="codex CLI — tài khoản ChatGPT riêng. KHÔNG review bảo mật "
                  "(bằng chứng 2026-08-28: Codex từ chối việc hình dạng bảo mật)"),
        Identity(
            worker_id="CLAUDE_LEAD", provider="claude",
            transport=Transport.NATIVE, auth_realm="claude-code:session",
            pool="CLAUDE_OPUS",
            capabilities=frozenset({"architecture", "integration"}),
            trusted_for_high_risk=True,
            notes="phiên đang chạy: lập kế hoạch, dựng DAG, tích hợp"),
    ]
    validate_pool(ds)
    return ds


def _tu_dict(d: dict) -> Identity:
    return Identity(
        worker_id=str(d["worker_id"]), provider=str(d["provider"]),
        transport=Transport(str(d.get("transport") or "native")),
        auth_realm=str(d.get("auth_realm") or ""),
        model=str(d.get("model") or ""),
        capabilities=frozenset(d.get("capabilities") or ()),
        max_concurrent=int(d.get("max_concurrent") or 1),
        trusted_for_high_risk=bool(d.get("trusted_for_high_risk")),
        pool=str(d.get("pool") or ""), workspace=str(d.get("workspace") or ""),
        host=str(d.get("host") or "127.0.0.1"), port=int(d.get("port") or 0),
        needs_provisioning=str(d.get("needs_provisioning") or ""),
        notes=str(d.get("notes") or ""),
        # Mac dinh True: mot cau hinh cu khong khai co nay la mot KHE tai
        # khoan. Mac dinh False se bien moi khe cu thanh "lan" thieu lane_of
        # va lam ca be tu choi nap — im lang doi nghia thi te hon.
        account_slot=bool(d.get("account_slot", True)),
        lane_of=str(d.get("lane_of") or ""))


def to_dict(i: Identity) -> dict:
    return {
        "worker_id": i.worker_id, "provider": i.provider,
        "transport": i.transport.value, "auth_realm": i.auth_realm,
        "model": i.model, "capabilities": sorted(i.capabilities),
        "max_concurrent": i.max_concurrent,
        "trusted_for_high_risk": i.trusted_for_high_risk,
        "pool": i.pool, "workspace": i.workspace, "host": i.host,
        "port": i.port, "needs_provisioning": i.needs_provisioning,
        "notes": i.notes, "account_slot": i.account_slot, "lane_of": i.lane_of,
    }


def nap(path: Optional[Path] = None, *, root: Optional[Path] = None
        ) -> List[Identity]:
    """Nạp cấu hình danh tính từ đĩa, hoặc mặc định nếu chưa có tệp.

    Tệp cấu hình được quét chống-xoay-tài-khoản TRƯỚC khi phân tích: một
    cấu hình độc hại không được có cơ hội chạy dù chỉ một dòng.
    """
    p = Path(path) if path else duong_cau_hinh(root)
    if not p.exists():
        return mac_dinh()
    tho = p.read_text(encoding="utf-8")
    assert_khong_xoay_tai_khoan(tho)
    try:
        d = json.loads(tho)
    except json.JSONDecodeError as exc:
        raise IdentityError(f"{p}: JSON hỏng — {exc}") from exc
    muc = d.get("identities") if isinstance(d, dict) else d
    if not isinstance(muc, list):
        raise IdentityError(f"{p}: cần một danh sách `identities`")
    ds = [_tu_dict(x) for x in muc]
    validate_pool(ds)
    return ds


def ghi(danh_sach: Sequence[Identity], path: Optional[Path] = None, *,
        root: Optional[Path] = None) -> Path:
    validate_pool(danh_sach)
    p = Path(path) if path else duong_cau_hinh(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"identities": [to_dict(i) for i in danh_sach]},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return p
