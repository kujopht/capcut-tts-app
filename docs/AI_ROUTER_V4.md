# Router V4 — kết cấu thực thi AI đa nhà cung cấp

Router V4 **mở rộng** Router V3, không thay nó. Mọi module V3 vẫn chạy;
`scripts/router_v4/compat.py` dịch hai chiều V3 ↔ V4.

Quy tắc kiến trúc trung tâm:

> **Định tuyến theo YÊU CẦU của việc. KHÔNG định tuyến theo vai trò model
> đóng cứng.**

Claude lead yêu cầu *năng lực* ("2 worker thực thi mạnh, 1 worker phân tích
kho giá rẻ, 1 reviewer đa phương thức"); bộ lập lịch tự phân giải ra
provider/tài khoản/model. Không dòng nào trong `scripts/router_v4/**` hay
`config/fabric.json` nói "AG01 = coding".

---

## 1. Ma trận audit Router V3 (thực hiện trước khi viết mã)

| Hạng mục | Trước khi sửa (V3, thực tế đo được) | Dùng lại được | Còn thiếu | Hành động |
|---|---|---|---|---|
| Hợp đồng `WorkerAdapter` | 9 phương thức, 4 provider đã có | ✅ toàn bộ | — | Dùng lại nguyên vẹn |
| `TaskDag` | bắt chu trình, phụ thuộc treo, ghi chồng, đường tới hạn | ✅ toàn bộ | nút không mang *hợp đồng* | `MissionDag` bọc lại, thêm bảng `task_id → TaskContract` |
| `WorkerRegistry` | `WorkerSpec` gộp tài khoản+model+pool làm một | ⚠️ một phần | tách account/model/quota | Thêm `WorkerRuntime`/`ModelCapability`/`QuotaPool` |
| `WorktreeManager` | worktree cô lập + `verify_scope` | ✅ toàn bộ | tên trùng khi chạy lại | Thêm `run_tag` cho mỗi lần chạy |
| Adapter OpenCode | HTTP server, đã có; server **đang chạy thật** (v1.18.25) | ✅ | bài kiểm đóng cứng "không có server" | Sửa bài kiểm để dò thật |
| Daemon bền OpenCode/AG | `setup_autostart.py` (schtasks), `run_bridge.py` | ✅ | — | Dùng lại |
| Tích hợp Codex | gọi thẳng trong `ai_router_dispatch.py`, **không** có adapter | ⚠️ hình dạng lệnh | adapter theo hợp đồng | Viết `CodexAdapter` |
| Tích hợp Claude Code | `CLAUDE_LEAD` trong sổ, coi như worker | ⚠️ | nó **không** dispatch được | `dispatchable=false` |
| Adapter Antigravity **lập trình được** | `AntigravityNativeAdapter` + `AntigravityBridgeAdapter` — **THẬT, đã chạy** | ✅ | 1 model/adapter | Placement `(runtime, model)` |
| 8 tài khoản Antigravity | **CHỈ AG01 thật.** AG02 có hồ sơ Windows, cầu nối chưa chạy. AG03–08 chưa tồn tại | ⚠️ | 7 hồ sơ xác thực | Mô hình hoá `OFFLINE`/`needs_provisioning` |
| Sức khoẻ/trạng thái | `Health` 7 giá trị + cầu dập mạch | ✅ | lease/nhịp tim | Thêm `leases.py` |
| Credential broker | `fanfic_credential_broker.py`, không bao giờ in bí mật | ✅ | — | Dùng lại; V4 chỉ đọc *nhãn chỉ chỗ* |
| Lược đồ kết quả | `TaskResult` khá đủ | ⚠️ | `requires_decision`, `raw_log_ref`, `resource_usage` | `ResultEnvelope` + nhật ký ngoài ngữ cảnh |
| Thử lại/dự phòng | cầu dập mạch; `pool/runner.py` thử lại+đổi worker | ✅ | — | Dùng lại ý tưởng ở tầng V4 |
| Quota | `quota_remaining` chỉ tính điểm khi *quan sát được* | ⚠️ | **bể dùng chung** | `QuotaPool` theo tài khoản |
| Benchmark/lịch sử | `routing_history.py` (JSONL) | ✅ | tổng hợp theo model+loại việc | `history.py` |

**Kết luận audit:** V3 vững ở *cơ chế* (DAG, worktree, adapter, kiểm định) và
thiếu ở *mô hình dữ liệu* (tài khoản ≠ model ≠ quota) cùng *hợp đồng việc*.
V4 chỉ thêm hai thứ đó.

---

## 2. Sự thật đo được, không phải giả định

Ghi ngày và cách đo, vì mọi quyết định kiến trúc dưới đây dựa vào chúng.

### 2.1 Một hồ sơ Windows = một tài khoản Antigravity (2026-09-03)

```
HOME=<thư mục rỗng hoàn toàn>  agy models   →  VẪN xác thực thành công
```

`agy` giữ phiên trong **Windows Credential Manager của từng tài khoản
Windows**, không trong thư mục cấu hình. Chuyển hướng `HOME`/thư mục cấu
hình **không** tách được một hồ sơ thành hai tài khoản.

**Hệ quả:** danh tính cố định **đòi** một hồ sơ Windows riêng. AG03–AG08 vì
thế ở `OFFLINE` + `needs_provisioning`, không phải "sẵn sàng".

**Trên máy này có sẵn** một công cụ đổi tài khoản (`agy-profiles/`) ghi đè
blob credential để chuyển tài khoản. Router V4 **không dùng, không import,
không phụ thuộc** nó, và `fabric_config.assert_khong_xoay_tai_khoan()` **từ
chối nạp** một cấu hình chạm tới nó.

### 2.2 Đa phương thức là THẬT (2026-09-03)

| Model | Việc | Kết quả |
|---|---|---|
| `gemini-3.8-flash-high` | đọc `docs/screenshots/01-home-desktop.png` | mô tả đúng phần tử UI tiếng Việt có thật → `image` = **probed** |
| `codex-default` | cùng ảnh | cũng đọc được → `image` = **probed** |

Nên `image` **không** khan hiếm giữa hai nhà cung cấp này. `video`/`audio`
vẫn là **declared** (theo UI, chưa đo) và bộ lập lịch **chiết khấu** năng
lực chưa đo qua `evidence_discount`.

### 2.3 Bể quota dùng chung

UI Antigravity gom **Gemini** một nhóm, **Claude + GPT** một nhóm. Nên dùng
`gpt-oss-120b-medium` **không miễn phí**: nó rút từ đúng bể mà
`claude-opus-4-6-thinking` rút. Bể được tạo **theo tài khoản**
(`ag-account-01:antigravity_gemini`), nên hai tài khoản có hai bể độc lập.

---

## 3. Mô hình dữ liệu

```
WorkerRuntime   VẬT CHỨA: tài khoản + ranh giới xác thực + hạn mức đồng thời
ModelCapability NĂNG LỰC: làm được gì, họ nào, rút quota bể nào
QuotaPool       NGÂN SÁCH DÙNG CHUNG, theo TÀI KHOẢN
Placement       = (runtime, model)  ← thứ bộ lập lịch thực sự chọn
```

```
AG01 ─┬─ gemini-3.8-flash-high      ─┐
      ├─ gemini-3.8-flash-medium     │
      ├─ gemini-3.1-pro-low          ├─ 6 placement, 1 tài khoản
      ├─ claude-opus-4-6-thinking    │
      ├─ claude-sonnet-4-6           │
      └─ gpt-oss-120b-medium        ─┘
```

`Fabric.dem_tai_khoan()` tồn tại để **không ai** — kể cả báo cáo tự động —
nhầm "51 placement" thành "51 tài khoản".

**Bất biến kiểm bằng máy:** hai runtime **đã cấp phát** không được dùng
chung `auth_profile`. Vi phạm ⇒ `FabricError` **lúc nạp**.

---

## 4. Hợp đồng việc

Ba khối tách bạch: `requirements` (cần gì — bộ lập lịch đọc),
`execution` (chạy thế nào), `verification` (chứng minh thế nào).

- `forbidden_scope` **luôn thắng** `allowed_scope`; chồng nhau ⇒ từ chối lúc dựng.
- `.git/`, `.github/workflows/`, `.claude/settings*.json`, `.claude/hooks/`,
  `.env` **luôn** bị thêm vào `forbidden_scope`, dù hợp đồng không khai.
- `repo_write` **bắt buộc** kèm `allowed_scope` **và** `worktree_required`.

## 5. Bộ lập lịch — ba giai đoạn

1. **Lọc cứng** — năng lực thiếu / runtime OFFLINE·COOLDOWN·đầy chỗ /
   không dispatch được / ghim loại / rào an toàn. Không điểm số nào cứu.
2. **Cho điểm** — 11 chiều **có tên**, trọng số trong `config/fabric.json`.
3. **Giải thích** — `router explain <task>` in vì sao mỗi ứng viên thắng/trượt.

**Rào an toàn KHÔNG cấu hình được** (nằm trong mã, không trong JSON):

- review bảo mật **không bao giờ** tới Codex — bằng chứng 2026-08-28: Codex
  trả kết quả **rỗng** kèm *"flagged for possible cybersecurity risk"*.
- ghim thủ công **không mở được** rào năng lực/tin cậy.
- `--dangerously-skip-permissions` **không bao giờ** được dùng.

**Khan hiếm** (`scarcity_penalty`) nhìn **hàng đợi thật** (`Demand`), không
nhìn hằng số: hàng đợi rỗng ⇒ không giữ chỗ.

## 6. Chế độ thực thi

| Chế độ | Khi nào | Điều kiện |
|---|---|---|
| `SOLO` | việc thường | `impact × uncertainty` < 0.25 |
| `PRIMARY_CRITIC` | đủ rủi ro | ≥ 0.25, hoặc hợp đồng đòi review |
| `PARALLEL_HYPOTHESES` | tác động lớn **và** chưa rõ nguyên nhân | ≥ 0.60 |

Người review được `exclude_families=(họ tác giả,)` và **không** có
`repo_write` — một tài khoản khác chạy **cùng model** không phải review độc lập.

## 7. Lệnh vận hành

```bash
python -m scripts.router_v4.cli status        # bảng runtime + bể quota + lease
python -m scripts.router_v4.cli workers
python -m scripts.router_v4.cli models        # kèm số năng lực ĐÃ ĐO
python -m scripts.router_v4.cli pools
python -m scripts.router_v4.cli explain <task_id> --dag plan.json
python -m scripts.router_v4.cli drain AG01    # ngừng nhận việc MỚI
python -m scripts.router_v4.cli resume AG01
python -m scripts.router_v4.cli request --need-file needs.json
```

Dùng được từ Warp nhưng **không phụ thuộc** Warp — Warp chỉ là phòng điều
khiển, không phải bộ lập lịch.

## 8. Cấp phát thêm khe Antigravity

1. Tạo tài khoản Windows `AG0x`.
2. Đăng nhập phiên đó, chạy `agy` một lần, đăng nhập Google **riêng của khe**.
3. Trong phiên đó: `python -m scripts.router_v3.run_bridge --worker-id AG0x`
4. Tuỳ chọn: `python -m scripts.router_v3.setup_autostart --worker-id AG0x ...`

**Không** dùng công cụ đổi tài khoản để giả lập nhiều danh tính — nó bị
chặn ở `identity.py` và `fabric_config.py`.

## 9. Bằng chứng thật

`python scripts/router_v4_real_proof.py --max-parallel 3`

DAG 4 nút trên kho thật, không phá huỷ, không xuất bản: phân tích chỉ đọc,
QA đa phương thức trên ảnh sản xuất thật, việc code trong worktree cô lập,
review độc lập. Xem `docs/reports/` cho số đo của lần chạy gần nhất.

## 10. Chưa làm (cố ý)

Router **lập lịch công việc**; nó không hấp thụ mọi hệ con. Chính sách xuất
bản Fanfic, kiến trúc TTS/lưu trữ/scraping/OpenMontage, di trú Appwrite/AWS
**không** thuộc Router — chúng là *khối công việc khách* chạy **qua** kết cấu
này về sau.
