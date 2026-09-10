# Kiểm toán bể tài khoản Antigravity — Router Control Center V0.6.1

Ngày đo: 2026-09-10 · Nhánh `feat/v061-memory-provider-vault` · Máy người vận hành (Windows 11).

Câu hỏi của đợt này không phải "có 8 tài khoản không" mà là **Router nhìn thấy
gì, chọn thế nào, và cái gì xảy ra khi một khe bận/hỏng**. Mọi con số dưới đây
đến từ sổ đăng ký đang chạy (`FC.nap(probe=True)`) hoặc từ bài kiểm có mock,
không từ giả định.

## 1. Số đếm — từ sổ đăng ký, không giả định

Lệnh đo (chỉ in nhãn/trạng thái, không đọc credential):
`FC.nap(root=<kho>, probe=True)` → 7.2 s.

| Hạng mục | Giá trị đo | Nguồn |
|---|---|---|
| Khe AG **đăng ký** | 8 (`AG01`…`AG08`) | `fabric.json` khai AG01/AG02 + mẫu `ag_slot_template` sinh AG03..AG08 (`AG_SLOTS`) |
| **Cấp phát** (`provisioned`) | 8 | lớp phủ launcher: `saved_profiles/acc1..acc8.bin` CÓ THẬT trên đĩa → `transport=launcher`, `auth_profile=agy-launcher:accN` |
| **Nhận dispatch** | 8 | `dispatchable=True` (chỉ `CLAUDE_LEAD` là `False`) |
| **Khoẻ** lúc dò | 8 IDLE | `do_suc_khoe` hỏi từng runtime |
| **Hồ sơ xác thực riêng** | 8/8 | `Fabric.validate`: hai runtime không được dùng chung `auth_profile` |
| **Tổng chỗ đồng thời** | 10 | AG01 `concurrency=3`, AG02..AG08 `=1` |
| Tài khoản theo nhà cung cấp | antigravity 8 · codex 1 · opencode 1 · claude 1 (không dispatch) | `Fabric.dem_tai_khoan()` |

Trên máy không có `accN.bin`, khe tương ứng **OFFLINE** với `needs_provisioning`
nói rõ lý do — không "worker giả" (bài kiểm `test_khe_thieu_profile_thi_OFFLINE_khong_khai_gia`).

## 2. Chọn khe, trải tải, cooldown, failover — cơ chế có sẵn của V4, nay có bài kiểm riêng

| Câu hỏi | Trả lời (mã) | Bài kiểm (`scripts/tests/test_account_pool_v061.py`) |
|---|---|---|
| Router có thấy > 1 tài khoản? | `Fabric.placements()` = mọi (runtime, model); 8 khe × 6 model AG | `test_so_khe_tu_so_dang_ky_khong_gia_dinh` |
| Có chọn được khe ngoài AG01? | `Scheduler._loai_vi` loại khe `đầy chỗ`; `_cham_diem.availability` ưu tiên khe rảnh | `test_chon_duoc_khe_ngoai_AG01_khi_AG01_day` |
| Trải tải thế nào? | điểm `availability = w·(1 − in_flight/concurrency)` → khe rảnh thắng; tất định (điểm giảm dần rồi theo khoá placement) | `test_giao_dong_thoi_ton_trong_suc_chua_tung_khe` (≥7 khe khác nhau trong 8 lượt đầu) |
| Failover khi một khe hỏng cho đúng việc đó? | `decide(exclude=…)`: "đã thử và hỏng cho chính việc này"; `orchestrator._chay_co_thu_lai` cộng dồn `exclude` | `test_failover_bo_khe_da_hong_cho_chinh_viec` — loại hết 8 → **fail closed**, không hạ chuẩn |
| Một khe bận có chặn cả nhà cung cấp? | Không: chỉ khe đó bị "đầy chỗ"; 7 khe còn lại đủ điều kiện | `test_mot_khe_khong_san_khong_lam_sap_nha_cung_cap` (AG03 OFFLINE + AG04 COOLDOWN → vẫn chọn được) |
| Giao đồng thời có vượt sức chứa? | Không: đúng 10 lượt rồi `None` với lý do "đầy chỗ x…"; mọi lúc `in_flight ≤ concurrency` | cùng bài trên |
| Cooldown | 3 hỏng liên tiếp → 60 s, rồi 300 / 900 / 1800 (`NGUONG_COOLDOWN`, `BACKOFF_COOLDOWN`); hết hạn tự chọn lại; thành công xoá chuỗi | `test_cooldown_co_bac_va_tu_het` |
| Tất định | cùng fabric + cùng trạng thái → cùng kết quả | `test_tat_dinh` |

## 3. Leader và worker có dùng cùng bể không? — CÓ, và trước V0.6.1 chỗ Leader vô hình

`leader.PhienLeader` là một tiến trình `agy` ẤM ghim `runtime_id="AG01"`
(`PROVIDER_LEADER = "antigravity"`). Worker được `Scheduler` xếp lên cả 8 khe,
kể cả AG01 (3 chỗ). Trước V0.6.1, phiên Leader **không** nằm trong
`running_tasks` của AG01 → bộ lập lịch vẫn xếp đủ 3 worker lên AG01 → bốn
tiến trình `agy` trên một tài khoản, và bảng điều khiển không nói vì sao AG01
"bận".

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Chỗ Leader chiếm trên AG01 | vô hình với `Scheduler` | `leader.chiem_cho_fabric(fabric, "AG01", "LEADER:<project>")` khi mở phiên; `tra_cho_fabric` ở `shutdown` |
| Worker còn được xếp lên AG01 | 3 | 2 (`test_cho_leader_chiem_hien_ra_voi_bo_lap_lich`) |
| Thống kê `completed/failed` | — | không bị nhãn Leader làm lệch (nhãn không đi qua `mark_finished`) |
| Bảng điều khiển | không thấy | `/api/usage` → `runtimes[].running_tasks` chứa `LEADER:<project>`; `pool.antigravity.leader_chiem` |

Đây là thay đổi **duy nhất** chạm hành vi bể: một nhãn trong `running_tasks`.
Không đổi số khe, không đổi cooldown, không chạm launcher, không chạm credential.

## 4. Tóm tắt bể cho giao diện (`/api/usage` → `pool`)

`UsageReporter.be_tai_khoan()` — theo nhà cung cấp: `dang_ky`, `cap_phat`,
`nhan_dispatch`, `khoe` (IDLE/BUSY/DEGRADED), `cooldown`, `offline`,
`tong_cho`, `dang_dung`, `ho_so_rieng`, `leader_chiem`. `runtimes[]` thêm
`auth_profile` (NHÃN chỉ chỗ), `transport`, `running_tasks`,
`consecutive_failures`, `cooldown_until`, `drained`, `health_detail`. Hộp thoại
**Providers** hiển thị bể này cạnh provider ngoài.

## 5. Bể tài khoản CHUNG cho provider ngoài (Part D5/C1)

`scripts/control_center/providers/be.py::BeTaiKhoan` dùng **cùng ba hằng** với
V4 (`NGUONG_COOLDOWN`, `BACKOFF_COOLDOWN`), chọn ít tải nhất, phá hoà tất định
theo alias, failover theo `loai_tru`, trạng thái bền trong `providers.db`. Một
luật cho cả hai bể — người vận hành không phải học hai cách cooldown.

## 6. Không làm (cố ý)

* Không chạm launcher, không đăng nhập lại, không xoay/đọc credential của
  `agy` — `_MAU_XOAY_TAI_KHOAN` trong `fabric_config` vẫn là rào.
* Không đổi `concurrency` của khe nào: số đó là khai báo của người vận hành.
* Không "gộp" bể Antigravity vào `providers.db`: bể AG sống trong fabric của
  V4 và có bài kiểm riêng; V0.6.1 chỉ làm nó **đọc được** và **đúng thực tế**.
