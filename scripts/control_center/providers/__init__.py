"""NHÀ CUNG CẤP NGOÀI + KHO BÍ MẬT (V0.6.1, Part D).

Năm mảnh, mỗi mảnh một tệp, ranh giới bí mật đi xuyên cả năm:

  kho_bi_mat   KhoBiMat — nơi DUY NHẤT giá trị credential được ghi/đọc.
               Windows Credential Manager (bền) hoặc bộ nhớ (kiểm thử).
               KHÔNG có "rơi về tệp thường": không kho an toàn thì không lưu.
  so           SoProvider — sổ SQLite `providers.db`: provider / tài khoản /
               model. Chỉ giữ `credential_ref`, alias, metadata. Từ chối ghi
               bất kỳ chuỗi giống bí mật.
  preset       Preset OpenAI-compatible + Alibaba DashScope + Tencent Hunyuan
               — cấu hình được, đánh dấu `da_do=False` cho tới khi đo thật.
  adapter      AdapterOpenAICompat — thử kết nối chi phí tối thiểu, hỏi một
               câu thủ công. Mọi lỗi trả về đã lọc; header xác thực chỉ tồn
               tại trong closure `BiMat.dung`.
  be           BeTaiKhoan — bể tài khoản chung: chọn ít tải nhất, cooldown có
               bậc (cùng hằng với Router V4), failover theo loại trừ.
  dich_vu      DichVuProvider — mặt tiền cho webapi/engine: agent và giao diện
               nhận `credential_ref`/khả năng, không bao giờ nhận giá trị.
"""
from scripts.control_center.providers.kho_bi_mat import (BiMat, KhoBiMat,          # noqa: F401
                                                         KhoBiMatBoNho,
                                                         KhoBiMatTrong,
                                                         KhongCoBiMat,
                                                         LoiKhoBiMat,
                                                         mo_kho_bi_mat)
from scripts.control_center.providers.dich_vu import DichVuProvider              # noqa: F401
