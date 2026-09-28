# Social & Play V1 — Gói C: schema mini-game (Caro/Gomoku, Memory Runes)

Trạng thái: **THIẾT KẾ, ADDITIVE** — schema đã có trong `scripts/setup_appwrite.py`
(dry-run xác nhận additive), nhưng **production CHƯA được áp/migrate**. Kho đang
chạy là `MockGamesStore`/`MockGamificationStore` trong bộ nhớ. Bản Appwrite
(`AppwriteGamesStore`, `server/appwrite_games_store.py`) tồn tại và có test hợp
đồng với client giả lập, nhưng **CHƯA được kiểm trên một dự án Appwrite thật**.

Tính năng đứng sau cờ `games_v1_enabled` (`FAS_GAMES_V1`, xem `server/config.py`):
mặc định BẬT khi `DATA_BACKEND != appwrite` (mock — an toàn), mặc định TẮT khi
`DATA_BACKEND == appwrite`, trừ khi đặt tường minh `FAS_GAMES_V1=1` **sau khi**
đã áp schema và đối soát.

## 1. Sáu collection mới

Tất cả định nghĩa nằm trong `scripts/setup_appwrite.py::SCHEMA`, khối "Social &
Play V1 Gói C" (ngay sau các collection gamification V4/V6, trước Image Studio).

| Collection | `documentId` | Vai trò |
|---|---|---|
| `game_rooms` | `room_id` (`"rm_" + hex(8)`) | Một phòng Caro/Gomoku — bàn cờ, ghế, trạng thái, settlement |
| `game_room_versions` | `f"{room_id}-v{version}"` | Marker CAS cho `save_room` (xem §3) |
| `game_runs` | `run_id` (`"mr_" + hex(8)`) | Một lượt Memory Runes — layout server-only, tiến độ |
| `game_run_versions` | `f"{run_id}-v{version}"` | Marker CAS cho `save_run` — bảng RIÊNG với `game_room_versions` |
| `game_results` | `"gr_" + sha256(result_id)[:24]` | Kết quả/thưởng ĐÃ SETTLE, một hàng cho mỗi (trận/lượt, người chơi) |
| `xp_progress_cas` | `"xc_" + sha256(f"{user_id}\|{prior_xp}\|{prior $updatedAt}")[:24]` | Marker CAS cho `award_xp_atomic` (dùng CHUNG cho mọi nguồn XP atomic, không chỉ mini-game) |

Thuộc tính/chỉ mục đầy đủ: xem trực tiếp `scripts/setup_appwrite.py` (nguồn sự
thật duy nhất — tài liệu này KHÔNG lặp lại từng trường để tránh hai bản lệch
nhau khi sửa một bên mà quên bên kia).

Các trường JSON (`moves`, `flips`, `xp_entries`, `reasons`) được lưu dưới dạng
chuỗi `string` (Appwrite không có kiểu mảng lồng tùy ý cho document thường),
`json.dumps`/`json.loads` ở tầng adapter (`_room_to_row`/`_room_from_row` v.v.
trong `server/appwrite_games_store.py`).

## 2. Quyền

- **Mọi ghi đều qua backend bằng API key** — không client SDK nào ghi trực
  tiếp, giống mọi kho Appwrite khác trong kho này.
- `game_rooms`/`game_results` **chỉ đọc được qua API** (route `/api/games/*`),
  không cấp quyền đọc SDK trực tiếp cho client — board/kết quả là dữ liệu
  nhiều người cùng xem nhưng qua tầng nghiệp vụ (ẩn thông tin nội bộ, tính
  `you`/`opponent_connected`...).
- `game_runs` **KHÔNG BAO GIỜ** cấp quyền đọc cho client (kể cả chủ lượt chơi):
  trường `layout` là lá bài thật — lộ nó là lộ toàn bộ bố cục Memory Runes.
  Route `GET /api/games/memory/runs/{run_id}` trả về **view đã lọc**
  (`memory_run_view`), không phải document thô.
- `game_room_versions`/`game_run_versions`/`xp_progress_cas` không cần quyền
  đọc nào — chỉ tồn tại để Appwrite cưỡng chế tính duy nhất `rowId`, không ai
  đọc nội dung của chúng.

## 3. CAS qua transaction — không phải đọc-rồi-ghi

Kỹ thuật **giống hệt** `AppwriteMetadataStore.claim_job` (`server/appwrite_store.py`,
đã đo thật trên Appwrite Cloud 1.9.6 — xem docstring ở đó):

- `save_room(room, expected_version)`: MỘT transaction gồm `create` hàng
  `game_room_versions` (`rowId=f"{room_id}-v{expected_version+1}"`) + `update`
  hàng `game_rooms`. Rowid đã tồn tại (ai đó vừa ghi trước) → Appwrite từ chối
  → `GamesConflict`. Người gọi (`games_service._mutate_room`) đọc lại, áp lại
  logic, thử tối đa 5 lần, rồi mới trả 409 cho client.
- `save_run(run, expected_version)`: cùng kỹ thuật, marker RIÊNG
  (`game_run_versions`) — tách bảng để không dựa vào quy ước tiền tố id
  (`rm_`/`mr_`) không bao giờ đổi.
- `award_xp_atomic(entry)` (xem §4): transaction BA thao tác, không phải hai.

**Vì sao transaction một mình KHÔNG đủ cho `award_xp_atomic`** (phát hiện ở
vòng review đầu của gói này — xem §6): transaction của Appwrite chỉ phát hiện
xung đột giữa hai transaction ĐANG MỞ CÙNG LÚC. Hai request TUẦN TỰ (không
chồng lấn) — request A đọc `xp=100`, commit xong ghi `xp=102`, RỒI request B
mới bắt đầu đọc và (do đọc từ bản sao/replica chậm, hoặc do đọc trước khi A
commit) vẫn thấy `xp=100` — sẽ KHÔNG bao giờ va chạm trong MỘT transaction, và
cả hai có thể commit THÀNH CÔNG, tạo "lost update" (một lần cộng XP biến mất).
`xp_progress_cas` biến "hai người cùng đọc thấy `xp=100`" thành "hai người
cùng xin tạo MỘT `rowId`" (`xc_sha256(user_id|prior_xp)`) — Appwrite cưỡng chế
`rowId` duy nhất nên chỉ MỘT commit thành công, đúng cơ chế `game_room_versions`.

## 4. `award_xp_atomic` — transaction ba thao tác

```
create  xp_ledger            rowId = entry_id
update  user_progress        rowId = user_id   (hoặc create nếu chưa có hàng)
create  xp_progress_cas      rowId = xc_sha256(user_id|prior_xp|prior_$updatedAt)
```

Khoá gắn với **trạng thái** hàng tiến độ (`$updatedAt` do Appwrite tự đặt ở mỗi
lần ghi), không chỉ con số XP. Bản đầu dùng `(user_id, prior_xp)` và bị bắt ở
vòng review cuối: nếu XP từng bị **giảm** (điều chỉnh bù) rồi quay lại đúng giá
trị cũ, marker của lần cộng trước đã tồn tại → mọi lần cộng sau từ giá trị đó
thua commit mãi mãi → người dùng không bao giờ được cộng XP nữa. Hồi quy:
`test_games_appwrite_contract.test_xp_chinh_ve_gia_tri_cu_khong_lam_ket_marker`;
tính chất chống ghi đè vẫn giữ:
`test_doc_trang_thai_cu_van_bi_marker_chan_khong_mat_lan_cong`.

Thua commit (transaction lỗi, HOẶC transaction trả về bình thường nhưng
`status != "committed"` — ví dụ bị từ chối vì một `rowId` đã tồn tại): đọc lại
`xp_ledger` bằng GET trực tiếp — **đã tồn tại** → coi là "đã cộng rồi", trả
`None`; **chưa tồn tại** → coi là xung đột tạm thời, đọc lại tiến độ MỚI và
thử lại (tối đa 5 lần, jitter nhỏ); hết lượt vẫn không commit được →
`AppwriteUnavailableError`.

## 5. Đường XP cũ — ĐÃ chuyển sang ghi nguyên tử (sau cờ `FAS_XP_ATOMIC`)

Mọi writer của hàng `user_progress` giờ đi qua **một** hàm: `update_progress_atomic(user, mutator, ledger_entry)`:
`award_xp` (xuất bản, nghe, đóng góp…), `claim_quest_reward`, `equip_title`, `open_reward_pack` và quyết toán
game (`award_xp_atomic`). Bản mock chạy dưới một khoá. Bản Appwrite gom sổ cái + tiến độ + hàng khoá
`xp_progress_cas` (theo trạng thái hàng) vào một giao dịch, thua thì đọc lại và thử lại.

- Cờ `FAS_XP_ATOMIC`: mặc định **bật** khi mock, **tắt** khi `DATA_BACKEND=appwrite`, nên production **giữ
  nguyên** đường cũ tới khi giao dịch được kiểm trên Appwrite **thử nghiệm**
  (`docs/migrations/SOCIAL_PLAY_V1_TEST_APPWRITE.md`). `Settings.validate()` **từ chối khởi động** nếu
  `FAS_GAMES_V1=1` trên Appwrite mà `FAS_XP_ATOMIC` tắt.
- `claim_quest_reward` đổi thứ tự thành cộng XP → cấp vật phẩm → rồi mới đánh dấu đã nhận. Cả hai bước đầu
  idempotent theo khoá tất định, nên sập giữa chừng không còn làm mất thưởng.
- Không đổi ngưỡng cấp, không đổi giá trị XP, không reset hay xoá dữ liệu nào.
- Test: `server/tests/test_xp_concurrency.py`. Nội dung: đồng thời game + nhiệm vụ + nghe + đổi danh xưng;
  từng writer đọc trạng thái cũ trên Appwrite giả lập; sập giữa lúc nhận thưởng; XP chỉnh về giá trị cũ; đường cũ
  khi tắt cờ; luật cấu hình.

## 6. Lỗi đã sửa ở vòng review (bài học, không phải chỉ lịch sử)

Ba lỗi sau bị bắt bởi review/test TRƯỚC khi merge — ghi lại vì chúng dễ tái
phạm nếu ai đó sửa lại `games_service.py` sau này mà không đọc mục này:

1. **Quyết định thưởng phải ĐÓNG BĂNG ở lần lưu `GameResult` ĐẦU TIÊN.**
   Bản đầu tính quyết định (thắng/thua/điểm/XP) rồi gọi `award_xp_atomic`
   TRƯỚC khi gọi `create_result`, và lấy `xp_awarded` từ giá trị `award_xp_atomic`
   trả về. Hỏng ở hai chỗ: (a) crash SAU khi cộng XP nhưng TRƯỚC khi
   `create_result` → lần thử lại tính LẠI quyết định với trạng thái trần
   (cap) MỚI, các entry đã cộng giờ trả `None` (trùng) → hàng lưu lại nói
   `xp_awarded=0` dù XP THẬT đã được cộng; (b) crash SAU `create_result`
   TRƯỚC khi cộng hết XP → lần thử lại thấy hàng đã tồn tại nên BỎ QUA
   người đó hoàn toàn → XP mất vĩnh viễn. **Sửa:** với mỗi người, dựng quyết
   định → `create_result` (hàng PLANNED, đã có sẵn `xp_entries`/`xp_awarded`
   dự định) TRƯỚC; thua `create_result` (đã có hàng) → đọc hàng ĐÃ LƯU qua
   `get_result`, dùng ĐÚNG hàng đó; rồi mới cộng XP cho TỪNG entry trong
   hàng ĐÃ LƯU (không bao giờ tính lại quyết định). Test:
   `test_games_settlement.py::CrashRecoveryTest` (crash trước mọi lần cộng,
   crash giữa hai lần cộng của cùng một người, hai luồng settle đồng thời).

2. **`leave()` giữa ván KHÔNG được vacate ghế trước khi settlement chạy.**
   Bản đầu: `leave` khi đang chơi vừa đánh dấu ván kết thúc (resign) VỪA xoá
   ghế người rời NGAY trong một mutation — `_settle_room` sau đó chỉ thấy
   MỘT người ngồi (ghế kia đã trống), tưởng thiếu người nên không tạo hàng
   kết quả nào: một ván ĐÃ HỢP LỆ (≥10 nước) bị rời phòng làm mất thưởng
   CẢ HAI bên. **Sửa:** `leave` khi đang chơi chỉ chuyển trạng thái
   `finished`/`resign`, GIỮ NGUYÊN cả hai ghế; settle chạy (thấy đủ hai
   người); rồi một CAS thứ hai mới xoá ghế người rời. Test:
   `test_games_settlement.py::LeaveDuringValidatedMatchTest`.

3. **Trận bị chặn vì quá số ván/ngày với CÙNG đối thủ phải là `validated=False`,
   không chỉ `xp=0`.** Bản đầu chỉ chặn XP (`xp_events=[]`, `points=0`) nhưng
   giữ `validated=True` — nghĩa là trận đó VẪN được đếm vào `matches`/`wins`
   trên bảng xếp hạng (vì bảng xếp hạng chỉ lọc `validated`), cho phép "cày"
   thứ hạng bằng cách đấu vô hạn lần với cùng một đối thủ (chỉ mất XP, không
   mất điểm mùa giải/thứ hạng). **Sửa:** `validated = not pair_capped`. Test:
   `test_games_settlement.py::PairCapValidationTest` (+ kiểm tra bảng xếp
   hạng ở `test_games_leaderboard.py`).

4. **(Vòng hai) `pair_count_today` phải LOẠI TRỪ chính trận đang settle.**
   Nếu một lần settle trước đó crash GIỮA hai lần `create_result` của hai
   người (người thứ nhất đã có hàng, người thứ hai thì chưa), lần thử lại
   không được tự đếm hàng của CHÍNH trận này (đã lưu cho người thứ nhất) vào
   "số ván với đối thủ này hôm nay" khi tính quyết định cho người thứ hai —
   nếu không, trận đang settle tự làm đầy trần của chính nó. **Sửa:** lọc
   `r.source_id != source_id` trong `list_results_for_pair_since`. Test:
   `test_games_settlement.py::PairCountExcludesOwnMatchTest`.

5. **(Đường Appwrite) `award_xp_atomic` bỏ sót kiểm tra "đã cộng chưa" khi
   commit thất bại KHÔNG NÉM NGOẠI LỆ.** Bản đầu chỉ kiểm tra "hàng
   `xp_ledger` đã tồn tại chưa" bên trong nhánh `except Exception` — một lần
   commit trả về BÌNH THƯỜNG với `status != "committed"` (ví dụ bị từ chối vì
   một `rowId` đã tồn tại, KHÔNG ném lỗi vận chuyển nào) bỏ qua hoàn toàn
   phép kiểm đó và cứ thử lại vô hạn thay vì trả `None` khi đã cộng rồi.
   **Sửa:** gộp cả hai nhánh (ném ngoại lệ VÀ không-commit-không-ngoại-lệ)
   qua CÙNG MỘT phép kiểm trước khi quyết định thử lại hay trả `None`. Test:
   `test_games_appwrite_contract.py::AwardXpAtomicContractTest` (ba kịch bản:
   payload transaction có đủ ba thao tác; commit thất bại vì hàng đã tồn tại
   → `None`; commit thất bại vì lỗi vận chuyển (không liên quan hàng đã tồn
   tại) → thử lại với dữ liệu MỚI → thành công, không cộng hai lần).

## 7. Dry-run / triển khai

```bash
# Xem TOÀN BỘ SCHEMA sẽ chạy (không gọi Appwrite) — an toàn, chỉ đọc mã.
python scripts/setup_appwrite.py --dry-run

# Chỉ xem MỘT collection (ví dụ khi review riêng phần mini-game).
python scripts/setup_appwrite.py --only=game_rooms --dry-run
```

**KHÔNG chạy script này (bỏ `--dry-run`) trong PR này** — schema thật CHỈ áp
khi có quyết định tường minh bật games trên production, theo thứ tự:

1. Đối soát schema (`--dry-run`) với người vận hành Appwrite.
2. Áp schema thật (bỏ `--dry-run`) — additive, không chạm collection nào khác.
3. Xác minh `award_xp_atomic`/CAS transaction hoạt động đúng trên Appwrite
   PRODUCTION THẬT (mục "CHƯA KIỂM THẬT" ở §4/§6 mục 5 — hiện chỉ có test hợp
   đồng với client giả lập, KHÔNG chứng minh được hành vi commit thật của
   Appwrite Cloud khi có xung đột thật).
4. Chuyển đường XP cũ (`award_xp`/`claim_quest_reward`, §5) sang
   `award_xp_atomic` để loại bỏ race còn lại.
5. Chỉ khi đó mới đặt `FAS_GAMES_V1=1`.

## 8. Rollback

Xoá cả sáu collection — KHÔNG ảnh hưởng dữ liệu đang dùng (kho đang chạy là
`MockGamesStore`/`MockGamificationStore` trong bộ nhớ; production chưa migrate
sang các bảng này). Không có bước "forward-only" nào cần lo — additive thuần
tuý, không sửa/xoá cột của bảng có sẵn.

## 9. Ngoài phạm vi

- **Điều chỉnh bù (compensating adjustment)** cho một trận bị settle sai
  (ví dụ do một lỗi khác chưa biết) — `GET /api/admin/games/rooms/{code}`
  chỉ cho XEM đầy đủ (phòng + kết quả + entry XP thật), không có route SỬA.
  Một route quản trị "hoàn/điều chỉnh XP mini-game" là việc theo dõi riêng.
- **Xác thực Appwrite thật** cho `AppwriteGamesStore`/`award_xp_atomic` xp_progress_cas
  (xem §4/§6 mục 5) — mới có test hợp đồng với client giả lập.

## 10. Giới hạn đã biết (review chéo Antigravity Claude Opus, vòng cuối)

| Phát hiện | Đánh giá | Xử lý |
|---|---|---|
| "Trần 3 ván/cặp/ngày chỉ đếm một chiều — đấu lại (đổi ghế) là né được" | **Không đúng**: mỗi ván ghi một hàng kết quả cho CẢ HAI người, nên đếm từ phía ai cầm X cũng đủ số ván | Khoá bằng bài test `PairCapDoiGheTest` (5 ván, đổi người cầm X mỗi ván → ván 4–5 không tính) |
| Hai ván KHÁC NHAU giữa cùng một cặp kết thúc đúng cùng lúc có thể cùng đọc "còn 1 suất" → vượt trần (tương tự: trần XP game/ngày, trần lượt Memory/ngày) | **Đúng, và nặng hơn "vượt 1"**: đo với 8 ván kết thúc cùng lúc, mỗi lần đọc chậm 20 ms (như gọi mạng tới Appwrite), không khoá → 8/3 ván cặp, 40/30 XP ngày, 8/5 lượt Memory | **Đã sửa trong một tiến trình**: khoá quyết toán theo người chơi (`games_service._khoa_quyet_toan`) → 3/3, 30/30, 5/5 (`test_xp_concurrency.TranDuoiTaiDongThoiTest`, tự hỏng nếu gỡ khoá). Nhiều instance API → mỗi instance một bộ khoá → **vẫn là trần MỀM**, không gọi là hard cap. Production hiện chạy một tiến trình uvicorn |
| Memory: người chơi (hoặc bot) nhớ hoàn hảo đạt điểm gần tối đa; phản hồi lật cho biết ký hiệu của thẻ vừa lật | Bản chất của trò chơi trí nhớ — máy chủ chỉ lộ thẻ đã lật, không lộ bố cục; kiểm độ hợp lý thời gian còn thấp | Không hứa chống bot tuyệt đối; XP bị trần (2 XP × 5 lượt/ngày). Bảng điểm Memory có thể bị bot đạt điểm cao — ghi trong báo cáo |
| Dùng tài khoản phụ đánh ≥ 10 nước rồi để nó "mất kết nối" để nhận thắng | Đúng nhưng có trần: 3 ván/cặp/ngày + 30 XP/ngày; tốn một tài khoản + ~10 nước + 45 s mỗi ván | Chấp nhận ở V1; theo dõi cặp có tỉ lệ thắng-do-timeout cao nếu cần |
| `touch_seat` (hiện diện) ghi ngoài khối CAS; một lần ghi phòng có thể đè `last_seen` bằng giá trị cũ vài mili giây | Không khai thác được: muốn gây "nhận thắng" giả cần trễ > 45 s giữa đọc và ghi | Chấp nhận, ghi rõ |
| Trùng thưởng khi thử lại; mạo danh; thử lại vô hạn; mất thưởng khi sập | Reviewer xác nhận an toàn | — |
