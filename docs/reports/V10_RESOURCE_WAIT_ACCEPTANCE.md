# V1.0 — CHỜ TÀI NGUYÊN (`WAITING_RESOURCE` / CHO_TAI_NGUYEN)

Nhánh `feat/v10-autonomous-project-leader`. **CHƯA merge / tag / push.**

Hạng mục mở số 1 của `V10_INCIDENT_LOOP_ACCEPTANCE.md` §10c, nay đã đóng.

---

## 1. VẤN ĐỀ, đo được trên đường thật

Đêm 2026-09-13, một tài khoản Antigravity thật trả về hết hạn mức. Vòng sự cố
phân loại **đúng** và chọn **đúng**:

```
loai=QUOTA_EXHAUSTED   chien_luoc=CHO_QUOTA
"hết hạn mức nhà cung cấp — CHỜ hoặc dùng bể khác.
 KHÔNG mua thêm credit, không bật overage"
```

Nhưng quyết định ấy **không tới được trạng thái việc**. `routerdogfood02.
t2ec8-1` nằm lại ở `FAILED`, `blocked_reason` rỗng. Người vận hành mở bảng
điều khiển đọc **"hỏng"**, trong khi sự thật là **"đang chờ hạn mức"**.

Cùng hình dạng với §7a của báo cáo kia: bộ điều phối quyết định đúng, rồi
quyết định ấy chết trên đường tới nơi cần đến.

## 2. VÌ SAO PHẢI LÀ MỘT TRẠNG THÁI RIÊNG

Ba trạng thái sẵn có đều nói dối, và mỗi cái sai một kiểu khác nhau:

| Dùng | Nó nói gì | Vì sao SAI |
|---|---|---|
| `FAILED` | "việc này hỏng" | không ai làm sai; và nó đốt lượt thử lại vào một việc không hỏng |
| `BLOCKED` | "cần NGƯỜI" | hạn mức tự hồi theo thời gian — biến một lần chờ hồi được thành một lần dừng vĩnh viễn, và gọi người dậy lúc 3 giờ sáng cho việc Router tự xử được |
| `WAITING` | "chờ việc phụ thuộc" | không mang theo bể nào, mốc reset nào, đường thay thế nào |
| `WAITING_AUTHORITY` | "chờ chủ sở hữu duyệt" | chưa có quyết định nào cần duyệt cả |

`WAITING_RESOURCE` nói đúng một câu: **ý định thực thi và mục tiêu GỐC vẫn
thuộc về việc này; Router đang chờ một tài nguyên, không chờ một con người.**

Bảng chuyển: `RUNNING`/`FAILED`/`NEEDS_EVIDENCE` → `WAITING_RESOURCE` →
`QUEUED`/`RUNNING`/`BLOCKED`/`PAUSED`/`FAILED`. **Không có mũi tên tới
`DONE`/`REVIEW`** — chờ hạn mức không chứng minh được gì về công việc, và
một trạng thái tài nguyên không được nới cổng nghiệm thu.

## 3. CHÍNH SÁCH — ba kết cục, ranh giới là ranh giới THẨM QUYỀN

`scripts/control_center/v10/tai_nguyen.py`, một hàm **THUẦN** (không chạm sổ,
không chạm mạng) — nên ba kịch bản dựng được bằng fixture tất định và
**không phải đốt hạn mức thật để dựng lại cảnh cạn**.

```
        tài nguyên không dùng được
                    │
    ┌───────────────┼───────────────────┐
    │               │                   │
 còn đường      hết đường           hết đường
  hợp lệ        CÓ mốc reset        KHÔNG mốc
    │               │                   │
 ĐỔI CHỖ        CHỜ RESET           LEO THANG
 không hỏi ai   giữ việc, hẹn giờ   BLOCKED + bằng chứng
```

Bốn luật không được phá, mỗi luật có bài kiểm riêng:

1. **Không bao giờ mua thêm.** Không credit, không overage, không nâng gói.
   Hết tiền là ranh giới THẨM QUYỀN và nó thuộc về chủ sở hữu.
2. **Không hạ chuẩn để đi tiếp.** Bể cùng họ với người viết bị **chặn cứng**
   cho vai đòi phản biện độc lập — một lần đổi chỗ vì hết quota KHÔNG được
   phép lặng lẽ xoá mất tính độc lập đã cất công dựng.
3. **`UNKNOWN` vẫn là `UNKNOWN`.** Không đo được mốc reset thì KHÔNG bịa một
   cái. Một mốc bịa biến *"chờ có cơ sở"* thành *"thử lại mù có lịch"*.
4. **Không tự thêm credential.** Cũng là ranh giới thẩm quyền.

Và chờ có lịch vẫn phải **có đáy**: trần `TRAN_CHO_RESET = 3` lần, cộng với
trần `TRAN_CHO_GIAY = 6 giờ` — một mốc reset 48 giờ là thật, nhưng một hệ
chạy qua đêm cần chủ sở hữu BIẾT điều đó thay vì im lặng ngủ hai ngày.

## 4. BỀN — cùng hồ sơ, không dựng kho thứ hai

Bản ghi chờ tài nguyên nằm **chung** `SuCoBen` (`INCIDENT_STATE`), không tách
kho riêng: chờ tài nguyên là một nhánh của cùng một sự cố, và nhờ nằm chung
nó sống sót qua khởi động lại theo đúng cơ chế đã có. Tách ra là dựng nơi thứ
hai cho cùng một loại sự thật — chế độ hỏng đã phải sửa nhiều lần trong bản
này.

Giữ đủ thứ chủ sở hữu liệt kê: `execution_id`, mục tiêu gốc, bể/provider/
account, câu **nguyên văn** nhà cung cấp trả về, `reset_luc` (nếu đo được),
`thu_lai_luc`, các ứng viên đã xét kèm lý do loại, `da_dung`, `dem_cho`.

`None` đọc ra `None`. `float(d.get("reset_luc") or 0.0)` là cách một mốc
KHÔNG ĐO ĐƯỢC biến thành mốc năm 1970 — và một mốc quá khứ nghĩa là "tới giờ
rồi" → đánh thức ngay → đúng cái *thử lại mù có lịch* mà luật 3 cấm.

## 5. VÒNG QUÉT — nửa còn lại của `CHO_RESET`

`tick()` quét việc `WAITING_RESOURCE` đã tới mốc và trả chúng về `QUEUED`.
Thiếu vòng quét này thì "hẹn giờ" chỉ là một dòng chữ trong sổ và việc nằm đó
vĩnh viễn: **vẫn là treo, chỉ khác tên.**

Đánh thức đưa việc về **HÀNG ĐỢI**, không ép một chỗ chạy. Đây không phải chi
tiết: tự gán placement là đi vòng qua `premium.GacAstra` (trần song song, cấm
đệ quy, ECO) và `chinh_sach` theo dự án (`qd_0001`: *"GPT-6 Astra chỉ dùng
cho task đặc biệt khó"*) — một lần hết hạn mức sẽ lặng lẽ mở đường tới model
đắt nhất. Có bài kiểm neo đúng điều đó.

## 6. BẰNG CHỨNG THẬT — chính bản ghi đã hỏng, chạy lại qua đường mới

Không đốt thêm hạn mức. Bản ghi đêm 13/09 còn nguyên trong sổ chính tắc, và
câu nhà cung cấp trả về được **đọc lại từ sổ**, không gõ tay lại.

```
TRƯỚC: routerdogfood02.t2ec8-1 = FAILED   attempts=3
       sc_567e7bc1b2f8  loai=QUOTA_EXHAUSTED  chien_luoc=CHO_QUOTA  DANG_MO

SAU  : routerdogfood02.t2ec8-1 = QUEUED   (kết cục: DOI_CHO)

[INCIDENT_WAIT_QUOTA]  DOI_CHO: còn đường tài nguyên hợp lệ: AG01
[TEAM_EVENT] REPAIR    DOI_CHO[AG01]
[INCIDENT_STATE]       CHO_TAI_NGUYEN -> DOI_CHO
[TASK_STATE]           FAILED -> WAITING_RESOURCE (chờ tài nguyên: đổi chỗ)
[TASK_STATE]           WAITING_RESOURCE -> QUEUED (tài nguyên đã sẵn sàng)
[TAI_NGUYEN_SAN_SANG]  còn đường tài nguyên hợp lệ: AG01
```

Cùng một việc, cùng một câu hạn mức, cùng một quyển sổ: đường **cũ** để nó
nằm lại `FAILED`, đường **mới** định tuyến sang AG01 và chạy tiếp. Hai dãy sự
kiện nằm cạnh nhau trong lịch sử của chính việc ấy. **7/7 khẳng định đạt.**

Hồ sơ ghi lại `AG02` là bể đang chờ, câu nguyên văn làm bằng chứng, mục tiêu
gốc còn nguyên, và `ung_vien_da_xet = [["AG02", "bể vừa cạn"]]`.

## 7. KHỞI ĐỘNG LẠI GIỮA LÚC ĐANG CHỜ TÀI NGUYÊN — **10/10**

Nửa sau là một **tiến trình MỚI** (`subprocess`), không phải một
`ControlStore` thứ hai trong cùng tiến trình — cái đó không chứng minh được
gì về tính bền thật.

| Khẳng định | Kết quả |
|---|---|
| vẫn ở `WAITING_RESOURCE` sau khởi động lại | OK |
| CÙNG `execution_id` | `ex_kdl_tn` |
| CÙNG hồ sơ chờ tài nguyên | `sc_kdl_tn` |
| mục tiêu GỐC còn nguyên | OK |
| bể đang chờ còn nguyên | `AG02` |
| **ngân sách chờ KHÔNG bị nạp lại** | `dem_cho = 2` |
| **ngân sách sửa chữa KHÔNG bị nạp lại** | `{'sua_tai_cho': 1}` |
| KHÔNG sinh việc trùng | 19 → 19 |
| mốc kế tiếp vẫn mạch lạc | còn 5.0 giờ |
| CHƯA tới mốc thì `tick()` KHÔNG đánh thức | vẫn `WAITING_RESOURCE` |

## 8. BA KHUYẾT TẬT CỦA CHÍNH BẢN NÀY, bị chặn trước khi kịp chạy

* **`ctx.fabric.runtimes()`** — `runtimes` là một **DICT**, không phải hàm.
  Gọi như hàm ném `TypeError`, `except` quanh đó nuốt mất, và bể ra **RỖNG**
  — tức "hết đường" cho MỌI lần, tức leo thang gọi người mỗi lần hết quota.
  Đúng hình dạng đã sửa nhiều lần: một `except` phòng thủ biến một cơ chế
  thành lệnh rỗng.
* **họ model suy từ `provider`** — Antigravity phục vụ cả gemini lẫn claude
  lẫn gpt, nên lấy provider làm họ là áp một cấu trúc tưởng tượng lên bể,
  đúng thứ `han_muc` cấm ở luật số hai. Nay suy từ `supported_models`.
* **một bài kiểm của tôi không đủ** — bài neo cấu trúc cho vòng quét vẫn
  XANH khi đột biến thay lời gọi bằng `pass  # _quet_cho_tai_nguyen`, vì
  chuỗi ấy còn nằm trong chính dòng chú thích. Đã thay bằng bài HÀNH VI gọi
  `tick()` thật.

## 9. SỐ

```
bộ kiểm chờ tài nguyên   30 bài  (3 kịch bản A/B/C · 8 ranh giới ·
                                  3 máy trạng thái · 3 bền · 13 dây nối thật)
đột biến                 10/10 đỏ  (cây gốc xanh trước và sau mỗi lần)
dogfood hạn mức thật      7/7
dogfood khởi động lại    10/10
chính sách Astra         `test_reasoning_v08` xanh, không đụng tới
targeted (14 bộ)         590 / 590
HỒI QUY ĐẦY ĐỦ           2728 chạy · 2728 đạt · 1 bỏ qua · **0 HỎNG**
```

**0 lượt model bị đốt để dựng lại cảnh cạn hạn mức.**
**0 thay đổi production, 0 khởi động lại production, 0 thao tác phá huỷ.**

`web/`, `server/`, `beam_apps/`, `desktop_app/`, `capcut_tts_api/` — không
tệp nào bị chạm trong toàn bộ đợt này.
