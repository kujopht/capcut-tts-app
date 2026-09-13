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

## 5–6. UỶ THÁC THẬT + SỬA CHỮA TỰ CHỦ — chứng minh trên một lần chạy

Điều kiện hỏng CÓ KIỂM SOÁT: `tests/app.test.js` đòi nút `#clear-completed`
chưa tồn tại, nên `npm test` đỏ với một khẳng định THẬT
(`expected: /id=["']clear-completed["']/`).

Một câu của chủ sở hữu, rồi không can thiệp gì nữa:

```
luot Leader   -> uy thac 1 viec: t5e7c-1  type=testing  scope=['.']
                 (pham vi ghi cap tu cum "Lam luon" trong chinh cau nguoi dung)

luot 1  worker status=ok        -> npm run test rc=1  -> DONE BI TU CHOI, thu lai
luot 2  worker sua              -> npm run test rc=0  -> DONE
        changes=['index.html', 'script.js']
        2 su kien PROJECT_VERIFIED
```

**Đây là bằng chứng trung tâm của cả bản này:** worker nói `ok`, Router chạy
bộ kiểm THẬT của dự án, bộ kiểm đỏ, và `DONE` **không** được cấp. Vòng lặp
tự thử lại, worker sửa, bộ kiểm xanh, và chỉ khi đó mới `DONE`. Chủ sở hữu
không phải xem một dòng log nào.

Runtime THẬT đã tham gia: worker chạy trên `AG02` (Antigravity), viết tệp
thật trong worktree cô lập, và cổng kiểm định chạy `npm` thật.

**Vai Leader dùng đường sẵn có, KHÔNG phải Opus 5 runtime.** `claude` CLI có
`--session-id`/`-r` (đo được, §1 audit) nhưng chưa lượt Leader nào chạy qua
nó dưới quyền Router. Đánh dấu **UNVERIFIED**, không giả vờ.

### Giới hạn còn lại của vòng này — ĐÃ ĐƯỢC GỠ Ở VÒNG SAU

Ở thời điểm viết mục này, vòng thử lại vẫn là **`_thu_lai_neu_dang` của
V0.9**, KHÔNG phải `su_co.VongSuCo`. Chủ sở hữu đọc đúng chỗ đó và trả lại
với một câu:

> *"The v1.0 incident loop is tested but not wired."*

Đã sửa. `VongSuCo` nay là **chủ sở hữu duy nhất của chính sách phục hồi** và
`_thu_lai_neu_dang` tụt xuống thành nguyên liệu. Bằng chứng, gồm cả **hai
khuyết tật của chính dây nối** mà lượt chạy thật đầu tiên phơi ra, ở
`V10_INCIDENT_LOOP_ACCEPTANCE.md`.

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

## 10. CỔNG PHÁT HÀNH — ĐO, không khẳng định suông

| Cổng | Kết quả |
|---|---|
| không có đường worker-success → DONE | ✅ `VERIFYING → DONE` đã bỏ; chỉ `VERIFIED` vào được |
| kiểm định dự án THỰC SỰ chạy khi có | ✅ 2 sự kiện `PROJECT_VERIFIED`, rc=1 rồi rc=0 |
| thiếu bằng chứng KHÔNG ra được DONE | ✅ `NEEDS_EVIDENCE` không có mũi tên tới DONE (cả hai tầng) |
| bộ kiểm Todo cô lập/lặp lại được | ✅ 6/6 trong bốn điều kiện, gồm kho bẩn thật |
| rào năng lực có hồi quy bảo vệ | ✅ 7 bài đi qua đường thật + đột biến 9/19 đỏ |
| hỏng/sửa tự chủ | ✅ đỏ → thử lại → xanh → DONE, không người can thiệp |
| ít nhất một đường uỷ thác runtime THẬT | ✅ AG02 viết tệp thật, `npm` thật |
| cổng review Gemini | ⚠️→✅ 10/10 trên hợp đồng, **nhưng khi ấy là MÃ CHẾT** — đã cắm vào `nen_goi_reviewer` 2026-09-13, xem `V10_INCIDENT_LOOP_ACCEPTANCE.md` §9 |
| vòng sự cố V1.0 chạy trên đường THẬT | ✅ ngắt mạch nổ đúng lẫy: 1 chữ ký × 3 → `HOI_DONG` (§6) |
| khởi động lại GIỮA LÚC phục hồi | ✅ **8/8** — cùng `incident_id`, ngân sách KHÔNG nạp lại, 18→18 việc (§10b) |
| khởi động lại / phục hồi vẫn xanh | ✅ nằm trong hồi quy đầy đủ |
| thay đổi / khởi động lại production | ✅ **0 / 0** |
| thao tác phá huỷ | ✅ **0** — không force push, không xoá nhánh |
| việc GATED hỏi thừa cho việc repo-local | ✅ **0** |
| fanfic bị đụng | ✅ **76 → 76**, 0 việc mới |

```
hồi quy đầy đủ   2659 đạt · 4 bỏ qua · 0 hỏng (5 khối, CẢ 5 chạy lại trên
                 cây cuối)
targeted         147 bài (kiểm định 20 · review 10 · năng lực 19 ·
                 nền móng 41 · mốc git 11 · phạm vi ghi 46)
```

**Một bài kiểm phụ thuộc tải, không phải hồi quy:**
`test_toa_v061.test_neu_nguoi_dung_neu_model_thi_ghim_provider` đỏ MỘT lần
trong khối 4 (đếm được 2 việc `RUNNING` thay vì 4) rồi xanh ở lần chạy lại,
và xanh 22/22 hai lần khi chạy riêng. Nó khẳng định số việc chạy ĐỒNG THỜI —
một đại lượng phụ thuộc tải máy.

> **ĐÃ ĐIỀU TRA VÀ SỬA (2026-09-13).** Câu *"cùng họ với một cuộc đua tầng
> khoá ở V0.9.1"* ở bản trước của mục này **SAI**. Đo trực tiếp: cửa sổ 4 con
> cùng ở `RUNNING` chỉ dài **~40ms** khi executor giả chạy xong ngay; trễ
> 0.05s còn 3/4, trễ 0.20s còn **2/4** — đúng con số đã quan sát. `claim_task`
> đặt `RUNNING` đồng bộ trong `tick()`, nên không có chiều "chưa kịp".
> Mọi bài anh em khẳng định cùng một thứ đều đã có độ trễ executor; chỉ bài
> này quên. **Khuyết tật của bài kiểm, không phải của sản phẩm, không phải
> tầng khoá.** Chi tiết: `V10_INCIDENT_LOOP_ACCEPTANCE.md` §8.
