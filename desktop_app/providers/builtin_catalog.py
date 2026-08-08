"""
Catalog giong built-in cho Edge TTS va Piper local.

NGUYEN TAC: cac giong o day LUON xuat hien trong catalog, ke ca khi may khong
co mang, chua cai `edge_tts`, hay chua tai model Piper. "Co trong catalog"
KHONG dong nghia voi "dang kha dung" - trang thai kha dung do probe quyet dinh.
"""

from __future__ import annotations

from typing import Dict, List

from desktop_app.providers.base import PROVIDER_EDGE, PROVIDER_PIPER, Voice

# -----------------------------------------------------------------------------
# Edge TTS - giong tieng Viet
# -----------------------------------------------------------------------------

#: ShortName that cua Microsoft Edge TTS cho tieng Viet.
EDGE_BUILTIN: List[Dict[str, str]] = [
    {
        "voice_key": "vi-VN-HoaiMyNeural",
        "display_name": "Hoài My",
        "language": "vi-VN",
        "gender": "Female",
    },
    {
        "voice_key": "vi-VN-NamMinhNeural",
        "display_name": "Nam Minh",
        "language": "vi-VN",
        "gender": "Male",
    },
]

# -----------------------------------------------------------------------------
# Piper local - model tuong thich nghimestudio/nghitts
# -----------------------------------------------------------------------------

#: Model theo bo nghimestudio/nghitts. Moi model can DUNG cap file
#: `.onnx` va `.onnx.json`.
#:
#: KHONG khai bao URL tai hay SHA-256 o day: chua xac minh duoc nguon tai on
#: dinh nen tuyet doi khong bia dat. Nguoi dung tu chon 2 file model trong
#: Cai dat; khi nao co URL chinh thuc kiem chung duoc thi bo sung sau.
#:
#: `voice_key` la dinh danh ON DINH trong ung dung, KHONG PHAI ten file.
#: Voi Ngoc Huyen, ten file ONNX that KHONG duoc suy doan tu ten hien thi -
#: nguoi dung chon dung cap file, va lien ket duoc luu trong models.json
#: (xem PiperModelManager.bind). Cac model theo quy uoc ten cu van tim thay
#: theo `<voice_key>.onnx` nhu truoc.
#:
#: THU TU o day chinh la thu tu hien thi trong catalog.
PIPER_BUILTIN: List[Dict[str, str]] = [
    {
        "voice_key": "ngochuyen",
        "display_name": "Ngọc Huyền (mới)",
        "description": "Giọng nữ review phim — Piper Local",
        "language": "vi-VN",
        "gender": "Female",
    },
    {
        "voice_key": "calmwoman3688",
        "display_name": "Giọng nữ điềm đạm (calmwoman3688)",
        "description": "Giọng nữ điềm đạm — Piper Local",
        "language": "vi-VN",
        "gender": "Female",
    },
    {
        "voice_key": "deepman3909",
        "display_name": "Giọng nam trầm (deepman3909)",
        "description": "Giọng nam trầm — Piper Local",
        "language": "vi-VN",
        "gender": "Male",
    },
    # ------------------------------------------------------------------
    # Phần còn lại của bộ NghiTTS (22 giọng).
    #
    # `display_name` GIỮ NGUYÊN TÊN KỸ THUẬT, và `gender` để trống. Đó là
    # chủ ý, không phải làm cho xong:
    #
    #   * Tách `banmai` thành "Ban Mai" hay `minhthu` thành "Minh Thư" là
    #     ĐOÁN ranh giới từ và ĐOÁN dấu. Đoán sai thì tên hiển thị sai với
    #     người dùng cuối, và không có nguồn nào để đối chiếu.
    #   * Vài tên trông như tên người thật (`mytam2`, `tranthanh3870`,
    #     `thanhphuong2`). Gán tên hiển thị dạng người thật cho một giọng
    #     tổng hợp là chuyện định danh, không phải chuyện thẩm mỹ — xem
    #     `docs/GCE-WORKER-CAPACITY.md` mục rủi ro.
    #   * Ba giọng phía trên giữ nguyên tên và giới tính CŨ để không phá
    #     tương thích ngược.
    #
    # TODO: khi có bảng tên chính thức từ nguồn model, cập nhật
    # `display_name`/`gender` ở ĐÂY — đây là nơi duy nhất khai báo.
    #
    # `voice_key` == tên tệp `.onnx` (không đuôi). Ánh xạ tất định, không
    # cần bảng tra riêng: `<voice_key>.onnx` + `<voice_key>.onnx.json`.
    # Bộ NghiTTS dùng một `config.json` chung và symlink từng
    # `<voice_key>.onnx.json` trỏ vào đó — `Path.is_file()` đi theo symlink
    # nên không phải xử lý gì thêm.
] + [
    {
        "voice_key": khoa,
        "display_name": khoa,          # TODO: tên hiển thị chính thức
        "description": "Piper Local (NghiTTS)",
        "language": "vi-VN",
        "gender": "",                  # không đoán
    }
    for khoa in (
        "adam1",
        "banmai",
        "chieuthanh",
        "duyoryx3175",
        "lacphi",
        "maiphuong",
        "manhdung",
        "minhkhang",
        "minhquang",
        "minhthu",
        "mytam2",
        "mytam2794",
        "ngochuyennew",
        "ngocngan3701",
        "phuongtrang",
        "taian2",
        "taian4",
        "thanhphuong2",
        "thientam",
        "tranthanh3870",
        "vietthao3886",
        "yannew",
    )
]

#: Giong Piper duoc uu tien lam mac dinh khi da cai model hop le.
PIPER_PREFERRED_KEY = "ngochuyen"


def edge_builtin_voices() -> List[Voice]:
    """Giong Edge built-in. `installed` phu thuoc goi edge_tts, xet o provider."""
    return [
        Voice(
            provider=PROVIDER_EDGE,
            voice_key=item["voice_key"],
            engine_voice_id=item["voice_key"],   # Edge dung chinh ShortName
            display_name=item["display_name"],
            language=item["language"],
            gender=item.get("gender", ""),
            supports_rate=True,
            output_format="mp3",
            installed=True,
            builtin=True,
        )
        for item in EDGE_BUILTIN
    ]


def piper_builtin_voices() -> List[Voice]:
    """
    Giong Piper built-in.

    `installed=False` va `model_path=None` la mac dinh: chua tai model. Provider
    se cap nhat lai theo model thuc te co trong thu muc du lieu nguoi dung.
    """
    return [
        Voice(
            provider=PROVIDER_PIPER,
            voice_key=item["voice_key"],
            engine_voice_id=item["voice_key"],
            display_name=item["display_name"],
            description=item.get("description", ""),
            language=item["language"],
            gender=item.get("gender", ""),
            model_path=None,
            supports_rate=True,
            output_format="wav",     # Piper sinh WAV, pipeline se chuyen sang MP3
            installed=False,
            builtin=True,
        )
        for item in PIPER_BUILTIN
    ]


#: Id day du cua cac giong built-in - dung trong test de bao ve yeu cau
#: "luon xuat hien trong catalog".
BUILTIN_VOICE_IDS = tuple(
    [f"{PROVIDER_EDGE}:{i['voice_key']}" for i in EDGE_BUILTIN]
    + [f"{PROVIDER_PIPER}:{i['voice_key']}" for i in PIPER_BUILTIN]
)
