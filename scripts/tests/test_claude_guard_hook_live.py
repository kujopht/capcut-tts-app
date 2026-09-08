"""Rào chặn thực-thi-gián-tiếp — kiểm SỐNG, không chỉ kiểm cấu hình.

`test_claude_permission_policy.py` khẳng định *cấu hình* đúng. Tệp này
khẳng định *cái rào thật sự chạy* — nó nạp chính `guard_indirect_exec.py`
và bắt hook quyết định trên những chuỗi lệnh cụ thể.

VÌ SAO CẦN CẢ HAI: một dòng `deny` trong `settings.json` và một hook là hai
lớp khác nhau. Hook là lớp duy nhất bắt được thứ mà glob của `settings.json`
không diễn tả nổi — `python -c`, `rm -rf` viết vòng, thay thế lệnh lồng
nhau. Bản `settings.json` có thể xanh trong khi hook đã bị gỡ khỏi cấu hình
hoặc hỏng — và ngược lại.

Bộ ca kiểm nằm sẵn ở `.claude/hooks/test_guard_indirect_exec.py`, nhưng tệp
đó là một KỊCH BẢN (`main()`), không phải module `unittest`, nên
`unittest discover` không thấy nó và CI chưa bao giờ chạy nó. Tệp này bọc
lại đúng các ca đó để CI thật sự cưỡng chế.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
HOOK = GOC / ".claude" / "hooks" / "guard_indirect_exec.py"


def _quyet_dinh(command: str, mode: str = "auto") -> str:
    """Chạy hook thật trên một chuỗi lệnh, trả về quyết định của nó."""
    payload = json.dumps({"tool_name": "Bash",
                          "permission_mode": mode,
                          "tool_input": {"command": command}})
    p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                       capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return f"error:{p.stderr.strip()[:120]}"
    out = (p.stdout or "").strip()
    if not out:
        return "silent"
    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return f"error:non-json:{out[:120]}"
    return d.get("hookSpecificOutput", {}).get("permissionDecision", "?")


@unittest.skipUnless(HOOK.is_file(), "chưa có hook")
class TestRaoChanViecNguyHiem(unittest.TestCase):
    """Những hình dạng này phải bị TỪ CHỐI, ở MỌI chế độ quyền.

    Đúng cái quan trọng nhất: rào phải giống nhau ở mọi mode. Nếu một hình
    dạng chỉ bị chặn ở `auto` mà mở ở `bypassPermissions`, thì nó không phải
    một cái rào — nó là một gợi ý.
    """

    #: Lay tu chinh `MUST_DENY` cua hook — KHONG tu nghi ra. Ban dau toi
    #: liet ke `echo "$(cat .env)"` o day va bai kiem hong: hook CO Y de
    #: thay the lenh thong thuong di qua, con `$(cat ...)` la viec cua dong
    #: `deny` trong `settings.json`. Dat ca kiem sai tang thi no khong do
    #: cai gi ca — no chi bao dong sai. Khang dinh ve `$(cat` nam o
    #: `test_claude_permission_policy.py`, dung tang cua no.
    NGUY_HIEM = (
        ("python -c", 'python -c "import os; os.remove(\'x\')"'),
        ("python3 -c", 'python3 -c "print(1)"'),
        ("venv python -c", '.venv/Scripts/python.exe -c "print(1)"'),
        ("node -e", 'node -e "1+1"'),
        ("powershell -Command", 'powershell -Command "Get-Process"'),
        ("cmd /c", "cmd /c echo hi"),
        ("xoa de quy", "rm -rf build"),
        ("xoa de quy -r", "rm -r build"),
        ("$() long nhau", "echo $(echo $(rm -rf /tmp/x))"),
        ("thay the -> trinh thong dich", 'echo "$(python -c \'print(1)\')"'),
        ("backtick -> rm", "echo `rm -rf /tmp/x`"),
        ("${} lau lenh", "echo ${rm -rf /tmp/x}"),
        ("noi chuoi bang &&", "git status && rm -rf /tmp/x"),
        ("noi chuoi bang |", "echo hi | xargs rm"),
        ("git reset --hard", "git reset --hard origin/main"),
    )

    def test_bi_tu_choi_o_moi_che_do(self):
        for mode in ("auto", "default", "bypassPermissions"):
            for nhan, cmd in self.NGUY_HIEM:
                with self.subTest(mode=mode, ca=nhan):
                    self.assertEqual(
                        _quyet_dinh(cmd, mode), "deny",
                        f"`{nhan}` phải bị chặn ở mode={mode}")


@unittest.skipUnless(HOOK.is_file(), "chưa có hook")
class TestRaoKHONGChanViecSoiKho(unittest.TestCase):
    """Nửa còn lại: rào không được chặn việc đọc thông thường.

    Một cái rào chặn cả việc vô hại thì người dùng sẽ tắt nó — nên "không
    chặn oan" cũng là một bất biến, không phải chuyện tiện nghi.
    """

    VO_HAI = (
        ("git status", "git status --porcelain"),
        ("git log", "git log --oneline -5"),
        ("git diff", "git diff --stat"),
        ("git rev-parse", "git rev-parse HEAD"),
        ("liet ke", "ls -la scripts/control_center"),
        ("unittest", ".venv/Scripts/python.exe -m unittest discover -s tests -t ."),
    )

    def test_khong_bi_tu_choi(self):
        for nhan, cmd in self.VO_HAI:
            with self.subTest(ca=nhan):
                self.assertNotEqual(
                    _quyet_dinh(cmd), "deny",
                    f"`{nhan}` là việc soi kho vô hại — không được chặn")


if __name__ == "__main__":
    unittest.main()
