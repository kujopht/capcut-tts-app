# V1.0 — NGHIỆM THU TRƯỚC PHÁT HÀNH

Nhánh `feat/v10-autonomous-project-leader`. **CHƯA merge, CHƯA tag, CHƯA
push** — chủ sở hữu xem bằng chứng trước.

Ba khoảng trống chủ sở hữu nêu, và trạng thái từng cái:

| # | Khoảng trống | Trạng thái |
|---|---|---|
| 1 | `DONE` mà không chạy phép kiểm của dự án | ĐÃ SỬA + chứng minh trên dự án thật |
| 2 | rào năng lực chết vì lệch kiểu ở chỗ gọi | ĐÃ SIẾT + đột biến + bài kiểm đi qua đường thật |
| 3 | chưa chứng minh uỷ thác runtime thật | xem §5 — nói rõ cái gì thật, cái gì chưa |

---

## 1. HỢP ĐỒNG KIỂM ĐỊNH — `DONE` phải có bằng chứng

### Khám phá, không bịa

`kiem_du_an.py` đọc phép kiểm từ BẰNG CHỨNG CÓ THẬT trong kho, theo đúng thứ
tự chủ sở hữu nêu:

```
1. lệnh kiểm tường minh trong kế hoạch / tiêu chí nghiệm thu
2. package.json  -> scripts.{test,build,typecheck,lint}
3. cấu hình pytest (pyproject/pytest.ini/setup.cfg/tox.ini)
4. Makefile      -> target test/tests/check/lint/typecheck
```

Danh sách khoá và target là **ĐÓNG**. `scripts.deploy`, `scripts.start`,
`scripts.publish` không bao giờ được chạy như một phép kiểm — chúng có hậu
quả ra ngoài kho. Và một lưới thứ hai từ chối **cả dòng** nếu nó chạm
`deploy|publish|push|wrangler|terraform|kubectl|curl|…` — kể cả khi dòng đó
nằm dưới khoá `scripts.test`.

Không tìm được gì thì **`NEEDS_EVIDENCE`**, không phải `DONE`.

### Chỉ cho thay đổi MÃ NGUỒN/SẢN PHẨM

Bản đầu của tôi bắt MỌI việc GHI phải qua cổng này, và nó làm 6 bài kiểm
`slice` đỏ. Đó là tín hiệu đúng: một việc chỉ sửa `docs/*.md` cũng là việc
GHI, nhưng đòi nó chạy cả bộ test của dự án là đòi một bằng chứng **không
nói gì về nó** — và trên một kho không có test thì mọi việc tài liệu thành
`NEEDS_EVIDENCE`. Thu hẹp theo ĐUÔI TỆP đúng như chủ sở hữu viết ("source-
code/product changes"), và 90/90 bài `slice` xanh trở lại.

### Đo trên dự án THẬT

`RouterDogfood02` nay khai `scripts.test = node --test tests/`:

```
KHAM PHA  npm run test
          nguồn=package.json  bằng chứng: scripts.test = node --test tests/
CHAY      rc=1  -> dat=False, thieu_bang_chung=False
```

Cổng phân biệt được ba thứ trước đây gộp làm một: **đạt**, **không đạt**, và
**không có gì để chạy**.

## 2. MÁY TRẠNG THÁI — không còn đường vòng

```
IMPLEMENTED → VERIFYING → VERIFIED → DONE
                  ↓
        FAILED_VERIFICATION → điều tra/sửa/lập lại → VERIFYING
                  ↓
        NEEDS_EVIDENCE  (KHÔNG có mũi tên nào tới DONE)
```

`VERIFYING → DONE` **đã bị bỏ**. Cửa duy nhất vào `DONE` là `VERIFIED`, và
cửa duy nhất vào `VERIFIED` là `VERIFYING`.

Bài kiểm V0.9 "mọi đường tới DONE đi qua VERIFYING" được **siết chặt**, không
nới: nay là `VERIFIED` — *đã kiểm định và ĐẠT*. Một mũi tên `VERIFYING →
DONE` gộp ba tình huống rất khác nhau, và cái nguy hiểm nhất (chưa có gì để
kiểm) trông y hệt cái an toàn nhất.

Ở tầng việc, `TaskState.NEEDS_EVIDENCE` cũng không có đường tới `DONE`: muốn
ra `DONE` phải chạy lại và lần đó phải có phép kiểm THẬT chạy được, hoặc
người vận hành quyết.

## 3. RÀO NĂNG LỰC — siết theo đúng cách nó đã chết

Khuyết tật gốc: `hd if isinstance(hd, dict) else {}` — chỗ gọi DUY NHẤT
truyền một `TaskContract` (đối tượng), nên vế `else` luôn đúng và hàm trả
rỗng **mọi lần**, từ V0.7 tới 2026-09-13.

Bốn thay đổi:

* **Một cửa duy nhất** `nang_luc_tu_hop_dong()`, nhận đúng hai hình dạng
  (`dict` | đối tượng có `.to_dict()` trả dict) và **ném `NangLucLoi`** cho
  mọi thứ khác. Hình dạng chính tắc được ghi thành hằng số trong mã, không
  còn là một giả định lỏng.
* **Không nuốt.** `NangLucLoi` kế thừa `TypeError`, nên khối
  `except (ImportError, AttributeError, TypeError)` cũ sẽ bắt được nó — đúng
  cách rào chết lần đầu. Nay bắt riêng và **ném lại TRƯỚC** khối rộng, và
  khối rộng thôi bắt `TypeError`.
* **Chỗ gọi fail closed.** Không chấm được năng lực thì việc bị `BLOCKED`
  kèm sự kiện `CAPABILITY_RESOLUTION_FAILED` — không bao giờ giao đi với một
  rào đã tắt.
* **Bài kiểm đi qua ĐƯỜNG THẬT.** Bộ kiểm cũ gọi hàm bằng `dict` — đúng thứ
  nó mong — nên nó xanh suốt trong khi đường thật đã chết. Bảy bài mới dựng
  `TaskContract` y như `_giao_khong_luoi` dựng.

Các trường hợp chủ sở hữu yêu cầu, và bài kiểm tương ứng:

| Yêu cầu | Bài |
|---|---|
| năng lực hợp lệ được chấp nhận | `test_13` |
| năng lực bị từ chối thì runtime bị cấm | `test_14` |
| việc hình dạng BẢO MẬT không lọt vào Codex | `test_15` |
| kiểu lạ FAIL CLOSED | `test_16`, `test_17` |
| `NangLucLoi` không bị nuốt bởi `except` rộng | `test_18` (cấu trúc) |
| chỗ gọi thật CHẶN việc lại | `test_19` (cấu trúc) |

**Đột biến:** tắt rào (trả về `isinstance` cũ) làm **9/19** bài đỏ.

## 4. CÔ LẬP BỘ KIỂM TODO

**Tầng chịu trách nhiệm: harness của bộ kiểm, không phải ứng dụng.**

`script.js` đọc `localStorage` MỘT LẦN ở `DOMContentLoaded` rồi giữ mảng
`todos` trong closure. `test.js` gọi `localStorage.clear()` bên trong
`setTimeout(500)` — tức là SAU khi ứng dụng đã đọc xong. Xoá kho lưu trữ
không reset biến closure, nên mọi phép đếm lệch đúng bằng số việc còn sót.

```
kho còn dữ liệu cũ -> 2 đạt / 3 HỎNG
kho sạch           -> 5 đạt / 0 hỏng
```

Sửa: `localStorage.clear()` chuyển lên **thì PARSE** (cả `script.js` lẫn
`test.js` đều chạy trước khi `DOMContentLoaded` phát), cộng một `finally`
dọn dẹp sau khi chạy. Kỷ luật fixture thông thường: dựng trạng thái rồi mới
khởi động thứ cần kiểm.

**KHÔNG tắt tính năng lưu trữ của sản phẩm** — bài kiểm §3 dưới đây cố ý tạo
3 việc thật qua giao diện và xác nhận chúng NẰM trong `localStorage` trước
khi chạy bộ kiểm.

Chứng minh trong bốn điều kiện chủ sở hữu nêu — **6/6 đạt**:

```
1. kho sạch, chạy riêng                        5 đạt / 0 hỏng
2. chạy lại NGAY sau lần trước                 5 đạt / 0 hỏng
3. kho BẨN có chủ ý (3 việc thật từ giao diện) 5 đạt / 0 hỏng
4. dọn dẹp sau khi chạy                        localStorage sạch
5. ba lần liên tiếp                            [(5,0), (5,0), (5,0)]
```

## 7. CỔNG REVIEW CHÉO HỌ MODEL

Chứng minh trên HỢP ĐỒNG ĐỊNH TUYẾN, tất định, không gọi model nào —
**10/10 đạt** (`test_cong_review_v10.py`):

* Gemini + `implementation|testing|refactor|migration` → **BẮT BUỘC** phản
  biện, và họ `gemini` bị cấm làm người phản biện;
* ưu tiên `claude-sonnet-4-6` khi fabric phơi ra nó; không có thì rơi xuống
  một họ độc lập khác (`codex-default`);
* **chỉ có Gemini** trong fabric → **báo suy giảm**, KHÔNG lặng lẽ để cùng
  họ tự chấm;
* quét nhiều cấu hình fabric: không lần nào trả về reviewer cùng họ;
* việc **dữ liệu** (cạo/theo dõi/metadata/phân loại/nghiên cứu) có kiểm
  schema tất định → **KHÔNG** bị đòi review;
* nhưng một việc `implementation` không được miễn chỉ vì có schema.

**Khả dụng THẬT của Sonnet được báo riêng** (§5) — hợp đồng định tuyến và
tình trạng nhà cung cấp là hai chuyện, và trộn chúng là cách một bản báo cáo
nói rằng có Sonnet trong khi không có.

## 8. `codex-chatgpt-web` — KHÔNG CÀI, adapter ở lại UNVERIFIED

Dò trực tiếp trên máy này: không có lệnh nào trên `PATH`, không có thư mục
cài ở `%LOCALAPPDATA%\Programs`, `%APPDATA%`, `%USERPROFILE%`. Nên **không
probe được**, và không có gì được bật.

Bốn thứ còn thiếu, ghi ra để lần sau không phải dò lại — xem
`V10_RUNTIME_CAPABILITY_AUDIT.md` §4c. Ngắn gọn: ứng dụng chưa cài; phiên
ChatGPT đã đăng nhập (Router **không** chạm, không sao chép, không lưu); một
quyết định tường minh của chủ sở hữu về việc chấp nhận transport KHÔNG chính
thức; và một `runtime_id`/`quota_pool` riêng để không trộn vào bể `codex`
đang đo được.

## 9. MỘT SAI SÓT CỦA TÔI TRONG CHÍNH BÀI NGHIỆM THU NÀY

Điều kiện hỏng có kiểm soát ban đầu dùng `scripts.test = node --test tests/`.
Trên Node 24 + Windows, `node --test <thư mục>` **không** duyệt thư mục — nó
cố nạp `tests` như một module và chết bằng `MODULE_NOT_FOUND`. Nên `npm test`
trả `rc=1` vì **bộ kiểm không nạp được**, chứ không phải vì thiếu tính năng.

Hậu quả trong lần chạy đầu: worker THÊM ĐÚNG nút `#clear-completed` vào cả
`index.html` lẫn `script.js` — và vẫn bị đánh hỏng hai lượt liền. Chạy lại
đúng tệp đó bằng lệnh đúng: **4/4 đạt**. Worker làm đúng từ đầu; lệnh kiểm
của tôi mới là thứ hỏng.

**Cổng vẫn hành xử ĐÚNG** — nó thấy `rc=1` và từ chối `DONE`, đúng như thiết
kế. Nhưng đây là một giới hạn thật, đáng nêu thay vì giấu:

> Cổng chỉ tốt bằng lệnh mà dự án tự khai. Nó phân biệt được "xanh" với
> "đỏ"; nó KHÔNG phân biệt được "tính năng còn thiếu" với "script test của
> bạn hỏng".

Vì thế cổng ghi **nguyên văn đuôi đầu ra** của lệnh vào sự kiện
`PROJECT_VERIFIED` (`duoi`, 800 ký tự cuối) — đúng chỗ tôi đã đọc ra
`MODULE_NOT_FOUND`. Không có nó thì sai sót này còn lâu mới lộ.
