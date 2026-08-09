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
#: Ten hien thi CHINH THUC cua tung model NghiTTS, do chu du an cung cap.
#:
#: DAY LA NOI KHAI BAO DUY NHAT. Truoc do `display_name` bang chinh
#: `voice_key` vi khong co bang doi chieu nao, va tu tach `banmai` thanh
#: "Ban Mai" la DOAN ranh gioi tu lan DOAN dau. Nay da co bang that nen
#: khong con phai doan.
#:
#: KHOA cua bang nay la `voice_key`, tuc la ten tep `.onnx` (khong duoi), va
#: no KHONG doi. `voice_id` (`piper:<voice_key>`) da nam trong job va track
#: da tao, va gop phan sinh `output_key` tren R2 — doi ten hien thi khong
#: duoc dong toi no.
#:
#: Luu y mot hoan doi CO Y: truoc day `ngochuyen` mang ten "Ngọc Huyền (mới)".
#: Nay `ngochuyen` la "Ngọc Huyền" con hau to "(Mới)" chuyen sang model
#: `ngochuyennew`, dung nhu bang chu du an dua. `voice_id` cua ca hai giu
#: nguyen, nen job cu van tro dung model cu.
NGHITTS_DISPLAY_NAMES: Dict[str, str] = {
    "adam1": "Adam",
    "banmai": "Ban Mai",
    "calmwoman3688": "Nữ Điềm Đạm",
    "chieuthanh": "Chiêu Thanh",
    "deepman3909": "Nam Trầm",
    "duyoryx3175": "Duy Oryx",
    "lacphi": "Lạc Phi",
    "maiphuong": "Mai Phương",
    "manhdung": "Mạnh Dũng",
    "minhkhang": "Minh Khang",
    "minhquang": "Minh Quang",
    "minhthu": "Minh Thư",
    "mytam2": "Mỹ Tâm 1",
    "mytam2794": "Mỹ Tâm 2",
    "ngochuyen": "Ngọc Huyền",
    "ngochuyennew": "Ngọc Huyền (Mới)",
    "ngocngan3701": "Ngọc Ngân",
    "phuongtrang": "Phương Trang",
    "taian2": "Tài An 1",
    "taian4": "Tài An 2",
    "thanhphuong2": "Thanh Phương",
    "thientam": "Thiên Tâm",
    "tranthanh3870": "Trần Thanh",
    "vietthao3886": "Việt Thảo",
    "yannew": "Yan (Mới)",
}

PIPER_BUILTIN: List[Dict[str, str]] = [
    {
        "voice_key": "ngochuyen",
        "display_name": NGHITTS_DISPLAY_NAMES["ngochuyen"],
        "description": "Giọng nữ review phim — NghiTTS",
        "language": "vi-VN",
        "gender": "Female",
    },
    {
        "voice_key": "calmwoman3688",
        "display_name": NGHITTS_DISPLAY_NAMES["calmwoman3688"],
        "description": "Giọng nữ điềm đạm — NghiTTS",
        "language": "vi-VN",
        "gender": "Female",
    },
    {
        "voice_key": "deepman3909",
        "display_name": NGHITTS_DISPLAY_NAMES["deepman3909"],
        "description": "Giọng nam trầm — NghiTTS",
        "language": "vi-VN",
        "gender": "Male",
    },
    # ------------------------------------------------------------------
    # Phần còn lại của bộ NghiTTS (22 giọng).
    #
    # `gender` VẪN để trống, và vẫn là chủ ý. Bảng tên chính thức chỉ nói
    # tên hiển thị; nó không nói giới tính. Suy giới tính từ tên là đoán, và
    # đoán sai thì bộ lọc giọng nam/nữ sau này lọc sai. Ba giọng phía trên
    # giữ `gender` CŨ vì chúng đã có từ trước và đã được kiểm chứng.
    #
    # Rủi ro định danh vẫn còn: `mytam2`, `tranthanh3870`, `thanhphuong2`
    # trùng dạng tên người nổi tiếng, và bảng tên chính thức làm chúng hiện
    # rõ hơn chứ không làm nó biến mất — xem `docs/GCE-WORKER-CAPACITY.md`.
    #
    # `voice_key` == tên tệp `.onnx` (không đuôi). Ánh xạ tất định, không
    # cần bảng tra riêng: `<voice_key>.onnx` + `<voice_key>.onnx.json`.
    # Bộ NghiTTS dùng một `config.json` chung và symlink từng
    # `<voice_key>.onnx.json` trỏ vào đó — `Path.is_file()` đi theo symlink
    # nên không phải xử lý gì thêm.
] + [
    {
        "voice_key": khoa,
        "display_name": NGHITTS_DISPLAY_NAMES[khoa],
        "description": "NghiTTS",
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
