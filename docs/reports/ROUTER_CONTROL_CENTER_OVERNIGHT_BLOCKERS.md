# Router Control Center V0.1 — chặn qua đêm (2026-09-08)

Ghi mọi thứ **không tự quyết được** trong lượt chạy qua đêm. Không chờ, không
đoán: ghi vào đây rồi làm tiếp mọi việc độc lập còn lại.

Quy ước: mỗi mục ghi **cần gì / vì sao chặn / đã làm gì thay thế**.

---

## B1. Hồ sơ router toàn cục đã QUÁ HẠN — cần người xác nhận

- **Cần gì:** xác nhận có giữ `ACTIVE PROFILE: CLAUDE_CONSERVATION` nữa không.
- **Vì sao chặn:** `~/.claude/CLAUDE.md` ghi `SET: 2026-08-28`,
  `INTENDED DURATION: ~1 week`. Hôm nay là 2026-09-08 — quá **11 ngày**.
  Chính tệp đó dặn: quá hạn thì **hỏi người dùng**, đừng lặng lẽ conserve mãi.
  Người dùng đang ngủ nên không hỏi được.
- **Đã làm thay thế:** không tự đổi hồ sơ. Chạy đúng quy trình bắt buộc
  (`ai_router_dispatch.py --dry-run`); bộ định tuyến TỰ trả về
  `pool = NATIVE_CLAUDE` cho `INTEGRATION/MEDIUM` với lý do "cross-file
  integration là vai trò thin-integrator mà conservation dành riêng cho
  native Claude". Nên phần dựng lõi chạy ở native Claude là ĐÚNG hồ sơ hiện
  hành, không phải lách. Review độc lập đẩy sang pool ngoài.
- **Quyết định buổi sáng:** giữ CLAUDE_CONSERVATION hay quay lại BALANCED.

## B2. AG02–AG08 chưa cấp phát — cần đăng nhập Google thủ công

- **Cần gì:** người vận hành đăng nhập `agy` trong từng hồ sơ Windows AG0x.
- **Vì sao chặn:** ranh giới OAuth/đăng nhập — nằm đúng trong danh sách
  "true human boundary" của đêm nay, và `docs/AI_ROUTER_V4.md` §2.1 đã đo:
  một hồ sơ Windows = một tài khoản Antigravity, không giả lập được.
- **Đã làm thay thế:** Control Center đọc trạng thái cấp phát THẬT từ
  `Fabric`; runtime chưa cấp phát hiện `OFFLINE` kèm lý do, không bị đếm
  nhầm thành khe sẵn sàng. Không đụng công cụ xoay tài khoản.

## B3. Không có con số quota ĐỌC ĐƯỢC BẰNG MÁY từ nhà cung cấp

- **Cần gì:** một API/CLI trả số dư quota thật của Antigravity/Codex.
- **Vì sao chặn:** không nhà cung cấp nào ở đây công bố số đọc được bằng máy.
- **Đã làm thay thế:** màn Usage phân loại tường minh
  `ACTUAL` / `ESTIMATED` / `UNAVAILABLE` và **không bịa** số nào. Chỉ
  `ACTUAL` cho thứ Control Center tự đếm được tại chỗ (số lượt dispatch,
  giây tường, số lượt trong cửa sổ trượt của `QuotaPool`).

## B4. `agy` headless TỪ CHỐI QUYỀN CÔNG CỤ — chặn đường việc CÓ GHI

**Đây là chặn thật, đo được, và nó cần một quyết định của bạn.**

- **Triệu chứng:** việc CÓ GHI giao cho `agy` chạy 35–95 giây rồi kết thúc
  với phản hồi **rỗng**. Việc CHỈ ĐỌC thì chạy tốt.
- **Nguyên nhân (đọc thẳng từ stderr của `agy`, 2026-09-08):**

  ```
  jetski: no output produced — a tool required the "command" permission
  that headless mode cannot prompt for, so it was auto-denied.
  Add an allow-rule under permissions.allow in settings.json
  (e.g. command(<target>)). Alternatively, re-run with
  --dangerously-skip-permissions to auto-approve all tools.
  ```

  Lần chạy khác cho đúng thông báo đó với `"read_file"`. Chế độ headless
  **không hỏi người dùng được**, nên nó tự chối và cả lượt mất trắng.
  `--mode accept-edits` chỉ phủ công cụ GHI TỆP — đánh đổi này đã được ghi
  sẵn trong docstring của `PoolAntigravityAdapter`, nay đo được bằng số.

- **Vì sao KHÔNG tự sửa:** hai đường sửa đều là quyết định của bạn.
  1. `--dangerously-skip-permissions` — **CẤM TUYỆT ĐỐI** trong kho này
     (`docs/AI_ROUTER_V4.md` §5, và `PoolAntigravityAdapter._KHONG_BAO_GIO_DUNG`
     chặn ở mức mã). Không đụng tới.
  2. Thêm allow-rule vào `settings.json` của **chính `agy`** — đây là nới
     quyền cho một CLI ngoài kho, tức thay đổi ranh giới bảo mật của máy.
     Đúng loại việc đề bài xếp vào "true human boundary".

- **Đã làm thay thế (không nới quyền một chút nào):**
  1. **Chẩn đoán được, thay vì im lặng.** `stderr_tail` đã được thu thập
     sẵn cho đúng trường hợp này nhưng **chưa bao giờ được đưa ra ngoài** —
     phong bì chỉ nói "worker không trả về khối JSON nào", đúng chữ nghĩa và
     vô dụng. Nay cả hai transport Antigravity (native + launcher) trả
     `failure_reason="tool_permission_denied"` kèm nguyên văn stderr.
  2. **Nói trước cho agent.** Hợp đồng do Control Center dựng ghi rõ môi
     trường KHÔNG có shell và yêu cầu dùng công cụ đọc/ghi tệp trực tiếp,
     kèm lệnh trả `blocked` nếu bắt buộc phải chạy lệnh.
  3. Việc CHỈ ĐỌC chạy THẬT, thành công, lặp lại được — xem
     `docs/reports/CONTROL_CENTER_V01_PROOF.md`.

- **Quyết định buổi sáng:** bạn có muốn thêm allow-rule hẹp cho `agy`
  (ví dụ chỉ `read_file`) để mở đường việc CÓ GHI không? Nếu có, nên hẹp
  tới mức nào.

## B5. Cổng `diff` của Router V4 đánh HỎNG một lượt làm ĐÚNG

- **Quan sát (2026-09-08):** một lượt agent tạo đúng `docs/reports/cc-probe.md`,
  đúng phạm vi, nội dung đúng — rồi để `changes` **rỗng**. Cổng `diff` của
  `router_v3/pool/validation.py` báo *"worker không khai sửa gì nhưng đĩa đổi
  [...]"* và cả lượt bị tính HỎNG.
- **Vì sao KHÔNG tự sửa:** đây là **cổng an toàn của Router V4**, và nó là
  thứ duy nhất chặn một worker sửa tệp ngoài phạm vi mà không ai biết. Nới
  nó là một thay đổi hành vi có hệ quả bảo mật — không phải việc làm lúc
  2 giờ sáng khi bạn đang ngủ.
- **Đã làm thay thế:** sửa ở **tầng của mình**, đúng gốc rễ — hợp đồng do
  Control Center dựng nay bắt agent liệt kê đường dẫn thật vào `changes`,
  kèm ví dụ và lời cảnh báo rằng khai thiếu sẽ bị tính là hỏng.
- **Quyết định buổi sáng:** có nên để cổng `diff` hạ xuống mức *cảnh báo*
  khi lệch theo chiều "làm nhiều hơn khai" **và** mọi thay đổi đều trong
  `allowed_scope` (cổng `scope` đã xanh)? Đó là vế đối xứng của nguyên tắc
  "bằng chứng thắng lời khai" mà `Executor` đã áp theo chiều ngược lại.

---

*(Không có mục nào khác tính tới lần cập nhật cuối. Đêm nay KHÔNG deploy,
KHÔNG đổi tài nguyên AWS/GCP, KHÔNG tự động đăng nhập Google, KHÔNG dựng
Browser Operator, KHÔNG thiết kế lại Router V4.)*
