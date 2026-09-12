"""Phong bì QUYỀN theo từng việc — Control Center V0.1, yêu cầu #9.

MỤC TIÊU: việc thường lệ KHÔNG hỏi người dùng lần nào; việc nguy hiểm KHÔNG
BAO GIỜ tự chạy. Hai vế đó phải cùng đúng — nới một vế để đạt vế kia là
đúng thứ hỏng mà module này tồn tại để chặn.

    AUTO   đọc/tìm kiếm kho, sửa tệp TRONG worktree mình sở hữu,
           lint/test/build, xem phụ thuộc, commit cục bộ
    GATED  deploy production, thay đổi phá huỷ trên production, IAM/gốc tin
           cậy, xoay/lộ bí mật, thay đổi hoá đơn/mở rộng tài nguyên

BA ĐIỀU MODULE NÀY KHÔNG LÀM, và không được ai làm hộ:

1. **KHÔNG nới rào có sẵn.** Phong bì chỉ biết NÓI KHÔNG. Nó không cấp thêm
   quyền cho ai: `TaskContract` vẫn giữ `destructive_actions_allowed=False`,
   `forbidden_scope` vẫn được `contract.py` nhồi thêm `FORBIDDEN_ALWAYS`, và
   cổng kiểm định của V3 vẫn chạy y nguyên. Đây là tầng thứ BA, không phải
   tầng thay thế.
2. **KHÔNG dùng `--dangerously-skip-permissions`.** `router_v4/executor.py`
   đã đóng cứng `dangerously_skip_permissions=False`; ở đây chỉ nhắc lại
   bằng một bài kiểm để không ai bật nó qua một đường vòng.
3. **KHÔNG tự quyết việc GATED.** Một việc chạm lớp GATED đi thẳng vào
   `BLOCKED` kèm câu hỏi cụ thể cho người dùng. Không có cờ nào trong V0.1
   biến `GATED` thành `AUTO`.

VÌ SAO PHÂN LOẠI BẰNG TỪ KHOÁ, VÀ VÌ SAO NHƯ VẬY LÀ ĐỦ Ở V0.1:

Phân loại chạy trên **ý định người dùng gõ vào** và trên **mục tiêu hợp
đồng** — văn bản, không phải lời gọi hệ thống. Nên nó là một bộ lọc THÔ, và
nó cố ý nghiêng về phía chặn nhầm: một việc bị hỏi thừa tốn của người dùng
mười giây; một lần `deploy` chạy lúc 3 giờ sáng tốn nhiều hơn thế rất nhiều.
Rào THẬT (phạm vi ghi, worktree cô lập, cổng kiểm định, quyền của chính CLI)
nằm ở tầng dưới và không phụ thuộc bộ lọc này.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from scripts.control_center.model import PermissionClass

#: Thao tac AUTO — mo ta de HIEN THI va de kiem, khong phai de cap quyen.
AUTO_OPERATIONS: Tuple[str, ...] = (
    "repo_read",
    "repo_search",
    "edit_in_owned_worktree",
    "run_tests",
    "run_lint",
    "run_build",
    "inspect_dependencies",
    "local_commit",
)

#: Thao tac GATED — cham vao la DUNG, hoi nguoi dung.
GATED_OPERATIONS: Tuple[str, ...] = (
    "production_deploy",
    "production_mutation",
    "iam_change",
    "secret_rotation",
    "secret_disclosure",
    "billing_change",
    "resource_expansion",
    "history_rewrite",
    "remote_push",
)

#: Mau nhan dien lop GATED tu VAN BAN. Tieng Viet va tieng Anh — nguoi dung
#: kho nay gõ ca hai, va mot bo loc chi biet mot thu tieng se lot dung
#: nhung cau nguy hiem nhat.
#:
#: Moi mau ANH XA toi mot thao tac GATED co ten, de cau hoi gui nguoi dung
#: noi duoc CU THE viec gi bi chan chu khong chi "co gi do nguy hiem".
_MAU_GATED: Tuple[Tuple[str, re.Pattern], ...] = (
    # "TRIỂN KHAI" MỘT MÌNH KHÔNG PHẢI MỘT LẦN DEPLOY.
    #
    # Trong tiếng Việt kỹ thuật, "triển khai" gần như luôn nghĩa là
    # *implement* — "triển khai tính năng", "ok triển khai phần repo-local đó
    # đi". Nghĩa *deploy* chỉ xuất hiện khi có một ĐÍCH production đi kèm:
    # "triển khai lên production", "triển khai worker".
    #
    # Bản trước liệt kê `triển khai` như một lựa chọn TRẦN, và hậu quả đo
    # được ở nghiệm thu thật V0.9 (2026-09-11): câu uỷ quyền
    # "ok triển khai phần repo-local đó đi" bị xếp `production_deploy` và
    # dừng ở `WAITING_AUTHORITY` — tức là KHÔNG CÒN cách nào nói bằng tiếng
    # Việt để cho phép một việc trong kho. Vòng kín mất đúng lối vào chính
    # của nó.
    #
    # Đây là CÙNG MỘT LỚP LỖI mà `docs/CONTROL_CENTER.md` §20 (luật 22-24) đã
    # sửa một lần cho phân loại bảo mật: **một TỪ ĐƠN không được làm trọng
    # tài**. Nay nó được phân loại bằng CỤM TỪ, đúng nguyên tắc đó.
    #
    # KHÔNG nới cho các dạng nguy hiểm: `deploy`, `cutover`, `go-live`,
    # `wrangler deploy`, `cf:deploy`, `lên production` vẫn khớp TRẦN như cũ;
    # và tầng dưới (`Bash(npx wrangler deploy)` deny, hook, cổng GATED của
    # việc) không đổi một dòng nào.
    ("production_deploy", re.compile(
        r"\b(deploy|deployment|cutover|go[\s-]?live|ship to prod|"
        r"publish to production|wrangler\s+deploy|cf:deploy|"
        r"len production|lên production|day len prod|đẩy lên prod)\b"
        r"|\btri[eể]n\s+khai\b(?:\s+\w+){0,3}\s+"
        r"(?:production|prod|staging|server|m[aá]y\s+ch[uủ]|worker|farmer|"
        r"fanfic\.world|cloudflare|render|r2|appwrite|drive|gce|ec2)\b",
        re.I)),
    ("production_mutation", re.compile(
        r"\b(drop\s+(table|database)|truncate\s+table|delete\s+from\s+prod|"
        r"prod(uction)?\s+(db|database|data)\s+(wipe|reset|delete|purge)|"
        r"xoa\s+du\s+lieu|xoá\s+dữ\s+liệu|reset\s+production)\b", re.I)),
    ("iam_change", re.compile(
        r"\b(iam|service\s+account|role\s+binding|grant\s+role|"
        r"api\s+token\s+create|root\s+of\s+trust|acl\s+change|"
        r"phan\s+quyen|phân\s+quyền|cap\s+quyen|cấp\s+quyền)\b", re.I)),
    # Cho phep toi 3 tu chen giua dong tu va danh tu: "rotate the R2 secret",
    # "reissue the production api key". Doi hai tu dinh nhau se de lot dung
    # cach nguoi ta thuc su viet cau — da vap that o bai kiem khoi dau.
    ("secret_rotation", re.compile(
        r"\b(?:rotate|re[\s-]?issue|regenerate|revoke)\s+(?:\w+\s+){0,3}"
        r"(?:secret|key|keys|token|tokens|credential|credentials)\b"
        r"|\bsecret\s+rotation\b"
        r"|\bxoay\s+(?:\w+\s+){0,2}(?:bi\s+mat|bí\s+mật|khoa|khoá|token)\b",
        re.I)),
    ("secret_disclosure", re.compile(
        r"\b(?:print|echo|dump|reveal|show|paste|expose)\s+(?:\w+\s+){0,3}"
        r"(?:secret|secrets|token|tokens|api[\s_-]?key|password|credential|"
        r"credentials)\b", re.I)),
    ("billing_change", re.compile(
        r"\b(billing|invoice|purchase\s+credits?|buy\s+credits?|"
        r"upgrade\s+plan|enable\s+overage|paid\s+tier|"
        r"mua\s+credit|nang\s+goi|nâng\s+gói|thanh\s+toan|thanh\s+toán)\b",
        re.I)),
    ("resource_expansion", re.compile(
        r"\b(provision|scale\s+up|create\s+(instance|cluster|bucket|vm)|"
        r"new\s+(gce|ec2|cloud\s+run)\s+(instance|service)|"
        r"terraform\s+apply|cap\s+phat\s+may|cấp\s+phát\s+máy)\b", re.I)),
    ("history_rewrite", re.compile(
        r"\b(force[\s-]?push|push\s+--force|git\s+reset\s+--hard\s+origin|"
        r"rebase\s+.*\bmain\b.*--force|filter[\s-]?branch|"
        r"xoa\s+lich\s+su|xoá\s+lịch\s+sử)\b", re.I)),
    ("remote_push", re.compile(
        r"\b(git\s+push|push\s+to\s+(github|origin|remote)|"
        r"open\s+a\s+pull\s+request|create\s+pr\b|"
        r"day\s+len\s+github|đẩy\s+lên\s+github)\b", re.I)),
)


@dataclass(frozen=True)
class GateHit:
    """Một lần chạm lớp GATED, kèm BẰNG CHỨNG là đoạn văn bản đã khớp."""

    operation: str
    matched: str

    def render(self) -> str:
        return f"{self.operation} (khớp: {self.matched!r})"


@dataclass(frozen=True)
class PermissionEnvelope:
    """Quyền của MỘT việc. Bất biến — dựng một lần, không sửa tại chỗ.

    Một phong bì sửa được sau khi dựng là một phong bì có thể bị nới ở giữa
    đường chạy, và lúc đó không ai dựng lại được nó đã cho phép những gì.
    """

    task_id: str
    decision: PermissionClass
    auto_operations: Tuple[str, ...] = AUTO_OPERATIONS
    gate_hits: Tuple[GateHit, ...] = ()
    #: Pham vi ghi ma viec nay SO HUU. Ngoai day la vi pham, du la AUTO.
    owned_scope: Tuple[str, ...] = ()

    @property
    def auto(self) -> bool:
        return self.decision is PermissionClass.AUTO

    @property
    def gated(self) -> bool:
        return self.decision is PermissionClass.GATED

    @property
    def gated_operations(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(h.operation for h in self.gate_hits))

    def ly_do(self) -> str:
        if self.auto:
            return ""
        return "; ".join(h.render() for h in self.gate_hits)

    def cau_hoi_cho_nguoi_dung(self) -> str:
        """Câu hỏi CỤ THỂ, không phải một cảnh báo chung chung.

        Người dùng đọc dòng này lúc vừa ngủ dậy. Nó phải nói được: việc nào,
        chạm cổng nào, và cần họ quyết định điều gì.
        """
        if self.auto:
            return ""
        ops = ", ".join(self.gated_operations)
        return (
            f"Việc {self.task_id} chạm lớp GATED ({ops}). Control Center "
            f"KHÔNG tự chạy loại thao tác này. Cần bạn xác nhận rõ ràng "
            f"trước khi nó được đưa lại vào hàng đợi. Bằng chứng khớp: "
            f"{self.ly_do()}")

    def render_for_agent(self) -> str:
        """Khối văn bản chèn vào hợp đồng gửi agent.

        Agent PHẢI biết ranh giới của nó bằng chữ, không chỉ bằng việc lệnh
        bị từ chối — một agent không biết vì sao mình bị chặn sẽ thử một
        đường vòng khác thay vì dừng lại và báo `blocked`.
        """
        d = ["PERMISSION_ENVELOPE (phong bì quyền của việc này):",
             "  ĐƯỢC TỰ LÀM, không phải hỏi:"]
        # V0.9.3 — DUNG QUANG CAO MOT QUYEN MA PHONG BI NAY KHONG CAP.
        #
        # `AUTO_OPERATIONS` la danh sach CO DINH de hien thi, nen mot viec chi
        # doc van in ra `edit_in_owned_worktree` ngay tren dong "KHONG so huu
        # pham vi ghi nao — chi doc". Hai dong canh nhau noi nguoc nhau, va
        # agent phai tu doan dong nao that. Thay vi bat no doan: viec khong co
        # pham vi ghi thi khong liet ke thao tac ghi.
        _ghi = {"edit_in_owned_worktree", "local_commit"}
        d += [f"    - {o}" for o in self.auto_operations
              if self.owned_scope or o not in _ghi]
        if self.owned_scope:
            d += ["  Chỉ được GHI trong phạm vi sở hữu:"]
            d += [f"    - {p}" for p in self.owned_scope]
        else:
            d += ["  Việc này KHÔNG sở hữu phạm vi ghi nào — chỉ đọc."]
        d += ["  TUYỆT ĐỐI KHÔNG tự làm (dừng và trả `blocked` kèm "
              "`requires_decision=true`):"]
        d += [f"    - {o}" for o in GATED_OPERATIONS]
        d += ["  Gặp bất kỳ mục nào ở trên: ĐỪNG tìm đường vòng, ĐỪNG đoán ý "
              "người dùng. Trả `blocked` và nói rõ cần quyết định gì."]
        return "\n".join(d)

    def to_dict(self) -> Dict:
        return {"task_id": self.task_id, "decision": self.decision.value,
                "auto_operations": list(self.auto_operations),
                "gated_operations": list(self.gated_operations),
                "gate_hits": [{"operation": h.operation, "matched": h.matched}
                              for h in self.gate_hits],
                "owned_scope": list(self.owned_scope),
                "reason": self.ly_do()}


def do_gated(*texts: str) -> Tuple[GateHit, ...]:
    """Quét văn bản tìm lớp GATED. Trả về MỌI lần chạm, không chỉ lần đầu.

    Trả hết có chủ đích: một câu vừa `deploy` vừa `rotate secret` cần hiện
    ra cả hai, vì người dùng có thể đồng ý một nửa.
    """
    ra: List[GateHit] = []
    for t in texts:
        if not t:
            continue
        for op, mau in _MAU_GATED:
            for m in mau.finditer(t):
                doan = m.group(0).strip()
                if not any(h.operation == op and h.matched == doan for h in ra):
                    ra.append(GateHit(operation=op, matched=doan[:80]))
    return tuple(ra)


def classify(*texts: str) -> PermissionClass:
    return PermissionClass.GATED if do_gated(*texts) else PermissionClass.AUTO


def envelope_for(task_id: str, *, objective: str = "", intent: str = "",
                 owned_scope: Sequence[str] = ()) -> PermissionEnvelope:
    """Dựng phong bì cho một việc từ mục tiêu + ý định gốc của người dùng.

    Quét CẢ HAI: bộ lập kế hoạch có thể diễn đạt lại ý định thành một mục
    tiêu nghe vô hại ("cập nhật cấu hình worker") trong khi câu gốc của
    người dùng nói rõ "deploy". Chỉ quét mục tiêu là bỏ lọt đúng trường hợp
    nguy hiểm nhất.

    KHOẢNG TRỐNG ĐÃ BIẾT (đo 2026-09-12, V0.9.3, **chưa sửa** — có chủ ý):
    khi Leader uỷ thác việc, `engine` truyền `intent` = mục tiêu **do Leader
    viết lại**, nên cả hai tham số trên đều là văn bản của Leader và câu gốc
    người dùng chưa bao giờ được quét ở đây. Đúng cái Leader có thể làm dịu
    đi lại là thứ duy nhất không ai đọc.

    Vì sao chưa vá trong V0.9.3: vá bằng cách quét thêm câu người dùng làm
    câu THẬT của họ — *"Chỉ repo-local, KHÔNG deploy"* — thành GATED, vì chữ
    `deploy` khớp mẫu bất kể chữ "không" đứng ngay trước. Sửa cho đúng thì
    phải dạy `do_gated` hiểu phủ định, tức là NỚI một bộ lọc an toàn — việc
    đó cần một lần xem xét riêng, không đi kèm một bản vá phạm vi ghi. Ghi
    lại ở `docs/reports/V093_WRITE_SCOPE.md`.
    """
    hits = do_gated(objective, intent)
    return PermissionEnvelope(
        task_id=task_id,
        decision=PermissionClass.GATED if hits else PermissionClass.AUTO,
        gate_hits=hits, owned_scope=tuple(owned_scope))


# ==========================================================================
# THAM QUYEN GHI REPO-LOCAL — V0.9.3
# ==========================================================================
#
# KHUYET TAT DO DUOC (RouterDogfood02, 2026-09-12): nguoi dung go
#
#     "ok trien khai luon web todo theo ke hoach vua lap. Tu code, chay test
#      va verify tu dau toi cuoi. Chi repo-local, khong deploy."
#
# Leader hieu DUNG (y_dinh=WORK, `delegate_work`). Nhung goi viec gui worker
# ra `type: analysis` + `ALLOWED_SCOPE: (khong)`, nen worker BI CHAN — dung
# dieu kien dung "phai ghi ra ngoai ALLOWED_SCOPE de lam xong viec". Worker
# lam DUNG; tang tren cap SAI quyen.
#
# VI SAO: `engine` goi `planner.plan(goal, project)` — CHI mot chuoi muc
# tieu. Su that "nguoi dung vua cho phep ghi trong kho" duoc tinh o tang
# Leader roi VUT DI, va bo lap ke hoach tu suy lai pham vi ghi bang regex
# tren mot menh de. Khong co duong dan trong cau + du an chua khai
# `default_write_scope` -> ha xuong CHI DOC.
#
# Voi du an TAO MOI bang V0.9.2 thi `default_write_scope` LUON rong, nen moi
# du an moi deu KHONG BAO GIO trien khai duoc. Do la mot NGO CUT.
#
# LAI LA HAI CAI NHIN VE MOT SU THAT: `planner._Y_GHI` da biet "trien khai"
# la dong tu GHI, va `y_dinh.LopThamQuyen.REPO_LOCAL` da dinh nghia dung
# "sua trong worktree cua minh" la thu nguoi dung cho phep khi noi "lam di" —
# ma tang cap quyen lai tin mot thu thu ba: co duong dan trong cau hay khong.

#: Cau NGUOI DUNG go de CHO PHEP trien khai trong kho. Co y HEP: day la mot
#: phep CAP QUYEN, khong phai mot bo doan y. Khong khop thi giu nguyen hanh
#: vi cu (ha xuong chi doc) — an toan van la mac dinh.
_CHO_PHEP_GHI = re.compile(
    r"(?:"
    r"triển khai|trien khai|"
    r"implement|"
    r"tự code|tu code|code nó|code no|code luôn|code luon|"
    r"viết code|viet code|"
    r"làm luôn|lam luon|làm đi|lam di|làm tiếp|lam tiep|"
    r"xây dựng|xay dung|"
    r"go ahead|just do it"
    r")", re.I)


@dataclass(frozen=True)
class ThamQuyenGhi:
    """Người dùng có cho phép GHI TRONG KHO ở lượt này không, và vì sao.

    Mang theo BẰNG CHỨNG chứ không chỉ một cờ: phạm vi ghi suy ra từ đây đi
    thẳng vào hợp đồng gửi agent, nên bản kiểm toán phải nói được *câu nào*
    của người dùng đã mở nó.
    """

    cho_phep: bool = False
    #: cau_nguoi_dung | khong_co | ngoai_kho | chua_uy_thac
    nguon: str = "khong_co"
    bang_chung: str = ""

    def to_dict(self) -> Dict:
        return {"cho_phep": self.cho_phep, "nguon": self.nguon,
                "bang_chung": self.bang_chung}


def tham_quyen_ghi_repo(cau_nguoi_dung: str, *,
                        da_uy_thac: bool = False) -> ThamQuyenGhi:
    """Giải quyền GHI REPO-LOCAL từ CHÍNH câu người dùng gõ.

    BA điều kiện, thiếu một là KHÔNG cấp:

    1. **Leader đã quyết uỷ thác việc.** Một câu bàn luận có chữ "triển khai"
       không được tự mở quyền ghi — §22, *THẢO LUẬN ≠ THỰC THI*.
    2. **Câu người dùng có lời cho phép tường minh.** Quét câu NGƯỜI DÙNG gõ,
       KHÔNG quét lời Leader diễn đạt lại: để Leader tự viết ra quyền của
       chính nó là đúng cái vòng lặp mà `envelope_for` đã từ chối.

    RANH GIỚI NGOÀI KHO **KHÔNG** ĐƯỢC XỬ Ở ĐÂY, và đó là quyết định quan
    trọng nhất của hàm này. Chủ sở hữu duy nhất của sự thật "việc này chạm
    lớp GATED" là `envelope_for`/`do_gated`, chấm trên TỪNG VIỆC. Dựng thêm
    một phép kiểm thứ hai ở đây chính là tái tạo đúng căn bệnh V0.9.3 sinh ra
    để chữa — và bản nháp đầu của chính hàm này đã mắc: nó `do_gated` câu
    người dùng, rồi từ chối cấp quyền cho câu THẬT

        "…Chỉ repo-local, KHÔNG deploy."

    vì chữ `deploy` khớp mẫu, bất kể chữ "không" ngay trước. Người dùng nói
    *đừng* deploy và bị đọc thành *hãy* deploy.

    Bỏ phép kiểm đó là AN TOÀN vì phạm vi ghi chỉ có nghĩa khi việc được
    chạy: một việc chạm GATED bị `envelope_for` chặn thành `BLOCKED` kèm
    `requires_decision` và không bao giờ được giao. Phạm vi cấp ở đây cũng
    chưa bao giờ nới được một thao tác GATED — nó chỉ là repo-local.

    Cấp rồi thì phạm vi vẫn CÓ TRẦN: gốc cây làm việc CỦA CHÍNH VIỆC ĐÓ (một
    worktree cô lập), không phải quyền ghi không giới hạn.
    """
    cau = cau_nguoi_dung or ""
    if not da_uy_thac:
        return ThamQuyenGhi(nguon="chua_uy_thac")
    m = _CHO_PHEP_GHI.search(cau)
    if not m:
        return ThamQuyenGhi(nguon="khong_co")
    return ThamQuyenGhi(cho_phep=True, nguon="cau_nguoi_dung",
                        bang_chung=m.group(0)[:80])
