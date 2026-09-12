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
import os
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


_G = None


def _guard():
    """Hook `PreToolUse` của kho, nạp theo đường dẫn."""
    global _G
    if _G is None:
        import importlib.util
        p = GOC / ".claude" / "hooks" / "guard_indirect_exec.py"
        spec = importlib.util.spec_from_file_location("cc_guard_mod", str(p))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _G = m
    return _G


def _hook_chan(lenh: str):
    """Chia đoạn ĐÚNG NHƯ `main()`: tier 1c, rồi `expand()` + `SEGMENT_SPLIT`.

    `cwd_laundered_read` xét QUAN HỆ giữa các đoạn (`cd` đoạn này, `grep`
    đoạn sau) nên nó KHÔNG nằm trong `evaluate()`; `main()` gọi nó tách ra,
    trước vòng lặp. Quên nó ở đây làm bài kiểm nói dối theo đúng chiều nguy
    hiểm: báo "chạy được" cho một hình dạng mà hook thật đang chặn.
    """
    g = _guard()
    if hasattr(g, "cwd_laundered_read"):
        r = g.cwd_laundered_read(lenh)
        if r:
            return r
    for chunk in g.expand(lenh):
        for doan in g.SEGMENT_SPLIT.split(chunk):
            if doan.strip() and g.evaluate(doan):
                return g.evaluate(doan)
    return None


def _quyet(lenh: str) -> str:
    """`deny` | `ask` | `allow` | `hoi` — đúng thứ tự ưu tiên của Claude Code.

    HOOK ĐƯỢC XÉT TRƯỚC, vì một `deny` của hook thắng cả `allow` và cả
    `bypassPermissions` (đo trực tiếp trên 2.1.231). Bản trước chỉ đọc
    `settings.json`, và điều đó làm bài kiểm nói dối theo cả hai chiều:
    nó báo AN TOÀN cho một lệnh mà hook chặn, và báo HỞ cho một lệnh mà
    chỉ hook đóng — đúng trường hợp `.env` sau khi các glob thô được gỡ.
    """
    if _hook_chan(lenh):
        return "deny"
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

    CẬP NHẬT 2026-09-11 — LẬP TRƯỜNG ĐỔI MỘT NỬA. Nửa "bí mật vẫn bị chặn"
    giữ NGUYÊN. Nửa "`cd <kho> && grep` được allow" thì KHÔNG còn:

        cd <kho> && git status        -> allow   (như cũ)
        cd <kho> && python -m unittest -> allow  (như cũ)
        cd <kho> && grep / cat / sed  -> DENY    (đổi, có chủ đích)

    Vì sao: luật `allow` chỉ khớp khi CẢ chuỗi lệnh khớp glob, nên nó chỉ cứu
    được dạng `cd X && grep …` đứng MỘT MÌNH. Một chuỗi thật —
    `cd X && python -m compileall … && echo OK && grep -n sym a.py` — không
    khớp glob nào và rơi xuống bộ phân loại, bộ này không phân giải tĩnh được
    thư mục sau `cd` nên nó HỎI NGƯỜI. Kết quả: một lời nhắc giữa một lượt
    chạy lẽ ra không cần người (đo 2026-09-11, lặp lại nhiều lần trong một
    phiên).

    Nên hình dạng đó nay bị hook chặn thẳng kèm `REMEDIATION:` — xem
    `guard_indirect_exec.cwd_laundered_read`. Không phải siết quyền đọc: mọi
    phép đọc vẫn làm được bằng Read/Grep/Glob, `scripts/tim.py`, `git grep`,
    hoặc cùng lệnh đó KHÔNG có `cd`.
    """

    KHO = "C:/FanficWorkers/router-control-center"

    def test_dang_cd_cua_lenh_KHONG_doc_pham_vi_mo_van_duoc_phep(self):
        """`cd` + động từ không nhắc một đường đọc mơ hồ nào -> vẫn allow."""
        for lenh in (
            f"cd {self.KHO} && git status --short",
            f"cd {self.KHO} && git diff --stat",
            f"cd {self.KHO} && python -m unittest scripts.tests.test_router_v3",
            f"cd {self.KHO} && node --check scripts/control_center/web/app.js",
        ):
            with self.subTest(lenh=lenh):
                self.assertEqual(_quyet(lenh), "allow", lenh)

    def test_tim_doc_sau_mot_cd_bi_CHAN_chu_khong_hoi(self):
        """Hình dạng gây ra sự cố 2026-09-11. `deny`, ở MỌI dạng viết."""
        for lenh in (
            f"cd {self.KHO} && grep -rn TODO scripts/",
            f"cd {self.KHO} && rg -n TODO scripts/",
            f"cd {self.KHO} && ls -la scripts",
            f"cd {self.KHO} && cat README.md",
            f"cd {self.KHO} && sed -n '1,40p' scripts/x.py",
            f'cd {self.KHO} && find scripts -name "*.py"',
            f"cd {self.KHO} ; grep -rn TODO scripts/",
            "cd /c/FanficWorkers/router-control-center && grep -rn x scripts/",
            # Chuỗi dài — dạng THẬT đã gây ra lời nhắc, không khớp glob nào.
            f"cd {self.KHO} && python -m compileall -q scripts && echo OK "
            f'&& grep -n "sym" a.py',
        ):
            with self.subTest(lenh=lenh):
                self.assertEqual(_quyet(lenh), "deny", lenh)

    def test_moi_lan_chan_deu_KEM_duong_di_thay_the(self):
        """Một `deny` không có bước tiếp theo chỉ dời chỗ tắc nghẽn."""
        for lenh in (f"cd {self.KHO} && grep -rn TODO scripts/",
                     f"cd {self.KHO} && cat README.md",
                     "python - <<'EOF'\nprint(1)\nEOF"):
            with self.subTest(lenh=lenh):
                ly = _hook_chan(lenh) or ""
                self.assertIn("REMEDIATION:", ly, lenh)
        ly = _hook_chan(f"cd {self.KHO} && grep -rn TODO scripts/") or ""
        for ten in ("scripts/tim.py", "git grep", "Read/Grep/Glob"):
            self.assertIn(ten, ly)

    def test_ma_noi_tuyen_qua_heredoc_bi_CHAN(self):
        """Cùng lớp với `python -c`, chỉ khác đường vào."""
        for lenh in ("python - <<'EOF'\nprint(1)\nEOF",
                     "python3 - <<EOF\nprint(1)\nEOF",
                     "bash <<'EOF'\nls\nEOF",
                     "echo 'print(1)' | python -"):
            with self.subTest(lenh=lenh):
                self.assertEqual(_quyet(lenh), "deny", lenh)

    def test_KHONG_chan_oan_cong_cu_an_toan(self):
        """Chống rỗng: bộ chặn mới không được chạm vào đường sạch."""
        for lenh in ('python scripts/tim.py "TrangThai"',
                     "python scripts/tim.py --doc scripts/x.py --tu 1 --den 60",
                     'git grep -n "TrangThai" -- scripts/',
                     'grep -rn "TrangThai" scripts/control_center/',
                     "python -m unittest scripts.tests.test_router_v3",
                     "python -m json.tool <<EOF\n{}\nEOF"):
            with self.subTest(lenh=lenh):
                self.assertNotEqual(_quyet(lenh), "deny", lenh)

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
                  "Bash(*cmdkey*)", "Bash(*PasswordVault*)"):
            with self.subTest(luat=x):
                self.assertIn(x, den)

    def test_luat_env_neo_theo_DONG_TU_chu_khong_theo_duong(self):
        """`.env` được neo theo ĐỘNG TỪ, và ba luật neo-theo-đường đã bị gỡ.

        VÌ SAO GỠ — đo được 2026-09-10: `Bash(* *.env)`, `Bash(*/.env)` và
        `Bash(*.env.*)` khớp CẢ chuỗi lệnh, nên chúng chặn luôn
        `git check-ignore -v server/.env` — một lệnh KHÔNG đọc byte nội
        dung nào, chỉ trả lời "đường này có bị `.gitignore` bỏ không", và
        nằm ngay trong danh sách AN TOÀN được yêu cầu.

        Thứ chúng từng bảo vệ (`cd x && cat .env`) giờ do
        `guard_indirect_exec.secret_file_read()` lo, và lo CHÍNH XÁC hơn:
        hàm đó tách được động từ khỏi toán hạng, còn glob thì không. Bài
        kiểm này khoá cả hai chiều — luật thô phải VẮNG, luật neo động từ
        phải CÓ — nên không ai lặng lẽ thêm lại cái thô.
        """
        den = set(_nap()["permissions"]["deny"])
        for x in ("Bash(* *.env)", "Bash(* *.env *)", "Bash(*/.env)",
                  "Bash(*/.env *)", "Bash(*.env.*)"):
            with self.subTest(vang=x):
                self.assertNotIn(x, den, f"{x} chặn oan `git check-ignore`")
        for x in ("Bash(cat *.env*)", "Bash(head *.env*)",
                  "Bash(tail *.env*)"):
            with self.subTest(co=x):
                self.assertIn(x, den)

    def test_glob_KHONG_neo_dong_tu_lay_MAU_lam_duong(self):
        """`grep`/`sed`/`awk` nhận MẪU ở toán hạng đầu, không phải đường.

        Đo được: `Bash(grep * *.env*)` chặn
        `grep -c '\\* \\*\\.env' settings.json` — tức là chặn việc TÌM
        chuỗi ".env" trong một tệp hoàn toàn bình thường. Một báo động sai
        kiểu đó là cách một luật thật bị gỡ về sau.
        """
        den = set(_nap()["permissions"]["deny"])
        for v in ("grep", "egrep", "rg", "sed", "awk", "cut"):
            for h in (" *.env*", " * *.env*", " *credentials*"):
                with self.subTest(luat=f"Bash({v}{h})"):
                    self.assertNotIn(f"Bash({v}{h})", den)

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


def _co_tang_nguoi_dung() -> bool:
    """Máy này CÓ tầng người dùng để mà kiểm hay không.

    TỰ phân giải đường dẫn, CỐ Ý KHÔNG nhập `scripts/kiem_quyen.py`.

    Bản đầu của hàm này có nhập, và nó làm hỏng 85 bài kiểm ở CI — không phải
    ở tệp này mà rải khắp `scripts/tests/`, với
    `ValueError: I/O operation on closed file` phát ra từ một `print()` bình
    thường ở `chinese_media_pipeline.py`.

    Cơ chế: `kiem_quyen` dựng `RA = io.TextIOWrapper(sys.stdout.buffer, ...)`
    ngay lúc nhập. Hàm này chạy ở thời điểm ĐỊNH NGHĨA LỚP (bộ trang trí
    `skipUnless` được tính khi nhập mô-đun), rồi bỏ tham chiếu tới mô-đun
    vừa tạo. Bộ đếm tham chiếu dọn mô-đun → dọn `RA` → `TextIOWrapper` đóng
    luôn buffer BÊN DƯỚI nó, tức `sys.stdout.buffer`. Mọi `print()` sau đó
    trong CÙNG tiến trình đều nổ.

    Lớp ở dưới vẫn nhập `kiem_quyen` trong `setUpClass` và điều đó AN TOÀN:
    nó giữ mô-đun ở `cls.kq` suốt vòng đời lớp, nên `RA` không bị dọn.

    Hai dòng dưới đây phải khớp `kiem_quyen.NGUOI_DUNG`/`CAU_HINH_NGUOI_DUNG`.
    Nếu lệch, `TestTangNguoiDungTuDung` sẽ bị bỏ qua ở máy lập trình và điều
    đó lộ ra ngay: `python -m unittest ...` sẽ báo `skipped=12` thay vì chạy
    đủ 57 bài.
    """
    goc = os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")
    return (Path(goc) / "settings.json").is_file()


@unittest.skipUnless(
    _co_tang_nguoi_dung(),
    "không có tầng người dùng (~/.claude/settings.json) trên máy này — "
    "lớp này kiểm CẤU HÌNH MÁY LÀM VIỆC, không kiểm sản phẩm",
)
class TestTangNguoiDungTuDung(unittest.TestCase):
    """Tầng NGƯỜI DÙNG phải tự đứng được — không dựa vào hồ sơ kho.

    BỎ QUA Ở CI, CHẠY THẬT Ở MÁY LẬP TRÌNH — và sự khác biệt đó là CỐ Ý.

    Thứ lớp này khẳng định (`~/.claude/settings.json` + hook người dùng) nằm
    NGOÀI kho một cách có chủ đích: chỉ tầng đó mới có hiệu lực ở một thư mục
    chưa được tin, nên nó không thể được commit vào đây. Một runner CI không
    có tệp đó, nên MỌI luật rơi về `hoi` và cả lớp đỏ — đo được: 50 failures
    + 1 error với `CLAUDE_CONFIG_DIR` trỏ vào một thư mục rỗng.

    Đỏ như vậy không nói lên điều gì về sản phẩm, nhưng nó chặn mọi PR web
    vì "Backend tests" là một check BẮT BUỘC. Nên: bỏ qua khi không có gì để
    kiểm, và kiểm đầy đủ khi có.

    Sáu lớp còn lại trong tệp này KHÔNG bị bỏ qua — chúng đọc hồ sơ kho, đã
    nằm trong git, và phải xanh ở CI. Đã kiểm từng lớp một dưới điều kiện CI
    mô phỏng: chỉ DUY NHẤT lớp này phụ thuộc môi trường.

    VÌ SAO ĐÂY LÀ BÀI KIỂM QUAN TRỌNG NHẤT TRONG TỆP NÀY.

    Đo được 2026-09-10, và chính Claude Code nói ra nguyên văn:

        Ignoring 241 permissions.allow entries from .claude/settings.json:
        this workspace has not been trusted. Run Claude Code interactively
        here once and accept the trust dialog, or set
        projects["<đường>"].hasTrustDialogAccepted: true in
        C:\\Users\\<u>\\.claude.json.

    Ở một thư mục CHƯA ĐƯỢC TIN, cả `settings.json` của kho **và** hook
    `PreToolUse` của kho đều bị bỏ qua. Đo trong một hộp cát như thế,
    TRƯỚC khi sửa: 12 trong 28 lệnh nguy hiểm **CHẠY THẬT** —
    `cat khoa.pem`, `sed -i`, `find -delete`, `rm -f khoa.pem`,
    `reg add`, `cmdkey /list`, `awk system()`, `npx wrangler deploy`,
    `npm run cf:deploy:production`, và
    `ssh ... "sudo systemctl restart fanfic-farmer"`.

    Và "thư mục chưa được tin" đúng là nơi làm việc tự động: mỗi worktree
    Router V4 vừa dựng là một thư mục mới.

    Nên hai nửa an toàn phải sống ở tầng NGƯỜI DÙNG, nơi luôn có hiệu
    lực. `scripts/kiem_quyen.py` giữ định nghĩa của hai nửa đó; bài kiểm
    này khẳng định định nghĩa ấy ĐANG THẬT SỰ nằm trong tệp mà Claude
    Code đọc.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cc_kiem_quyen", str(GOC / "scripts" / "kiem_quyen.py"))
        cls.kq = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.kq)

    def test_tep_nguoi_dung_co_that(self):
        self.assertTrue(self.kq.CAU_HINH_NGUOI_DUNG.is_file(),
                        f"thiếu {self.kq.CAU_HINH_NGUOI_DUNG}")

    def test_tang_cho_phep_co_du_o_tang_nguoi_dung(self):
        p = self.kq.ho_so(gom_kho=False)
        co = set(p["allow"])
        thieu = [r for r in self.kq.tang_cho_phep() if r not in co]
        self.assertEqual(thieu[:8], [], f"{len(thieu)} luật allow còn thiếu")

    def test_tang_cam_co_du_o_tang_nguoi_dung(self):
        p = self.kq.ho_so(gom_kho=False)
        co = set(p["deny"])
        thieu = [r for r in self.kq.tang_cam() if r not in co]
        self.assertEqual(thieu[:8], [], f"{len(thieu)} luật deny còn thiếu")

    def test_khong_con_luat_qua_rong(self):
        for muc in (self.kq.ho_so(gom_kho=False),
                    self.kq.ho_so(gom_kho=True)):
            for r in self.kq.LUAT_QUA_RONG:
                with self.subTest(luat=r):
                    self.assertNotIn(r, set(muc["deny"]),
                                     self.kq.LUAT_QUA_RONG[r])

    def test_hook_co_ban_o_tang_nguoi_dung_va_KHOP_ban_kho(self):
        """Bản sao phải giống hệt — lệch nhau là một rào hai phiên bản."""
        self.assertTrue(self.kq.HOOK_NGUOI_DUNG.is_file(),
                        f"thiếu {self.kq.HOOK_NGUOI_DUNG}")
        self.assertEqual(self.kq.HOOK_NGUOI_DUNG.read_bytes(),
                         self.kq.HOOK_KHO.read_bytes(),
                         "bản hook ở tầng người dùng đã LỆCH bản kho")

    def test_hook_da_dang_ky_o_tang_nguoi_dung(self):
        d = json.loads(
            self.kq.CAU_HINH_NGUOI_DUNG.read_text(encoding="utf-8"))
        pre = json.dumps((d.get("hooks") or {}).get("PreToolUse") or [])
        self.assertIn("guard_indirect_exec", pre)

    def test_ma_tran_AN_TOAN_o_thu_muc_CHUA_duoc_tin(self):
        p = self.kq.ho_so(gom_kho=False)
        for lenh in self.kq.MA_TRAN_AN_TOAN:
            with self.subTest(lenh=lenh):
                self.assertEqual(self.kq.quyet_dinh(lenh, p), "allow", lenh)

    def test_ma_tran_NGUY_HIEM_o_thu_muc_CHUA_duoc_tin(self):
        """Bar là `deny`, KHÔNG phải "khác allow".

        Vì một lệnh không khớp luật nào rơi xuống bộ phân loại nội tại của
        Claude Code, và bộ đó **cho chạy** phần lớn — đó chính là cách 12
        lệnh nguy hiểm chạy thật trong hộp cát.
        """
        p = self.kq.ho_so(gom_kho=False)
        for lenh in self.kq.MA_TRAN_NGUY_HIEM:
            with self.subTest(lenh=lenh):
                self.assertEqual(self.kq.quyet_dinh(lenh, p), "deny", lenh)

    def test_ma_tran_NGUY_HIEM_o_thu_muc_DA_duoc_tin(self):
        p = self.kq.ho_so(gom_kho=True)
        for lenh in self.kq.MA_TRAN_NGUY_HIEM:
            with self.subTest(lenh=lenh):
                self.assertEqual(self.kq.quyet_dinh(lenh, p), "deny", lenh)

    def test_nhom_dua_lop_nen_KHONG_bi_chan(self):
        for gom in (False, True):
            p = self.kq.ho_so(gom_kho=gom)
            for lenh in self.kq.MA_TRAN_AN_TOAN_NEN:
                with self.subTest(lenh=lenh, gom_kho=gom):
                    self.assertNotEqual(self.kq.quyet_dinh(lenh, p), "deny",
                                        lenh)

    def test_KHONG_them_blanket_cho_cong_cu_da_co_kiem_co(self):
        """`Bash(find:*)`/`Bash(sed:*)` KHÔNG được vào tầng người dùng.

        Đo được 2026-08-28: viết một luật như thế vào `allow` **thay** phép
        cho-phép-có-kiểm-cờ sẵn có của Claude Code bằng một phép vô điều
        kiện, và nó mở lại `find -delete`, `find -exec`, `sed -i` thật.
        Nhu cầu tìm được đáp bằng `scripts/tim.py` và `git grep` — hai thứ
        chứng minh được phạm vi theo cấu tạo.
        """
        for x in ("Bash(find:*)", "Bash(sed:*)", "Bash(grep:*)",
                  "Bash(rg:*)", "Bash(cat:*)", "Bash(head:*)",
                  "Bash(tail:*)", "Bash(awk:*)", "Bash(xargs:*)",
                  "Bash(curl:*)", "Bash(tee:*)"):
            with self.subTest(luat=x):
                self.assertNotIn(x, self.kq.tang_cho_phep(),
                                 f"{x} nới rộng phép kiểm cờ sẵn có")

    def test_tin_cay_TU_CHOI_duong_ngoai_goc_phat_trien(self):
        for d in ("C:/Windows/Temp", "C:/Users/nguye/Downloads", "C:/"):
            with self.subTest(duong=d):
                ok, _ = self.kq.tin_cay(Path(d), that=False)
                self.assertFalse(ok, d)


class TestCuaTimAnToan(unittest.TestCase):
    """`scripts/tim.py` — cửa TÌM/ĐỌC duy nhất, và bốn điều nó phải giữ."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cc_tim", str(GOC / "scripts" / "tim.py"))
        cls.tim = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tim)

    def test_goc_suy_tu_vi_tri_tep_KHONG_tu_cwd(self):
        """Đây là điều làm `cd` trở nên VÔ NGHĨA thay vì bị cấm."""
        self.assertEqual(self.tim.GOC, GOC)
        ma = (GOC / "scripts" / "tim.py").read_text(encoding="utf-8")
        self.assertIn("Path(__file__).resolve().parents[1]", ma)
        # `Path.cwd()` chi duoc dung de IN ra trong `--kiem`, khong bao gio
        # de quyet dinh doc gi.
        for dong in ma.splitlines():
            if "Path.cwd()" in dong and not dong.lstrip().startswith("#"):
                self.assertIn("RA.write", dong,
                              f"`cwd` không được quyết định phạm vi: {dong}")

    def test_khong_ra_ngoai_kho_duoc(self):
        for d in ("../..", "C:/Windows", "C:/Users/nguye/.ssh",
                  "scripts/../../..", "/"):
            with self.subTest(duong=d):
                with self.assertRaises(self.tim.BiTuChoi):
                    self.tim.trong_kho(Path(d) if Path(d).is_absolute()
                                       else self.tim.GOC / d)

    def test_tep_hinh_dang_bi_mat_bi_loai_tru(self):
        from pathlib import PurePosixPath as P
        for r in (".env", "server/.env", "web/.env.local", "khoa.pem",
                  "a/b/id_rsa", "x/id_ed25519.pub", "cai/credentials.json",
                  "rclone.conf", ".ssh/config", "x/.aws/credentials",
                  "a.p12", "b.pfx", "c.kdbx", "d.keystore"):
            with self.subTest(tep=r):
                self.assertTrue(self.tim.bi_loai_tru(P(r)), r)

    def test_tep_nguon_that_KHONG_bi_loai_tru(self):
        """Loại trừ phải HẸP. `env.test.mjs` là một tệp nguồn thật."""
        from pathlib import PurePosixPath as P
        for r in ("scripts/tim.py", "web/tests/env.test.mjs",
                  "docs/CONTROL_CENTER.md", "scripts/control_center/store.py",
                  "web/src/app/page.tsx", "server/main.py"):
            with self.subTest(tep=r):
                self.assertFalse(self.tim.bi_loai_tru(P(r)), r)

    def test_mau_bi_mat_PHU_bo_cua_packet(self):
        """Hai bộ mẫu không được lệch nhau lặng lẽ.

        `tim.py` giữ bộ RIÊNG (để chạy được khi gói của kho đang hỏng),
        nên bài kiểm này là thứ duy nhất ngăn nó tụt lại sau `packet`.
        """
        from scripts.router_v3.packet import _MAU_BI_MAT
        cua_tim = {m.pattern for m in self.tim.MAU_BI_MAT}
        for m in _MAU_BI_MAT:
            with self.subTest(mau=m.pattern):
                self.assertIn(m.pattern, cua_tim)

    def test_dong_in_ra_di_qua_bo_loc(self):
        for xau in ("ghp_" + "a" * 30, "sk-" + "b" * 30,
                    "AKIA" + "C" * 16, "xoxb-" + "1" * 20,
                    "-----BEGIN RSA PRIVATE KEY-----",
                    "password = sieu-mat-khau-dai",
                    "https://nguoi:matkhau@vi.du"):
            with self.subTest(xau=xau[:20]):
                self.assertIn(self.tim.DA_LOC, self.tim.loc(xau))

    def test_doc_TU_CHOI_tep_bi_mat(self):
        self.assertEqual(self.tim.doc(".env"), 2)
        self.assertEqual(self.tim.doc("khong/ton/tai.pem"), 2)


class TestHookLaLopCHINH_XAC(unittest.TestCase):
    """Hook tách được ĐỘNG TỪ khỏi TOÁN HẠNG — glob thì không.

    Hai lớp có hai việc khác nhau, và ranh giới đó phải được khoá lại:
    glob lo thứ glob diễn đạt CHÍNH XÁC, hook lo thứ cần biết cấu trúc
    lệnh. Mỗi khẳng định dưới đây là một báo động sai hoặc một lỗ THẬT đã
    đo được.
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cc_guard_test", str(GOC / ".claude" / "hooks"
                                 / "guard_indirect_exec.py"))
        cls.g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.g)

    def _qd(self, lenh: str):
        """Chia đoạn ĐÚNG NHƯ `main()` — `expand()` một mình là chưa đủ.

        `expand()` tách thân `$(...)`/backtick nhưng KHÔNG tách `&&`, nên
        gọi `evaluate()` trên nguyên chuỗi `cd /tmp && cat .env` chỉ thấy
        nhị phân `cd`. `main()` còn một tầng `SEGMENT_SPLIT.split(chunk)`
        nữa, và phép chia của bài kiểm phải giống hệt bản thật.
        """
        for chunk in self.g.expand(lenh):
            for doan in self.g.SEGMENT_SPLIT.split(chunk):
                if not doan.strip():
                    continue
                r = self.g.evaluate(doan)
                if r:
                    return r
        return None

    def test_doc_bi_mat_bi_chan_KE_CA_sau_mot_cd(self):
        """Cái lỗ mà không glob nào neo-động-từ bịt được."""
        for lenh in ("cat .env", "cat server/.env", "head -5 khoa.pem",
                     "cd /tmp && cat .env",
                     "cd C:/FanficWorkers/router-control-center "
                     "&& head -5 server/.env",
                     "grep -rn TOKEN .env", "sed -n '1,2p' .env",
                     "cp server/.env /tmp/x", "tar czf o.tgz .ssh",
                     "cat ~/.git-credentials",
                     "cat C:/Users/nguye/.aws/credentials"):
            with self.subTest(lenh=lenh):
                self.assertIsNotNone(self._qd(lenh), lenh)

    def test_lenh_KHONG_doc_noi_dung_thi_KHONG_bi_chan(self):
        """`git check-ignore -v .env` đọc 0 byte nội dung."""
        for lenh in ("git check-ignore -v .env",
                     "git check-ignore -v server/.env",
                     "git status --porcelain --ignored",
                     "git log --oneline -5"):
            with self.subTest(lenh=lenh):
                self.assertIsNone(self._qd(lenh), lenh)

    def test_MAU_tim_khong_bi_doc_thanh_DUONG_DAN(self):
        """`grep`/`sed`/`awk`: toán hạng đầu là MẪU, không phải đường.

        Chặn oan đo được: `grep -c '\\* \\*\\.env' settings.json` — tìm
        CHUỖI ".env" trong một tệp bình thường.
        """
        for lenh in (r"""grep -c '\* \*\.env' .claude/settings.json""",
                     'grep -rn "\\.env" scripts/tests/x.py',
                     'rg "\\.env" scripts/',
                     "awk '/\\.env/{print}' README.md"):
            with self.subTest(lenh=lenh):
                self.assertIsNone(self._qd(lenh), lenh)

    def test_co_cua_SCRIPT_khong_bi_doc_thanh_co_cua_PYTHON(self):
        """`-C` không phải `-c`, và cờ sau đường script là của script.

        Chặn oan đo được:
        `python scripts/tim.py "KHONG" scripts --glob "*.py" -i -C 1`
        bị báo là `inline code execution (python -c)`.
        """
        for lenh in ('python scripts/tim.py "x" scripts --glob "*.py" -i -C 1',
                     "python scripts/tim.py x -C 2",
                     "python -m pytest scripts/tests -q",
                     "python scripts/build_desktop_exe.py --clean",
                     "node --check scripts/control_center/web/app.js"):
            with self.subTest(lenh=lenh):
                self.assertIsNone(self._qd(lenh), lenh)

    def test_thi_hanh_inline_THAT_van_bi_chan(self):
        """Nửa còn lại của cặp trên — nới quá thì mất rào."""
        for lenh in ('python -c "print(1)"', 'python3 -c "print(1)"',
                     "bash -lc 'echo x'", "node -pe '1+1'",
                     "node -e 'x'", "perl -E 'say 1'", "perl -e 'x'",
                     "ruby -e 'x'", "sh -c 'x'"):
            with self.subTest(lenh=lenh):
                self.assertIsNotNone(self._qd(lenh), lenh)

    def test_cua_tim_da_kiem_duyet_duoc_uy_thac(self):
        """`tim.py` tự giữ ranh giới của nó, có bài kiểm ở lớp trên."""
        self.assertIsNone(
            self._qd('python scripts/tim.py "\\.env" --glob "*.py"'))
        self.assertIsNone(self._qd("python scripts/kiem_quyen.py --kiem"))
        # Nhung mot script KHAC thi KHONG duoc thua huong.
        self.assertIsNotNone(
            self._qd("python ke_tan_cong.py server/.env"))

    def test_pha_huy_va_he_thong_van_bi_chan(self):
        for lenh in ("rm -rf scripts", "rm -f khoa.pem",
                     "git reset --hard HEAD~1", "git clean -fdx",
                     "git push -f origin main",
                     "reg add HKCU\\Software\\X /v a /d b /f",
                     "awk 'BEGIN{system(\"echo x\")}'",
                     "Remove-Item scripts -Recurse -Force"):
            with self.subTest(lenh=lenh):
                self.assertIsNotNone(self._qd(lenh), lenh)

    def test_reg_query_chi_doc_van_chay(self):
        self.assertIsNone(self._qd("reg query HKCU\\Software"))


if __name__ == "__main__":
    unittest.main()
