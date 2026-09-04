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
             mock.patch.object(pc, "ghi_audit"):
            ma = pc.pha_prepare(mock.Mock())
        self.assertEqual(ma, 5)


if __name__ == "__main__":
    unittest.main()
