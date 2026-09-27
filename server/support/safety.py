"""
An toan cho Fanfic AI Support — phan loai Y DINH BI TU CHOI + loc dau ra.

Phan loai o day KHONG phai lop bao ve chinh: lop chinh la KIEN TRUC (khong co
cong cu nao lam duoc nhung viec nay — xem `server/support/__init__.py`). Lop
nay ton tai de (a) tra loi THANG THAN rang viec do bi tu choi va vi sao, thay
vi mot cau tra loi mo ho; (b) de bao cao/admin thay ai dang thu gi.

Tu dong nghia tieng Viet co dau/khong dau deu duoc tinh — "xoa tai khoan" va
"xoá tài khoản" la mot y dinh.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

from server.support.sanitize import sach_chuoi


def bo_dau(s: str) -> str:
    """"Xoá tài khoản" -> "xoa tai khoan" (va "đ" -> "d")."""
    t = unicodedata.normalize("NFD", s or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.replace("đ", "d").replace("Đ", "D").lower()


#: Y dinh -> mau (tren chuoi DA bo dau, chu thuong).
Y_DINH_CAM: Dict[str, re.Pattern] = {
    # Doi/xem bi mat: DONG TU doi + MUC TIEU (de "sao token dang nhap het han?"
    # khong bi coi la doi token), HOAC mot thuat ngu chi co nghia la bi mat.
    "bi_mat": re.compile(
        r"((show|give|reveal|print|dump|leak|list|tell|send|display|expose|cho (toi|minh|tao|em) (xem|biet)|"
        r"in ra|hien thi|lay|dua|gui|tiet lo|liet ke|doc)\b.{0,40}"
        r"(secret|bi mat|api[\s_-]?key|khoa( api)?|access key|private key|token|password|mat khau|credential|"
        r"cau hinh|config)"
        r"|\baws\b|\.env\b|bien moi truong|environment variable|\benv var|private key|sdk ?secret|usersig|"
        r"connection string|secret[_ ]?key)"),
    "cookie": re.compile(
        r"((read|show|give|steal|dump|doc|lay|xem|cho (toi|minh) xem)\b.{0,30}"
        r"(cookie|localstorage|local storage|sessionstorage|session storage)|document\.cookie)"),
    "shell": re.compile(
        r"(\bshell\b|\bbash\b|terminal|powershell|\bcmd\b|run (a |the )?command|chay lenh|thuc thi lenh|"
        r"\bsudo\b|rm -rf|exec\(|os\.system|subprocess)"),
    "pha_huy": re.compile(
        r"((xoa|delete|drop|wipe|purge|truncate|reset|huy)\b.{0,24}"
        r"(tai khoan|account|database|co so du lieu|du lieu|data|truyen|chuong|user|nguoi dung|bang|table))"),
    "van_hanh": re.compile(
        r"(restart|khoi dong lai|reboot|redeploy|\bdeploy\b|trien khai|rollback|shutdown|tat may chu|"
        r"scale (up|down)|kill (the )?(server|process)|dung may chu)"),
    "goi_url": re.compile(
        r"(https?://(?!(?:[a-z0-9-]+\.)*fanfic\.world\b)\S+|\blocalhost\b|127\.0\.0\.1|169\.254\.|"
        r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+|metadata\.google|"
        r"(fetch|goi|truy cap|call|curl|wget|request)\s+(url|link|dia chi|endpoint|http))"),
    "nguoi_khac": re.compile(
        r"(nguoi khac|user khac|tai khoan khac|another user|other user'?s?|someone else|cua (anh|chi|ban|ong|ba) ay|"
        r"\buser_?id\b|\buserid\b|cua moi nguoi|all users|tat ca nguoi dung)"),
    "tiem_lenh": re.compile(
        r"(ignore (all |the |any )?(previous |prior |above )?instructions|bo qua (moi|cac|tat ca) (chi dan|huong dan|lenh)|"
        r"system prompt|you are now|developer mode|jailbreak|act as (an? )?(admin|root|developer)|"
        r"pretend (to be|you are)|disregard (the )?(rules|instructions))"),
}

#: Cau tra loi THANG cho tung y dinh — noi viec gi bi tu choi va vi sao.
CAU_TU_CHOI: Dict[str, str] = {
    "bi_mat": "Mình không có và không thể cung cấp khoá, mật khẩu, token hay cấu hình bí mật của hệ thống — trợ lý hỗ trợ không được cấp những thứ đó.",
    "cookie": "Mình không đọc được cookie hay dữ liệu lưu trong trình duyệt của bạn, và cũng không được phép hỏi chúng.",
    "shell": "Mình không có quyền chạy lệnh trên máy chủ hay máy của bạn. Mình chỉ có vài phép kiểm tra chỉ-đọc cố định.",
    "pha_huy": "Mình không xoá hay thay đổi dữ liệu nào — trợ lý chỉ đọc. Muốn xoá tài khoản, hãy dùng trang Tài khoản; muốn xoá truyện, dùng Studio.",
    "van_hanh": "Mình không khởi động lại, triển khai hay thay đổi máy chủ. Nếu hệ thống có sự cố, mình có thể gửi báo cáo cho quản trị viên.",
    "goi_url": "Mình không truy cập được địa chỉ web tuỳ ý — các phép kiểm tra chỉ dành cho trang và dữ liệu của Fanfic World.",
    "nguoi_khac": "Mình chỉ xem được thông tin chẩn đoán của chính bạn, không của người dùng khác.",
    "tiem_lenh": "Mình vẫn làm theo quy tắc an toàn của Fanfic World — không có chỉ dẫn nào mở thêm quyền cho trợ lý.",
}


def phan_loai(van_ban: str) -> List[str]:
    """Danh sach y dinh bi tu choi (co the rong), theo thu tu co dinh."""
    t = bo_dau(van_ban or "")
    return [ten for ten, mau in Y_DINH_CAM.items() if mau.search(t)]


_URL_NGOAI = re.compile(r"(?i)\bhttps?://(?!(?:[a-z0-9-]+\.)*fanfic\.world\b)\S+")
_DONG_BI_MAT = re.compile(r"(?im)^.*\b([A-Z][A-Z0-9_]{3,})\s*=\s*\S+.*$")


def loc_dau_ra(van_ban: str, toi_da: int = 2000) -> str:
    """Dau ra cua mo hinh -> an toan de hien: bo URL ngoai Fanfic, bo dong kieu
    `TEN_BIEN=gia_tri`, roi lam sach nhu moi chuoi khac."""
    t = _URL_NGOAI.sub("[liên kết đã bỏ]", van_ban or "")
    t = _DONG_BI_MAT.sub("[đã bỏ một dòng cấu hình]", t)
    # Giu xuong dong cho de doc: lam sach TUNG dong.
    dong = [sach_chuoi(d, toi_da) for d in t.splitlines()]
    return "\n".join(d for d in dong if d)[:toi_da]
