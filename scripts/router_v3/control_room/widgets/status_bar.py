"""Widget thanh trạng thái và phím tắt — Router V4 Control Room."""
from __future__ import annotations

from rich.text import Text
from textual.app import RenderResult
from textual.widget import Widget


class StatusBarWidget(Widget):
    """Thanh điều khiển nhanh + CHỈ BÁO SỨC KHOẺ ĐỌC dưới đáy màn hình.

    Chỉ báo sức khoẻ tồn tại vì `refresh_state()` từng nuốt mọi lỗi: bảng
    điều khiển vẽ lại số liệu cũ và trông bình thường trong khi việc đọc
    trạng thái đã hỏng. Một dòng luôn nhìn thấy được nói "đọc được hay
    không, và từ nguồn nào" là thứ chặn chuyện đó.
    """

    DEFAULT_CSS = """
    StatusBarWidget {
        height: 1;
        dock: bottom;
        background: #1f2335;
        color: #c0caf5;
        padding: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._errors: list = []
        self._failures: int = 0
        self._source: str = ""
        self._last_error: str = ""

    def set_health(self, *, errors: list, failures: int = 0,
                   source: str = "", last_error: str = "") -> None:
        """Nhận chỉ báo từ `app.refresh_state`. Văn bản ĐÃ được lọc bí mật
        ở phía gọi (`packet.redact`) — widget không tự lọc lại, nhưng cũng
        KHÔNG BAO GIỜ hiển thị gì ngoài những gì được truyền vào."""
        self._errors = list(errors or [])
        self._failures = int(failures or 0)
        self._source = source or ""
        self._last_error = last_error or ""
        self.refresh()

    @property
    def healthy(self) -> bool:
        return not self._errors and self._failures == 0

    def render(self) -> RenderResult:
        text = Text()
        # CHI BAO SUC KHOE truoc phim tat: no la thu nguoi van hanh phai
        # thay ngay, khong phai thu phai di tim.
        if self._failures or self._errors:
            text.append(" ! DOC LOI ", style="bold white on #f7768e")
            chi_tiet = self._last_error or (self._errors[0] if self._errors
                                            else "")
            if self._failures:
                text.append(f" x{self._failures} ", style="#f7768e")
            if chi_tiet:
                text.append(f" {chi_tiet[:70]} ", style="#ff9e64")
            text.append("  ")
        elif self._source:
            nhan = ("DATA: runtime THAT" if self._source == "fabric_v4"
                    else f"DATA: {self._source} (DU PHONG — co the CU)")
            style = ("bold black on #9ece6a" if self._source == "fabric_v4"
                     else "bold black on #e0af68")
            text.append(f" {nhan} ", style=style)
            text.append("  ")

        bindings = [
            ("Enter", "detail"),
            ("E", "explain"),
            ("L", "logs"),
            ("D", "drain"),
            ("R", "retry"),
            ("P", "pause"),
            ("W", "worktrees"),
            ("F", "filter"),
            ("Tab", "focus"),
            ("Q", "quit"),
        ]
        for key, desc in bindings:
            text.append(f" {key} ", style="bold black on #7aa2f7")
            text.append(f" {desc}  ", style="white")
        return text
