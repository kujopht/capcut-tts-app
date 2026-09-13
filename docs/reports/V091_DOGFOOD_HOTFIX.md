# V0.9.1 — HOTFIX DOGFOOD: bảo trì kho + tra cứu thành phần

Nhánh `feat/v091-dogfood-hotfix`, dựng từ `main` đã phát hành
(`router-control-center-v0.9.0`). **Chưa merge/tag/push.**

Hai ma sát ĐO ĐƯỢC khi bắt đầu dùng thật Router cho Fanfic.

---

## A. Việc bảo trì kho hợp lệ bị `BLOCKED`

**Triệu chứng.** Việc *"dọn worktree cũ và nhả xung đột tài nguyên"* —
thuần repo-local, hoàn toàn hợp lệ — đi đúng đường tới Router V4 rồi worker
`BLOCKED`: nó phải tự gọi `git worktree` / ghi `.git`, mà quyền headless
chối (ĐÚNG thiết kế).

**Không sửa bằng cách nới quyền.** Đây là khuôn đã trả giá ba lần trước —
`nguon_git`, `web_reader`, `probe_van_hanh`: Router làm thao tác an toàn HỘ
rồi đưa BẰNG CHỨNG; quyền agent KHÔNG đổi. Khác biệt duy nhất: thao tác này
có ĐỘT BIẾN, nên mọi rào fail-closed và có dấu vết kiểm toán.

`bao_tri_kho.MoiGioiBaoTri` — API **có kiểu**, không nhận chuỗi lệnh, không
`shell=True`:

| Thao tác | Mức |
|---|---|
| `liet_ke` | chỉ đọc |
| `tia_sieu_du_lieu` | chỉ siêu dữ liệu (`git worktree prune`) |
| `nha_khoa_mo_coi` | nhả khoá mà CHỦ đã kết thúc |
| `go_cay_cu` | gỡ MỘT cây, sau sáu rào |
| `don_dep` | trọn gói, mỗi cây vẫn qua đủ rào |

**Sáu rào trước khi gỡ**, mỗi rào nói lý do CHÍNH XÁC:

1. không bao giờ là **cây làm việc chính**;
2. phải trong `.router/worktrees/` của ĐÚNG kho này (`resolve()` trước khi
   so — junction không lách được);
3. phải là cây Router **biết** (hoặc duyệt tay tường minh);
4. không **phiên sống** nào sở hữu;
5. không **lần thực thi sống** nào trỏ tới — *không tra được sổ thì TỪ CHỐI*,
   không đoán là an toàn;
6. không **thay đổi chưa commit**, trừ khi cho phép tường minh.

Khoá: chỉ nhả khi chủ đã kết thúc, và **không bao giờ** nhả `PRODUCTION` —
luật `LockKind.tu_thu_hoi_duoc` không đổi.

**Không xoá bằng chứng:** hàng worktree ở lại (đánh dấu `STALE`), sự kiện
`REPO_MAINTENANCE` ghi CẢ lần cho phép LẪN lần từ chối.

16 bài kiểm tất định, phần lớn là những lần **phải từ chối**.

---

## B. Leader không nhớ nổi thành phần dự án

**Triệu chứng.** Người dùng hỏi tự nhiên:

> ê cái tool cạo audio t sao r

Leader tra Ký ức/Viên nang, trượt, rồi **hỏi ngược người dùng tên
script/thư mục**. Với một dự án đã nhận nuôi, bắt người dùng nhớ đường dẫn
nội bộ là câu trả lời sai.

**Đo trước khi sửa.** Viên nang Fanfic thật có 19 mục, và mục `muc_tieu`
ghi *"(theo CLAUDE.md) Fanfic Audio Studio — hai sản phẩm dùng chung một
pipeline TTS"* — đúng cái hẹp mà người dùng chỉ ra. Không có mục nào là
**chỉ mục thành phần**.

Nhưng thứ được hỏi CÓ THẬT trong kho: `server/scraper/` (23 tệp, có
`chinese_media_sources.py` dùng `yt_dlp`) và `scripts/chinese_media_pipeline.py`.
**Nên đây không phải thiếu kiến thức — mà thiếu PHÉP TRA CỨU.**

`tim_thanh_phan.BoTimThanhPhan` — thang leo có đáy, dừng sớm khi đủ chắc,
ghi lại đã tra những bậc nào:

```
ký ức → viên nang → KHO (tên tệp, rồi nội dung) → git → tài liệu → lịch sử Router
```

Mở rộng từ khoá TẤT ĐỊNH (không LLM): *cạo/cào* → `scrape|crawl|harvest`,
*audio* → `tts|yt_dlp|media`, *web* → `next|cloudflare|wrangler`.

**Một lần sai đã sửa, đáng ghi.** Bản đầu xếp `docs` (51 điểm) TRÊN
`server/scraper` (45) — vì tên tệp báo cáo khớp gần như mọi từ khoá. Câu trả
lời "thành phần của anh là `docs`" thì vô dụng. Nay `docs/`, `deploy/` và
mọi thư mục `tests/` là **bằng chứng**, không bao giờ là ứng viên.

**Vá ký ức:** khi tra ra CHẮC CHẮN, Router ghi một bản ghi `semantic` —
*"bí danh «…» → thành phần `X`, bằng chứng: …"* — idempotent, có nguồn gốc,
để lần sau khỏi tra lại. Chỉ ghi khi CHẮC: đóng đinh một bí danh còn mơ hồ
sẽ khiến lần sau trả lời sai một cách tự tin.

**Vùng phủ nói thật.** Mọi kết quả kèm dòng `VÙNG KHÔNG PHỦ`: lịch sử hội
thoại ChatGPT Project **không** trong tầm với của Router. Không lấp bằng
phỏng đoán.

---

## Dogfood THẬT (dự án Fanfic thật, model thật)

| Câu hỏi | Kết quả |
|---|---|
| *"ê cái tool cạo audio t sao r"* | nhận ra `server/scraper`, dẫn đường dẫn bằng chứng, báo trạng thái nhánh/working tree, **không hỏi ngược đường dẫn** |
| *"còn cái web fanfic giờ sao rồi?"* | hiểu là `web/` (Next.js + Open-Next) của **cả dự án**, không chỉ TTS; kèm trạng thái probe sống |

* việc worker sinh thêm: **0** — câu hỏi được trả lời bằng tra cứu, không
  bằng một lượt agent;
* `execution`: **(không tạo)** ở cả hai câu;
* thay đổi production: **0**;
* sự kiện `RECALL_AUDIT`: 2.

**Khoảng trống còn lại (khai báo, không giấu):** phần lịch sử Fanfic chỉ tồn
tại trong hội thoại ChatGPT Project nằm ngoài tầm với của Router. Câu trả
lời nào chạm vùng đó đều nói rõ là khoảng trống.

---

## Vấn đề ĐÃ BIẾT (không chặn phát hành v0.9.1)

**Một cuộc đua ở tầng KHOÁ, phụ thuộc tải.** Trong một lần chạy hồi quy đầy
đủ, `test_con_hong_khong_ro_khoa_va_anh_em_van_song_song` hỏng một lần: sau
khi MỘT việc con của một lượt toả hỏng, một khoá `FILESYSTEM ... mode=read`
còn sót lại thay vì được nhả.

Bằng chứng hai chiều, ghi cả hai:

* **hỏng**: 1 lần, trong hồi quy đầy đủ 2462 bài;
* **không tái hiện**: 23/23 khi chạy riêng bộ đó, 3×4 khi lặp riêng lớp đó,
  và **2462/2462 ở lần chạy đầy đủ THỨ HAI** (cùng số bài, cùng nhánh).

Kết luận: cuộc đua có THẬT nhưng phụ thuộc tải, và nó nằm ở tầng khoá —
không phải do các thay đổi của v0.9.1 (nhánh này đã xanh 2453 bài trước khi
có ba bản sửa, và xanh 2462 sau). **Cố ý KHÔNG mở rộng phạm vi để sửa trong
lần phát hành này.**

Đáng biết trước khi chạy dogfood SONG SONG nặng: nếu thấy một khoá `read`
mồ côi, `MoiGioiBaoTri.nha_khoa_mo_coi()` (v0.9.1) nhả được nó một cách an
toàn — nó chỉ nhả khoá mà CHỦ đã kết thúc, và không bao giờ nhả khoá
`PRODUCTION`.

### ĐÃ SỬA — 2026-09-13 (bổ sung)

Cuộc đua trên **đã đóng**, sau khi nó quay lại chặn CI của một nhánh khác
(`fix/ci-permission-tests-env-guard`) với đúng chữ ký đã mô tả ở đây: hỏng
1 lần trong hồi quy đầy đủ, không tái hiện khi chạy riêng.

**Khuyết tật thật.** Không phải cuộc đua ở phép nhả khoá — `LockManager.tra()`
vẫn đúng. Khuyết tật nằm ở chỗ **không ai thu hồi khoá mồ côi TRONG một phiên
đang chạy**:

* `_nha_khoa_mo_coi()` xử đúng ca này, và đã an toàn từ v0.9.1;
* nhưng nó CHỈ được gọi từ `recover()` — tức lúc **khởi động lại**;
* nên trong một phiên đang chạy, một việc kết thúc ở trạng thái cuối mà chưa
  kịp nhả khoá sẽ giam mọi việc sau nó **hết `LOCK_TTL` = 1 giờ**, còn bộ lập
  lịch chỉ lặng lẽ đẩy việc kia sang `WAITING` mỗi lượt.

Vì phụ thuộc tải: trên máy lập trình, `finally` của luồng cũ hầu như luôn kịp
nhả trước khi lượt mới xin, nên cửa sổ này gần như không bao giờ mở. Dưới tải
CI thì có.

**Bản sửa (nhỏ nhất có thể).** Ở `_giao_khong_luoi`, khi một lượt xin khoá bị
từ chối *và* chủ khoá đang chặn có dấu hiệu đã chết, gọi đúng
`_nha_khoa_mo_coi()` có sẵn rồi **xin lại một lần**. Không lặp: lượt thứ hai
vẫn bị từ chối nghĩa là chủ khoá còn sống thật, và `WAITING` là câu trả lời
đúng.

Bản sửa KHÔNG nới một bất biến nào — mọi lưới an toàn vẫn nằm nguyên trong
`_nha_khoa_mo_coi()`: miễn trừ `PRODUCTION`, guard `_dang_chay`, và lease còn
sống. `_chu_khoa_co_the_da_chet()` chỉ là một cổng RẺ để khỏi quét toàn bộ
khoá ở mọi lượt bị từ chối; đoán sai ở đó chỉ tốn thêm một lần quét.

**Hai bài kiểm khoá bất biến lại**, cả hai TẤT ĐỊNH (không ngủ, không đua,
không phụ thuộc tải) ở `test_control_center_slice.TestVerticalSlice`:

| Bài | Khẳng định |
|---|---|
| `test_khoa_mo_coi_duoc_nha_TRONG_PHIEN_chu_khong_doi_recover` | một lượt `tick()` đủ để việc sau chạy — không phải đợi `recover()` |
| `test_khoa_PRODUCTION_mo_coi_VAN_giam_viec_o_duong_lap_lich` | khoá `PRODUCTION` mồ côi VẪN giam việc; `WAITING` ở đây là đúng |

Bài thứ nhất **hỏng trên mã trước khi sửa** và đạt sau — đó là điều khiến nó
là một bài kiểm hồi quy chứ không phải một lời khẳng định suông.
