"""Sổ đăng ký adapter + siêu dữ liệu năng lực — Story Harvester V4, Phase A.

`site_registry.py` đã trả lời được "domain này cấu hình ra sao". Nó **không**
trả lời được "adapter nào sở hữu domain này, và adapter đó làm được những gì" —
và đó là câu hỏi mà tầng định tuyến cần trước khi có adapter thứ hai, thứ ba.

Module này **không** dựng một trừu tượng cạnh tranh. Nó bọc đúng
`site_registry` + `StoryProvider` đang có: `resolve()` vẫn hỏi `site_registry`
về cấu hình, còn phần thêm vào là **quyền sở hữu host** (adapter nào nhận
domain nào) và **năng lực** (adapter đó tuyên bố làm được gì).

Vì sao năng lực phải là dữ liệu chứ không phải `isinstance`: một bộ lập lịch
muốn biết "adapter này có cần trình duyệt không" để xếp việc vào worker phù
hợp, và muốn biết "có hỗ trợ cập nhật gia tăng không" để quyết định có gọi
`ChangeDetector` hay không. Suy ra những điều đó bằng cách kiểm tra kiểu sẽ
buộc tầng lập lịch phải import mọi adapter.

Cố ý KHÔNG có gì dành riêng cho YouTube/Bilibili ở đây. Một nguồn cần trình
duyệt, hoặc không có trang mục lục, chỉ việc khai `requires_browser=True` hay
`supports_chapter_index=False` — hợp đồng V4 không phải đổi.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from server.scraper.contract import StoryProvider

__all__ = [
    "AdapterCapabilities",
    "AdapterRegistration",
    "AdapterRegistry",
    "DuplicateHostError",
    "InvalidRegistrationError",
    "RegistryError",
    "UnsupportedUrlError",
    "default_registry",
    "normalize_host",
]


class RegistryError(RuntimeError):
    """Gốc chung — nơi gọi bắt được cả họ mà không cần biết từng loại."""


class InvalidRegistrationError(RegistryError):
    """Bản khai báo adapter sai — phát hiện lúc ĐĂNG KÝ, không phải lúc chạy."""


class DuplicateHostError(RegistryError):
    """Hai adapter cùng nhận một host. KHÔNG được chọn bừa một cái.

    Đây cũng chính là lưới chặn "khớp adapter nhập nhằng": tra cứu dùng khớp
    host CHÍNH XÁC sau chuẩn hoá, nên một URL không bao giờ khớp hai adapter
    cùng lúc — nhập nhằng bị chặn ngay lúc ĐĂNG KÝ thay vì phải phân xử lúc
    chạy. Một `sub.vd.test` khi chỉ có `vd.test` được đăng ký sẽ là "không hỗ
    trợ", không phải "khớp gần đúng": đoán mò ở đây sẽ quét nhầm site.
    """


class UnsupportedUrlError(RegistryError):
    """Không adapter nào nhận URL này. KHÁC hẳn "có nhưng hỏng"."""


def normalize_host(url_or_host: str) -> str:
    """Rút host đã chuẩn hoá từ URL (hoặc từ chính chuỗi host).

    Cùng quy tắc với `site_registry.lookup`: chữ thường, bỏ `www.`. Thêm hai
    việc `lookup` không phải lo vì nó chỉ tra một dict:

    * bỏ cổng (`:443`) — `example.com` và `example.com:443` là một host;
    * bỏ dấu chấm cuối (`example.com.`) — dạng FQDN tuyệt đối hợp lệ trong
      DNS và trình duyệt chấp nhận, nên một URL viết như vậy phải trỏ về cùng
      adapter chứ không rơi vào "không hỗ trợ".
    """
    raw = (url_or_host or "").strip()
    host = urlsplit(raw).netloc if "//" in raw else raw
    host = host.split("@")[-1]            # bo userinfo neu co
    if host.startswith("["):              # IPv6 dang [::1]:8080
        host = host.split("]")[0] + "]"
    else:
        host = host.split(":")[0]
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


#: Chiến lược chuẩn hoá URL mà một adapter tuyên bố dùng. Chuỗi chứ không
#: phải hàm: đây là siêu dữ liệu để đọc/định tuyến, còn phép chuẩn hoá thật
#: sống ở `contract.canonicalize_url`.
CANONICALIZATION_STRATEGIES = frozenset({
    "url_normalized",     # bo tracking param + chuan hoa scheme/host/duoi
    "source_id",          # nguon co ID rieng, URL chi la vo boc
    "redirect_resolved",  # phai theo redirect that moi biet URL cuoi
})


@dataclass(frozen=True)
class AdapterCapabilities:
    """Adapter tự khai mình làm được gì. Đọc được, không phải suy ra."""

    supported_hosts: Tuple[str, ...]
    supports_story_metadata: bool = True
    supports_chapter_index: bool = True
    supports_chapter_fetch: bool = True
    #: Có dùng được với `change_detection` không. `False` nghĩa là mỗi lượt
    #: phải quét lại từ đầu — bộ lập lịch cần biết để không hứa hẹn "kiểm tra
    #: cập nhật rẻ" cho nguồn này.
    supports_incremental_updates: bool = True
    #: Cần một trình duyệt thật (JS). Tách khỏi `supports_static_fetch` vì
    #: một adapter có thể làm được cả hai, và bộ lập lịch cần chọn worker.
    requires_browser: bool = False
    supports_static_fetch: bool = True
    canonicalization: str = "url_normalized"
    stable_story_identity: bool = True
    stable_chapter_identity: bool = True

    def validate(self, ten: str) -> None:
        """Bắt bản khai hỏng lúc ĐĂNG KÝ.

        Một năng lực khai sai chỉ lộ ra khi bộ lập lịch tin nó và xếp việc
        vào sai worker — muộn hơn nhiều so với lúc nạp module.
        """
        if not self.supported_hosts:
            raise InvalidRegistrationError(
                f"{ten}: `supported_hosts` rỗng — một adapter không nhận host "
                f"nào thì không bao giờ được chọn, và im lặng bỏ qua nó sẽ "
                f"trông y hệt như 'URL không được hỗ trợ'.")
        for h in self.supported_hosts:
            if not h or h != normalize_host(h):
                raise InvalidRegistrationError(
                    f"{ten}: host {h!r} chưa chuẩn hoá — phải là chữ thường, "
                    f"không `www.`, không cổng, không dấu chấm cuối "
                    f"(dạng đúng: {normalize_host(h)!r}).")
        if self.canonicalization not in CANONICALIZATION_STRATEGIES:
            raise InvalidRegistrationError(
                f"{ten}: `canonicalization`={self.canonicalization!r} không "
                f"thuộc {sorted(CANONICALIZATION_STRATEGIES)}.")
        if not self.supports_static_fetch and not self.requires_browser:
            raise InvalidRegistrationError(
                f"{ten}: không tải tĩnh được VÀ cũng không cần trình duyệt — "
                f"vậy thì không có đường nào lấy được nội dung.")
        if self.supports_incremental_updates and not self.stable_chapter_identity:
            # Cap nhat gia tang so sanh theo DANH TINH chuong. Khong co danh
            # tinh on dinh thi moi lan quet lai se doc thanh "chuong moi" —
            # dung dieu ma cap nhat gia tang sinh ra de tranh.
            raise InvalidRegistrationError(
                f"{ten}: khai `supports_incremental_updates` nhưng "
                f"`stable_chapter_identity=False` — cập nhật gia tăng so theo "
                f"danh tính chương, không có danh tính ổn định thì mọi lượt "
                f"quét đều đọc thành 'chương mới'.")


@dataclass(frozen=True)
class AdapterRegistration:
    """Một adapter + năng lực + cách dựng nó."""

    name: str
    capabilities: AdapterCapabilities
    #: `(url, fetcher) -> StoryProvider`. Nhận `fetcher` để tầng vận chuyển
    #: vẫn được tiêm vào — không adapter nào tự tạo client mạng của riêng nó.
    build: Callable[[str, Any], StoryProvider]

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise InvalidRegistrationError("adapter thiếu `name`.")
        if not callable(self.build):
            raise InvalidRegistrationError(f"{self.name}: `build` không gọi được.")
        self.capabilities.validate(self.name)


class AdapterRegistry:
    """Tra cứu adapter theo host — tường minh và tất định.

    Không có phép "đoán khớp gần đúng". Một host hoặc thuộc về đúng một
    adapter, hoặc không adapter nào nhận nó.
    """

    def __init__(self) -> None:
        self._theo_host: Dict[str, AdapterRegistration] = {}
        self._dang_ky: List[AdapterRegistration] = []

    def register(self, reg: AdapterRegistration) -> None:
        reg.validate()
        for h in reg.capabilities.supported_hosts:
            chu_cu = self._theo_host.get(h)
            if chu_cu is not None and chu_cu.name != reg.name:
                # KHONG ghi de. Ai so huu host nay tro thanh chuyen phu thuoc
                # thu tu import — mot cach hong khong tai hien duoc.
                raise DuplicateHostError(
                    f"host {h!r} đã thuộc adapter {chu_cu.name!r}; "
                    f"{reg.name!r} cũng nhận nó. Quyền sở hữu host phải là duy "
                    f"nhất — nếu không, adapter nào thắng sẽ phụ thuộc thứ tự "
                    f"import.")
            self._theo_host[h] = reg
        self._dang_ky.append(reg)

    def names(self) -> List[str]:
        return sorted(r.name for r in self._dang_ky)

    def hosts(self) -> List[str]:
        return sorted(self._theo_host)

    def capabilities_of(self, name: str) -> AdapterCapabilities:
        for r in self._dang_ky:
            if r.name == name:
                return r.capabilities
        raise UnsupportedUrlError(f"không có adapter tên {name!r}.")

    def find(self, url: str) -> Optional[AdapterRegistration]:
        """Tra cứu, trả `None` khi không hỗ trợ. Không ném lỗi."""
        return self._theo_host.get(normalize_host(url))

    def resolve(self, url: str) -> AdapterRegistration:
        """Như `find` nhưng ném lỗi rõ ràng — dùng ở đường thi hành."""
        host = normalize_host(url)
        if not host:
            raise UnsupportedUrlError(
                f"không rút được host từ {url!r} — URL thiếu scheme/host?")
        reg = self._theo_host.get(host)
        if reg is None:
            raise UnsupportedUrlError(
                f"host {host!r} chưa được hỗ trợ. Đang hỗ trợ: "
                f"{', '.join(self.hosts()) or '(chưa có)'}.")
        return reg

    def build_for(self, url: str, fetcher: Any) -> StoryProvider:
        return self.resolve(url).build(url, fetcher)


# ---------------------------------------------------------------------------
# Sổ đăng ký mặc định — dựng TỪ `site_registry`, không chép lại nó.
# ---------------------------------------------------------------------------

def _dung_generic(url: str, fetcher: Any) -> StoryProvider:
    """Dựng `GenericIndexAdapter` từ cấu hình mà `site_registry` đã xác minh.

    Nếu `site_registry` không biết host này thì đây là mâu thuẫn nội bộ: sổ
    đăng ký tuyên bố sở hữu host mà cấu hình lại thiếu. Ném lỗi to, không lùi
    về một pattern đoán mò.
    """
    from server.scraper import site_registry
    from server.scraper.adapters.generic_index_adapter import GenericIndexAdapter

    cfg = site_registry.lookup(url)
    if cfg is None:
        raise UnsupportedUrlError(
            f"sổ đăng ký nhận host của {url!r} nhưng `site_registry` không có "
            f"cấu hình — hai nguồn sự thật đã lệch nhau.")
    return GenericIndexAdapter(
        fetcher,
        chapter_href_pattern=cfg.chapter_href_pattern,
        title_suffix_to_strip=cfg.title_suffix_to_strip or None,
    )


def default_registry() -> AdapterRegistry:
    """Sổ đăng ký cho các host mà `site_registry` đã XÁC MINH.

    Danh sách host lấy thẳng từ `site_registry.supported_domains()` chứ không
    chép tay: chép tay thì thêm một site vào `site_registry` mà quên ở đây sẽ
    làm site đó im lặng thành "không hỗ trợ".
    """
    from server.scraper import site_registry

    reg = AdapterRegistry()
    hosts = tuple(normalize_host(d) for d in site_registry.supported_domains())
    if hosts:
        reg.register(AdapterRegistration(
            name="generic_index",
            capabilities=AdapterCapabilities(
                supported_hosts=hosts,
                supports_story_metadata=True,
                supports_chapter_index=True,
                supports_chapter_fetch=True,
                supports_incremental_updates=True,
                requires_browser=False,
                supports_static_fetch=True,
                canonicalization="url_normalized",
                stable_story_identity=True,
                stable_chapter_identity=True,
            ),
            build=_dung_generic,
        ))
    return reg
