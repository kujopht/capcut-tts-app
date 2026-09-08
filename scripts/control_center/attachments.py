"""Tệp đính kèm của ô chat — lưu CỤC BỘ, địa chỉ hoá theo nội dung.

Tầng này KHÔNG import Qt và KHÔNG gọi mạng. Cả hai đều có chủ đích: nhờ vậy
mọi bất biến an toàn dưới đây nằm trong `scripts/tests` và **CI cưỡng chế**
chúng, thay vì chỉ được kiểm bởi bộ kiểm desktop cục bộ.

BỐN BẤT BIẾN, và mỗi cái đều có bài kiểm khoá lại:

1. **Nhị phân KHÔNG vào SQLite.** Sổ chỉ giữ metadata: tên đã làm sạch,
   loại, kích cỡ, `sha256`, đường dẫn TƯƠNG ĐỐI, phạm vi, ai thêm. Nhét
   vài chục MB ảnh vào SQLite làm mọi truy vấn chậm đi và làm bản sao lưu
   phình lên vì một thứ vốn không cần giao dịch.

2. **Đường dẫn lưu trữ do TẦNG NÀY sinh, không bao giờ do frontend đưa.**
   Nó là `objects/<sha[:2]>/<sha><đuôi>` — suy ra hoàn toàn từ băm nội dung
   cộng một đuôi lấy từ ALLOWLIST. Không một byte nào của tên tệp người
   dùng đi vào đường dẫn, nên `../../` hay `C:\\Windows\\...` không có chỗ
   để chen vào. Tên gốc chỉ dùng để HIỂN THỊ.

3. **Đọc phải đi qua `attachment_id`.** `duong_dan()` kiểm lại rằng đường
   dẫn đã resolve nằm TRONG kho, và nâng ngoại lệ nếu không. Frontend không
   có cách nào bảo tầng này đọc một tệp tuỳ ý như thể nó là đính kèm.

4. **Agent chỉ nhận đính kèm được cấp cho ĐÚNG việc của nó.**
   `cho_agent(task_id)` không bao giờ trả cả kho của dự án.

VÀ MỘT ĐIỀU KHÔNG PHẢI BẤT BIẾN KỸ THUẬT MÀ LÀ LỜI HỨA VỚI NGƯỜI DÙNG:
tầng này **không tải tệp lên đâu cả**. Nó chép byte vào một thư mục cạnh sổ
và trả về đường dẫn cục bộ. Nếu sau này có một adapter cần gửi tệp ra nhà
cung cấp, việc đó phải là một bước TƯỜNG MINH ở tầng khác — không được lặng
lẽ xảy ra ở đây.

DÒNG CHẢY (streaming), không nạp hết vào RAM: băm và chép cùng một lượt,
theo khối 1 MiB, vào một tệp tạm trong kho rồi mới đổi tên vào chỗ. Một
người kéo vào đây một tệp 2 GB thì tiến trình cũng chỉ giữ 1 MiB.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Dict, Iterable, List, Optional, Tuple

#: Khoi doc/ghi. 1 MiB: du lon de nhanh, du nho de mot tep 2 GB khong lam
#: tien trinh phinh len.
KHOI = 1024 * 1024

#: Tran MOI tep. Vuot thi TU CHOI — khong cat bot, khong "chac la duoc".
TRAN_MOI_TEP = 200 * 1024 * 1024

#: Tran TONG mot tin nhan, de mot cu keo-tha 50 tep khong lam day dia.
TRAN_MOI_TIN = 500 * 1024 * 1024


class DinhKemLoi(RuntimeError):
    """Từ chối nhận tệp. Luôn kèm lý do đọc được cho người dùng."""


#: Duoi tep -> LOAI. Allowlist, fail closed: khong co trong bang thi tu
#: choi. Danh sach nay la hop dong voi nguoi dung nen no o mot cho duy nhat.
LOAI_THEO_DUOI: Dict[str, str] = {}


def _nap(loai: str, duoi: Iterable[str]) -> None:
    for d in duoi:
        LOAI_THEO_DUOI[d] = loai


_nap("image", ("png", "jpg", "jpeg", "webp", "gif", "bmp"))
_nap("document", ("pdf", "txt", "md", "docx", "rtf", "odt"))
_nap("data", ("csv", "json", "xlsx", "tsv", "xml", "yaml", "yml", "parquet"))
_nap("code", (
    "py", "pyi", "js", "mjs", "cjs", "ts", "tsx", "jsx", "html", "htm",
    "css", "scss", "sql", "sh", "bash", "zsh", "ps1", "psm1", "bat", "cmd",
    "c", "h", "cpp", "hpp", "cc", "cs", "java", "kt", "go", "rs", "rb",
    "php", "swift", "m", "mm", "lua", "pl", "r", "jl", "dart", "vue", "svelte",
))
_nap("config", (
    "toml", "ini", "cfg", "conf", "env_example", "properties", "gradle",
    "dockerfile", "gitignore", "editorconfig", "lock",
))
_nap("log", ("log", "out", "err", "trace"))
_nap("archive", ("zip",))

#: Chu ky byte dau tep. Chi kiem nhung loai co chu ky ON DINH.
#:
#: VI SAO CAN: mot tep ten `anh.png` co the la mot tep thi hanh. Doi duoi
#: tep la thao tac de nhat the gioi, nen tin vao duoi tep la khong tin duoc
#: gi. Cai nay KHONG bien tang nay thanh mot may quet virus — no chi doi
#: hoi duoi tep va noi dung PHAI KHOP NHAU.
CHU_KY: Dict[str, Tuple[bytes, ...]] = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF87a", b"GIF89a"),
    "bmp": (b"BM",),
    "pdf": (b"%PDF-",),
    # zip, va moi thu la zip doi ten: docx/xlsx/odt/parquet-in-zip.
    "zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "odt": (b"PK\x03\x04",),
}

#: `webp` = RIFF....WEBP — chu ky khong lien tuc nen kiem rieng.
def _la_webp(dau: bytes) -> bool:
    return len(dau) >= 12 and dau[:4] == b"RIFF" and dau[8:12] == b"WEBP"


#: Ten bi HE DIEU HANH Windows giu rieng. `CON.txt` cung khong dung duoc.
TEN_DANH_RIENG = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_XAU = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
DAI_TOI_DA_TEN = 120


def lam_sach_ten(ten: str) -> str:
    """Tên để HIỂN THỊ, đã bỏ mọi thứ có thể thoát ra khỏi một thư mục.

    Tên này KHÔNG được dùng để dựng đường dẫn lưu trữ (xem bất biến #2),
    nhưng nó vẫn phải sạch: nó đi vào CSV, vào nhật ký, vào hợp đồng gửi
    cho agent, và có thể được dùng làm tên khi người dùng bấm "Lưu thành".

    Xử lý, theo đúng thứ tự này:
      * chỉ lấy phần TÊN, bỏ mọi thành phần thư mục (kể cả dấu `\\` của
        Windows lẫn `/` của POSIX, vì một tên tới từ clipboard có thể mang
        cả hai);
      * bỏ ký tự điều khiển và ký tự Windows cấm;
      * bỏ dấu chấm/khoảng trắng ở hai đầu (Windows tự cắt chúng, nên
        `..` và `. ` là đường dẫn nguỵ trang);
      * đổi tên dành riêng của hệ điều hành;
      * cắt độ dài nhưng GIỮ đuôi tệp.
    """
    t = (ten or "").replace("\\", "/").split("/")[-1]
    t = _XAU.sub("_", t)
    t = t.strip(" .")
    if not t:
        return "khong_ten"
    goc, duoi = os.path.splitext(t)
    if goc.lower() in TEN_DANH_RIENG:
        goc = "_" + goc
    if len(goc) > DAI_TOI_DA_TEN:
        goc = goc[:DAI_TOI_DA_TEN]
    t = (goc + duoi).strip(" .")
    return t or "khong_ten"


def duoi_cua(ten: str) -> str:
    """Đuôi tệp, chữ thường, không có dấu chấm. `""` nếu không có."""
    d = os.path.splitext(ten or "")[1].lstrip(".").lower()
    return d if d.isalnum() else ""


def loai_cua(ten: str) -> Optional[str]:
    """Loại nội dung theo allowlist, hoặc `None` nếu KHÔNG được phép."""
    return LOAI_THEO_DUOI.get(duoi_cua(ten))


def _kiem_chu_ky(duoi: str, dau: bytes) -> None:
    """Đuôi tệp và nội dung phải khớp nhau. Lệch thì TỪ CHỐI."""
    if duoi == "webp":
        if not _la_webp(dau):
            raise DinhKemLoi(
                "tệp có đuôi .webp nhưng nội dung không phải WebP")
        return
    mau = CHU_KY.get(duoi)
    if not mau:
        return                          # loai van ban: khong co chu ky
    if not any(dau.startswith(m) for m in mau):
        raise DinhKemLoi(
            f"tệp có đuôi .{duoi} nhưng nội dung không khớp định dạng đó")


@dataclass
class DinhKem:
    """Một đính kèm. `duong_dan` KHÔNG nằm ở đây — phải hỏi kho."""

    attachment_id: str
    project_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    rel_path: str
    message_id: Optional[int] = None
    task_id: str = ""
    owner: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "attachment_id": self.attachment_id,
            "project_id": self.project_id,
            "filename": self.filename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "rel_path": self.rel_path,
            "message_id": self.message_id,
            "task_id": self.task_id,
            "owner": self.owner,
            "created_at": self.created_at,
        }

    @property
    def la_anh(self) -> bool:
        return self.media_type == "image"

    def co_doc_duoc(self) -> str:
        """`1.4 MB` — kích cỡ cho người đọc, không phải số byte thô."""
        n = float(self.size_bytes)
        for don in ("B", "KB", "MB", "GB"):
            if n < 1024 or don == "GB":
                return f"{n:.0f} {don}" if don == "B" else f"{n:.1f} {don}"
            n /= 1024
        return f"{n:.1f} GB"


def ma_dinh_kem(project_id: str, message_id: Optional[int], task_id: str,
                sha: str, ten: str) -> str:
    """Mã TẤT ĐỊNH: cùng phạm vi + cùng nội dung + cùng tên -> cùng mã.

    Tất định là yêu cầu tường minh, và nó có một lợi ích cụ thể: dán lại
    đúng một ảnh vào đúng một tin nhắn hai lần thì không sinh ra hai bản
    ghi. Phạm vi nằm TRONG mã nên cùng một tệp gắn vào hai dự án vẫn là hai
    đính kèm khác nhau — đúng như phải vậy, vì quyền truy cập khác nhau.
    """
    thanh = f"{project_id}\x00{message_id if message_id is not None else ''}" \
            f"\x00{task_id}\x00{sha}\x00{ten}"
    return "att_" + hashlib.sha256(thanh.encode("utf-8")).hexdigest()[:24]


class KhoDinhKem:
    """Kho đính kèm cục bộ, địa chỉ hoá theo nội dung.

    `store` là `ControlStore` (để ghi metadata). `goc` là thư mục gốc chứa
    `.router/` — cùng gốc với sổ, nên sao lưu một chỗ là đủ cả hai.
    """

    def __init__(self, store, *, goc: Path,
                 tran_moi_tep: int = TRAN_MOI_TEP):
        self.store = store
        self.goc = Path(goc).resolve()
        self.thu_muc = (self.goc / ".router" / "attachments").resolve()
        self.doi_tuong = self.thu_muc / "objects"
        self.tam = self.thu_muc / "tmp"
        self.tran_moi_tep = int(tran_moi_tep)
        self.doi_tuong.mkdir(parents=True, exist_ok=True)
        self.tam.mkdir(parents=True, exist_ok=True)

    # -- ghi -----------------------------------------------------------------

    def them_tu_tep(self, project_id: str, nguon, *,
                    message_id: Optional[int] = None, task_id: str = "",
                    owner: str = "", ten_hien: str = "") -> DinhKem:
        """Nhận một tệp từ đĩa (kéo-thả, hộp chọn tệp, dán từ Explorer).

        `nguon` là đường dẫn NGƯỜI DÙNG chọn — nó được phép ở bất kỳ đâu
        trên máy, đó là bản chất của kéo-thả. Cái được kiểm là: nó phải
        tồn tại, phải là tệp thường (không phải thư mục/thiết bị/FIFO), và
        byte của nó được CHÉP vào kho. Sau lượt này, đường dẫn gốc không
        còn được ghi nhớ ở đâu cả — nên một tệp bị xoá/đổi sau đó không
        làm đính kèm hỏng, và không có ai giữ một con trỏ tới `C:\\Users\\...`.
        """
        p = Path(nguon)
        try:
            p = p.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise DinhKemLoi(f"không mở được tệp: {exc}") from exc
        if not p.is_file():
            raise DinhKemLoi(f"{p.name!r} không phải một tệp thường")

        ten = lam_sach_ten(ten_hien or p.name)
        loai = loai_cua(ten)
        if loai is None:
            raise DinhKemLoi(
                f"đuôi tệp {duoi_cua(ten)!r} không nằm trong danh sách được "
                f"phép — từ chối để an toàn")

        co = p.stat().st_size
        if co > self.tran_moi_tep:
            raise DinhKemLoi(
                f"tệp {ten!r} nặng {co / 1048576:.0f} MB, vượt trần "
                f"{self.tran_moi_tep / 1048576:.0f} MB")
        if co == 0:
            raise DinhKemLoi(f"tệp {ten!r} rỗng")

        with open(p, "rb") as f:
            return self._nhan_dong(project_id, f, ten, loai,
                                   message_id=message_id, task_id=task_id,
                                   owner=owner)

    def them_tu_bytes(self, project_id: str, du_lieu: bytes, ten: str, *,
                      message_id: Optional[int] = None, task_id: str = "",
                      owner: str = "") -> DinhKem:
        """Nhận dữ liệu đã ở trong RAM — đường của ẢNH TỪ CLIPBOARD.

        Win+Shift+S đặt một bitmap lên clipboard, không phải một tệp; nên
        đường này tồn tại và nó là đường DUY NHẤT được nhận bytes thô.
        """
        import io
        ten = lam_sach_ten(ten)
        loai = loai_cua(ten)
        if loai is None:
            raise DinhKemLoi(f"đuôi tệp {duoi_cua(ten)!r} không được phép")
        if not du_lieu:
            raise DinhKemLoi("không có dữ liệu để đính kèm")
        if len(du_lieu) > self.tran_moi_tep:
            raise DinhKemLoi(
                f"dữ liệu {len(du_lieu) / 1048576:.0f} MB vượt trần")
        return self._nhan_dong(project_id, io.BytesIO(du_lieu), ten, loai,
                               message_id=message_id, task_id=task_id,
                               owner=owner)

    def _nhan_dong(self, project_id: str, f: BinaryIO, ten: str, loai: str,
                   *, message_id: Optional[int], task_id: str,
                   owner: str) -> DinhKem:
        """Băm VÀ chép cùng một lượt, theo khối. Không nạp hết vào RAM."""
        duoi = duoi_cua(ten)
        h = hashlib.sha256()
        co = 0
        tam = self.tam / f"nhan-{os.getpid()}-{time.time_ns()}.part"
        dau = b""
        try:
            with open(tam, "wb") as ra:
                while True:
                    khoi = f.read(KHOI)
                    if not khoi:
                        break
                    if not dau:
                        dau = khoi[:16]
                        # Kiem chu ky NGAY o khoi dau, truoc khi chep het
                        # mot tep 200 MB roi moi phat hien no khong khop.
                        _kiem_chu_ky(duoi, dau)
                    h.update(khoi)
                    co += len(khoi)
                    if co > self.tran_moi_tep:
                        raise DinhKemLoi(
                            f"tệp {ten!r} vượt trần "
                            f"{self.tran_moi_tep / 1048576:.0f} MB")
                    ra.write(khoi)
            if co == 0:
                raise DinhKemLoi(f"tệp {ten!r} rỗng")

            sha = h.hexdigest()
            rel = f"objects/{sha[:2]}/{sha}.{duoi}" if duoi else \
                  f"objects/{sha[:2]}/{sha}"
            dich = (self.thu_muc / rel).resolve()
            self._kiem_trong_kho(dich)
            dich.parent.mkdir(parents=True, exist_ok=True)
            if dich.exists():
                # Da co doi tuong nay: trung noi dung, khong chep lai.
                tam.unlink(missing_ok=True)
            else:
                shutil.move(str(tam), str(dich))
        finally:
            if tam.exists():
                tam.unlink(missing_ok=True)

        dk = DinhKem(
            attachment_id=ma_dinh_kem(project_id, message_id, task_id, sha,
                                      ten),
            project_id=project_id, filename=ten, media_type=loai,
            size_bytes=co, sha256=sha, rel_path=rel, message_id=message_id,
            task_id=task_id, owner=owner)
        self.store.luu_dinh_kem(dk)
        return dk

    def gan_cho_task(self, attachment_id: str, task_id: str) -> bool:
        """Cấp một đính kèm cho MỘT việc.

        Đây là chỗ duy nhất mở quyền cho agent. Gọi nó khi một tin nhắn có
        đính kèm được phân rã thành việc — chỉ những việc sinh ra từ đúng
        tin nhắn đó.
        """
        return self.store.gan_dinh_kem_cho_task(attachment_id, task_id)

    def xoa(self, attachment_id: str) -> bool:
        """Bỏ một đính kèm khỏi sổ, và bỏ blob nếu KHÔNG còn ai tham chiếu.

        Không xoá blob khi còn bản ghi khác cùng `sha256`: hai tin nhắn có
        thể đính kèm đúng một ảnh, và xoá một tin không được làm hỏng tin
        kia.
        """
        dk = self.lay(attachment_id)
        if dk is None:
            return False
        self.store.xoa_dinh_kem(attachment_id)
        if not self.store.dinh_kem_theo_sha(dk.sha256):
            p = (self.thu_muc / dk.rel_path).resolve()
            try:
                self._kiem_trong_kho(p)
                p.unlink(missing_ok=True)
            except DinhKemLoi:
                pass
        return True

    # -- doc -----------------------------------------------------------------

    def lay(self, attachment_id: str) -> Optional[DinhKem]:
        return self.store.dinh_kem(attachment_id)

    def duong_dan(self, attachment_id: str) -> Path:
        """Đường dẫn thật của một đính kèm — cửa DUY NHẤT để đọc byte.

        Kiểm lại rằng nó nằm trong kho, mỗi lần. Bản ghi trong SQLite giữ
        đường dẫn TƯƠNG ĐỐI, nhưng "tương đối" một mình không đủ:
        `../../../Windows/System32/...` cũng là tương đối. Nên phép kiểm là
        so sánh sau khi RESOLVE, không phải kiểm chuỗi.
        """
        dk = self.lay(attachment_id)
        if dk is None:
            raise DinhKemLoi(f"không có đính kèm {attachment_id!r}")
        p = (self.thu_muc / dk.rel_path).resolve()
        self._kiem_trong_kho(p)
        if not p.is_file():
            raise DinhKemLoi(
                f"đính kèm {dk.filename!r} mất tệp trên đĩa — sổ còn, byte "
                f"thì không")
        return p

    def _kiem_trong_kho(self, p: Path) -> None:
        try:
            p.relative_to(self.thu_muc)
        except ValueError as exc:
            raise DinhKemLoi(
                f"TỪ CHỐI: đường dẫn {p} nằm ngoài kho đính kèm "
                f"{self.thu_muc}") from exc

    def kiem_toan_ven(self, attachment_id: str) -> bool:
        """Băm lại byte trên đĩa và so với sổ. Dùng cho bằng chứng."""
        dk = self.lay(attachment_id)
        if dk is None:
            return False
        h = hashlib.sha256()
        with open(self.duong_dan(attachment_id), "rb") as f:
            while True:
                khoi = f.read(KHOI)
                if not khoi:
                    break
                h.update(khoi)
        return h.hexdigest() == dk.sha256

    def cua_message(self, project_id: str,
                    message_id: int) -> List[DinhKem]:
        return self.store.dinh_kem_cua_message(project_id, message_id)

    def cua_project(self, project_id: str) -> List[DinhKem]:
        return self.store.dinh_kem_cua_project(project_id)

    def cho_agent(self, task_id: str) -> List[DinhKem]:
        """Đính kèm mà agent của MỘT việc được đọc. Không hơn.

        Cố ý KHÔNG trả theo dự án. Một agent đang sửa `docs/` không có lý
        do gì đọc ảnh chụp màn hình người dùng dán cho một việc khác, và
        "cùng dự án" là một phạm vi quá rộng để làm ranh giới quyền.
        """
        if not task_id:
            return []
        return self.store.dinh_kem_cua_task(task_id)

    def mo_ta_cho_agent(self, task_id: str) -> str:
        """Đoạn văn bản chèn vào hợp đồng, kèm ĐƯỜNG DẪN CỤC BỘ.

        Agent đọc tệp bằng công cụ đọc tệp của nó trong worktree/`--add-dir`;
        nên nó cần đường dẫn thật. Không có tệp nào được tải lên đâu.
        """
        ds = self.cho_agent(task_id)
        if not ds:
            return ""
        dong = ["", "TỆP ĐÍNH KÈM CHO VIỆC NÀY (đọc tại chỗ, trên đĩa):"]
        for dk in ds:
            dong.append(
                f"  - {dk.filename}  ({dk.media_type}, {dk.co_doc_duoc()}, "
                f"sha256={dk.sha256[:12]}…)")
            dong.append(f"    {self.duong_dan(dk.attachment_id)}")
        return "\n".join(dong)
