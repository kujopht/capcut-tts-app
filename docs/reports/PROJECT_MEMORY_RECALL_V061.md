# Project Memory không phải lớp liên tục có thẩm quyền — chẩn đoán đo được + sửa (V0.6.1, 2026-09-10)

Phạm vi: chỉ Project Memory (đề bạt, nhập lịch sử, truy hồi Leader, nhất quán
kho). Không đụng browser runtime, vector ngữ nghĩa, Artifact Vault, provider
routing, UI. Đọc từ trạng thái THẬT của ứng dụng source-mode đang chạy, không
tin bài kiểm/báo cáo cũ.

## 1. Đường dữ liệu THẬT (đo, không đoán)

Ứng dụng source-mode chạy qua `router-cc-desktop.cmd` (`pythonw -m
scripts.control_center.desktop`, không `--root`). Gốc mặc định = `parents[2]`
của `desktop.py` = **thư mục checkout đang chạy**. Máy này chạy từ worktree
`C:\FanficWorkers\router-control-center`, nên:

| Thứ | Giá trị THẬT |
|---|---|
| project_id của Fanfic | `fanfic` (không phải "Fanfic"/"Fanfic Audio Studio") |
| namespace ký ức | `fanfic-dcf29d1141` (= `khong_gian_ten("fanfic")`, chỉ theo project_id) |
| repo_path của dự án | `C:\Users\nguye\Documents\CapCut-TTS-App` (checkout chính) |
| sổ ký ức (live) | `C:\FanficWorkers\router-control-center\.router\memory\fanfic-dcf29d1141\memory.db` |
| sổ Router (live) | `C:\FanficWorkers\router-control-center\.router\control_center\control.db` |
| tiến trình đang giữ | `pythonw` pid 7440, cổng 57905 (desktop.lock) |

Ghi chat, đề bạt, backfill, UI, truy hồi Leader — TẤT CẢ đi qua
`DichVuKyUc.provider("fanfic")`, một `LocalMemoryProvider` cache theo project_id,
trỏ đúng sổ trên. Chúng nhất quán TRONG một gốc. Bài kiểm
`test_ky_uc_first_v061.TestNhatQuanKho` khoá điều đó.

## 2. Nguyên nhân gốc của "Decisions = 0 sau khi người dùng tuyên bố"

Đề bạt tất định (`memory/de_bat.py` → `service.de_bat_tu_chat`, gọi từ
`ghi_nhan._chat` ở MỌI tin nhắn người dùng) **chạy đúng trong mã V0.6.1 hiện
tại** — đo trực tiếp:

```
them_chat(user, "hãy ghi nhớ đây là một quyết định của project: GPT-6 Astra…")
 -> qd_0001, tin_cay=user_explicit, nguon_loai=chat_user, nguon_id=<sk id>,
    bằng chứng -> đúng dòng L0, liet_ke("decision") = 1 NGAY LẬP TỨC.
```

Vậy vì sao UI thật báo 0? **Hai nguyên nhân chồng nhau, cả hai là tách kho:**

1. **Tuyên bố được gõ vào một bản EXE CŨ.** Câu Astra tường minh nằm trong sổ
   của `dist-v06` (bản đóng gói V0.6, lược đồ CHƯA có cột `nguon_loai`, CHƯA có
   `de_bat`). V0.6 cố ý không suy quyết định từ chat — đó chính là khuyết tật
   V0.6 mà V0.6.1 sinh ra để sửa. Bản đó không bao giờ đề bạt được.
2. **Mỗi gốc `.router` là một sổ riêng.** Bản đóng gói neo gốc cạnh EXE
   (`dist-v06/…/.router`); source-mode neo gốc ở checkout. Cùng project_id →
   cùng namespace slug, nhưng KHÁC tệp vật lý. Sổ source-mode (đang xem) chưa
   bao giờ nhận câu Astra — nó chỉ có CÂU HỎI "policy GPT-6 Astra … là gì?"
   (#53) và câu trả lời "không có thông tin" (#55). Không có bug đề bạt trong
   mã hiện tại; có một sổ khác.

Đo bằng chứng: quét mọi `memory.db` dưới repo — chỉ sổ `dist-v06` chứa cụm
"đây là một quyết định"; sổ source-mode không có tin nhắn người dùng nào chứa
nó. Không bịa: KHÔNG chép câu Astra từ đề bài vào sổ nào.

## 3. 13 (nay 17) "structured memories" là gì

Toàn bộ là **episodic tự sinh từ vòng đời việc/Leader** (do người ghi tất định
chưng cất từ L0): "tạo việc …", "việc … hoàn thành", "Leader uỷ thác", "kết quả
việc …", cộng một `incident` `leader_unavailable` (một lỗi runtime headless).
Không có bản nào là decision/constraint/requirement/procedure vì **không có
tuyên bố người dùng nào được gõ vào sổ này** và backfill CHƯA chạy vào sổ này.
Authority: `do_duoc` (vòng đời) / `ghi_nhan` (kết quả chat). Đúng thiết kế —
không phải đếm sai UI.

## 4. Vì sao "8.089 backfill" mà UI chỉ 56/13

**Sổ source-mode CHƯA BAO GIỜ được backfill.** `GET
/api/memory/backfill/sources?project=fanfic` (gọi vào app THẬT đang chạy):
`da_nhap=0`, `lan_cuoi=null` cho cả 4 nguồn. Dry-run khám phá **7.557 mục** (so
chính 92, git 515, tài liệu 1257, phiên Claude 5693) — khớp con số "~8.089" báo
cáo cũ. Vậy con số cũ là KHÁM PHÁ (dry-run) hoặc ghi vào một sổ nghiệm thu tạm,
KHÔNG vào sổ live. Đây là biến thể khác của cùng gốc: tách kho/gốc.

## 5. Backfill THẬT vào sổ live (đã chạy)

Chạy qua API của chính app đang chạy (đường thật, không tranh chấp ghi):

| Hạng mục | Trước | Sau |
|---|---|---|
| su_kien (L0) | 75 | 7.647 |
| ky_uc (L1) | 17 | 91 |
| incident | 1 | **55** |
| constraint | 8 | 8 |
| procedural | 0 | 9 |
| decision | 0 | 0 (đúng — backfill KHÔNG bao giờ `user_explicit`) |
| authority backfill | 0 | 70 |

Idempotent (chạy lại `trung` tăng, `da_nhap` 0), resumable, khử trùng theo dấu
vân tay, lọc bí mật ở cổng vào. Quét 55 incident: **0 rò bí mật**. Chỉ nguồn
được phép (sổ Router, git kho dự án, tài liệu/HANDOFF, phiên Claude khớp
worktree). Không dự án lạ.

## 6. Sự cố SSH — CHỨNG MINH từ nguồn được phép, không từ đề bài

Git kho Fanfic (`C:\Users\nguye\Documents\CapCut-TTS-App`):
`scripts/ops/prod_cutover.py:96` tham chiếu `~/.ssh/fanficappwrrite.pem` (SAI —
thừa một `r`), commit `b8b2592` (2026-09-04, kujopht). Khoá thật là
`fanficappwrite.pem`. Backfill đưa các incident quanh sự mismatch này vào sổ
(vd `ku_e89c32e257818256`, `ku_4020d7924251a1ac`), tìm lại được qua
`/api/memory/search`. Các sự cố SSH khác nhau giữ THÀNH BẢN GHI RIÊNG, không
gộp. Không tiêm gì từ đề bài — bằng chứng là git + phiên Claude của dự án.

## 7. Leader LÀM ĐẦU BẰNG KÝ ỨC (sửa "SSH → dispatch AG02 200s")

Trước: "cái vụ SSH key … trước đây bị gì?" → Leader tạo việc analysis →
dispatch AG02 → 200s khảo sát kho. Đó KHÔNG phải memory recall — và nó xảy ra
vì (a) sổ chưa có SSH (nay đã backfill), (b) Leader không có luật ưu tiên ký ức
cho câu hỏi lịch sử.

Sửa (tất định, không LLM):

* `leader.la_cau_hoi_lich_su(text)` — bộ nhận diện regex câu QUÁ KHỨ ("trước
  đây", "vì sao", "cái vụ … bị gì", "what happened") + KIẾN THỨC DỰ ÁN ("policy
  / quyết định / rule … của project là gì"). Nghiêng nhẹ về nhận.
* `leader.LUAT_LICH_SU` — luật per-lượt (song song `LUAT_SONG` cho câu hỏi
  hiện tại) nhét NGAY TRƯỚC khối ký ức khi bộ nhận diện bật: TRẢ TỪ ký ức +
  bằng chứng L0 trước, trích MÃ; KHÔNG uỷ thác worker chỉ vì từ khoá vắng
  trong hội thoại; thiếu trong ký ức thì NÓI RÕ và HỎI, đừng tự dựng việc.
  Vẫn WORK khi người dùng nói rõ muốn điều tra sâu ("đọc repo này…").
* `service.khoi_cho_leader(..., kem_su_kien=True)` — với câu hỏi lịch sử, đính
  thêm dòng L0 khớp câu hỏi (FTS) làm BẰNG CHỨNG để Leader trả lời trực tiếp.
  FTS đã có, không thêm vector ngữ nghĩa.
* `engine._giao_leader` — tính `la_lich_su` từ câu, truyền vào `_khoi_ky_uc`
  (bật `kem_su_kien`) và `dung_nhac_nho` (bật `LUAT_LICH_SU`).
* `HUONG_DAN` luật 7 — memory-first cho câu hỏi lịch sử/kiến thức dự án.

Bậc thẩm quyền GIỮ NGUYÊN: SỐNG > SỔ/KHO > KÝ ỨC > SUY LUẬN. Câu hỏi HIỆN TẠI
("production farmer còn chạy không?") vẫn đi `LUAT_SONG`/đo sống, KHÔNG rơi vào
nhánh lịch sử (bộ nhận diện tách bạch — bài kiểm khoá).

## 8. Bộ kiểm

`scripts/tests/test_ky_uc_first_v061.py` (11): bộ nhận diện lịch sử/kiến thức
vs việc/hiện tại/chào; `LUAT_LICH_SU` chỉ khi lịch sử + có khối; bằng chứng L0
đính đúng và cite `sk#`; đề bạt qua chat → UI thấy qd ngay; câu hỏi không thành
quyết định; **nhất quán kho** (ghi/backfill/UI/Leader cùng một namespace + một
tệp vật lý; project_id khác → sổ khác, không rò chéo). Các bộ cũ
(`test_project_memory*`, `test_memory_backfill_v061`) giữ nguyên xanh.

## 9. Nhất quán kho (bước 11) — và điểm mong manh còn lại

Bốn đường trỏ MỘT sổ TRONG một gốc — đã khoá bằng test. Điểm mong manh THẬT:
gốc `.router` đổi theo cách khởi chạy (đóng gói cạnh EXE ≠ source-mode ở
checkout ≠ nếu chạy từ checkout chính). Đây là bản chất của `--root`, KHÔNG sửa
bằng cách đổi bố cục lưu trữ (sẽ là tính năng mới, rủi ro). Cách dùng đúng:
LUÔN mở app từ CÙNG một nơi — `router-cc-desktop.cmd` ở worktree này — để dùng
đúng sổ live `fanfic-dcf29d1141`. Đã ghi vào HANDOFF.

## 10. Trả lời gọn (các trường đề bài)

| Trường | Giá trị |
|---|---|
| Nguyên nhân gốc | Đề bạt V0.6.1 chạy đúng; UI báo 0 vì tuyên bố gõ vào bản CŨ (dist-v06, không de_bat) + tách kho theo gốc; sổ live chưa backfill |
| project_id Fanfic thật | `fanfic` |
| Sổ ký ức live | `…\router-control-center\.router\memory\fanfic-dcf29d1141\memory.db` |
| Sổ Router live | `…\router-control-center\.router\control_center\control.db` |
| Backfill cũ đi đâu | dry-run/sổ tạm — sổ live `da_nhap=0`, `lan_cuoi=null` |
| Có mismatch namespace/gốc? | Namespace nhất quán theo project_id; MISMATCH là ở GỐC (đóng gói vs source) |
| 13 structured là gì | episodic vòng đời việc/Leader + 1 incident runtime; do_duoc/ghi_nhan |
| Đề bạt quyết định tường minh | **PASS** (qd_0001, user_explicit, provenance đầy đủ — đo qua đường app) |
| Backfill lịch sử | **PASS** (7.557 vào sổ live, 55 incident, 0 rò bí mật) |
| Sự cố SSH chứng minh | **PASS** từ git `b8b2592` + phiên Claude — không từ đề bài |
| Leader memory-first | code PASS (bộ nhận diện + LUAT_LICH_SU + bằng chứng L0); nghiệm thu Leader thật ở §11 |
| Bậc SỐNG > KÝ ỨC | GIỮ (câu hỏi hiện tại vẫn đo sống; bộ nhận diện tách bạch) |
| Số production/kho thật bị chạm | 0 (đọc git chỉ đọc; backfill ghi vào sổ ký ức cục bộ) |

## 11. Nghiệm thu source-mode THẬT (đã chạy)

`scripts/control_center_v061_ky_uc_web_acceptance.py`, app mở bằng đường
source-mode (`pythonw -m scripts.control_center.desktop`, không `--root` — y
như `router-cc-desktop.cmd`), **gốc dữ liệu THẬT** của người dùng
(`C:\FanficWorkers\router-control-center`), dự án `fanfic`.

### Pha A — tuyên bố quyết định (app pid 27700, cổng 64852): **7/7 ĐẠT**

| Bước | Kết quả |
|---|---|
| Tuyên bố tường minh → Decision đề bạt NGAY (không job nền) | ĐẠT — decisions **0 → 1** trong 9.1s |
| Đủ trường | ĐẠT — `qd_0001`, `tin_cay=user_explicit`, nguồn `chat_user#7654`, 1 mắt xích bằng chứng |
| Provenance tra được | ĐẠT — ID + `ts=1789048282` + nguồn + bằng chứng L0 |
| Tuyên bố KHÔNG sinh việc worker | ĐẠT — việc 7 → 7 |
| UI đếm | ĐẠT — `decision=1`, `incident=55` |

### Pha B — phiên Leader MỚI sau đóng/mở (pid 3552, cổng 59425): **9/9 ĐẠT**

Đóng sạch bằng WM_CLOSE, mở lại, rồi **đẩy tuyên bố ra khỏi cửa sổ hội thoại**
của Leader bằng 8 câu đệm — đo được: tuyên bố cách cuối **17 tin nhắn**, ngoài
trần `SO_LUOT_NGU_CANH = 14`. Nên câu trả lời đúng **không thể** đến từ
transcript được phục hồi; nó đến từ ký ức.

| Bước | Kết quả |
|---|---|
| Tuyên bố đã ra khỏi cửa sổ hội thoại | ĐẠT — cách cuối 17 tin (cần ≥ 14) |
| Recall CHÉO PHIÊN bằng diễn giải khác, 0 việc mới | ĐẠT — *"Theo quyết định `qd_0001` (bản ghi `ku_dd605f187deff41e`, ghi nhận 2 phút trước từ `sk#7654`), chính sách hiện tại của dự án là: GPT-6 Astra chỉ được dùng cho các task đặc biệt khó hoặc cần reasoning cao, không dùng mặc định…"* · việc 7 → 7 |
| Trả lời nêu MÃ bản ghi | ĐẠT — `qd_0001` + `ku_dd605f…` + `sk#7654` |
| **Sự cố SSH lịch sử → recall trực tiếp, 0 worker dispatch** | ĐẠT — *"Theo ký ức sự cố của dự án (bản ghi `ku_903075d957b3c8ae`, 18 ngày trước)…"* · **việc mới = 0** (trước: AG02 chạy 200s) |
| Câu hỏi HIỆN TẠI vẫn đo SỐNG | ĐẠT — 1 sự kiện `LIVE_PROBE`; *"fanfic-farmer vẫn ĐANG CHẠY (ACTIVE)… live probe vừa kiểm tra qua SSH, 10 giây trước"* → **live > ký ức giữ nguyên** |

Ghi chú trung thực: bản ghi SSH mà Leader nêu (`ku_903075d957b3c8ae`) là một
sự cố khoá/xoay khoá production 18 ngày trước, KHÔNG phải bản ghi typo
`fanficappwrrite.pem`. Cả hai cùng tồn tại như **bản ghi riêng** (đúng yêu cầu
"không gộp mọi vấn đề SSH vào một sự kiện"); bản typo là
`ku_e89c32e257818256` / `ku_4020d7924251a1ac`, tìm lại được qua
`/api/memory/search`. Điều được chứng minh ở đây là: câu hỏi lịch sử được trả
TỪ KÝ ỨC, có mã, **không dispatch worker**.

### Số lần sửa production trong toàn bộ nghiệm thu: **0**

Kho Fanfic (`C:\Users\nguye\Documents\CapCut-TTS-App`) không có tệp tracked
nào đổi. Quét toàn bộ state dự án: **0** chuỗi giống credential.
