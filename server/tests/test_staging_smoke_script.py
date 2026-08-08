"""
Script smoke test staging khong duoc lo gi ra log.

Script nay chay tren may nguoi van hanh va dau ra cua no thuong duoc dan vao
ticket hoac bao cao. Mot presigned URL in nguyen ra la du de bat ky ai tai file
ve, va host cua no chua R2 account id.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

GOC = Path(__file__).resolve().parents[2]


def nap_script():
    duong = GOC / "scripts" / "staging_smoke.py"
    spec = importlib.util.spec_from_file_location("staging_smoke", duong)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["staging_smoke"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestPresignedUrlIsRedacted(unittest.TestCase):
    #: Dang that cua mot URL R2 da ky. MOI GIA TRI DEU LA GIA — chuoi lap
    #: `000…`/`111…` co y de khong ai nham voi dinh danh that. Ban dau cho nay
    #: chua R2 account id THAT, chep tu dau ra luc chay thu; commit len la lo.
    URL = (
        "https://00000000000000000000000000000000.r2.cloudflarestorage.com"
        "/fanfic-staging/audio/11111111111111111111/chp_2222222222222222"
        "/3333333333333333333333333333333333333333333333333333333333333333.mp3"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256"
        "&X-Amz-Credential=00000000000000000000000000000000%2F20260808%2Fauto%2Fs3%2Faws4_request"
        "&X-Amz-Signature=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    )

    def setUp(self) -> None:
        self.mod = nap_script()

    def rut_gon(self) -> str:
        return self.mod.rut_gon_url(self.URL)

    def test_the_signature_is_gone(self):
        ra = self.rut_gon()
        for cam in ("X-Amz-Signature", "deadbeef", "X-Amz-Credential",
                    "AWS4-HMAC-SHA256"):
            self.assertNotIn(cam, ra, f"chu ky/credential bi lo: {cam}")

    def test_the_r2_account_id_is_gone(self):
        ra = self.rut_gon()
        self.assertNotIn("00000000000000000000000000000000", ra,
                         "host chua R2 account id — khong duoc in")
        self.assertNotIn("r2.cloudflarestorage.com", ra)

    def test_the_bucket_and_owner_are_gone(self):
        ra = self.rut_gon()
        for cam in ("fanfic-staging", "11111111111111111111",
                    "chp_2222222222222222"):
            self.assertNotIn(cam, ra, f"dinh danh bi lo: {cam}")

    def test_the_object_hash_is_gone(self):
        ra = self.rut_gon()
        bam = "3" * 64
        self.assertIn(bam, self.URL, "moc phai con nam trong URL nguon")
        self.assertNotIn(bam[:16], ra, "hash noi dung bi lo")

    def test_it_still_says_something_useful(self):
        """Che het ma khong con thong tin gi thi cung vo dung."""
        ra = self.rut_gon()
        self.assertIn("mp3", ra, "phai con biet duoc duoi tep")
        self.assertIn("co_query=co", ra, "phai con biet URL co duoc ky hay khong")

    def test_a_url_without_a_query_is_reported_as_unsigned(self):
        ra = self.mod.rut_gon_url("https://vi-du.test/a/b.mp3")
        self.assertIn("co_query=KHONG", ra)


class TestTheScriptCleansUpAfterItself(unittest.TestCase):
    def setUp(self) -> None:
        self.nguon = (GOC / "scripts" / "staging_smoke.py").read_text(encoding="utf-8")

    def test_cleanup_runs_even_when_a_step_fails(self):
        """
        `don_dep` phai nam trong `finally`.

        Mot buoc hong ma khong don thi fixture `[SMOKE]` nam lai tren staging,
        va lan chay sau se doc phai rac cua lan truoc.
        """
        i = self.nguon.find("finally:")
        self.assertGreater(i, 0, "phai co khoi finally")
        self.assertIn("don_dep(", self.nguon[i:i + 400],
                      "don dep phai nam trong finally")

    def test_fixtures_are_clearly_marked(self):
        self.assertIn("[SMOKE]", self.nguon,
                      "fixture phai co tien to de nhan ra va don duoc")

    def test_it_forces_utf8_before_printing_anything(self):
        """
        LOI DA GAP: script sap tren console cp1252 cua Windows.

        Mot dong ket qua co dau — tieu de chuong "[SMOKE] Chương đã sửa" — nem
        `UnicodeEncodeError` trong `kt()`. Cho do nam NGOAI khoi `try` cua
        `main()`, nen `ids` chua kip tra ve va buoc don dep khong biet phai xoa
        gi: fixture nam lai tren staging.
        """
        self.assertIn('reconfigure(encoding="utf-8"', self.nguon)
        self.assertIn('errors="replace"', self.nguon,
                      "mot ky tu la khong duoc quan trong hon viec chay het bai")
        self.assertIn("\n_ep_utf8()\n", self.nguon,
                      "phai goi ngay khi nap module, truoc moi lan in")

    def test_vietnamese_output_is_encodable(self):
        """Chinh chuoi da lam sap script truoc day."""
        cau = "[SMOKE] Chương đã sửa"
        self.assertTrue(cau.encode("utf-8"))
        with self.assertRaises(UnicodeEncodeError):
            cau.encode("cp1252")

    def test_it_never_prints_a_token(self):
        """Khong duoc in `token`, `tok_a`, `tok_b` ra man hinh."""
        for dong in self.nguon.splitlines():
            hep = dong.strip()
            if not hep.startswith("print("):
                continue
            for cam in ("tok_a", "tok_b", '["token"]', "['token']"):
                self.assertNotIn(cam, hep, f"dong print lo token: {hep[:80]}")


class TestLoginFailureDoesNotCrashTheScript(unittest.TestCase):
    """
    LOI DA GAP tren staging that: `KeyError: 'token'`.

    Khi API key Appwrite thieu scope `users.write`, `/api/auth/register` tra
    `400 {"detail": "... missing scopes ..."}` va `/api/auth/login` tra `401`.
    Ca hai phan hoi do KHONG co khoa `token`. Script luc do doc thang
    `r["token"]` nen nem `KeyError` va sap giua chung.

    Hau qua that su khong phai dong traceback, ma la: `main()` sap TRUOC khi toi
    `finally`, nen buoc don dep khong chay va fixture `[SMOKE]` nam lai tren
    staging cho lan chay sau doc phai.
    """

    def setUp(self) -> None:
        self.mod = nap_script()
        self.mod.KET_QUA.clear()
        self.addCleanup(setattr, self.mod, "goi", self.mod.goi)
        self.da_goi = []

    def gia_lap(self, dang_nhap_hong=False, dang_nhap_lai_hong=False):
        """
        Backend gia. Ghi lai moi request de kiem buoc don dep co chay khong.

        Phan hoi loi dung DUNG hinh dang that cua FastAPI: `{"detail": ...}`,
        khong co khoa `token`.
        """
        dem = {"n": 0}

        def goi(base, method, path, payload=None, token=None, timeout=300):
            self.da_goi.append((method, path))
            if path == "/api/auth/register":
                return 201, {"token": "tok-gia", "profile": {"user_id": "u1"}}
            if path == "/api/auth/login":
                dem["n"] += 1
                if (payload or {}).get("password") == "sai-mat-khau":
                    return 401, {"detail": "Sai mat khau."}
                if dang_nhap_hong or (dang_nhap_lai_hong and dem["n"] > 1):
                    return 401, {"detail": "Khong dang nhap duoc."}
                return 200, {"token": "tok-gia", "profile": {"user_id": "u1"}}
            if path == "/api/health":
                return 200, {"environment": "staging", "inline_worker": False,
                             "data_backend": "appwrite", "storage_backend": "r2"}
            if path == "/api/ready":
                return 200, {"status": "ready",
                             "phu_thuoc": {"metadata": {"dat": True},
                                           "storage": {"dat": True}}}
            if path == "/api/novels" and method == "POST":
                if not (payload or {}).get("title", "").strip():
                    return 422, {"detail": "Tieu de trong."}
                return 201, {"novel": {"novel_id": "nov_gia"}}
            if path == "/api/chapters" and method == "POST":
                return 201, {"chapter": {"chapter_id": "chp_gia"}}
            if method == "DELETE" and path.startswith("/api/novels/"):
                return 200, {"removed": {"chapters": 1}}
            if path.startswith("/api/novels?mine=true"):
                return 200, {"novels": []}
            if path.startswith("/api/novels/"):
                return 200, {"novel": {"title": "x"}, "chapters": [{}]}
            # Job va audio phai co hinh dang THAT. Tra `{}` cho qua loa thi
            # `buoc_tts` nem `KeyError: 'job'` va phep thu se do mot loi cua
            # chinh ban gia lap, khong phai cua san pham.
            if path == "/api/jobs" and method == "POST":
                return 201, {"job": {"job_id": "job_gia", "status": "pending"}}
            if path.startswith("/api/jobs/"):
                return 200, {"job": {"job_id": "job_gia", "status": "completed",
                                     "attempts": 1, "done_parts": 1,
                                     "total_parts": 1}}
            if path.startswith("/api/audio/") and path.endswith("/url"):
                return 200, {"url": "https://vi-du.test/a.mp3?X-Amz-Signature=z"}
            if path.startswith("/api/audio/"):
                return 403, {"detail": "Không có quyền."}
            return 200, {}

        return goi

    # -- chung minh loi CU that su ton tai --------------------------------

    def test_the_old_direct_index_raised_keyerror(self):
        """
        Tai hien hanh vi CU tren dung hinh dang phan hoi that.

        Khong co phep thu nay thi cac test duoi chi chung minh "ma moi chay
        duoc", chu khong chung minh no SUA cai gi.
        """
        phan_hoi = {"detail": "Khong dang nhap duoc."}
        with self.assertRaises(KeyError) as nc:
            _ = phan_hoi["token"]
        self.assertEqual(nc.exception.args[0], "token")

    def test_the_source_no_longer_indexes_token_directly(self):
        """
        Xet MA, khong xet chu thich.

        Ban dau phep thu nay quet ca tep va bat phai chinh dong chu thich dang
        giai thich loi — mot khang dinh sai, no se bao dong ngay ca khi ma da
        dung.
        """
        import io
        import tokenize

        nguon = (GOC / "scripts" / "staging_smoke.py").read_text(encoding="utf-8")
        ma = []
        for tok in tokenize.generate_tokens(io.StringIO(nguon).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                ma.append(tok.string)
        chi_ma = " ".join(ma)
        self.assertNotIn('r [ "token" ]', chi_ma.replace('r["token"]', 'r [ "token" ]'),
                         "phan hoi loi khong co khoa `token`")
        for dong in nguon.splitlines():
            hep = dong.split("#", 1)[0]
            self.assertNotIn('r["token"]', hep,
                             f"con doc thang khoa token: {dong.strip()[:70]}")
        self.assertIn('r.get("token"', nguon)

    # -- hanh vi MOI ------------------------------------------------------

    def test_a_failed_login_raises_the_specific_error_not_keyerror(self):
        self.mod.goi = self.gia_lap(dang_nhap_hong=True)
        with self.assertRaises(self.mod.KhongDangNhapDuoc):
            self.mod.buoc_xac_thuc("http://vi-du.test")

    def test_the_guard_is_not_a_blanket_except(self):
        """Bat `Exception` chung se nuot ca loi that. Chi duoc bat DUNG mot loai."""
        import inspect

        nguon = inspect.getsource(self.mod.main)
        self.assertIn("except KhongDangNhapDuoc", nguon)
        for rong in ("except Exception", "except BaseException", "except:"):
            self.assertNotIn(rong, nguon, f"khong duoc bat {rong} o main()")

    def test_a_successful_login_still_returns_the_token(self):
        self.mod.goi = self.gia_lap()
        tk = self.mod.buoc_xac_thuc("http://vi-du.test")
        self.assertEqual(tk["tok_a"], "tok-gia")
        self.assertEqual(tk["tok_b"], "tok-gia")

    def test_main_does_not_crash_when_login_fails(self):
        self.mod.goi = self.gia_lap(dang_nhap_hong=True)
        try:
            ma = self.mod.main(["--api", "http://vi-du.test",
                                "--wake-timeout", "1"])
        except KeyError as exc:
            self.fail(f"van con KeyError: {exc}")
        self.assertEqual(ma, 1, "co buoc hong thi phai thoat khac 0")

    # -- cho thu hai: dang nhap "refresh" trong buoc noi dung --------------

    def test_the_refresh_login_failure_still_returns_ids_for_cleanup(self):
        """
        Cho thu hai cung loai loi: `tok2 = r["token"]` trong `buoc_noi_dung`.

        Luc do novel va chapter DA duoc tao. Sap o day nghia la `ids` khong bao
        gio duoc tra ve, nen `main()` khong biet phai xoa gi.
        """
        self.mod.goi = self.gia_lap(dang_nhap_lai_hong=True)
        tk = {"a": "a@example.test", "mk": "mk", "dau": "abcd1234",
              "tok_a": "tok-gia", "tok_b": "tok-gia"}
        ids = self.mod.buoc_noi_dung("http://vi-du.test", tk)
        self.assertEqual(ids, {"novel": "nov_gia", "chapter": "chp_gia"},
                         "phai tra ve id de con don duoc")

    def test_cleanup_runs_even_when_the_refresh_login_fails(self):
        self.mod.goi = self.gia_lap(dang_nhap_lai_hong=True)
        self.mod.main(["--api", "http://vi-du.test", "--wake-timeout", "1"])
        da_xoa = [d for m, d in self.da_goi
                  if m == "DELETE" and d.startswith("/api/novels/")]
        self.assertTrue(da_xoa, "phai goi DELETE de don fixture [SMOKE]")

    def test_nothing_is_deleted_when_nothing_was_created(self):
        self.mod.goi = self.gia_lap(dang_nhap_hong=True)
        self.mod.main(["--api", "http://vi-du.test", "--wake-timeout", "1"])
        self.assertEqual([d for m, d in self.da_goi if m == "DELETE"], [],
                         "chua tao gi thi khong co gi de xoa")


if __name__ == "__main__":
    unittest.main()


class TestTheAcceptanceCoversTheLocalVoicePath(unittest.TestCase):
    """
    Hai lo hong khien `61/61 xanh` khong chung minh duoc thu no tuong chung minh.

      1. Bo nghiem thu cu CHI chay giong di qua mang (Edge/CapCut). Duong giong
         cuc bo — nap model ONNX, WAV -> MP3 — chua bao gio duoc cham toi, du
         do la duong duy nhat chay tren may nguoi dung.
      2. Chuong smoke chi 3 cau = MOT doan, nen `_concat_mp3` khong bao gio
         chay. Mot may THIEU ffmpeg van cho 61/61 xanh roi hong o chuong dai
         that — dung cai bay da ghi trong `deploy/RUNBOOK-WORKER.md` nhung
         chinh bo nghiem thu lai khong bat duoc.
    """

    def setUp(self) -> None:
        self.nguon = (GOC / "scripts" / "staging_smoke.py").read_text(
            encoding="utf-8")

    def test_co_buoc_chay_giong_cuc_bo(self) -> None:
        self.assertIn("def buoc_giong_cuc_bo(", self.nguon)
        self.assertIn("buoc_giong_cuc_bo(a.api", self.nguon)

    def test_buoc_do_ep_ra_NHIEU_doan(self) -> None:
        """`chunk_chars` nho la thu duy nhat ep duong ghep ffmpeg phai chay."""
        than = _than_ham(self.nguon, "buoc_giong_cuc_bo")
        self.assertIn('"chunk_chars"', than)
        self.assertIn("total_parts", than)
        self.assertIn(">= 2", than)

    def test_buoc_do_doi_dung_mot_lan_chay(self) -> None:
        than = _than_ham(self.nguon, "buoc_giong_cuc_bo")
        self.assertIn('(j.get("attempts") or 0) == 1', than)

    def test_danh_sach_giong_duoc_kiem_pham_vi(self) -> None:
        than = _than_ham(self.nguon, "buoc_danh_sach_giong")
        self.assertIn("/api/voices", than)
        self.assertIn('startswith("vi")', than)
        self.assertIn("recommended", than)
        self.assertIn("== 7", than)

    def test_giong_ngoai_pham_vi_bi_kiem(self) -> None:
        than = _than_ham(self.nguon, "buoc_tu_choi_giong")
        self.assertIn("ma == 400", than)
        # Va phai chung minh KHONG job nao duoc tao — tu choi ma van ghi job
        # xuong kho thi van la hong.
        self.assertIn("khong job nao duoc tao", than)

    def test_bo_qua_giong_cuc_bo_phai_noi_ro_cai_gia(self) -> None:
        """Co `--skip-local-voice` phai ghi ro no lam mat kiem tra gi."""
        self.assertIn("--skip-local-voice", self.nguon)
        i = self.nguon.index("--skip-local-voice", self.nguon.index("add_argument"))
        self.assertIn("ffmpeg", self.nguon[i:i + 400])

    def test_don_dep_doi_soat_ca_chuong_thu_hai(self) -> None:
        than = _than_ham(self.nguon, "don_dep")
        self.assertIn("chapter_cuc_bo", than)
        self.assertIn('da_xoa.get("chapters")', than)


def _than_ham(nguon: str, ten: str) -> str:
    """Than cua mot ham cap module, cat den `\ndef ` ke tiep."""
    i = nguon.index(f"def {ten}(")
    j = nguon.find("\ndef ", i + 1)
    return nguon[i:j if j > 0 else len(nguon)]
