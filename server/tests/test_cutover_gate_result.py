"""Bai kiem hoi quy: doc ket qua tu cong dieu hanh KHONG duoc fail-open.

LOI THAT (2026-09-04, lo ra khi CHAY pha PREPARE)
--------------------------------------------------
Cong dieu hanh ghi ket qua bang `{ ...; echo "# exit=$?"; } > "$out"`, tuc
tep lon dan trong luc verb chay. Bo dieu phoi thi doc `cat $out` moi 3 giay
va TRA VE ngay khi tep khac rong, voi `ma_thoat` mac dinh la 0 khi chua co
dong `# exit=`.

Hau qua do duoc: `preflight` that su tra ve `# exit=1` (unit staging con
chay), nhung bo dieu phoi doc trung phan dau cua tep, khong thay dau ket
thuc, va bao **PREPARE_PASS**. Mot cong an toan bao dat trong khi no dang
tu choi.

Hai sua doc lap:
  1. cong ghi vao tep tam roi `mv` (nguyen tu) — ben goi khong bao gio
     thay ban do dang
  2. bo dieu phoi DOI dong `# exit=`; thieu no la CHUA XONG, va het gio ma
     van thieu la THAT BAI (124), khong phai thanh cong
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops import prod_cutover as pc  # noqa: E402

GOC = Path(__file__).resolve().parents[2]

DAY_DU_FAIL = (
    "# verb=preflight luc=2026-09-04T16:11:20Z\n"
    "=== 1. ENV ===\n"
    "=== 2. STAGING DA TAT ===\n"
    "TU CHOI: unit staging con dang chay\n"
    "# exit=1\n"
)
MOT_PHAN = (
    "# verb=preflight luc=2026-09-04T16:11:20Z\n"
    "=== 1. ENV ===\n"
    "=== 2. STAGING DA TAT ===\n"
)
DAY_DU_PASS = MOT_PHAN + "  PREFLIGHT_PASS\n# exit=0\n"


class DocKetQua(unittest.TestCase):
    def _cong(self, chuoi_doc, han=30):
        """`chuoi_doc` la cac lan `cat` lien tiep tra ve."""
        lan = {"i": 0}

        def _aws(lenh, nhap=None, han=300):
            if lenh.startswith("printf"):
                return 0, "", ""
            i = min(lan["i"], len(chuoi_doc) - 1)
            lan["i"] += 1
            return 0, chuoi_doc[i], ""

        with mock.patch.object(pc, "aws", side_effect=_aws), \
             mock.patch.object(pc.time, "sleep"):
            return pc.cong("preflight", han=han)

    def test_ket_qua_day_du_FAIL_duoc_bao_la_FAIL(self):
        ma, _ = self._cong([DAY_DU_FAIL])
        self.assertEqual(ma, 1)

    def test_ket_qua_day_du_PASS_duoc_bao_la_PASS(self):
        ma, _ = self._cong([DAY_DU_PASS])
        self.assertEqual(ma, 0)

    def test_KHONG_bao_thanh_cong_khi_moi_doc_duoc_MOT_PHAN(self):
        """Day dung la lo hong: mot phan tep, chua co `# exit=`."""
        ma, _ = self._cong([MOT_PHAN])
        self.assertNotEqual(ma, 0, "doc mot phan KHONG duoc bao la thanh cong")
        self.assertEqual(ma, 124)

    def test_doi_den_khi_dau_ket_thuc_xuat_hien(self):
        """Doc mot phan truoc, day du sau -> phai lay ma THAT."""
        ma, out = self._cong([MOT_PHAN, MOT_PHAN, DAY_DU_FAIL])
        self.assertEqual(ma, 1)
        self.assertIn("# exit=1", out)

    def test_het_gio_la_THAT_BAI(self):
        ma, out = self._cong([MOT_PHAN], han=0)
        self.assertEqual(ma, 124)
        self.assertIn("het gio", out)

    def test_ma_thoat_khong_phai_so_thi_coi_la_that_bai(self):
        ma, _ = self._cong(["# verb=x\n# exit=khong-phai-so\n"])
        self.assertEqual(ma, 1)

    def test_lay_dong_exit_CUOI_CUNG(self):
        """Neu vi ly do nao do co nhieu dong, dong cuoi la cua verb ngoai."""
        ma, _ = self._cong(["# exit=0\nlung tung\n# exit=3\n"])
        self.assertEqual(ma, 3)


class CongGhiNguyenTu(unittest.TestCase):
    def test_cong_ghi_tep_tam_roi_mv(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('mv -f "$tam" "$out"', sh)
        # Khong duoc con duong ghi THANG vao $out.
        self.assertNotIn('} > "$out" 2>&1', sh)


class PrepareTatStagingTruocPreflight(unittest.TestCase):
    """Preflight tu choi chay khi con unit staging song, nen `prepare` phai
    tat chung TRUOC — neu khong `prepare` khong bao gio qua duoc."""

    def test_thu_tu_verb(self):
        goi = []

        def _cong(v, han=900):
            goi.append(v)
            return 0, f"# verb={v}\n# exit=0\n"

        with mock.patch.object(pc, "aws", return_value=(0, "CO", "")), \
             mock.patch.object(pc, "_chay", return_value=(0, "", "")), \
             mock.patch.object(pc, "cong", side_effect=_cong), \
             mock.patch.object(pc, "lay_env_production",
                               return_value={"R2_BUCKET": "fanfic-prod"}), \
             mock.patch.object(pc, "render_env_text", return_value="X=1\n"), \
             mock.patch.object(pc, "tom_tat_env", return_value=[]), \
             mock.patch.object(pc, "lay_env_translation", return_value={}), \
             mock.patch.object(pc, "ghi_audit"):
            pc.pha_prepare(mock.Mock())
        self.assertIn("stop-staging", goi)
        self.assertIn("preflight", goi)
        self.assertLess(goi.index("stop-staging"), goi.index("preflight"),
                        "phai tat staging TRUOC preflight")

    def test_preflight_that_bai_thi_prepare_that_bai(self):
        def _cong(v, han=900):
            return (1, "# exit=1\n") if v == "preflight" else (0, "# exit=0\n")

        with mock.patch.object(pc, "aws", return_value=(0, "CO", "")), \
             mock.patch.object(pc, "_chay", return_value=(0, "", "")), \
             mock.patch.object(pc, "cong", side_effect=_cong), \
             mock.patch.object(pc, "lay_env_production",
                               return_value={"R2_BUCKET": "fanfic-prod"}), \
             mock.patch.object(pc, "render_env_text", return_value="X=1\n"), \
             mock.patch.object(pc, "tom_tat_env", return_value=[]), \
             mock.patch.object(pc, "lay_env_translation", return_value={}), \
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_prepare(mock.Mock())
        self.assertEqual(ma, 5)



class InAnToan(unittest.TestCase):
    """Mot loi HIEN THI khong bao gio duoc phep lam do duong khoi phuc.

    LOI THAT: giua mot lan TU DONG ROLLBACK, lenh bat lai GCE DA chay,
    nhung tien trinh chet ngay sau do voi `UnicodeEncodeError: 'charmap'
    codec can't encode character '\u2192'` khi in ket qua tra ve tu
    `journalctl`. Ban ghi noi "dang lui" roi im.
    """

    def test_in_khoi_khong_nem_khi_console_khong_ma_hoa_duoc(self):
        import io

        class ConsoleCp1252(io.StringIO):
            def write(self, s):
                s.encode("cp1252")      # nem UnicodeEncodeError nhu console that
                return super().write(s)

        gia = ConsoleCp1252()
        with mock.patch("sys.stdout", gia):
            # Khong duoc nem — day la ca bai kiem.
            pc._in_khoi("Started fanfic-worker-prod.service — TTS worker → OK")
            pc._in("kiểm tra nhịp → xong")

    def test_in_khoi_van_in_duoc_van_ban_binh_thuong(self):
        import io

        gia = io.StringIO()
        with mock.patch("sys.stdout", gia):
            pc._in_khoi("dong mot\ndong hai\n\n  dong ba  ")
        ra = gia.getvalue()
        self.assertIn("dong mot", ra)
        self.assertIn("dong hai", ra)
        self.assertIn("dong ba", ra)
        self.assertNotIn("\n\n\n", ra)

    def test_khong_con_print_tho_cho_dau_ra_tu_xa(self):
        src = (GOC / "scripts" / "ops" / "prod_cutover.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertNotIn('.join("   " + d', src,
                         "dau ra tu xa phai di qua `_in_khoi`")


class EnvWorkerDich(unittest.TestCase):
    """Thieu `/etc/fanfic-audio/translation-worker-prod.env` thi
    `fanfic-translation-worker-prod.service` chet voi 'Failed to load
    environment files' roi restart vo han. Da xay ra that o canary lan 1."""

    def _env_tts(self):
        from scripts.ops.cutover_target import (
            PROD_APPWRITE_DATABASE_ID, PROD_APPWRITE_ENDPOINT,
            PROD_APPWRITE_PROJECT_ID, PROD_R2_BUCKET)
        return {
            "FAS_ENV": "production", "DATA_BACKEND": "appwrite",
            "STORAGE_BACKEND": "r2", "FAS_INLINE_WORKER": "false",
            "APPWRITE_ENDPOINT": PROD_APPWRITE_ENDPOINT,
            "APPWRITE_PROJECT_ID": PROD_APPWRITE_PROJECT_ID,
            "APPWRITE_DATABASE_ID": PROD_APPWRITE_DATABASE_ID,
            "APPWRITE_API_KEY": "k" * 265, "R2_ACCOUNT_ID": "a" * 32,
            "R2_BUCKET": PROD_R2_BUCKET, "R2_ACCESS_KEY_ID": "i" * 32,
            "R2_SECRET_ACCESS_KEY": "s" * 64,
            "FAS_LOCAL_VOICES": "piper:ngochuyen",
            "FAS_PUBLIC_VOICE_LANGUAGES": "vi",
        }

    def test_dung_duoc_env_worker_dich_tu_env_TTS(self):
        e = pc.lay_env_translation(self._env_tts())
        self.assertEqual(e["STORAGE_BACKEND"], "local")
        self.assertEqual(e["FAS_TRANSLATION_INLINE_WORKER"], "false")
        self.assertEqual(e["FAS_LOCAL_VOICES"], "piper:ngochuyen")

    def test_worker_dich_KHONG_duoc_mang_credential_R2(self):
        """No khong can, va mot khoa thua la mot khoa co the ro ri ma
        khong ai co ly do de dung."""
        e = pc.lay_env_translation(self._env_tts())
        for k in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                  "R2_ACCOUNT_ID", "R2_BUCKET"):
            self.assertNotIn(k, e)

    def test_khang_dinh_tu_choi_khi_co_credential_R2(self):
        from scripts.ops.cutover_target import (
            CutoverRefused, khang_dinh_translation_production)
        e = pc.lay_env_translation(self._env_tts())
        e["R2_SECRET_ACCESS_KEY"] = "s" * 64
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_translation_production(e)
        self.assertIn("R2_SECRET_ACCESS_KEY", str(ctx.exception))

    def test_khang_dinh_tu_choi_storage_backend_r2(self):
        from scripts.ops.cutover_target import (
            CutoverRefused, khang_dinh_translation_production)
        e = pc.lay_env_translation(self._env_tts())
        e["STORAGE_BACKEND"] = "r2"
        with self.assertRaises(CutoverRefused):
            khang_dinh_translation_production(e)

    def test_khang_dinh_tu_choi_du_an_khong_phai_production(self):
        from scripts.ops.cutover_target import (
            CutoverRefused, khang_dinh_translation_production)
        e = pc.lay_env_translation(self._env_tts())
        e["APPWRITE_PROJECT_ID"] = "fanfic-world-staging"
        with self.assertRaises(CutoverRefused):
            khang_dinh_translation_production(e)

    def test_cong_co_verb_install_translation_env(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("install-translation-env", sh)
        self.assertIn("env-translation.stage", sh)

    def test_preflight_TU_CHOI_khi_thieu_env_worker_dich(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        i = sh.index("vh_preflight()")
        than = sh[i:sh.index("vh_stop_staging()", i)]
        self.assertIn("ENV_TR", than)

    def test_trinh_cai_tao_ca_HAI_tep_stage(self):
        sh = (GOC / "scripts" / "ops" / "install_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("env-translation.stage", sh)


class DongBoCongKhongDuocIMLANG(unittest.TestCase):
    """LOI THAT: `ProtectSystem=full` lam /usr CHI DOC, nen verb `update`
    khong bao gio ghi duoc ban root cua cong. Loi bi nuot bang
    `2>/dev/null || true`, nen `update` bao THANH CONG trong khi cong tren
    may van chay ban CU — mot verb vua merge khong bao gio toi noi."""

    def test_update_KHONG_nuot_loi_khi_dong_bo(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        i = sh.index("vh_update()")
        than = sh[i:sh.index("vh_canary()", i)]
        # Chi soi DONG dong bo ban root cua cong. `git config
        # --add safe.directory ... || true` ben tren la mot lan nuot loi
        # KHAC va hoan toan vo hai — soi ca ham thi bai kiem truot vi mot
        # dong khong lien quan.
        dong_dong_bo = [d for d in than.splitlines()
                        if "/usr/local/sbin/fanfic-prod-admin" in d]
        self.assertTrue(dong_dong_bo)
        for d in dong_dong_bo:
            self.assertNotIn("2>/dev/null", d,
                             "buoc dong bo cong khong duoc nuot loi")
            self.assertNotIn("|| true", d)
        self.assertIn("CANH BAO", than)
        self.assertIn("return 1", than)

    def test_unit_drain_cho_phep_ghi_usr_local_sbin(self):
        sh = (GOC / "scripts" / "ops" / "install_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        rwp = [d for d in sh.splitlines() if d.startswith("ReadWritePaths=")]
        self.assertTrue(rwp, "khong tim thay ReadWritePaths")
        self.assertIn("/usr/local/sbin", rwp[0],
                      "thieu duong nay thi `update` khong bao gio dong bo duoc cong")

    def test_update_tao_moi_tep_stage_con_thieu(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        i = sh.index("vh_update()")
        than = sh[i:sh.index("vh_canary()", i)]
        self.assertIn("env-translation.stage", than)
        self.assertIn("0620", than)

if __name__ == "__main__":
    unittest.main()
