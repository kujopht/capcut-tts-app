"""Chính sách quyền của kho này — kiểm bằng máy, không bằng lời hứa.

VÌ SAO TỆP NÀY TỒN TẠI:

Ma sát quyền là một lỗi UX thật. Bản V0.1 làm việc soi kho thông thường
(`git status`, `git log`, `git diff`) phải chờ người bấm duyệt, nên chạy
không người trông là không dùng được. Nhưng cách sửa sai — `bypassPermissions`
hay `--dangerously-skip-permissions` — mở luôn cả những thứ phải đóng.

Nên chính sách phải giữ ĐỒNG THỜI hai nửa, và hai nửa đó dễ lệch nhau âm
thầm khi ai đó thêm một dòng `allow`:

    1. việc soi kho vô hại  -> chạy được, KHÔNG cần duyệt
    2. việc phá huỷ/sản xuất -> vẫn bị chặn

Bài kiểm này khoá cả hai. Nó đọc đúng tệp mà Claude Code đọc, nên nó không
thể "xanh trong khi cấu hình thật đã lệch".

MỘT ĐIỀU QUAN TRỌNG VỀ THỨ TỰ: `deny` THẮNG `allow`. Cấu hình này dựa vào
đúng tính chất đó — ví dụ `git push *` nằm trong `allow` nhưng
`git push --force*` nằm trong `deny`, và `--force` bị chặn. Vài bài kiểm
dưới đây khẳng định chính cặp đó, vì nếu ai đó gỡ dòng `deny` thì dòng
`allow` rộng kia lập tức trở thành một lỗ.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]
CAU_HINH = GOC / ".claude" / "settings.json"


def _nap() -> dict:
    return json.loads(CAU_HINH.read_text(encoding="utf-8"))


class TestCauHinhDocDuoc(unittest.TestCase):
    def test_json_hop_le_va_co_ba_phan(self):
        d = _nap()
        self.assertIn("permissions", d)
        for k in ("allow", "deny", "ask"):
            self.assertIsInstance(d["permissions"].get(k), list, k)


class TestSoiKhoKhongCanDuyet(unittest.TestCase):
    """Nửa thứ nhất: việc đọc thông thường phải tự chạy.

    Danh sách này là những lệnh THẬT tôi đã dùng khi làm việc trong kho.
    Nếu một dòng ở đây biến mất khỏi `allow`, phiên chạy không người trông
    lại đứng chờ một cú bấm chuột — đúng lỗi UX mà V0.1.1 phải đóng.
    """

    #: Mỗi phần tử: tiền tố lệnh phải có mặt trong `allow` dưới dạng
    #: `Bash(<tien to>:*)` hoặc `Bash(<tien to>)`.
    DOC_THONG_THUONG = (
        "git status", "git diff", "git log", "git show",
        "git rev-parse", "git rev-list", "git merge-base",
        "git ls-files", "git ls-remote", "git worktree list",
        "git describe", "git blame", "git cat-file",
        "ls", "wc",
    )

    def setUp(self):
        self.allow = set(_nap()["permissions"]["allow"])

    def test_moi_lenh_doc_thong_thuong_deu_duoc_cho_phep(self):
        for lenh in self.DOC_THONG_THUONG:
            with self.subTest(lenh=lenh):
                self.assertTrue(
                    f"Bash({lenh}:*)" in self.allow or f"Bash({lenh})" in self.allow,
                    f"`{lenh}` không có trong allow — phiên không người "
                    f"trông sẽ đứng chờ duyệt")

    def test_doc_tep_va_tim_trong_tep_duoc_cho_phep(self):
        """Read/Grep/Glob là đường ĐÚNG để soi kho, nên chúng phải mở.

        Mở chúng cũng là cách bỏ được `cd && grep` và các đường ống
        `head`/`tail` — thứ vừa khó đọc vừa làm mất phạm vi đọc tường minh.
        """
        for r in ("Read(**)", "Grep(**)"):
            self.assertIn(r, self.allow)

    def test_bo_kiem_chay_duoc_bang_duong_venv_TUYET_DOI(self):
        """Worktree này dùng venv của kho chính bằng đường dẫn tuyệt đối.

        Chỉ có luật cho `.venv/Scripts/python.exe` (tương đối) là không đủ:
        trong worktree, `.venv` không tồn tại, nên mọi lượt chạy bộ kiểm đi
        bằng đường tuyệt đối và không khớp luật nào.
        """
        co = [a for a in self.allow
              if "python.exe -m unittest" in a and "CapCut-TTS-App" in a]
        self.assertTrue(co, "chưa cho phép chạy unittest bằng đường tuyệt đối")


class TestViecNguyHiemVanBiChan(unittest.TestCase):
    """Nửa thứ hai, và là nửa không được phép mất."""

    def setUp(self):
        self.deny = set(_nap()["permissions"]["deny"])
        self.tho = json.dumps(_nap())

    def test_KHONG_co_bypass_o_bat_ky_dau(self):
        for x in ("bypassPermissions", "dangerously-skip", "dangerouslySkip"):
            with self.subTest(co=x):
                self.assertNotIn(x, self.tho)

    def test_default_mode_khong_phai_bypass(self):
        self.assertEqual(_nap()["permissions"].get("defaultMode"), "auto")

    def test_pha_huy_he_tep_van_bi_chan(self):
        for x in ("Bash(rm -rf *)", "Bash(rm -r *)",
                  "Bash(git reset --hard*)", "Bash(git clean -f*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_thay_the_lenh_doc_bi_mat_van_bi_chan(self):
        """`$(cat ...)` là việc của TẦNG NÀY, không phải của hook.

        Hook cố ý để thay thế lệnh thông thường đi qua (`echo "$(date)"`
        phải chạy được), nên thứ duy nhất chặn `echo "$(cat .env)"` là dòng
        `deny` ở đây. Ghi rõ vì tôi đã từng đặt khẳng định này sai tầng và
        bài kiểm báo động sai.

        Dòng này cũng là thứ đã chặn `git commit -m "$(cat <<EOF ...)"` của
        chính tôi trong lượt phát hành V0.1 — dùng `-F` là đường đúng.
        """
        for x in ("Bash(*$(cat *)*)", "Bash(*`cat *)", "Bash(*${cat *)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_bi_mat_van_bi_chan(self):
        for x in ("Read(**/.env)", "Read(**/.ssh/**)", "Read(**/.aws/**)",
                  "Read(**/*.pem)", "Bash(gh auth token*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_thay_doi_ha_tang_may_van_bi_chan(self):
        for x in ("Bash(wrangler delete*)", "Bash(wrangler secret*)",
                  "Bash(aws * delete*)", "Bash(gcloud * delete*)",
                  "Bash(runas*)", "Bash(reg delete*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_force_push_van_bi_chan_DU_git_push_duoc_cho_phep(self):
        """Đây là cặp allow/deny quan trọng nhất của tệp cấu hình.

        `git push *` nằm trong `allow` để việc phát hành chạy được; điều duy
        nhất giữ `--force` ngoài cửa là dòng `deny`. Gỡ dòng đó thì luật
        `allow` rộng kia lập tức thành một lỗ, và không có gì khác báo động.
        """
        self.assertIn("Bash(git push *)", set(_nap()["permissions"]["allow"]))
        for x in ("Bash(git push --force*)", "Bash(git push * --force*)",
                  "Bash(git push -f *)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_xoa_nhanh_va_tag_bi_chan_DU_git_branch_tag_duoc_doc(self):
        """Cùng hình dạng: động từ mở để đọc, cờ phá huỷ thì đóng.

        `git branch -D` và `git tag -d` xoá thật. Chúng bị chặn tường minh
        vì `allow` có `git tag:*` và các dạng đọc của `git branch`.
        """
        for x in ("Bash(git branch -D*)", "Bash(git branch -d*)",
                  "Bash(git tag -d*)", "Bash(git tag --delete*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_go_worktree_bang_git_TRAN_bi_chan(self):
        """Worktree chỉ được gỡ qua đường đã chuẩn hoá của Control Center.

        Luật thứ ba không được phá của gói này: *không tự xoá worktree, chỉ
        đánh dấu* (`CLAUDE.md`). `git worktree:*` nằm trong `allow` cho
        `git worktree list`/`add`, nên `remove`/`prune` phải bị chặn riêng.
        """
        for x in ("Bash(git worktree remove*)", "Bash(git worktree prune*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)

    def test_sua_chinh_tep_chinh_sach_van_phai_HOI(self):
        """Tệp cấu hình quyền không được tự sửa lặng lẽ."""
        ask = set(_nap()["permissions"]["ask"])
        self.assertIn("Edit(.claude/settings.json)", ask)
        self.assertIn("Edit(.claude/hooks/**)", ask)

    def test_hook_chan_thuc_thi_gian_tiep_van_duoc_gan(self):
        """Hook là lớp chặn `python -c`/`rm -rf` — không được rơi ra."""
        d = _nap()
        hooks = d.get("hooks", {}).get("PreToolUse", [])
        arg = json.dumps(hooks)
        self.assertIn("guard_indirect_exec.py", arg)
        self.assertTrue((GOC / ".claude" / "hooks"
                         / "guard_indirect_exec.py").is_file())


if __name__ == "__main__":
    unittest.main()
