"""
Cau truc du lieu cho DANH GIA THU CONG chat luong anh bia sinh ra
(`CoverQualityEvaluation`) - mot NGUOI xem anh that va DIEN vao, KHONG
phai ket qua mot bo giam khao AI/thi giac may tinh nao ca (mission ra chi
thi RO RANG: "Do NOT implement an AI visual judge tonight - manual
checklist schema only"). File nay CHI la schema + vai phuong thuc tien
loi round-trip qua dict (de luu kem job record sau nay) - KHONG co logic
tu dong dien du lieu tu anh.

Xem thanh phan doc-duoc-cho-nguoi song song o docs/cover_quality_checklist.md
- cung mot bo truong, mot ban la dataclass (de luu/truy van bang code),
mot ban la markdown (de mot nguoi thuc su tick vao khi xem anh)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class CoverQualityEvaluation:
    """Mot lan danh gia THU CONG cho MOT anh bia da sinh ra. Cac truong
    khop CHINH XAC danh sach trong mission brief:

      - `character_count`: so nhan vat NGUOI DANH GIA dem duoc thuc su
        xuat hien tren anh (co the khac `max_visible_characters` cua
        CoverGenerationRequest neu model ve thieu/thua nhan vat).
      - `primary_identity_recognizable` / `secondary_identity_recognizable`:
        nguoi dung nhan ra DUNG nhan vat chinh/phu du dinh hay khong (vd
        co dung mau toc/trang phuc dac trung, khong bi "nhan vat anime
        chung chung" - xem van de that trong server/character_identity.py).
      - `identity_blending_observed`: co hien tuong tron lan dac diem giua
        hai nhan vat (vd nhan vat A mang trang phuc cua nhan vat B).
      - `duplicate_people_observed`: co nguoi/khuon mat THUA xuat hien
        ngoai y muon (loi bo cuc that tung ghi nhan - xem
        CoverPromptBuilder._build_compact_prompt's own docstring).
      - `faces_visible`: khuon mat (cua cac nhan vat chinh) co lo ro,
        khong bi cat xen/quay lung.
      - `composition_acceptable`: bo cuc tong the co chap nhan duoc
        (khung hinh, can bang, khong loi ky la ro rang).
      - `text_artifact_observed`: model co "ve" ra chu/glyph gia (khong
        phai chu that, thuong la artifact cua model anh khi gap tu ngu
        trong prompt) - anh huong den vung "negative space for title" du
        dinh danh cho overlay tieu de that.
      - `production_ready`: KET LUAN cuoi cung cua nguoi danh gia - anh
        nay co du dung duoc cho san xuat (hien thi cho nguoi doc that)
        hay khong.
      - `notes`: ghi chu tu do, vd mo ta cu the loi quan sat duoc.

    KHONG co truong nao duoc TINH TU DONG - moi truong deu do nguoi danh
    gia dien tay sau khi xem anh that.
    """

    character_count: int = 0
    primary_identity_recognizable: bool = False
    secondary_identity_recognizable: bool = False
    identity_blending_observed: bool = False
    duplicate_people_observed: bool = False
    faces_visible: bool = False
    composition_acceptable: bool = False
    text_artifact_observed: bool = False
    production_ready: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Round-trip qua dict - de luu keo mot job record (vd JSON hoa
        canh CoverJob/GPUJobTelemetry) ma khong ro ri kieu dataclass."""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "CoverQualityEvaluation":
        """Dung lai CHINH XAC field name cua dataclass - se raise
        TypeError ro rang neu dict truyen vao co key la, tot hon la am
        tham bo qua du lieu sai dinh dang."""
        return CoverQualityEvaluation(**data)
