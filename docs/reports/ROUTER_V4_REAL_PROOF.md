# Router V4 — số đo lần chạy bằng chứng thật (2026-09-03)

Chạy trên kho Fanfic World thật. Không mock, không phá huỷ, không xuất bản.
Lệnh: `python scripts/router_v4_real_proof.py --max-parallel {1,3}`

## Bốn lớp việc (mission #21)

| Nút | Lớp việc | Placement đã chọn | Kết quả |
|---|---|---|---|
| `T1-phan-tich` | phân tích kho, CHỈ ĐỌC | `AG01/gemini-3.8-flash-medium` | OK — trả lời đúng: `ProviderRegistry`, 3 provider (`capcut`/`edge`/`piper`), cách thêm provider mới |
| `T2-qa-da-phuong-thuc` | QA đa phương thức trên ảnh sản xuất THẬT | `AG01/gemini-3.8-flash-medium` | OK — đọc `docs/screenshots/01-home-desktop.png`, nêu 5 phần tử UI có thật + 3 vấn đề khả dụng |
| `T3-viet-report` | việc code trong worktree CÔ LẬP | `AG01/claude-opus-4-6-thinking` | OK — ghi `scripts/router_v4/report.py`, biên dịch được, đúng phạm vi |
| `T4-review-doc-lap` | review ĐỘC LẬP | `AG01/claude-opus-4-6-thinking` | OK — tìm ra lỗi THẬT (xem dưới) |

Ảnh **không** bị sửa/di chuyển/ghi đè — nút chỉ đọc, không có worktree,
không có quyền ghi.

## Số đo

| Hạng mục | Tuần tự (`--max-parallel 1`) | Song song (`--max-parallel 3`) |
|---|---|---|
| Thời gian tường | 174.0s | **117.0s** |
| Tổng thời gian worker (gồm review) | 125.3s | 87.4s |
| Thành công | 4/4 | 4/4 |
| Lượt thử lại | 1 | 0 |
| Nút có review độc lập | 2 | 2 |
| Xung đột gộp | 0 | 0 |

**Tăng tốc wall-clock thực đo: 174.0 / 117.0 = 1.49x** trên cùng một DAG.

Giới hạn của con số này, nói rõ: hai lần chạy **không** đối chứng hoàn hảo —
lần tuần tự có 1 lượt thử lại, lần song song có 0. Trần tăng tốc ở đây thấp
vì **chỉ có MỘT tài khoản Antigravity thật**: cả 4 nút tranh 3 khe của AG01,
và `T4` phụ thuộc `T3` nên không song song được. Mỗi việc còn tốn một lần
khởi động nguội tiến trình `agy` (~4–10s) vì mỗi việc dùng một `--add-dir`
khác nhau. Cấp phát AG02–AG08 sẽ nới trần này; nó **không** phải giới hạn
của bộ lập lịch.

## Review độc lập tìm ra lỗi thật

`T4` (Claude Opus, khác họ model với worker viết code) báo về mã do `T3` sinh:

- `# type: ignore[arg-type]` che một cảnh báo mypy **hợp lệ** — hệ quả của
  việc khai `Dict[str, object]` thay vì `Dict[str, Any]`/`TypedDict`.
- `float(task.get('duration', 0.0))` sẽ **ném `TypeError` lúc chạy** nếu
  `duration` không phải số.

Đây là phát hiện có giá trị, không phải "đủ số cho đẹp".

## Nhà cung cấp / tài khoản đã chứng minh

| Provider | Tài khoản | Trạng thái | Bằng chứng |
|---|---|---|---|
| Antigravity | `ag-account-01` (AG01) | **THẬT, đã dùng** | chạy 4 nút qua 3 model khác nhau (Gemini Flash Medium, Claude Opus, + Gemini Flash High ở lần trước) |
| Codex | `codex-account-01` | **THẬT, đã xác thực** | `codex login status` = đã đăng nhập; đã đọc được ảnh; đã ghi tệp đúng trong worktree ở một lần chạy |
| OpenCode | `opencode-account-01` | **THẬT, đã xác thực** | `opencode serve` v1.18.25, `/provider` báo `connected: ["opencode"]` |
| Claude Code | phiên hiện tại | điều phối | `dispatchable=false` — không nhận dispatch |
| Antigravity AG02 | `ag-account-02` | **OFFLINE** | hồ sơ Windows `C:\Users\AG02` **có tồn tại**, cầu nối chưa chạy (cần đăng nhập phiên đó) |
| Antigravity AG03–08 | — | **OFFLINE** | chưa có hồ sơ Windows; đòi hồ sơ riêng (xem `docs/AI_ROUTER_V4.md` §2.1) |

**Tài khoản Antigravity thật đã chứng minh: 1.** Mission đòi "ít nhất hai
runtime đã xác thực khác nhau" cho Antigravity — **CHƯA đạt**, và nó không
thể đạt được mà không có người vận hành đăng nhập vào hồ sơ Windows AG02.
Ba **nhà cung cấp** khác nhau (Antigravity + Codex + OpenCode) đã được
chứng minh là thật và dùng được.

## Lỗi thật do chính lần chạy này phát hiện (đã sửa + có bài kiểm khoá lại)

1. `raw_excerpt` bị cắt còn 400 ký tự nhưng vẫn bị đọc lại để suy ra trạng
   thái ⇒ **mọi** việc thành công đều bị gán `no_json_block` giả.
2. `agy` thừa kế `cwd` của tiến trình Python ⇒ đường dẫn tương đối giải ra
   **ngoài** `--add-dir`, lệnh ghi bị từ chối, việc "xong" mà không có tệp.
3. Lease khoá theo **runtime** ⇒ AG01 (3 khe) bị ép xuống 1 việc một lúc.
4. `LeaseStore` dùng **một** kết nối sqlite chia sẻ ⇒ `InterfaceError` khi
   3 nút chạy song song; cả ba hỏng trước khi gửi việc.
5. Worker ghi đúng tệp nhưng để **mô tả** trong `changes` thay vì đường dẫn
   ⇒ cổng `diff` chặn cứng một việc làm đúng.
6. Worker ghi đúng tệp rồi trả **phản hồi rỗng** ⇒ bị coi là hỏng dù bằng
   chứng trên đĩa đều đạt. Nay bằng chứng khách quan **thắng** lời khai.
7. Nút phụ thuộc đọc ở **gốc kho** nên không thấy kết quả nằm trong worktree
   cô lập của nút trước ⇒ reviewer báo "không tìm thấy tệp" một cách sai.
8. `_dem_hong_truoc` rơi về lịch sử **toàn cục** ⇒ một lần hỏng ở bất kỳ đâu
   làm **mọi** việc leo thang chế độ.
9. Chạy lại cùng mission ⇒ trùng tên worktree, mọi lần chạy sau hỏng cho tới
   khi dọn tay. Nay mỗi lần chạy có `run_tag` riêng.
10. `test_KHONG_dung_gi_ngoai_thu_muc_muc_tieu` chụp **toàn bộ** thư mục temp
    của HĐH ⇒ hỏng khi bất kỳ tiến trình nào tạo tệp tạm (lỗi có từ trước).
