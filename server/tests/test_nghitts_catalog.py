"""
Catalog NghiTTS: 25 giọng, một nguồn khai báo duy nhất, lọc đúng.

Bộ test này giữ ba thứ mà nếu trôi đi sẽ hỏng âm thầm:

  1. **Tương thích ngược.** Ba `voice_id` đã tồn tại trước khi mở rộng catalog
     (`piper:ngochuyen`, `piper:calmwoman3688`, `piper:deepman3909`) phải giữ
     nguyên id, tên hiển thị và giới tính. Chúng đã nằm trong `.env`, trong
     `FAS_LOCAL_VOICES` và trong danh sách đề xuất của app desktop.

  2. **Không đoán metadata.** 22 giọng thêm mới giữ tên kỹ thuật và để trống
     giới tính. Tách `banmai` thành "Ban Mai" là đoán ranh giới từ và đoán dấu;
     gán giới tính từ tên tệp là đoán nốt. Test này chặn việc "làm cho đẹp".

  3. **Ánh xạ tệp tất định.** `voice_key` == tên tệp `.onnx` không đuôi. Không
     có bảng tra riêng nào được phép xuất hiện.
"""

from __future__ import annotations

import unittest

from desktop_app.providers.builtin_catalog import (
    PIPER_BUILTIN,
    PIPER_PREFERRED_KEY,
    piper_builtin_voices,
)
from server import tts_bridge


#: Ba giọng có TRƯỚC khi mở rộng catalog.
#:
#: `voice_key` và `gender` KHÔNG được đổi: khoá đã nằm trong cấu hình vận hành
#: và trong job/track đã tạo. `display_name` thì đã đổi một lần, theo bảng tên
#: chính thức của chủ dự án — tên hiển thị là thứ người dùng đọc, không phải
#: thứ hệ thống tra cứu.
CU = {
    "ngochuyen": "Female",
    "calmwoman3688": "Female",
    "deepman3909": "Male",
}

#: 22 giọng thêm mới trong lượt mở rộng.
MOI = {
    "adam1", "banmai", "chieuthanh", "duyoryx3175", "lacphi", "maiphuong",
    "manhdung", "minhkhang", "minhquang", "minhthu", "mytam2", "mytam2794",
    "ngochuyennew", "ngocngan3701", "phuongtrang", "taian2", "taian4",
    "thanhphuong2", "thientam", "tranthanh3870", "vietthao3886", "yannew",
}


class CatalogDayDu(unittest.TestCase):

    def test_dung_hai_muoi_lam_giong(self) -> None:
        self.assertEqual(len(PIPER_BUILTIN), 25)

    def test_khong_trung_voice_key(self) -> None:
        khoa = [m["voice_key"] for m in PIPER_BUILTIN]
        self.assertEqual(len(khoa), len(set(khoa)))

    def test_du_ca_cu_lan_moi(self) -> None:
        khoa = {m["voice_key"] for m in PIPER_BUILTIN}
        self.assertEqual(khoa, set(CU) | MOI)

    def test_moi_giong_deu_tieng_viet(self) -> None:
        for m in PIPER_BUILTIN:
            self.assertEqual(m["language"], "vi-VN", m["voice_key"])


class TuongThichNguoc(unittest.TestCase):
    """Ba id cũ đã nằm trong cấu hình vận hành — đổi là hỏng production."""

    def test_ba_id_cu_van_ton_tai(self) -> None:
        ids = {v.id for v in piper_builtin_voices()}
        for khoa in CU:
            self.assertIn(f"piper:{khoa}", ids)

    def test_ba_id_cu_van_dung_gioi_tinh(self) -> None:
        """
        `gender` của ba giọng này đã được kiểm chứng từ trước, nên giữ nguyên.
        Chỉ `display_name` đổi theo bảng tên chính thức.
        """
        theo_khoa = {m["voice_key"]: m for m in PIPER_BUILTIN}
        for khoa, gt in CU.items():
            self.assertEqual(theo_khoa[khoa]["gender"], gt, khoa)

    def test_ba_id_cu_van_dung_dau_danh_sach(self) -> None:
        """Thứ tự trong catalog là thứ tự hiển thị, và cũng là thứ tự dự phòng
        của `default_voice_key()`."""
        dau = [m["voice_key"] for m in PIPER_BUILTIN[:3]]
        self.assertEqual(dau, ["ngochuyen", "calmwoman3688", "deepman3909"])

    def test_giong_uu_tien_khong_doi(self) -> None:
        self.assertEqual(PIPER_PREFERRED_KEY, "ngochuyen")


class KhongDoanMetadata(unittest.TestCase):

    def test_ten_hien_thi_lay_tu_bang_ten_chinh_thuc(self) -> None:
        """
        Truoc day bai test nay khoa dieu NGUOC LAI: `display_name` phai BANG
        `voice_key`, vi khong co bang doi chieu nao va tu tach `banmai` thanh
        "Ban Mai" la doan ranh gioi tu lan doan dau.

        Chu du an da cung cap bang ten chinh thuc, nen tien de do het hieu luc.
        Cai con phai khoa la: ten den TU BANG, chu khong phai go tay tung muc —
        go tay thi hai cho lech nhau ma khong ai thay.
        """
        from desktop_app.providers.builtin_catalog import NGHITTS_DISPLAY_NAMES

        for m in PIPER_BUILTIN:
            self.assertEqual(m["display_name"],
                             NGHITTS_DISPLAY_NAMES[m["voice_key"]],
                             m["voice_key"])

    def test_giong_moi_van_KHONG_gan_gioi_tinh(self) -> None:
        """
        Bang ten chinh thuc chi noi TEN HIEN THI. No khong noi gioi tinh, va
        suy gioi tinh tu ten van la doan — doan sai thi bo loc giong nam/nu
        sau nay loc sai.
        """
        for m in PIPER_BUILTIN:
            if m["voice_key"] in MOI:
                self.assertEqual(m["gender"], "", m["voice_key"])

    def test_bang_ten_phu_dung_ca_catalog(self) -> None:
        """Thieu mot khoa la `NGHITTS_DISPLAY_NAMES[khoa]` nem KeyError luc nap."""
        from desktop_app.providers.builtin_catalog import NGHITTS_DISPLAY_NAMES

        self.assertEqual(set(NGHITTS_DISPLAY_NAMES),
                         {m["voice_key"] for m in PIPER_BUILTIN})


class AnhXaTepTatDinh(unittest.TestCase):

    def test_voice_key_chinh_la_ten_tep(self) -> None:
        """`<voice_key>.onnx` — không bảng tra, không suy đoán."""
        from desktop_app.providers.piper_models import PiperModelManager

        m = PiperModelManager(models_dir="/khong-ton-tai")
        for muc in PIPER_BUILTIN:
            onnx, cfg = m.paths_for(muc["voice_key"])
            self.assertEqual(onnx.name, f"{muc['voice_key']}.onnx")
            self.assertEqual(cfg.name, f"{muc['voice_key']}.onnx.json")

    def test_khong_co_bang_tra_ten_tep_rieng(self) -> None:
        """
        Catalog không được chứa tên tệp trong MÃ.

        Chỉ xét dòng mã, bỏ qua chú thích: ghi chú giải thích quy ước
        `<voice_key>.onnx` là thứ nên có, còn một chuỗi `.onnx` trong mã nghĩa
        là ai đó đã bắt đầu dựng bảng tra tên tệp.
        """
        import inspect
        from desktop_app.providers import builtin_catalog

        ma = [d for d in inspect.getsource(builtin_catalog).splitlines()
              if not d.strip().startswith("#")]
        dinh = [d for d in ma if ".onnx" in d]
        self.assertEqual(dinh, [],
                         "catalog có tên tệp trong mã — ánh xạ phải tất định")


class LocTheoDanhSachTrang(unittest.TestCase):
    """Catalog rộng ra KHÔNG được nới lỏng thứ được phục vụ."""

    class CauHinh:
        def __init__(self, *v, languages=("vi",)):
            self.local_voices = tuple(v)
            self.public_voice_languages = tuple(languages)

    def test_vu_tru_nghitts_bang_dung_catalog(self) -> None:
        self.assertEqual(
            tts_bridge.nghitts_voice_ids(),
            frozenset(f"piper:{m['voice_key']}" for m in PIPER_BUILTIN))
        self.assertEqual(len(tts_bridge.nghitts_voice_ids()), 25)

    def test_mac_dinh_van_chi_mot_giong_duoc_phuc_vu(self) -> None:
        """Thêm 22 giọng vào catalog không tự bật giọng nào."""
        from server.config import Settings

        self.assertEqual(Settings.local_voices, ("piper:ngochuyen",))

    def test_chi_giong_duoc_cau_hinh_moi_qua(self) -> None:
        s = self.CauHinh("piper:banmai")
        self.assertTrue(tts_bridge.voice_is_local_allowed("piper:banmai", s))
        self.assertFalse(tts_bridge.voice_is_local_allowed("piper:ngochuyen", s))

    def test_giong_ngoai_catalog_van_bi_chan(self) -> None:
        s = self.CauHinh("piper:khong-co-trong-catalog")
        self.assertEqual(tts_bridge.allowed_local_voice_ids(s), frozenset())

    def test_tat_het_bang_chuoi_rong_van_dung(self) -> None:
        self.assertEqual(
            tts_bridge.allowed_local_voice_ids(self.CauHinh()), frozenset())

    def test_bat_nhieu_giong_cung_luc_duoc(self) -> None:
        s = self.CauHinh("piper:ngochuyen", "piper:banmai", "piper:thientam")
        self.assertEqual(len(tts_bridge.allowed_local_voice_ids(s)), 3)


if __name__ == "__main__":
    unittest.main()
