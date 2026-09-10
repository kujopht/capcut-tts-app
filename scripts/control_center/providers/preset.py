"""PRESET nhà cung cấp — OpenAI-compatible + hai đích cụ thể, đều cấu hình được.

Mỗi preset là một KHAI BÁO (`da_do=False`): base_url, đường `/models`,
đường `/chat/completions`, header xác thực, vài model gợi ý. Không preset
nào được coi là ĐÃ ĐO cho tới khi `thu_ket_noi` chạy thật với một tài khoản
thật — cùng kỷ luật với `capability_source: declared|probed` của
`fabric.json`. Alibaba và Tencent KHÔNG được giả định giống nhau: mỗi cái có
base_url riêng, model riêng, ghi chú riêng, và mọi trường đều sửa được ở
tầng provider (base_url ghi đè preset).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

#: Nang luc khai bao cho model chat OpenAI-compatible — CHUA do.
NANG_LUC_KHAI_BAO: Tuple[str, ...] = ("coding", "repo_read", "structured_output",
                                      "long_context")


@dataclass(frozen=True)
class Preset:
    ma: str
    ten: str
    kieu: str = "openai_compatible"
    base_url_mac_dinh: str = ""
    duong_models: str = "/models"
    duong_chat: str = "/chat/completions"
    header_xac_thuc: str = "Authorization"
    tien_to: str = "Bearer "
    models_goi_y: Tuple[str, ...] = ()
    ghi_chu: str = ""
    tai_lieu: str = ""
    da_do: bool = False
    yeu_cau_base_url: bool = False
    #: Ten bien moi truong pho bien de nguoi van hanh nhan ra (KHONG doc
    #: bien do — chi de hien thi goi y).
    bien_moi_truong_goi_y: Tuple[str, ...] = ()

    def to_dict(self) -> Dict:
        return {"ma": self.ma, "ten": self.ten, "kieu": self.kieu,
                "base_url_mac_dinh": self.base_url_mac_dinh,
                "duong_models": self.duong_models, "duong_chat": self.duong_chat,
                "header_xac_thuc": self.header_xac_thuc, "tien_to": self.tien_to.strip(),
                "models_goi_y": list(self.models_goi_y), "ghi_chu": self.ghi_chu,
                "tai_lieu": self.tai_lieu, "da_do": self.da_do,
                "yeu_cau_base_url": self.yeu_cau_base_url,
                "bien_moi_truong_goi_y": list(self.bien_moi_truong_goi_y)}


PRESETS: Dict[str, Preset] = {
    "openai_compatible": Preset(
        ma="openai_compatible", ten="OpenAI-compatible (tuỳ chỉnh)",
        base_url_mac_dinh="", yeu_cau_base_url=True,
        ghi_chu="Bất kỳ endpoint theo hình dạng OpenAI: nhập base_url tới gốc `/v1` "
                "(vd `https://api.example.com/v1`). Model lấy qua GET /models khi thử kết nối.",
    ),
    "alibaba_dashscope": Preset(
        ma="alibaba_dashscope", ten="Alibaba Cloud Model Studio (DashScope, chế độ OpenAI-compatible)",
        base_url_mac_dinh="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        models_goi_y=("qwen-plus", "qwen-turbo", "qwen-max"),
        ghi_chu="Mặc định là endpoint QUỐC TẾ (Singapore). Khoá tạo ở vùng Trung Quốc "
                "đại lục dùng `https://dashscope.aliyuncs.com/compatible-mode/v1` — sửa "
                "base_url khi thêm provider. Tên model là GỢI Ý theo tài liệu công khai, "
                "danh sách thật lấy khi thử kết nối.",
        tai_lieu="https://www.alibabacloud.com/help/en/model-studio/",
        bien_moi_truong_goi_y=("DASHSCOPE_API_KEY",),
    ),
    "tencent_hunyuan": Preset(
        ma="tencent_hunyuan", ten="Tencent Cloud Hunyuan (endpoint OpenAI-compatible)",
        base_url_mac_dinh="https://api.hunyuan.cloud.tencent.com/v1",
        models_goi_y=("hunyuan-turbos-latest", "hunyuan-lite"),
        ghi_chu="Hunyuan phơi một endpoint OpenAI-compatible với khoá API riêng (KHÁC cặp "
                "SecretId/SecretKey của Tencent Cloud API v3 — cặp đó KHÔNG dùng được ở "
                "đây). Nếu tài khoản của bạn chỉ có SecretId/SecretKey, tạo khoá API "
                "Hunyuan trong console trước. Tên model là GỢI Ý; danh sách thật lấy khi "
                "thử kết nối.",
        tai_lieu="https://cloud.tencent.com/document/product/1729",
        bien_moi_truong_goi_y=("HUNYUAN_API_KEY",),
    ),
}


def preset(ma: str) -> Preset:
    try:
        return PRESETS[ma]
    except KeyError:
        raise KeyError(f"không có preset {ma!r}; có: {', '.join(sorted(PRESETS))}") from None


def danh_sach() -> List[Dict]:
    return [p.to_dict() for p in PRESETS.values()]
