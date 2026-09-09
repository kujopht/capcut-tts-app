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

import fnmatch
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
        # V0.4: do thay tren mot phien that — 16 lenh doc/chay-kiem
        # thong thuong KHONG co luat nao khop, nen chung roi vao "hoi
        # nguoi" va mot phien khong nguoi trong dung lai o do.
        "grep", "rg", "find", "cat", "head", "tail", "sed", "dir",
        "python -m unittest", "python -m pytest", "python -m compileall",
        "node --check",
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
        # `Glob(**)` TUNG THIEU o day va o cau hinh: bai kiem chi doi
        # `Read`+`Grep`, nen cho thieu do khong ai thay. Ba cong cu nay
        # la mot bo — mo hai cai roi de cai thu ba hoi nguoi thi phien
        # khong nguoi trong van dung.
        for r in ("Read(**)", "Grep(**)", "Glob(**)"):
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

    def test_KHONG_mo_python_tran(self):
        """`Bash(python:*)` se cho qua `python -c "<bat ky>"`.

        Do dung la duong ma hook `guard_indirect_exec` ton tai de chan, va
        mot luat `allow` tran o day se lam lop hook thanh vo nghia cho
        truong hop pho bien nhat. Nen chi tung MODULE duoc mo.
        """
        al = set(_nap()["permissions"]["allow"])
        for x in ("Bash(python:*)", "Bash(python3:*)", "Bash(py:*)",
                  "Bash(node:*)", "Bash(python scripts/:*)"):
            with self.subTest(luat=x):
                self.assertNotIn(x, al)

    def test_kich_ban_ops_KHONG_chay_duoc_du_kich_ban_kho_duoc_mo(self):
        """`scripts/ops/*` cham vao Appwrite/R2/Drive/AWS THAT.

        Cap allow/deny nay cung hinh dang voi `git push`/`--force`: danh
        sach `allow` liet ke tung kich ban an toan, va dong `deny` giu
        `scripts/ops/` ngoai cua ke ca khi ai do sau nay them mot luat
        `python scripts/*` rong hon.

        CHAN THEO HINH DANG THUC THI, khong chan viec DOC ma nguon do —
        `grep`/`cat` trong `scripts/ops/` la viec phat trien binh thuong.
        """
        for x in ("Bash(python scripts/ops/*)",
                  "Bash(*&& python scripts/ops/*)"):
            with self.subTest(luat=x):
                self.assertIn(x, self.deny)
        al = set(_nap()["permissions"]["allow"])
        self.assertIn("Bash(python scripts/build_desktop_exe.py:*)", al)

    def test_Write_duoc_mo_thi_moi_cong_ASK_cua_Edit_phai_co_ban_song_sinh(self):
        """`Write(**)` vua duoc mo, va do la mot lo neu `ask` khong theo.

        Cac cong `ask` duoc viet cho `Edit(...)`. Neu `Write` mo ma khong
        co ban song sinh thi mot lan `Write` di vong qua DUNG cai cong ma
        `Edit` phai dung lai — sua `.claude/settings.json` hay
        `web/wrangler.jsonc` ma khong ai duyet.
        """
        p = _nap()["permissions"]
        if "Write(**)" not in set(p["allow"]):
            self.skipTest("chưa mở Write(**)")
        ask = set(p["ask"])
        for r in p["ask"]:
            if r.startswith("Edit("):
                song_sinh = r.replace("Edit(", "Write(", 1)
                with self.subTest(cong=r):
                    self.assertIn(song_sinh, ask,
                                  f"{r} có cổng ASK nhưng {song_sinh} thì "
                                  f"không — Write đi vòng qua được")

    def test_hook_chan_thuc_thi_gian_tiep_van_duoc_gan(self):
        """Hook là lớp chặn `python -c`/`rm -rf` — không được rơi ra."""
        d = _nap()
        hooks = d.get("hooks", {}).get("PreToolUse", [])
        arg = json.dumps(hooks)
        self.assertIn("guard_indirect_exec.py", arg)
        self.assertTrue((GOC / ".claude" / "hooks"
                         / "guard_indirect_exec.py").is_file())


def _khop(mau: str, lenh: str) -> bool:
    """Khớp MỘT luật `Bash(...)` với MỘT chuỗi lệnh.

    Đây là một **mô hình** hai dạng khớp mà chính tệp cấu hình này đã dựa
    vào từ đầu, không phải một bản cài lại đầy đủ của Claude Code:

        `x:*`   -> tiền tố: lệnh là `x` hoặc bắt đầu bằng `x `
        còn lại -> glob trên CẢ chuỗi lệnh (`Bash(head * *.env*)`)

    Hai dạng đó là đủ để khoá lại điều cần khoá ở đây: `deny` thắng
    `allow`, và một luật neo ở ĐẦU động từ không khớp khi có tiền tố
    `cd ... &&`. Chính chỗ đó là DEFECT được sửa, nên nó phải được kiểm
    bằng hành vi chứ không bằng phép "chuỗi có trong danh sách".
    """
    if mau.endswith(":*"):
        goc = mau[:-2]
        return lenh == goc or lenh.startswith(goc + " ")
    return mau == lenh or fnmatch.fnmatchcase(lenh, mau)


def _quyet(lenh: str) -> str:
    """`deny` | `ask` | `allow` | `hoi` — đúng thứ tự ưu tiên của Claude Code."""
    p = _nap()["permissions"]
    for muc in ("deny", "ask", "allow"):
        for r in p.get(muc, []):
            if r.startswith("Bash(") and r.endswith(")"):
                if _khop(r[5:-1], lenh):
                    return muc
    return "hoi"


class TestTienToCdKhongConHoi(unittest.TestCase):
    """`cd <kho> && grep ...` phải chạy — và phải chạy AN TOÀN.

    VÌ SAO CÓ LỚP NÀY. Luật `Bash(...)` khớp trên CẢ chuỗi lệnh, nên một
    lệnh bắt đầu bằng `cd` không thể khớp `Bash(grep:*)` — kể cả khi
    `grep` đã được cho phép. Đo được trên một phiên thật: **mọi** dạng
    `cd <kho> && ...` đều rơi vào "hỏi người", kể cả
    `cd <kho> && git status` vốn đã nằm trong `allow`.

    NHƯNG cách sửa dễ nhất lại là một cái lỗ. Các luật `deny` bảo vệ bí
    mật được neo ở ĐẦU động từ (`Bash(cat *.env*)`), nên chúng KHÔNG khớp
    khi có tiền tố `cd ... &&`. Đo được trước bản sửa:

        cat .env                        -> CHẶN
        cd <kho> && cat .env            -> chỉ HỎI (hook cũng im lặng)

    Nên nếu chỉ thêm `allow` cho dạng `cd`, chỗ đó thành CHẠY NGAY. Hai
    điều phải đi cùng nhau, và lớp này khoá cả hai lại:

        1. `cd <cây FanficWorkers> && <động từ an toàn>` -> allow
        2. luật `deny` NEO THEO BÍ MẬT (`*id_rsa*`, `* *.env`, …) khớp
           bất kể tiền tố -> `cd <kho> && cat .env` thành CHẶN

    Sau bản sửa, dạng có `cd` **an toàn hơn trước**: HỎI -> CHẶN.
    """

    KHO = "C:/FanficWorkers/router-control-center"

    def test_dang_cd_cua_lenh_doc_thong_thuong_duoc_phep(self):
        for lenh in (
            f"cd {self.KHO} && grep -rn TODO scripts/",
            f"cd {self.KHO} && rg -n TODO scripts/",
            f"cd {self.KHO} && git status --short",
            f"cd {self.KHO} && git diff --stat",
            f"cd {self.KHO} && ls -la scripts",
            f"cd {self.KHO} && python -m unittest scripts.tests.test_router_v3",
            f"cd {self.KHO} && node --check scripts/control_center/web/app.js",
            "cd /c/FanficWorkers/router-control-center && grep -rn x scripts/",
        ):
            with self.subTest(lenh=lenh):
                self.assertEqual(_quyet(lenh), "allow", lenh)

    def test_dang_cd_KHONG_mo_duong_toi_bi_mat(self):
        """Phần không được phép mất: `deny` thắng luật `cd` ở trên."""
        for lenh in (
            f"cd {self.KHO} && cat .env",
            f"cd {self.KHO} && grep -r AKIA server/.env",
            f"cd {self.KHO} && head -5 ~/.ssh/id_rsa",
            f"cd {self.KHO} && sed -n '1,3p' ~/.ssh/id_ed25519",
            f"cd {self.KHO} && cat ~/.git-credentials",
            f"cd {self.KHO} && python scripts/ops/appwrite_backup_to_drive.py",
        ):
            with self.subTest(lenh=lenh):
                self.assertEqual(_quyet(lenh), "deny", lenh)

    def test_luat_cd_KHONG_duoc_la_dau_hoa_TRAN(self):
        """`Bash(cd <cây> && *)` sẽ cho qua MỌI thứ sau `cd`.

        Đó là "tắt hệ thống an toàn cho một thư mục", không phải một luật
        hẹp: `cd <kho> && cat .env` sẽ thành CHẠY NGAY. Luật `cd` phải
        được viết THEO TỪNG ĐỘNG TỪ.
        """
        for r in _nap()["permissions"]["allow"]:
            if r.startswith("Bash(cd "):
                than = r[5:-1]
                with self.subTest(luat=r):
                    self.assertFalse(
                        than.endswith("&& *") or than.endswith("&&*"),
                        f"{r} mở mọi động từ sau `cd`")

    def test_dang_cd_chi_ap_cho_cay_lam_viec_nay(self):
        """`cd` sang chỗ khác trên đĩa thì KHÔNG được thừa hưởng gì."""
        for lenh in (
            "cd C:/Windows/System32 && grep -rn x .",
            "cd C:/Users/nguye/Documents && cat notes.txt",
            "cd /tmp && grep -rn x .",
        ):
            with self.subTest(lenh=lenh):
                self.assertNotEqual(_quyet(lenh), "allow", lenh)

    def test_luat_neo_theo_bi_mat_co_mat(self):
        """Nửa thứ hai của cặp trên, khẳng định tường minh.

        Gỡ những dòng này thì các luật `cd` ở trên lập tức thành một lỗ,
        và không có gì khác báo động — cùng hình dạng với cặp
        `git push`/`--force`.
        """
        den = set(_nap()["permissions"]["deny"])
        for x in ("Bash(*id_rsa*)", "Bash(*id_ed25519*)",
                  "Bash(*.git-credentials*)", "Bash(*.ssh/*)",
                  "Bash(*.aws/credentials*)", "Bash(*rclone.conf*)",
                  "Bash(* *.env)", "Bash(*/.env)", "Bash(*.env.*)",
                  "Bash(*cmdkey*)", "Bash(*PasswordVault*)"):
            with self.subTest(luat=x):
                self.assertIn(x, den)

    def test_doc_ma_nguon_co_chu_Cookies_VAN_chay_duoc(self):
        """Luật chặn kho credential của trình duyệt không được rộng tới
        mức chặn việc ĐỌC MÃ NGUỒN có chữ đó.

        Bản đầu dùng `Bash(*Cookies*)` và nó chặn
        `grep -rn Cookies scripts/` — một báo động sai mà người sau sẽ gỡ
        cả dòng luật để hết bị chặn, và lúc đó mất luôn ranh giới thật.
        """
        self.assertEqual(_quyet("grep -rn Cookies scripts/control_center/"),
                         "allow")
        self.assertEqual(
            _quyet('cat "C:/Users/x/AppData/Local/Google/Chrome/'
                   'User Data/Default/Cookies"'),
            "deny")


if __name__ == "__main__":
    unittest.main()
