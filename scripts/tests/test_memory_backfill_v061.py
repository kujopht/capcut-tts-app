# -*- coding: utf-8 -*-
"""V0.6.1 — NHẬP KHẨU LỊCH SỬ (backfill) vào ký ức dự án.

Mọi bài chạy trên kho tạm + thư mục `~/.claude/projects` GIẢ. Không chạm sổ
thật, không đọc phiên thật. Bốn nhóm bất biến:

  1. AN TOÀN: idempotent, chỉ đọc nguồn, không ghi đè L0, bí mật bị lọc ở
     cổng vào (kể cả trong blob), nguồn không sẵn thì NÓI RA — không im.
  2. PHẠM VI DỰ ÁN: chỉ phiên Claude của đúng các worktree của kho; phiên của
     dự án khác nằm cạnh không bao giờ được đọc.
  3. THẨM QUYỀN: lịch sử luôn `backfill`, không bao giờ `user_explicit`; vai
     "user" tổng hợp (tóm tắt nén ngữ cảnh, skill, nhắc hệ thống) không đề
     bạt; chỉ đề bạt lịch sử TRƯỚC mốc ký ức.
  4. PHỤC HỒI SỰ CỐ THẬT TỪ BẰNG CHỨNG: một tin trợ lý kể "X.pem không tồn
     tại, tệp thật là X' (lệch một ký tự)" thành INCIDENT với bằng chứng trỏ
     về đúng dòng L0 — và câu hỏi "vụ SSH key hôm trước" tìm lại được nó.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.control_center.memory import DichVuKyUc, LoaiKyUc          # noqa: E402
from scripts.control_center.memory import nhap_khau as NK                # noqa: E402
from scripts.control_center.memory.model import TinCay                    # noqa: E402
from scripts.control_center.model import Project                          # noqa: E402
from scripts.control_center.store import ControlStore                     # noqa: E402

# Khoa GIA — dung mau AWS de bo loc bat; KHONG phai khoa that.
KHOA_GIA = "AKIA" + "Q" * 16
TOKEN_GIA = "Bearer " + "x" * 40
GIO = 3600.0


def _git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return p.stdout


def _dong_phien(role: str, text: str, ts: float, **them) -> str:
    d = {"type": role, "uuid": f"u{abs(hash((role, text, ts))) % 10**9}",
         "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + ".000Z",
         "message": {"role": role, "content": [{"type": "text", "text": text}]}}
    d.update(them)
    return json.dumps(d, ensure_ascii=False)


class _CoSo(unittest.TestCase):
    """Kho git thật (tạm) + `projects/` giả + sổ Control Center tạm."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cc-bf-test-")).resolve()
        self.repo = self.tmp / "kho"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@t")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "docs" / "reports").mkdir(parents=True)
        (self.repo / "docs" / "reports" / "SU_CO.md").write_text(
            "# Báo cáo\n\n## Sự cố: khoá SSH sai tên\n\nTệp `fanficappwrite.pem` không tồn tại; "
            "tệp thật là `fanficappwrrite.pem` (hai chữ r). Đã kiểm tra bằng ssh -i.\n\n"
            "## Quy trình deploy\n\nChạy `npm run cf:deploy:production` sau khi typecheck xong. "
            "Không có lệnh cf:deploy trần.\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "docs: bao cao su co ssh")
        self.goc_claude = self.tmp / "projects"
        self.goc_claude.mkdir()
        self.st = ControlStore(root=self.tmp / "so")
        self.dv = DichVuKyUc(self.st, self.tmp / "so")
        self.st.luu_project(Project(project_id="p1", name="P1", repo_path=str(self.repo)))
        self.p = self.dv.provider("p1")
        self.moc = time.time()                      # ky uc "bat dau" bay gio
        self.xua = self.moc - 30 * 24 * GIO         # lich su: mot thang truoc

    def tearDown(self):
        self.dv.close()
        self.st.close()

    def _slug(self) -> str:
        return NK.PhienClaudeAdapter(str(self.repo), goc_claude=self.goc_claude).worktrees()[0]

    def _viet_phien(self, slug: str, ten: str, dong: list, *, dang_mo: bool = False) -> Path:
        d = self.goc_claude / slug
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ten}.jsonl"
        f.write_text("\n".join(dong) + "\n", encoding="utf-8")
        if not dang_mo:
            # Phien DA DONG: mtime cu. Tep vua sua = phien dang mo -> bo qua.
            os.utime(f, (self.xua, self.xua))
        return f

    def _bo(self, **kw) -> NK.BoNhapKhau:
        ads = NK.adapters_mac_dinh(self.st, self.st.project("p1"), goc_claude=self.goc_claude)
        return NK.BoNhapKhau(self.p, ads, moc_ky_uc=kw.pop("moc_ky_uc", self.moc), **kw)


class TestPhamViVaAnToan(_CoSo):

    def test_nguon_khong_san_duoc_noi_ra_khong_im(self):
        ad = NK.GitAdapter(str(self.tmp / "khong-co"))
        self.assertTrue(ad.san())
        tk = NK.BoNhapKhau(self.p, [ad], moc_ky_uc=self.moc).chay()[0]
        self.assertTrue(tk.khong_san)
        self.assertEqual((tk.kham_pha, tk.da_nhap), (0, 0))
        # Trang thai cho UI cung noi ro.
        tt = NK.BoNhapKhau(self.p, [ad], moc_ky_uc=self.moc).trang_thai()[0]
        self.assertFalse(tt["san"])
        self.assertTrue(tt["ly_do"])

    def test_chi_doc_phien_cua_worktree_kho_nay(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("user", "xin chào, kho này", self.xua)])
        # Du an KHAC nam canh — co mot "quyet dinh" rat ro; khong bao gio duoc doc.
        self._viet_phien("C--DuAnKhac-x", "s9", [
            _dong_phien("user", "quyết định của project: dùng Postgres cho mọi thứ", self.xua)])
        tk = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertEqual(tk.kham_pha, 1)
        self.assertFalse(self.p.tim_su_kien("Postgres"))
        self.assertEqual(self.p.liet_ke(loai=LoaiKyUc.DECISION, limit=10), [])

    def test_idempotent_va_khong_ghi_de_L0(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", "dòng lịch sử thứ nhất zebra", self.xua),
                                      _dong_phien("assistant", "dòng lịch sử thứ hai yak", self.xua + 1)])
        a = self._bo().chay()
        n1 = self.p.so_su_kien()
        b = self._bo().chay()
        self.assertEqual(self.p.so_su_kien(), n1)
        tk_b = [t for t in b if t.nguon == "phien_claude"][0]
        self.assertEqual(tk_b.da_nhap, 0)
        self.assertEqual(tk_b.trung, 2)
        # Git + tai lieu cung idempotent.
        for t in b:
            self.assertEqual(t.da_nhap, 0, t.to_dict())
        # L0 ghi lan dau van con y nguyen (khong ghi de): so dong va noi dung.
        sk = self.p.tim_su_kien("zebra")
        self.assertEqual(len(sk), 1)
        self.assertIn("thứ nhất", sk[0].tom_tat)
        self.assertGreater(sum(t.da_nhap for t in a), 0)

    def test_thu_kho_khong_ghi_gi(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", "chỉ thử khô", self.xua)])
        tks = self._bo().chay(thu_kho=True)
        self.assertGreater(sum(t.kham_pha for t in tks), 0)
        self.assertEqual(self.p.so_su_kien(), 0)
        self.assertEqual(self.p.liet_ke(limit=10), [])

    def test_khong_sua_tep_nguon(self):
        slug = self._slug()
        f = self._viet_phien(slug, "s1", [_dong_phien("assistant", "giữ nguyên", self.xua)])
        doc = self.repo / "docs" / "reports" / "SU_CO.md"
        truoc = (f.read_bytes(), doc.read_bytes(), _git(self.repo, "rev-parse", "HEAD"))
        self._bo().chay()
        self.assertEqual(truoc, (f.read_bytes(), doc.read_bytes(), _git(self.repo, "rev-parse", "HEAD")))

    def test_bi_mat_trong_lich_su_bi_loc_ca_inline_ca_blob(self):
        slug = self._slug()
        dai = ("Cấu hình worker: AWS_ACCESS_KEY_ID=" + KHOA_GIA + " và header Authorization: "
               + TOKEN_GIA + "\n") + ("dòng đệm cho dài quá trần inline. " * 120)
        self._viet_phien(slug, "s1", [_dong_phien("assistant", dai, self.xua)])
        tk = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertGreater(tk.da_loc, 0)
        sks = self.p.su_kien(loai="backfill:phien_claude:chat_assistant", limit=10)
        self.assertEqual(len(sks), 1)
        sk = sks[0]
        self.assertNotIn(KHOA_GIA, sk.tom_tat)
        self.assertNotIn("x" * 40, sk.tom_tat)
        self.assertTrue(sk.blob_sha, "tin dài phải có blob")
        blob = self.p.doc_blob(sk.blob_sha) or ""
        self.assertTrue(blob)
        self.assertNotIn(KHOA_GIA, blob)
        self.assertNotIn("x" * 40, blob)
        # Khong mot dong nao trong DB mang khoa gia (ke ca bang nhap_khau/meta).
        c = self.p.kho._c()
        for bang in ("su_kien", "nhap_khau", "ky_uc"):
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({bang})")]
            for r in c.execute(f"SELECT * FROM {bang}"):
                for v in r:
                    if isinstance(v, str):
                        self.assertNotIn(KHOA_GIA, v, f"{bang}.{cols}")

    def test_resumable_qua_tran_moi_lan(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", f"mục {i}", self.xua + i)
                                      for i in range(5)])
        # tran=2, han_giay=0 -> mot luot roi dung, con_lai duoc bao.
        bo = self._bo(tran=2)
        tk = [t for t in bo.chay(chi=["phien_claude"], han_giay=0) if t.nguon == "phien_claude"][0]
        self.assertEqual((tk.da_nhap, tk.con_lai), (2, 3))
        self.assertTrue(any("còn 3" in g for g in tk.ghi_chu))
        # Chay lai voi han -> lap toi het.
        tk2 = [t for t in self._bo(tran=2).chay(chi=["phien_claude"]) if t.nguon == "phien_claude"][0]
        self.assertEqual((tk2.da_nhap, tk2.con_lai, tk2.trung), (3, 0, 2))
        self.assertEqual(len(self.p.su_kien(loai="backfill:phien_claude:chat_assistant", limit=10)), 5)

    def test_phien_dang_mo_khong_duoc_nhap(self):
        """Phiên Claude đang được ghi (mtime mới) là HIỆN TẠI — bỏ qua, nói rõ,
        lần sau nhập tiếp. Chặn đúng kịch bản 'đề bài hôm nay kể một sự cố cũ'."""
        slug = self._slug()
        self._viet_phien(slug, "cu", [_dong_phien("assistant", "phiên đã đóng", self.xua)])
        self._viet_phien(slug, "moi", [_dong_phien(
            "assistant", "`a.pem` does not exist; the real file is `ab.pem` — typo", self.xua)],
            dang_mo=True)
        tk = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertEqual((tk.kham_pha, tk.da_nhap), (1, 1))
        self.assertTrue(any("phiên đang mở" in g for g in tk.ghi_chu), tk.ghi_chu)
        # Su co tu TAI LIEU (SU_CO.md) van duoc; tu PHIEN DANG MO thi khong.
        self.assertEqual([k for k in self.p.liet_ke(loai=LoaiKyUc.INCIDENT, limit=10)
                          if k.nguon_loai == "backfill:phien_claude"], [])
        self.assertFalse(self.p.tim_su_kien("typo"))
        # Khi phien do da dong (mtime cu) -> lan chay sau nhap.
        os.utime(self.goc_claude / slug / "moi.jsonl", (self.xua, self.xua))
        tk2 = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertEqual((tk2.kham_pha, tk2.da_nhap, tk2.trung), (2, 1, 1))
        self.assertTrue(self.p.tim_su_kien("typo"))

    def test_moi_dong_L0_mang_nguon_goc_va_bam(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", "có nguồn gốc", self.xua)])
        self._bo().chay()
        sk = self.p.su_kien(loai="backfill:phien_claude:chat_assistant", limit=10)[0]
        self.assertTrue(sk.tham_chieu.startswith(f"{slug}/s1:"))
        self.assertEqual(sk.nguon, "backfill:phien_claude")
        self.assertTrue(sk.meta.get("sha"))
        self.assertEqual(sk.meta.get("session"), "s1")
        r = self.p.kho._c().execute("SELECT sha, su_kien_id FROM nhap_khau WHERE nguon='phien_claude' "
                                    "AND ma_nguon=?", (sk.tham_chieu,)).fetchone()
        self.assertIsNotNone(r)
        self.assertEqual((r["sha"], r["su_kien_id"]), (sk.meta["sha"], sk.id))
        # Commit git cung co sha lam ma nguon.
        cm = self.p.su_kien(loai="backfill:git:commit", limit=10)
        self.assertEqual(len(cm), 1)
        self.assertEqual(len(cm[0].tham_chieu), 40)


class TestThamQuyenDeBat(_CoSo):

    def test_lich_su_khong_bao_gio_user_explicit(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien(
            "user", "quyết định của project: Astra chỉ dùng cho task khó.", self.xua)])
        self._bo().chay()
        qd = self.p.liet_ke(loai=LoaiKyUc.DECISION, limit=10)
        self.assertEqual(len(qd), 1)
        self.assertIs(qd[0].tin_cay, TinCay.BACKFILL)
        self.assertEqual(qd[0].nguon_loai, "backfill:phien_claude")
        self.assertIn("chat_user", qd[0].the)
        self.assertEqual(self.p.dem().get("ky_uc_user_explicit", 0), 0)
        # Bang chung tro ve dung dong L0.
        self.assertEqual(len(qd[0].bang_chung), 1)
        sk = self.p.su_kien_theo_id(qd[0].bang_chung[0].su_kien_id)
        self.assertIsNotNone(sk)
        self.assertIn("Astra", sk.tom_tat)

    def test_vai_user_tong_hop_khong_de_bat(self):
        slug = self._slug()
        tom_tat_nen = ("This session is being continued from a previous conversation that ran out "
                       "of context. quyết định của project: dùng Postgres cho mọi thứ.")
        self._viet_phien(slug, "s1", [
            _dong_phien("user", tom_tat_nen, self.xua),
            _dong_phien("user", "<system-reminder>quyết định của project: bỏ CI</system-reminder>",
                        self.xua + 1),
            _dong_phien("user", "# Update Config Skill\nquyết định: đổi port 9000", self.xua + 2),
            _dong_phien("user", "quyết định của project: giữ SQLite", self.xua + 3, isMeta=True),
            _dong_phien("user", "quyết định của project: giữ FTS5", self.xua + 4,
                        isCompactSummary=True),
        ])
        tk = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertEqual(tk.da_nhap, 5, "van vao L0 — la lich su that")
        self.assertEqual(tk.de_bat, 0, "nhung khong dong nao duoc de bat")
        self.assertEqual(self.p.liet_ke(loai=LoaiKyUc.DECISION, limit=10), [])
        self.assertFalse(NK.tin_nguoi_go(tom_tat_nen))
        self.assertTrue(NK.tin_nguoi_go("quyết định của project: giữ SQLite"))

    def test_chi_de_bat_truoc_moc_ky_uc(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [
            _dong_phien("user", "quyết định của project: A trước mốc", self.xua),
            _dong_phien("user", "quyết định của project: B sau mốc", self.moc + 60)])
        tk = [t for t in self._bo().chay() if t.nguon == "phien_claude"][0]
        self.assertEqual((tk.da_nhap, tk.de_bat), (2, 1))
        nd = [k.noi_dung for k in self.p.liet_ke(loai=LoaiKyUc.DECISION, limit=10)]
        self.assertEqual(len(nd), 1)
        self.assertIn("A trước mốc", nd[0])

    def test_bao_cao_done_chi_co_fixed_failed_khong_thanh_su_co(self):
        m = NK.MucNhap(ma_nguon="x", ts=self.xua, loai="chat_assistant", vai="assistant",
                       tom_tat="Done. CI failed once on a flaky test in test_a.py, then fixed by rerun. "
                               "Everything merged and green now, nothing else to report here.")
        self.assertIsNone(NK.de_bat_tu_muc(m))

    def test_ten_hai_cach_viet(self):
        self.assertEqual(NK.ten_hai_cach_viet("`fanficappwrite.pem` không có; tệp thật `fanficappwrrite.pem`"),
                         ("fanficappwrite.pem", "fanficappwrrite.pem"))
        self.assertIsNone(NK.ten_hai_cach_viet("a.py và b.py khác hẳn nhau; config.json và config.yaml"))
        self.assertTrue(NK._lech_mot("worker.env", "workre.env") is False)   # hoan vi = 2 phep sua
        self.assertTrue(NK._lech_mot("abc.pem", "abcd.pem"))
        self.assertTrue(NK._lech_mot("abc.pem", "abd.pem"))


class TestPhucHoiSuCoSSH(_CoSo):
    """B1 — bằng chứng nằm trong phiên/tài liệu của kho → INCIDENT có nguồn."""

    TIN = ("Two things before the restore.\n\n- Both instances are still RUNNING and billing.\n"
           "- **`fanficappwrite.pem` does not exist.** The real file is `fanficappwrrite.pem` — "
           "double \"r\". I'll use that automatically; just noting it so the path you gave is "
           "corrected. ssh -i ~/.ssh/fanficappwrrite.pem ubuntu@host works.\n\n"
           "Next I will run the rehearsal restore.")

    def test_incident_tu_phien_va_tai_lieu_co_bang_chung(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", self.TIN, self.xua)])
        tks = self._bo().chay()
        inc = self.p.liet_ke(loai=LoaiKyUc.INCIDENT, limit=20)
        self.assertGreaterEqual(len(inc), 2, [t.to_dict() for t in tks])
        nguon = {k.nguon_loai for k in inc}
        self.assertEqual(nguon, {"backfill:phien_claude", "backfill:tai_lieu"})
        for k in inc:
            self.assertIs(k.tin_cay, TinCay.BACKFILL)
            self.assertEqual(len(k.bang_chung), 1)
            sk = self.p.su_kien_theo_id(k.bang_chung[0].su_kien_id)
            self.assertIsNotNone(sk, "bằng chứng phải trỏ về một dòng L0 có thật")
            self.assertTrue(sk.loai.startswith("backfill:"))
            self.assertEqual(k.nguon_id, str(sk.id))
            self.assertIn("fanficappwrrite.pem", k.noi_dung)
        tu_phien = [k for k in inc if k.nguon_loai == "backfill:phien_claude"][0]
        self.assertTrue(any(d.startswith("ten_hai_cach_viet:") for d in tu_phien.meta["dau_hieu"]))
        self.assertIn("does not exist", tu_phien.noi_dung)

    def test_tim_lai_duoc_bang_cau_hoi_tu_nhien(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", self.TIN, self.xua)])
        self._bo().chay()
        kq = self.dv.tim("p1", "cái vụ SSH key fanficappwrite hôm trước bị gì?")
        self.assertTrue(kq["ket_qua"], kq)
        self.assertEqual(kq["ket_qua"][0]["loai"], "incident")
        self.assertEqual(kq["ket_qua"][0]["tin_cay"], "backfill")
        self.assertTrue(kq["su_kien"])
        khoi = self.dv.khoi_cho_leader("p1", "vụ SSH key fanficappwrite hôm trước?")
        self.assertIn("incident", khoi)
        self.assertIn("backfill", khoi)

    def test_khong_bia_khi_nguon_khong_co_bang_chung(self):
        # Kho co tai lieu quy trinh nhung KHONG co gi ve ssh/pem trong phien.
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", "hôm nay chỉ sửa CSS.", self.xua)])
        (self.repo / "docs" / "reports" / "SU_CO.md").unlink()
        self._bo().chay()
        for k in self.p.liet_ke(loai=LoaiKyUc.INCIDENT, limit=20):
            self.assertNotIn("pem", k.noi_dung.lower())


class TestDichVuVaAPI(_CoSo):

    def test_dich_vu_nguon_va_nhap_khau(self):
        slug = self._slug()
        self._viet_phien(slug, "s1", [_dong_phien("assistant", "qua dịch vụ", self.xua)])
        ng = self.dv.nguon_nhap_khau("p1", goc_claude=self.goc_claude)
        self.assertEqual({n["nguon"] for n in ng["nguon"]},
                         {"so_chinh", "git", "tai_lieu", "phien_claude"})
        kq = self.dv.nhap_khau("p1", thu_kho=True, goc_claude=self.goc_claude)
        self.assertTrue(kq["thu_kho"])
        self.assertEqual(self.p.so_su_kien(), 0)
        kq = self.dv.nhap_khau("p1", thu_kho=False, goc_claude=self.goc_claude)
        self.assertFalse(kq["thu_kho"])
        self.assertGreater(kq["tong"]["da_nhap"], 0)
        self.assertGreater(self.p.so_su_kien(), 0)
        ng = self.dv.nguon_nhap_khau("p1", goc_claude=self.goc_claude)
        pc = [n for n in ng["nguon"] if n["nguon"] == "phien_claude"][0]
        self.assertEqual(pc["da_nhap"], 1)
        self.assertIsNotNone(pc["lan_cuoi"])


if __name__ == "__main__":
    unittest.main()
