"""Ý ĐỊNH -> VIỆC ĐƯỢC QUẢN LÝ — Control Center V0.1, yêu cầu #2.

Người dùng gõ vào ô chat của dự án:

    "finish the production web and separately investigate AWS cleanup"

và phải nhận về HAI việc độc lập, mỗi việc có hợp đồng, phạm vi, phong bì
quyền và tài nguyên cần khoá — không phải một dòng chữ đợi người đọc.

HAI BỘ LẬP KẾ HOẠCH, và vì sao bản mặc định là bản THEO LUẬT:

    `RulePlanner`   tất định, chạy offline, không tốn quota, kiểm được bằng
                    bài kiểm. LÀ MẶC ĐỊNH.
    `RouterPlanner` nhờ một worker rẻ của Router V4 phân rã, rồi ÉP kết quả
                    qua đúng bộ kiểm của `RulePlanner`. Tốt hơn khi có mạng;
                    phải bật tường minh.

Bản theo luật là mặc định có chủ đích. Ô chat là CỔNG VÀO của mọi thứ khác:
nếu nó chỉ hoạt động khi có mạng và còn quota, thì cả Control Center chỉ
hoạt động khi có mạng và còn quota. `RouterPlanner` luôn lùi về
`RulePlanner` khi worker trả rác — và nó KHÔNG được nới bất kỳ rào an toàn
nào: phong bì quyền và phạm vi vẫn do tầng này quyết, không do worker.

MỘT PHỤ THUỘC SAI TỐN HƠN MỘT PHỤ THUỘC THIẾU:

Với liên từ mơ hồ ("and", "và"), bản này chọn ĐỘC LẬP. Lý do: một phụ thuộc
thừa nối tiếp hai việc vốn chạy song song được — mất đúng thứ Control Center
tồn tại để có. Còn một phụ thuộc thiếu giữa hai việc thật sự đụng nhau thì
đã có `LockManager` bắt bằng tài nguyên THẬT chứ không bằng suy đoán ngữ
pháp. Bắt bằng khoá đúng hơn bắt bằng liên từ.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from scripts.router_v4.capabilities import Priority, Reasoning, Requirements
from scripts.router_v4.contract import Execution, TaskContract, Verification
from scripts.control_center.model import (LockKind, PermissionClass, Project,
                                          Task, TaskState)
from scripts.control_center.permissions import PermissionEnvelope, envelope_for

# ---------------------------------------------------------------------------
# Tu vung
# ---------------------------------------------------------------------------

#: Lien tu bao viec sau PHU THUOC viec truoc.
_NOI_TIEP = re.compile(
    r"(?:^|[\s,;])(?:then|after that|afterwards|once that(?:'s| is) done|"
    r"followed by|sau đó|sau do|rồi thì|roi thi|tiếp theo|tiep theo)(?=[\s,:])",
    re.I)

#: Lien tu bao viec sau DOC LAP hoan toan.
_DOC_LAP = re.compile(
    r"(?:^|[\s,;])(?:and separately|separately|in parallel|meanwhile|"
    r"at the same time|đồng thời|dong thoi|song song|riêng|rieng|"
    r"tách riêng|tach rieng)(?=[\s,:])", re.I)

#: Dau tach cung — xuong dong, gach dau dong, dau cham phay.
_TACH_CUNG = re.compile(r"(?:\r?\n\s*[-*•]\s*|\r?\n{2,}|;\s*)")

#: Loai viec suy ra tu dong tu. Thu tu QUAN TRONG: mau dung truoc thang.
_LOAI_VIEC: Tuple[Tuple[str, re.Pattern], ...] = (
    ("review", re.compile(
        r"\b(review|audit|kiểm tra lại|kiem tra lai|soát|soat|thẩm định)\b", re.I)),
    ("testing", re.compile(
        r"\b(test|tests|testing|unit test|viết test|viet test|kiểm thử|"
        r"kiem thu|coverage)\b", re.I)),
    ("analysis", re.compile(
        r"\b(investigate|analy[sz]e|analysis|research|explore|survey|"
        r"look into|find out|figure out|diagnose|inspect|assess|"
        r"điều tra|dieu tra|phân tích|phan tich|khảo sát|khao sat|"
        r"tìm hiểu|tim hieu|rà soát|ra soat|chẩn đoán|chan doan)\b", re.I)),
    ("documentation", re.compile(
        r"\b(document|write docs?|readme|changelog|handoff|"
        r"viết tài liệu|viet tai lieu|tài liệu hoá)\b", re.I)),
    ("implementation", re.compile(
        r"\b(finish|complete|implement|build|add|create|fix|refactor|migrate|"
        r"wire up|hook up|clean ?up|update|improve|port|"
        r"hoàn thiện|hoan thien|hoàn thành|hoan thanh|làm xong|lam xong|"
        r"triển khai code|viết|viet|sửa|sua|thêm|them|tạo|tao|dọn|don)\b",
        re.I)),
)

#: Viec CHI DOC — khong xin `repo_write`, khong can worktree.
_CHI_DOC = frozenset({"analysis", "review"})

#: Duong dan trong cau: `web/admin/content-queue`, `server/tts_bridge.py`.
#: Doi hoi it nhat mot dau `/` de khong bat nham moi tu thuong.
_DUONG_DAN = re.compile(r"\b([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.*-]+)+/?)")

#: Dau hieu RUI RO CAO -> can suy luan manh hon.
_RUI_RO_CAO = re.compile(
    r"\b(production|prod|security|auth|authentication|permission|migration|"
    r"schema|concurrency|race|incident|outage|payment|billing|"
    r"sản xuất|san xuat|bảo mật|bao mat|xác thực|xac thuc|di trú|di tru)\b",
    re.I)

#: Dau hieu can NGU CANH DAI (nhieu tep / toan kho).
_NGU_CANH_DAI = re.compile(
    r"\b(across the (repo|codebase)|whole (repo|codebase)|repo-?wide|"
    r"every (file|module)|all (files|modules|providers)|"
    r"toàn kho|toan kho|toàn bộ|toan bo)\b", re.I)


def _bo_lien_tu(s: str) -> str:
    s = _NOI_TIEP.sub(" ", s)
    s = _DOC_LAP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" ,;.:")


def _tieu_de(s: str, *, max_len: int = 70) -> str:
    t = re.sub(r"\s+", " ", s).strip()
    if len(t) <= max_len:
        return t
    return t[:max_len - 1].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------------------
# Ket qua
# ---------------------------------------------------------------------------

@dataclass
class PlannedTask:
    """Một việc đã phân rã, TRƯỚC khi chạm sổ."""

    task_id: str
    title: str
    objective: str
    kind: str
    contract: TaskContract
    envelope: PermissionEnvelope
    dependencies: Tuple[str, ...] = ()
    resources: Tuple[Tuple[LockKind, str], ...] = ()
    priority: int = 50
    scope_inferred: bool = False
    note: str = ""

    @property
    def gated(self) -> bool:
        return self.envelope.gated

    def to_dict(self) -> Dict:
        return {"task_id": self.task_id, "title": self.title, "kind": self.kind,
                "objective": self.objective,
                "dependencies": list(self.dependencies),
                "resources": [[k.value, r] for k, r in self.resources],
                "permission": self.envelope.decision.value,
                "scope": list(self.contract.allowed_scope),
                "scope_inferred": self.scope_inferred,
                "read_only": not self.contract.requirements.repo_write,
                "priority": self.priority, "note": self.note}


@dataclass
class PlanResult:
    intent: str
    tasks: List[PlannedTask] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    planner: str = "rule"

    @property
    def gated_tasks(self) -> List[PlannedTask]:
        return [t for t in self.tasks if t.gated]

    def render(self) -> str:
        """Câu trả lời Router gửi lại vào ô chat.

        Viết cho người vừa gõ một câu và muốn biết ngay: nó hiểu thành mấy
        việc, việc nào chạy được luôn, việc nào đang chờ mình.
        """
        if not self.tasks:
            return ("Chưa tách được việc nào từ câu này. Thử nói rõ hơn mục "
                    "tiêu, hoặc tách thành từng ý bằng xuống dòng.")
        d = [f"Đã tách thành {len(self.tasks)} việc "
             f"(bộ lập kế hoạch: {self.planner}):"]
        for t in self.tasks:
            co = "CHỈ ĐỌC" if not t.contract.requirements.repo_write else \
                 "GHI " + ",".join(t.contract.allowed_scope)
            phu = f" ← sau {', '.join(t.dependencies)}" if t.dependencies else ""
            gate = "  ⛔ GATED — chờ bạn xác nhận" if t.gated else ""
            d.append(f"  • [{t.task_id}] {t.title}")
            d.append(f"      {t.kind} · {co}{phu}{gate}")
        if self.gated_tasks:
            d.append("")
            d.append("CẦN BẠN QUYẾT ĐỊNH (đã đưa vào BLOCKED, không tự chạy):")
            for t in self.gated_tasks:
                d.append(f"  - {t.envelope.cau_hoi_cho_nguoi_dung()}")
        for n in self.notes:
            d.append(f"  (ghi chú) {n}")
        return "\n".join(d)

    def to_dict(self) -> Dict:
        return {"intent": self.intent, "planner": self.planner,
                "tasks": [t.to_dict() for t in self.tasks],
                "notes": list(self.notes)}


# ---------------------------------------------------------------------------
# Bo lap ke hoach theo LUAT
# ---------------------------------------------------------------------------

@dataclass
class _Menh_de:
    text: str
    doc_lap: bool


class RulePlanner:
    """Phân rã ý định bằng luật. Tất định, offline, kiểm được."""

    name = "rule"

    def __init__(self, *, default_write_scope: Sequence[str] = ()):
        #: Pham vi ghi mac dinh khi cau khong noi ro duong dan nao. Rong =
        #: khong doan; viec se thanh CHI DOC kem ghi chu.
        self.default_write_scope = tuple(default_write_scope)

    # -- tach menh de -------------------------------------------------------

    def tach(self, intent: str) -> List[_Menh_de]:
        """Cắt ý định thành mệnh đề + đánh dấu độc lập/nối tiếp.

        Cắt theo dấu CỨNG trước (xuống dòng, gạch đầu dòng, `;`) rồi mới xét
        liên từ bên trong từng mảnh. Làm ngược lại sẽ để một liên từ trong
        dòng thứ hai gắn nhầm vào dòng thứ nhất.
        """
        ra: List[_Menh_de] = []
        for tho in _TACH_CUNG.split(intent or ""):
            tho = tho.strip()
            if not tho:
                continue
            ra.extend(self._tach_lien_tu(tho, dau_dong=not ra))
        return [m for m in ra if m.text]

    def _tach_lien_tu(self, s: str, *, dau_dong: bool) -> List[_Menh_de]:
        # Tim moi vi tri lien tu, giu lai LOAI cua no.
        moc: List[Tuple[int, int, bool]] = []
        for m in _DOC_LAP.finditer(s):
            moc.append((m.start(), m.end(), True))
        for m in _NOI_TIEP.finditer(s):
            moc.append((m.start(), m.end(), False))
        # "and" tran: chi tach khi hai ben deu du dai de la mot menh de that.
        for m in re.finditer(r"(?:^|\s),?\s*(?:and|và|va)\s(?=\S)", s, re.I):
            if any(a <= m.start() < b for a, b, _ in moc):
                continue
            # Hai dieu kien, va dieu kien thu hai moi la thu quan trong.
            #
            # (a) hai ben deu du dai de la mot menh de THAT (>= 2 tu).
            # (b) VE PHAI PHAI BAT DAU BANG MOT DONG TU cong viec.
            #
            # Khong co (b), "and" noi hai DANH TU bi cat nham thanh hai viec.
            # Do that 2026-09-08 tren mot cau nguoi dung go that:
            #
            #   "investigate the auth and permission checks in
            #    scripts/control_center/permissions.py"
            #
            # bi cat thanh "investigate the auth" + "permission checks in
            # ..." — ve trai la mot manh cau vo nghia, va Router dispatch no
            # nhu mot viec that. "auth and permission" la MOT cum danh tu,
            # khong phai hai menh de.
            #
            # Doi ve phai mo dau bang dong tu ("update ...", "investigate
            # ...", "viet ...") giai dung ca hai kieu, va giai bang dung thu
            # von phan biet chung.
            trai, phai = s[:m.start()].strip(), s[m.end():].strip()
            if len(trai.split()) < 2 or len(phai.split()) < 2:
                continue
            if not any(mau.match(phai) for _ten, mau in _LOAI_VIEC):
                continue
            moc.append((m.start(), m.end(), True))
        moc.sort()

        if not moc:
            return [_Menh_de(_bo_lien_tu(s), doc_lap=dau_dong)]
        ra: List[_Menh_de] = []
        vt = 0
        doc_lap_dau = dau_dong
        for a, b, doc_lap in moc:
            phan = s[vt:a].strip()
            if phan:
                ra.append(_Menh_de(_bo_lien_tu(phan), doc_lap=doc_lap_dau))
                doc_lap_dau = doc_lap
            else:
                doc_lap_dau = doc_lap
            vt = b
        cuoi = s[vt:].strip()
        if cuoi:
            ra.append(_Menh_de(_bo_lien_tu(cuoi), doc_lap=doc_lap_dau))
        if ra:
            ra[0].doc_lap = True            # menh de dau khong phu thuoc ai
        return ra

    # -- phan loai ----------------------------------------------------------

    @staticmethod
    def loai_viec(s: str) -> str:
        for ten, mau in _LOAI_VIEC:
            if mau.search(s):
                return ten
        return "analysis"                   # mac dinh AN TOAN NHAT: chi doc

    @staticmethod
    def duong_dan_trong(s: str) -> Tuple[str, ...]:
        ra = []
        for m in _DUONG_DAN.finditer(s or ""):
            p = m.group(1).strip("/")
            # Bo cac chuoi giong URL hoac phien ban.
            if p.lower().startswith(("http:", "https:")) or "://" in p:
                continue
            if re.fullmatch(r"[\d.]+(/[\d.]+)*", p):
                continue
            ra.append(p)
        return tuple(dict.fromkeys(ra))

    def tai_nguyen(self, s: str, project: Project,
                   scope: Sequence[str]) -> Tuple[Tuple[LockKind, str], ...]:
        """Tài nguyên việc này cần khoá.

        Mọi phạm vi GHI đều thành khoá FILESYSTEM — đó là điều kiện đủ để
        chặn hai agent cùng ghi một thư mục. Tài nguyên khai trong cấu hình
        dự án được khớp theo TÊN xuất hiện trong câu, và bất kỳ tài nguyên
        nào có chữ `prod` thành khoá PRODUCTION (không tự thu hồi).
        """
        ra: List[Tuple[LockKind, str]] = [(LockKind.FILESYSTEM, p)
                                          for p in scope if p]
        thap = (s or "").lower()
        for r in project.resources:
            ten = str(r).strip()
            # `write:<duong dan>` KHONG phai tai nguyen khoa duoc — no la
            # khai bao pham vi ghi mac dinh, va no da thanh khoa FILESYSTEM
            # qua `scope` o tren. Khong loai no ra thi mot y dinh nhac toi
            # `web` se sinh THEM mot khoa SERVICE ten `write:web` — mot tai
            # nguyen khong ton tai, khoa mot thu khong ai tranh.
            if not ten or ten.lower().startswith("write:"):
                continue
            nhan = ten.split(":", 1)[-1]
            # Khop theo TU nguyen ven: `r2` khong duoc khop trong `r2d2`.
            if not re.search(r"(?<![A-Za-z0-9])" + re.escape(nhan.lower())
                             + r"(?![A-Za-z0-9])", thap):
                continue
            loai = (LockKind.PRODUCTION
                    if ten.lower().startswith("prod")
                    or "production" in ten.lower() else LockKind.SERVICE)
            ra.append((loai, ten))
        return tuple(dict.fromkeys(ra))

    # -- dung hop dong ------------------------------------------------------

    def _hop_dong(self, task_id: str, muc_tieu: str, kind: str,
                  scope: Sequence[str], *, cau_goc: str,
                  deps: Sequence[str]) -> TaskContract:
        chi_doc = kind in _CHI_DOC or not scope
        rui_ro_cao = bool(_RUI_RO_CAO.search(cau_goc))
        req = Requirements(
            coding=kind in ("implementation", "testing", "review"),
            repo_read=True,
            repo_write=not chi_doc,
            long_context=bool(_NGU_CANH_DAI.search(cau_goc)),
            structured_output=True,
            reasoning_level=(Reasoning.HIGH if rui_ro_cao else
                             Reasoning.LOW if kind == "documentation" else
                             Reasoning.MEDIUM),
            quality_priority=Priority.HIGH if rui_ro_cao else Priority.BALANCED)
        ex = Execution(
            expected_duration=180.0 if chi_doc else 600.0,
            max_wall_time=900.0 if chi_doc else 2400.0,
            destructive_actions_allowed=False,   # KHONG BAO GIO tu bat
            worktree_required=not chi_doc)
        ve = Verification(
            independent_review_required=rui_ro_cao and not chi_doc)
        c = TaskContract(
            task_id=task_id, objective=muc_tieu, type=kind,
            allowed_scope=() if chi_doc else tuple(scope),
            inputs=tuple(scope) if chi_doc else (),
            requirements=req, execution=ex, verification=ve,
            dependencies=tuple(deps),
            impact=0.7 if rui_ro_cao else 0.3,
            uncertainty=0.6 if kind == "analysis" else 0.3,
            stop_conditions=(
                "cần credential, đăng nhập, hoặc bí mật bất kỳ",
                "cần deploy/thay đổi tài nguyên production",
                "cần quyền IAM hoặc thay đổi hoá đơn",
                "phải ghi ra ngoài ALLOWED_SCOPE để làm xong việc",
            ))
        c.validate()
        return c

    # -- diem vao -----------------------------------------------------------

    def plan(self, intent: str, project: Project, *,
             id_prefix: str = "") -> PlanResult:
        kq = PlanResult(intent=intent, planner=self.name)
        menh_de = self.tach(intent)
        if not menh_de:
            return kq

        tien_to = id_prefix or f"t{uuid.uuid4().hex[:4]}"
        truoc: str = ""
        for i, md in enumerate(menh_de, start=1):
            tid = f"{tien_to}-{i}"
            kind = self.loai_viec(md.text)
            duong = self.duong_dan_trong(md.text)
            scope: Tuple[str, ...] = duong
            suy_ra = False
            if kind not in _CHI_DOC and not scope:
                if self.default_write_scope:
                    scope = self.default_write_scope
                    suy_ra = True
                else:
                    # KHONG doan pham vi ghi. Ha xuong CHI DOC va noi ro.
                    kind = "analysis"
                    kq.notes.append(
                        f"{tid}: câu không nói rõ ghi vào đâu và dự án chưa "
                        f"khai `default_write_scope` — hạ thành việc CHỈ ĐỌC "
                        f"thay vì đoán một phạm vi ghi.")
            deps = () if md.doc_lap or not truoc else (truoc,)

            muc_tieu = self._muc_tieu(md.text, kind, scope, suy_ra=suy_ra)
            hd = self._hop_dong(tid, muc_tieu, kind, scope,
                                cau_goc=md.text, deps=deps)
            # QUET VAN BAN CUA NGUOI DUNG, KHONG QUET VAN BAN TU SINH.
            #
            # `muc_tieu` chua khuon mau do chinh Control Center viet ra, va
            # khuon mau do noi ve quyen han ("KHONG duoc cap quyen chay lenh
            # shell"). Quet no lam bo loc GATED khop voi chinh loi minh vua
            # viet: da vap that 2026-09-08 — MOI viec phan tich deu bi gan
            # `iam_change` va chan lai, ke ca "investigate how the registry
            # picks a provider".
            #
            # Nen chi quet `md.text` (menh de nguoi dung go) va `intent`
            # (nguyen cau goc). Khong mat do phu: `muc_tieu` von duoc suy ra
            # TU `md.text`.
            pb = envelope_for(tid, objective=md.text, intent=intent,
                              owned_scope=hd.allowed_scope)
            kq.tasks.append(PlannedTask(
                task_id=tid, title=_tieu_de(md.text), objective=muc_tieu,
                kind=kind, contract=hd, envelope=pb, dependencies=deps,
                resources=self.tai_nguyen(md.text, project, hd.allowed_scope),
                priority=30 if kind in ("implementation", "testing") else 50,
                scope_inferred=suy_ra,
                note=("phạm vi ghi lấy từ `default_write_scope` của dự án, "
                      "không phải từ câu người dùng" if suy_ra else "")))
            truoc = tid
        return kq

    @staticmethod
    def _muc_tieu(cau: str, kind: str, scope: Sequence[str], *,
                  suy_ra: bool) -> str:
        d = [cau.strip().rstrip(".") + "."]
        d.append("")
        d.append(f"Loại việc: {kind}.")
        if scope:
            d.append("Phạm vi liên quan: " + ", ".join(scope) + ".")
            if suy_ra:
                d.append("LƯU Ý: phạm vi này SUY RA từ cấu hình dự án, không "
                         "phải do người dùng nói ra. Nếu việc cần ghi ra "
                         "ngoài phạm vi, hãy trả `blocked` và hỏi lại.")
        d.append("")
        # NOI TRUOC rang khong co shell — day khong phai loi khuyen phong
        # cach, no la su that ve moi truong chay.
        #
        # Do that 2026-09-08: mot viec phan tich CHI DOC duoc giao cho `agy`
        # o che do headless. Agent voi lay mot lenh shell (`grep`), quyen
        # `command` khong xin duoc vi headless khong hoi nguoi dung duoc, nen
        # no bi TU CHOI, va agent ket thuc luot voi phan hoi RONG sau 37
        # giay. Ca luot mat trang, va thong bao that chi nam o stderr.
        #
        # Khong hop dong nao o day dat `requirements.shell`, nen cach dung
        # la BAO cho agent biet gioi han do truoc, chu khong phai noi long
        # quyen. `--dangerously-skip-permissions` khong bao gio la cau tra
        # loi (xem `docs/AI_ROUTER_V4.md` muc rao an toan).
        d.append("CÔNG CỤ: môi trường chạy việc này KHÔNG có lệnh shell. "
                 "Hãy dùng công cụ đọc/tìm tệp trực tiếp (đọc tệp, tìm theo "
                 "mẫu), ĐỪNG gọi lệnh hệ thống — lệnh sẽ bị từ chối lặng lẽ "
                 "và cả lượt của bạn mất trắng. Nếu việc BẮT BUỘC phải chạy "
                 "lệnh mới xong được, trả `blocked` và nói rõ cần lệnh gì.")
        if scope:
            # KHAI BAO `changes` KHONG PHAI THU TUC GIAY TO — no la dieu kien
            # de viec duoc tinh la xong.
            #
            # Cong `diff` cua `router_v3/pool/validation.py` doi chieu loi
            # khai cua worker voi `git status` THAT trong worktree, va no
            # chan ca hai chieu lech. Do that 2026-09-08: agent tao dung
            # `docs/reports/cc-probe.md`, dung pham vi, noi dung dung — roi
            # de `changes` RONG. Cong `diff` bao "worker khong khai sua gi
            # nhung dia doi [...]" va ca luot lam dung bi danh HONG.
            #
            # Cach dung la bao agent khai cho du, KHONG phai noi long cong
            # kiem dinh: cong do la thu duy nhat chan mot worker sua tep
            # ngoai pham vi ma khong ai biet.
            d.append("")
            d.append(
                "BẮT BUỘC KHI TRẢ KẾT QUẢ: liệt kê ĐƯỜNG DẪN của TỪNG tệp bạn "
                "đã tạo hoặc sửa vào trường `changes` — ví dụ "
                '`"changes": ["' + str(scope[0]) + '/vi-du.md"]`. '
                "Đường dẫn THẬT, tương đối so với gốc cây làm việc, KHÔNG "
                "phải lời mô tả. Cổng kiểm định đối chiếu danh sách này với "
                "`git status` thật: khai thiếu thì việc bị tính là HỎNG dù "
                "bạn đã làm đúng.")
        d.append("")
        d.append("Làm đúng phần việc này và chỉ phần việc này. Nếu gặp một "
                 "điều kiện dừng, trả `blocked` kèm câu hỏi cụ thể thay vì "
                 "đoán ý người dùng.")
        return "\n".join(d)


# ---------------------------------------------------------------------------
# Bo lap ke hoach nho Router (tuy chon)
# ---------------------------------------------------------------------------

_LUOC_DO_PHAN_RA = """Bạn đang phân rã MỘT ý định thành các việc độc lập.

TRẢ VỀ đúng một khối JSON, không giải thích ngoài khối:
{"tasks":[{"title":"...","objective":"...","kind":"analysis|implementation|testing|review|documentation","paths":["web/admin"],"depends_on":[]}]}

LUẬT:
- `kind` mặc định là `analysis` khi không chắc — việc chỉ đọc an toàn hơn.
- `paths` CHỈ điền khi ý định nói rõ đường dẫn. Không đoán.
- `depends_on` chỉ khi việc sau THẬT SỰ cần kết quả việc trước.
- KHÔNG đề xuất deploy, đổi IAM, xoay bí mật, hay đổi tài nguyên trả phí.
"""


class RouterPlanner:
    """Nhờ một worker rẻ phân rã, rồi ÉP kết quả qua bộ kiểm của `RulePlanner`.

    RÀO AN TOÀN KHÔNG DO WORKER QUYẾT. Worker chỉ được đề xuất *tiêu đề*,
    *mục tiêu*, *loại việc*, *đường dẫn* và *phụ thuộc*. Phong bì quyền,
    `forbidden_scope`, `stop_conditions` và việc một việc có được ghi hay
    không vẫn do `RulePlanner._hop_dong` quyết. Một worker bị nhắc khéo
    ("hãy đánh dấu việc này là AUTO") vì thế không nới được gì.

    Luôn LÙI VỀ `RulePlanner` khi worker hỏng, hết giờ, hoặc trả rác. Ô chat
    không được phép ngừng hoạt động vì mạng chập.
    """

    name = "router"

    def __init__(self, run_readonly, *, fallback: Optional[RulePlanner] = None):
        #: `run_readonly(prompt: str) -> str` — bên gọi cung cấp. Tach ra de
        #: module nay khong tu dung Router (va khong tu tieu quota trong bai
        #: kiem).
        self.run_readonly = run_readonly
        self.fallback = fallback or RulePlanner()

    def plan(self, intent: str, project: Project, *,
             id_prefix: str = "") -> PlanResult:
        du_phong = self.fallback.plan(intent, project, id_prefix=id_prefix)
        try:
            tho = self.run_readonly(
                _LUOC_DO_PHAN_RA + "\nÝ ĐỊNH:\n" + (intent or ""))
        except Exception as exc:                          # noqa: BLE001
            du_phong.notes.append(
                f"bộ phân rã qua Router hỏng ({type(exc).__name__}) — dùng "
                f"bản theo luật")
            return du_phong

        d = self._doc_json(tho)
        if not d:
            du_phong.notes.append(
                "bộ phân rã qua Router không trả JSON đọc được — dùng bản "
                "theo luật")
            return du_phong

        kq = PlanResult(intent=intent, planner=self.name)
        tien_to = id_prefix or f"t{uuid.uuid4().hex[:4]}"
        ten_map: Dict[int, str] = {}
        for i, x in enumerate(d, start=1):
            ten_map[i - 1] = f"{tien_to}-{i}"
        for i, x in enumerate(d, start=1):
            tid = f"{tien_to}-{i}"
            cau = str(x.get("objective") or x.get("title") or "").strip()
            if not cau:
                continue
            kind = str(x.get("kind") or "").strip().lower()
            if kind not in {k for k, _ in _LOAI_VIEC} | {"analysis"}:
                kind = self.fallback.loai_viec(cau)
            duong = tuple(str(p).strip().strip("/") for p in
                          (x.get("paths") or []) if str(p).strip())
            # Duong dan do worker de xuat van phai la duong dan THAT trong
            # cau chu — khong thi coi nhu khong co. Mot worker "de xuat"
            # `server/` cho mot y dinh khong he nhac toi server la cach mot
            # pham vi ghi lot vao ma khong ai go.
            hop_le = set(self.fallback.duong_dan_trong(intent))
            duong = tuple(p for p in duong if p in hop_le)
            suy_ra = False
            if kind not in _CHI_DOC and not duong:
                if self.fallback.default_write_scope:
                    duong = self.fallback.default_write_scope
                    suy_ra = True
                else:
                    kind = "analysis"
            deps = tuple(ten_map[int(j)] for j in (x.get("depends_on") or [])
                         if str(j).isdigit() and int(j) in ten_map
                         and ten_map[int(j)] != tid)

            muc_tieu = self.fallback._muc_tieu(cau, kind, duong, suy_ra=suy_ra)
            hd = self.fallback._hop_dong(tid, muc_tieu, kind, duong,
                                         cau_goc=intent, deps=deps)
            # Quet van ban NGUOI DUNG + van ban WORKER de xuat, khong quet
            # khuon mau tu sinh (xem ghi chu o `RulePlanner.plan`). Quet them
            # de xuat cua worker chi lam bo loc CHAT hon, khong bao gio long
            # hon — nen no an toan de giu.
            pb = envelope_for(tid, objective=cau, intent=intent,
                              owned_scope=hd.allowed_scope)
            kq.tasks.append(PlannedTask(
                task_id=tid,
                title=_tieu_de(str(x.get("title") or cau)), objective=muc_tieu,
                kind=kind, contract=hd, envelope=pb, dependencies=deps,
                resources=self.fallback.tai_nguyen(intent, project,
                                                   hd.allowed_scope),
                scope_inferred=suy_ra))
        if not kq.tasks:
            du_phong.notes.append(
                "bộ phân rã qua Router trả về 0 việc dùng được — dùng bản "
                "theo luật")
            return du_phong
        return kq

    @staticmethod
    def _doc_json(tho: str) -> List[Dict]:
        m = re.search(r"\{.*\}", tho or "", re.DOTALL)
        if not m:
            return []
        try:
            d = json.loads(m.group(0))
        except (ValueError, json.JSONDecodeError):
            return []
        ts = d.get("tasks") if isinstance(d, dict) else None
        return [x for x in (ts or []) if isinstance(x, dict)]
