"""Hợp đồng schema của Bulk Import — thứ `appwrite_bulk_import_store` TƯỞNG đã có.

`server/appwrite_bulk_import_store.py` khẳng định ngay trong mã:

    "Phải khớp CHÍNH XÁC schema trong `scripts/setup_appwrite.py` — bộ test hợp
     đồng (`server/tests/test_bulk_chapter_import.py`) so sánh hai tập này."

Câu đó SAI. `test_bulk_chapter_import.py` không hề nhắc tới `PERSISTED_FIELDS`,
và `test_appwrite_schema_contract.py` chỉ phủ bốn collection `novels`/`chapters`/
`tts_jobs`/`audio_tracks`. Hai collection của Bulk Import KHÔNG có lưới nào cả:
hôm nay chúng khớp là nhờ kỷ luật, không nhờ kiểm chứng.

Điều đó đáng sửa vì hậu quả im lặng: thêm một trường vào `PERSISTED_FIELDS` mà
quên khai trong `SCHEMA` thì Appwrite từ chối cả bản ghi bằng HTTP 400 — và chỉ
lộ ra trên môi trường THẬT, vì store giả trong test chấp nhận mọi trường.

`scrape_runs`/`scrape_run_items` đã có lưới tương đương trong
`test_appwrite_scrape_run_store.py::SchemaContractTest`; đây là phần còn thiếu.
"""
from __future__ import annotations

import unittest

from server.appwrite_bulk_import_store import (
    COL_BATCHES,
    COL_ITEMS,
    PERSISTED_FIELDS,
)


def _schema(collection: str) -> set:
    from scripts.setup_appwrite import SCHEMA

    return {key for key, *_ in SCHEMA[collection]["attributes"]}


class SchemaContractTest(unittest.TestCase):
    def test_hai_collection_khop_schema(self) -> None:
        for collection in (COL_BATCHES, COL_ITEMS):
            self.assertEqual(
                set(PERSISTED_FIELDS[collection]), _schema(collection),
                f"{collection}: PERSISTED_FIELDS lệch với scripts/setup_appwrite.py")

    def test_ca_hai_collection_deu_co_trong_schema(self) -> None:
        """Thiếu hẳn collection là dạng lệch tệ nhất — mọi thao tác ghi hỏng."""
        from scripts.setup_appwrite import SCHEMA

        for collection in (COL_BATCHES, COL_ITEMS):
            self.assertIn(collection, SCHEMA)

    def test_moi_collection_deu_co_it_nhat_mot_index(self) -> None:
        """Không index nghĩa là mọi truy vấn lọc thành quét toàn bảng."""
        from scripts.setup_appwrite import SCHEMA

        for collection in (COL_BATCHES, COL_ITEMS):
            self.assertTrue(SCHEMA[collection]["indexes"],
                            f"{collection}: không có index nào")

    def test_index_chi_tro_toi_thuoc_tinh_co_that(self) -> None:
        """Một index trỏ vào cột không tồn tại làm migration hỏng giữa chừng,
        SAU khi đã tạo xong thuộc tính — trạng thái nửa vời khó đọc nhất."""
        from scripts.setup_appwrite import SCHEMA

        for collection in (COL_BATCHES, COL_ITEMS):
            co = _schema(collection)
            for ten, _kieu, cot in SCHEMA[collection]["indexes"]:
                for c in cot:
                    self.assertIn(c, co, f"{collection}.{ten} trỏ tới cột {c!r} "
                                         f"không có trong schema")


class DocumentIdCeilingTest(unittest.TestCase):
    """`$id` của Appwrite tối đa 36 ký tự. Vượt trần thì Appwrite từ chối
    và cả lô nhập hỏng — nhưng chỉ trên môi trường thật.

    `scrape_run_items` đã có bài tương đương; Bulk Import thì chưa, dù nó
    xâu chuỗi ID còn nhiều tầng hơn (`batch_id` -> `item_id` -> `chapter_id`).
    """

    def test_batch_id_khong_vuot_36(self) -> None:
        from server.bulk_import_domain import batch_id_from_fingerprint

        self.assertLessEqual(len(batch_id_from_fingerprint("a" * 64)), 36)

    def test_item_id_khong_vuot_36_o_chi_so_lon_nhat(self) -> None:
        from server.bulk_import_domain import batch_id_from_fingerprint, item_id_for

        batch_id = batch_id_from_fingerprint("a" * 64)
        # 9999 la chi so LON NHAT duoc phep — cung la chuoi dai nhat.
        self.assertLessEqual(len(item_id_for(batch_id, 9999)), 36)

    def test_chapter_id_khong_vuot_36(self) -> None:
        from server.bulk_import_domain import (
            batch_id_from_fingerprint, chapter_id_for, item_id_for)

        item_id = item_id_for(batch_id_from_fingerprint("a" * 64), 9999)
        self.assertLessEqual(len(chapter_id_for(item_id)), 36)

    def test_chi_so_ngoai_pham_vi_bi_tu_choi_chu_khong_tao_id_dai(self) -> None:
        """Lối duy nhất tạo được ID quá dài là chỉ số 5 chữ số. Nó phải bị
        chặn ở cổng vào, chứ không lặng lẽ sinh ra một `$id` Appwrite từ chối."""
        from server.bulk_import_domain import (
            BulkImportFormatError, batch_id_from_fingerprint, item_id_for)

        batch_id = batch_id_from_fingerprint("a" * 64)
        for xau in (0, 10000, -1):
            with self.assertRaises(BulkImportFormatError, msg=f"chấp nhận {xau}"):
                item_id_for(batch_id, xau)


if __name__ == "__main__":
    unittest.main()
