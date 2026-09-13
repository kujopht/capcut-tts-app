# V1.0 — VÒNG SỰ CỐ ĐƯỢC CẮM VÀO ĐƯỜNG THẬT

Nhánh `feat/v10-autonomous-project-leader`. **CHƯA merge / tag / push.**

Chủ sở hữu xem bản nền móng và chỉ đúng chỗ còn thiếu:

> *"The v1.0 incident loop is tested but not wired."*

Đúng vậy. Lần sửa Todo thành công trước đó chạy bằng `_thu_lai_neu_dang` của
V0.9. `VongSuCo` có 41 bài kiểm và **không một dặm đường thật nào**.

---

## TÓM TẮT

Vòng sự cố nay CHẠY trên đường thật, và bốn khuyết tật của chính dây nối ấy
đã lộ ra — **cả bốn đều do một lượt chạy THẬT phát hiện, không phải bài
kiểm.** Đó là kết quả đáng kể nhất của đêm nay, và nó nói đúng điều chủ sở
hữu đã nói.

| # | Khuyết tật | Hậu quả nếu không sửa | Mục |
|---|---|---|---|
| 1 | `hien_tai()` đọc bản ghi CŨ NHẤT | ngân sách không bao giờ cạn → **ngắt mạch không bao giờ nổ** | §4a |
| 2 | bằng chứng cổng kiểm định không vào sự cố | `loai=UNKNOWN` cho lần hỏng đã biết rõ | §4b |
| 3 | bộ phân loại khớp LỜI VĂN, lời văn đã đổi | vẫn `UNKNOWN`; phân loại không dẫn được tới hành động | §5a |
| 4 | vân tay băm cả văn xuôi của model | 1 lần hỏng → 3 chữ ký → nhánh "lặp chữ ký" là **mã chết** | §5b |
| 5 | leo thang không tới trạng thái việc | sổ ghi đã gọi người, bảng vẫn đọc "hỏng" | §7a |
| 6 | leo thang làm việc CHA treo vĩnh viễn | treo tệ ngang lặp vô hạn với hệ chạy qua đêm | §7b |
| 7 | `FAILED` không còn là trạng thái nghỉ | anh em chốt kết quả khi hệ vẫn đang sửa (4 xanh/11 đỏ) | §7c |

Bằng chứng chính, từ sổ chứ không phải từ lời:

* **ngắt mạch nổ đúng lẫy** — 1 chữ ký đếm 3 → `HOI_DONG`, không phải cạn
  ngân sách (§6);
* **khởi động lại giữa lúc phục hồi 8/8** — cùng `incident_id`, ngân sách
  KHÔNG nạp lại, không sinh việc trùng (§10b);
* **cùng một vân tay qua hai tiến trình** — `VERIFICATION_FAILURE:0c2d236598`
  ở cả §6 lẫn §10b;
* **ma trận đột biến 10/10** (§10), trong đó **hai** bài ban đầu xanh khi
  tháo dây — bộ kiểm chưa đủ, và đã được thay bằng bài HÀNH VI.

Và luật review B5 — cũng là **mã chết** cho tới đêm nay — nay đã cắm VÀ đã
chạy thật: Gemini viết mã → `codex/codex-default` phản biện `REVISE`, khác họ,
độc lập (§14).

### BA HẠNG MỤC MỞ, ghi rõ chứ không giấu

| # | Hạng mục | Mục |
|---|---|---|
| 1 | nhánh `CHO_QUOTA` chưa tới được trạng thái việc — bảng đọc "hỏng" trong khi sự thật là "đang chờ hạn mức" | §10c |
| 2 | `phien_leader.py` + `han_muc.py` vẫn là **mã chết** — KHÔNG tính là năng lực V1.0 đang chạy | §11 |
| 3 | `.beamignore` thiếu `build/`/`dist/` — có từ TRƯỚC đêm nay, không thuộc V1.0 | §12d |

Không hạng mục nào trong ba cái đó được "sửa cho xanh" lúc nửa đêm: cái thứ
nhất cần một quyết định thiết kế của chủ sở hữu, hai cái sau nằm ngoài phạm
vi được giao.

---

## 1. MỘT CHỦ SỞ HỮU CHÍNH SÁCH PHỤC HỒI

Trước:

```
worker hỏng ──> _thu_lai_neu_dang        (tự quyết: thử lại / từ chối / cạn)
```

Sau:

```
worker hỏng ──> _dieu_phoi_su_co         ← CHỦ SỞ HỮU DUY NHẤT
                    │
                    ├── SỰ CỐ BỀN  (mở/lấy, ngân sách tiếp tục)
                    ├── phân loại  (su_co.phan_loai)
                    ├── chọn chiến lược (VongSuCo.xet)
                    └── gọi NGUYÊN LIỆU:
                          SUA_TAI_CHO / DOI_CHO_CHAY / LAP_LAI_KE_HOACH
                          SUA_MOI_TRUONG / SUA_HA_TANG_KIEM
                              └─> _thu_lai_neu_dang   (nguyên liệu)
                          CHO_QUOTA        └─> chờ, KHÔNG mua thêm
                          HOI_DONG / LEO_THANG └─> BLOCKED kèm bằng chứng
```

`_thu_lai_neu_dang` **không còn tự quyết**. Nó vẫn giữ nguyên mọi lưới an
toàn đã trả giá để có (không thử lại lỗi không phụ thuộc chỗ chạy, định
tuyến lại có trần, `MAX_ATTEMPTS`) — nhưng nay nó là *cách thi hành* một
quyết định, không phải *người ra quyết định*.

Hai chủ sở hữu chính sách nghĩa là hai ngân sách đếm song song cho cùng một
việc, và đó đúng là chế độ hỏng `su_co.py` sinh ra để chặn.

`NEEDS_EVIDENCE` **cũng** đi vào vòng này. Thiếu bằng chứng là một sự cố phải
xử, không phải một ngõ cụt yên lặng.

## 2. SỰ CỐ BỀN — ngân sách không được nạp lại

`su_co_ben.py` ghi hồ sơ vào **sổ sự kiện chung** (kind `INCIDENT_STATE`);
trạng thái hiện tại là bản ghi mới nhất của việc đó. Không di trú lược đồ,
không dựng kho thứ hai cho cùng một loại sự thật, và tự có sẵn dòng thời
gian đọc lại được.

Hồ sơ giữ đúng những gì cần để tiếp tục: `incident_id`, `execution_id`, mục
tiêu GỐC, lớp hỏng, chữ ký hỏng, tham chiếu bằng chứng, `da_dung` theo từng
loại hành động, `dem_chu_ky` theo chữ ký, chiến lược đang chạy, chỗ chạy
trước, trạng thái.

`SoSuCo.vong()` **nạp ngược** `da_dung`/`dem_chu_ky` vào bộ quyết định. Đây
là chỗ tính bền trở thành hành vi: một tiến trình tắt giữa lúc sửa rồi bật
lại **không** được cấp thêm lượt nào. Ngân sách chỉ có nghĩa khi nó được đếm
qua các lần chạy.

Và `mo_hoac_lay` không bao giờ mở hai hồ sơ cho một việc đang mở — nếu không
thì mỗi lần hỏng lại có một ngân sách mới, tức là không có ngân sách nào.

## 3. HẠ TẦNG KIỂM ĐỊNH ≠ SẢN PHẨM SAI

Bài nghiệm thu trước tự nó chứng minh vì sao cần tách: `scripts.test` viết
là `node --test tests/`, mà trên Node 24 + Windows câu đó nạp `tests` như
một **module** và chết `MODULE_NOT_FOUND`. `rc=1` → cổng từ chối `DONE`
(đúng), nhưng worker đã làm ĐÚNG — chạy lại đúng cây đó bằng lệnh đúng cho
**4/4 đạt**.

Gộp hai thứ làm một dẫn tới hành động sai: hệ đi sửa mã sản phẩm (không
hỏng) thay vì sửa lệnh kiểm (hỏng), và đổ lỗi cho worker về một việc nó làm
đúng.

Nay:

| Lớp | Dấu hiệu | Hành động |
|---|---|---|
| `INVALID_VERIFICATION_COMMAND` | `MODULE_NOT_FOUND`, `missing script`, `not recognized`, `No inputs were found` | `SUA_HA_TANG_KIEM` |
| `TEST_HARNESS_FAILURE` | `no test files found`, `0 tests collected`, `INTERNALERROR` | `SUA_HA_TANG_KIEM` |
| `TEST_FAILURE` | `test failed`, `AssertionError` | `SUA_TAI_CHO` |

Hai lớp hạ tầng xét **TRƯỚC** `TEST_FAILURE` — đặt sau thì chuỗi
`'test failed'` nuốt mất chúng.

`kiem_du_an` nay ghi đủ để chẩn đoán mà không phải đoán: **lệnh chính xác**,
**cwd**, **mã thoát**, **đuôi stdout/stderr**, **nguồn khám phá**, và một cờ
`ha_tang_hong` riêng kèm đoạn văn bản đã khớp làm bằng chứng.

`rc != 0` **không** phải bằng chứng rằng mã sản phẩm sai. Nó chỉ nói lệnh này
trả về khác 0.

Và vì cả hai trường hợp nghĩa là **ta không có phép đo**, cổng trả
`NEEDS_EVIDENCE` chứ không `FAILED`:

| | |
|---|---|
| `thieu_bang_chung` | không có lệnh nào để chạy |
| `ha_tang_hong` | có lệnh, nhưng CHÍNH LỆNH hỏng |

Đánh `FAILED` ở đây là đổ lỗi cho worker về một việc nó làm đúng — đã xảy ra
thật.

## 4. HAI KHUYẾT TẬT CỦA CHÍNH DÂY NỐI, do lượt chạy thật đầu tiên phát hiện

Lượt cắm dây đầu tiên chạy ĐÚNG đường:

```
PROJECT_VERIFIED (rc=1) -> INCIDENT_STATE -> TEAM_EVENT INCIDENT
                        -> TEAM_EVENT REPAIR -> RETRY_QUEUED   (×2)
```

Nhưng chính nó phơi ra hai lỗi của tôi.

### 4a. `hien_tai()` lấy bản ghi CŨ NHẤT — bộ ngắt mạch không bao giờ nổ

`store.su_kien` trả `ORDER BY id DESC` (mới nhất trước). Hàm đọc hồ sơ gọi
`reversed()` rồi lấy phần tử đầu, tức là lấy bản **cũ nhất**.

Bằng chứng từ sổ, sau HAI lần hỏng liên tiếp:

```
da_dung    = {'sua_tai_cho': 1}     ← phải là 2
dem_chu_ky = {'…': 1}               ← phải là 2
```

Mỗi lần hỏng nạp lại ngân sách của lần ĐẦU rồi ghi đè. Ngân sách không bao
giờ cạn, nên **bộ ngắt mạch không bao giờ nổ** — đúng cái vòng lặp vô hạn mà
cả tầng này sinh ra để chặn.

Bản giả `_SoGia` trong bộ kiểm cũng trả ngược thứ tự với bản thật. **Đó là
cách một khuyết tật thứ tự sống sót qua mọi bài kiểm.** Nay bản giả trùng
bản thật, và có thêm một bài kiểm HÀNH VI (`test_12c`: đếm phải tiến
`1, 2, 3`).

### 4b. Bằng chứng của cổng kiểm định không đi vào sự cố — `loai=UNKNOWN`

Khi việc hỏng vì cổng kiểm định dự án, câu giải thích (*"phép kiểm của dự án
KHÔNG đạt … rc=1"* kèm đuôi đầu ra) nằm ở `ly_do` của chỗ gọi, **không** nằm
trong phong bì của worker. Lượt đầu chỉ đưa phong bì vào, nên bộ phân loại
mù và ghi `loai=UNKNOWN` cho một lần hỏng mà ta biết chính xác nguyên nhân.

Nay `bang_chung_them` là **mảnh đầu** của văn bản đem phân loại.

Cả hai lỗi chỉ lộ ra vì có một lượt chạy THẬT. Không bài kiểm đơn vị nào của
tôi bắt được chúng — cái thứ nhất vì bản giả sai thứ tự, cái thứ hai vì bài
kiểm tự dựng sẵn văn bản hỏng thay vì lấy từ đường thật.

## 5. HAI KHUYẾT TẬT NỮA, do lượt chạy thật THỨ HAI phơi ra

Lượt sau khi sửa §4 chạy đúng bậc thang mong muốn — `SUA_TAI_CHO` ×2 rồi
`LAP_LAI_KE_HOACH`, có trần, không lặp vô hạn:

```
da_dung = {'sua_tai_cho': 2, 'lap_lai_ke_hoach': 1}
```

Nhưng cùng sổ ấy phơi ra hai chỗ còn đọc SAI NGUỒN.

### 5a. `loai=UNKNOWN` — bộ phân loại khớp LỜI VĂN, mà lời văn đã đổi

`bang_chung_them` đã vào tới nơi (§4b), nhưng vẫn `UNKNOWN`. Lý do:

| | |
|---|---|
| mẫu `VERIFICATION_FAILURE` bắt | `kiểm định không đạt` |
| `kiem_du_an` thật sự viết | `phép kiểm của dự án KHÔNG đạt` |

Cùng một sự thật, hai cách nói, hai tệp. Đây lại đúng hình dạng đã gặp suốt
cả hai bản: **hai nơi giữ một sự thật và bất đồng, tầng trên tin nơi sai.**

Sửa ở NGUỒN, không ở chuỗi cuối: `kiem_du_an` nay phát một **MÃ MÁY ĐỌC
ĐƯỢC** mở đầu `ly_do` — `KIEM_DU_AN_KHONG_DAT` / `KIEM_DU_AN_HA_TANG_HONG` —
và bộ phân loại khớp MÃ. Văn xuôi ở lại cho người đọc, và sửa lời văn không
còn làm câm bộ phân loại ở tệp khác.

Kèm theo: hai lớp hạ tầng nay xét **trước** `VERIFICATION_FAILURE` nữa, không
chỉ trước `TEST_FAILURE` — một chữ "thiếu bằng chứng" lẫn trong phong bì
worker cũng đủ nuốt mất chúng. Mã do Router TÍNH phải thắng mọi mẫu bắt-chữ.

### 5b. Vân tay lấy từ VĂN XUÔI CỦA MODEL — bộ ngắt mạch chỉ còn một lưới

Ba lần hỏng của **cùng một lệnh kiểm, cùng mã thoát** cho ra ba chữ ký:

```
dem_chu_ky = {'UNKNOWN:6ea35e59ee': 1, 'UNKNOWN:8c8a80a8da': 1,
              'UNKNOWN:9c2097db80': 1}
```

`chu_ky()` băm cả `pb.summary`, mà model viết mỗi lượt một khác. Nên
`dem_chu_ky` không bao giờ vượt 1, nhánh `lap >= ns.lap_chu_ky` là **mã
chết**, và vòng chỉ còn dừng được nhờ ngân sách.

Nó vẫn dừng — nên nhìn từ ngoài lượt chạy trông như đạt. Nhưng hai lưới an
toàn đã thành một, và lưới mất đi đúng là lưới sinh ra để nhận biết **"thử
mù"**: ngân sách chỉ đếm *bao nhiêu lần*, chữ ký mới trả lời *có phải vẫn
đúng lần hỏng ấy không*.

Sửa: `xet()` tách `van_ban_chu_ky` (bằng chứng **Router tính**: lệnh, mã
thoát, lớp hỏng) khỏi văn bản đem **phân loại** (rộng hơn, gồm cả phong bì
worker, để dễ khớp mẫu). Hai mục đích ngược nhau — một cái muốn ỔN ĐỊNH
nhất, một cái muốn ĐỌC ĐƯỢC NHIỀU nhất — nên chúng không được dùng chung một
chuỗi.

### 5c. Bộ kiểm cũng phải đỏ được

Cả 5 đột biến đều đỏ, cây gốc xanh trước và sau:

| Đột biến | Bài kiểm bắt được |
|---|---|
| vân tay lấy lại từ văn xuôi model | `test_22`, `test_22c` |
| engine thôi truyền bằng chứng làm vân tay | `test_22d` |
| bỏ mã máy khỏi mẫu `VERIFICATION_FAILURE` | `test_21` |
| hạ tầng xét SAU verification (thứ tự cũ) | `test_21b` |
| `kiem_du_an` thôi phát mã | `test_21c` |

Một bài trong số đó ban đầu XANH khi tháo dây — `test_22c` dựng văn xuôi khác
nhau bằng *"lần thứ 0/1/2"*, mà `chu_ky()` quy mọi chữ số về `#`, nên ba câu
băm ra một giá trị dù dây đã tháo. Nó đúng vì lý do sai. Đã đổi sang văn xuôi
khác nhau về TỪ NGỮ, và nay nó đỏ được.

## 6. BỘ NGẮT MẠCH TRÊN ĐƯỜNG THẬT — bằng chứng từ sổ

**Hỏng có chủ đích, không sửa được bằng cách lặp lại cùng một hành động.**
`RouterDogfood02/tests/app.test.js` có hai khẳng định đỏ: `#clear-completed`
(thứ mục tiêu YÊU CẦU) và `escapeHtml` (cố ý NGOÀI mục tiêu). Dù worker làm
đúng phần việc được giao, `npm test` vẫn `rc=1` — nên lặp lại y nguyên không
bao giờ thoát được.

Cùng một kịch bản, chạy hai lần, trước và sau §5:

| | lượt 2 (trước) | lượt 3 (sau) |
|---|---|---|
| phân loại | `UNKNOWN` | `VERIFICATION_FAILURE` |
| chữ ký | 3 chữ ký khác nhau, mỗi cái ×1 | **1** chữ ký, đếm **3** |
| thứ đã chặn | chỉ còn ngân sách | **lặp chữ ký** |
| bậc thang | `SUA_TAI_CHO`×2 → `LAP_LAI_KE_HOACH` | `SUA_TAI_CHO`×2 → **`HOI_DONG`** |

Sổ của lượt 3 (`routerdogfood02.t7d00-1`):

```
[PROJECT_VERIFIED] KIEM_DU_AN_KHONG_DAT phép kiểm của dự án KHÔNG đạt:
                   C:\Program Files\nodejs\npm.CMD run test -> rc=1
[INCIDENT_STATE]   VERIFICATION_FAILURE -> SUA_TAI_CHO
[TEAM_EVENT]       INCIDENT[AG02/gemini-3.1-pro-low] VERIFICATION_FAILURE
[TEAM_EVENT]       REPAIR[router] SUA_TAI_CHO
[RETRY_QUEUED]     lượt 1/3 hỏng; nhả phiên cũ để lượt sau chọn chỗ khác
        … (lượt 2 y hệt) …
[INCIDENT_STATE]   VERIFICATION_FAILURE -> HOI_DONG: chữ ký hỏng lặp 3 lần —
                   dừng thử mù, đưa sang hội đồng để nhìn bằng con mắt khác
[TEAM_EVENT]       ESCALATION[router] HOI_DONG
[INCIDENT_STATE]   đóng sự cố

incident=sc_f3f0a8a22d50   loai=VERIFICATION_FAILURE
chu_ky=VERIFICATION_FAILURE:0c2d236598
da_dung={'sua_tai_cho': 2, 'hoi_dong': 1}
dem_chu_ky={'VERIFICATION_FAILURE:0c2d236598': 3}
chien_luoc=HOI_DONG   trang_thai=DA_DONG
```

Đọc theo đúng bốn điều chủ sở hữu yêu cầu chứng minh:

| Yêu cầu | Bằng chứng |
|---|---|
| cùng chữ ký hỏng lặp lại | `dem_chu_ky` = **3** trên MỘT chữ ký |
| không thử lại mù vô hạn | dừng ở lượt 3, `trang_thai=DA_DONG` |
| đổi chiến lược / leo thang | `SUA_TAI_CHO` → `SUA_TAI_CHO` → `HOI_DONG` |
| cạn có trần nếu chưa xong | `da_dung` khớp trần, `khong_tien_trien=True` |

**Đây là `VongSuCo`, KHÔNG phải `thu_lai_neu_dang` cũ.** Bốn dấu vết chỉ tầng
V1.0 mới sinh ra được, và không dấu nào nằm trong đường V0.9:

1. `INCIDENT_STATE` — kind sự kiện của `su_co_ben`;
2. `TEAM_EVENT INCIDENT/REPAIR/ESCALATION` — ba loại có kiểu của `su_kien.py`;
3. `da_dung` / `dem_chu_ky` — ngân sách theo TỪNG loại hành động, thứ
   `_thu_lai_neu_dang` không có khái niệm (nó chỉ đếm `attempts`);
4. `HOI_DONG` — một hành động V0.9 không biết tồn tại.

Ngược lại `RETRY_QUEUED` vẫn còn, và đó là điều ĐÚNG: `_thu_lai_neu_dang` nay
là **nguyên liệu** thi hành quyết định `SUA_TAI_CHO`, không phải người ra
quyết định. Thấy `RETRY_QUEUED` mà KHÔNG thấy `INCIDENT_STATE` đứng trước mới
là dấu hiệu dây nối đứt.

## 7. KHUYẾT TẬT THỨ BA VÀ THỨ TƯ — leo thang không tới nơi, rồi làm treo cha

### 7a. Leo thang dừng ở sổ, không tới trạng thái việc

Sổ của lượt 3 ghi đủ `ESCALATION HOI_DONG` và đóng sự cố đúng. Mà việc vẫn
đọc `FAILED`. Người vận hành nhìn bảng điều khiển thấy **"hỏng"**, không thấy
**"đang chờ người"** — tức là leo thang, thứ duy nhất được phép gọi người,
không tới được nơi nó cần tới.

`FAILED -> BLOCKED` không có trong bảng chuyển, `doi_trang_thai` ném
`TransitionError`, và lời từ chối rơi vào `except Exception: pass`.

Lại đúng hình dạng ấy: **một `except` phòng thủ biến một cơ chế an toàn thành
một lệnh rỗng** — lần thứ ba trong hai bản này.

Sửa hai nửa, và nửa thứ hai mới là nửa quan trọng:

* `model.py` thêm ĐÚNG MỘT mũi tên `FAILED -> BLOCKED`. Nó là nửa còn lại của
  `FAILED -> QUEUED`: bộ điều phối chạy SAU khi lượt đã bị chấm `FAILED`, nên
  `SUA_TAI_CHO` xếp lại việc (`-> QUEUED`, vốn hợp lệ) và `HOI_DONG` phải dừng
  việc lại (`-> BLOCKED`). `NEEDS_EVIDENCE` vốn đã có mũi tên này; `FAILED` bị
  bỏ quên vì **trước V1.0 không có gì leo thang cả**. Không mở đường nào tới
  `DONE`/`REVIEW`.
* `engine.py` thôi nuốt: leo thang hỏng thì ghi `ESCALATION_KHONG_DAT` mức
  ERROR. Sửa bảng chuyển mà vẫn để `except ... pass` thì lần sau lại im lặng.

### 7b. Mũi tên ấy làm việc CHA treo vĩnh viễn — bộ kiểm bắt được

`test_mot_con_hong_khong_huy_anh_em` đi từ **2.7s** sang **61s rồi đỏ**. Quy
trách rành mạch, đo hai chiều: gỡ mũi tên → xanh; giữ mũi tên → treo.

`BLOCKED` MANG HAI NGHĨA và chỉ một nghĩa là kết thúc:

| Nghĩa | Còn tự chạy? | Cha nên làm gì |
|---|---|---|
| chờ thẩm quyền / tài nguyên | **có** — người mở rào là nó chạy tiếp | CHỜ |
| phục hồi tự chủ đã cạn (V1.0) | không | GỘP, kể là hỏng |

Thiết kế cũ chỉ biết nghĩa thứ nhất, vì nghĩa thứ hai trước V1.0 không tồn
tại. Coi nghĩa thứ hai là "chờ" thì cha treo vĩnh viễn — và **với một hệ chạy
qua đêm không người trực, treo tệ ngang lặp vô hạn**, đúng thứ cả tầng này
sinh ra để chặn.

Phân biệt bằng **hồ sơ sự cố bền** (sự thật có cấu trúc), không bằng cách dò
chữ trong `blocked_reason`.

### 7c. Một cuộc đua thứ hai, chỉ lộ ra khi đo 15 lần

Sau bản sửa 7b bài kiểm xanh. Chạy lại 15 lần: **4 xanh / 11 đỏ**, lệch giữa
`(3 xong, 1 hỏng)` và `(3 xong, 0 hỏng)`.

`FAILED` **không còn là trạng thái NGHỈ** từ khi vòng sự cố được cắm vào — nó
là một nhịp TRUNG GIAN trên đường tới "xếp lại" hoặc "leo thang". Anh em gộp
đúng lúc đó thì chốt một kết quả mà chính hệ vẫn đang sửa.

Nay `FAILED` + **sự cố còn mở** = CHƯA kết thúc. Đo lại: **15/15 tất định.**

Một lần chạy xanh đã suýt làm tôi kết luận là xong — đúng cái bẫy mà chính
báo cáo này ghi ở §4.

### 7d. Bản tổng hợp phải nói THẬT

Con leo thang nay được kể vào `hong` (không phải `khac`), kèm đếm riêng
`leo_thang`. *"3 xong, 0 hỏng"* trong khi có một việc đang chờ người là một
câu **đúng về kỹ thuật mà sai về sự thật** — đúng loại câu luật 2 của V0.9
cấm.

## 8. BÀI KIỂM PHỤ THUỘC TẢI — điều tra có trần, và kết luận cũ là SAI

`V10_RELEASE_ACCEPTANCE.md` ghi `test_toa_v061.test_neu_nguoi_dung_neu_model_
thi_ghim_provider` là *"cùng họ với một cuộc đua tầng khoá ở V0.9.1"*.
**Kết luận đó sai**, và phép đo nói rõ tại sao.

Không cần chạy đi chạy lại cầu may: câu hỏi là một câu TẤT ĐỊNH — *sau
`tick()`, bốn việc con còn ở `RUNNING` trong bao lâu?* `claim_task` đặt
`RUNNING` **đồng bộ ngay trong `tick()`** trước khi dựng luồng, nên chiều
"chưa kịp RUNNING" là bất khả; đếm thiếu chỉ có thể vì con đã **RỜI**
`RUNNING`.

| executor | trễ 0.00s | trễ 0.05s | trễ 0.20s |
|---|---|---|---|
| `cham=0` (bài đỏ) | 4/4 | **3/4** | **2/4** |
| `cham=0.4` (hai bài anh em) | 4/4 | 4/4 | 4/4 |

Cửa sổ quan sát với `cham=0` đo được **~40ms**. `2/4` ở cột cuối đúng bằng
con số lần hồi quy đỏ đã ghi ("đếm được 2 việc `RUNNING` thay vì 4").

Và chứng cứ quyết định nằm trong chính tệp bài kiểm: **mọi** bài khẳng định
một số đếm `RUNNING` tức thời đều đã có `cham` — `test_giao_nhieu_tai_khoan…`
(0.4), `test_leader_chiem_mot_khe…` (0.5). Chỉ bài này quên.

Đây là **khuyết tật CỦA BÀI KIỂM**, không phải đua ở tầng khoá, và không phải
khuyết tật sản phẩm. Sửa: cho nó đúng cửa sổ quan sát mà hai bài anh em đã
có. Không chạm tầng khoá — chủ sở hữu dặn thẳng là không viết lại khoá trong
việc này, và phép đo nói rằng không cần.

## 9. CHÍNH SÁCH REVIEW CŨNG LÀ MÃ CHẾT — và cũng đã được cắm

Kiểm lại đúng câu chủ sở hữu dùng cho vòng sự cố, nhưng cho phần review:

```
grep -rn "can_review_doc_lap" scripts/ --exclude-dir=tests
    -> scripts/control_center/v10/vai_tro.py:157   (định nghĩa)
    -> (không có chỗ gọi nào)
```

`can_review_doc_lap` và `chon_reviewer` có **10 bài kiểm** và **không một
dặm đường thật nào** — đúng cùng một hình dạng. Luật *"họ Gemini viết mã sản
phẩm ⇒ BUỘC PHẢI phản biện khác họ"* chưa từng chạy một lần.

Cắm ở **đúng một seam**: `nen_goi_reviewer` — nơi duy nhất giữ chính sách gọi
Reviewer. Nó **HỎI** luật, không chép lại luật. Vị trí mệnh đề mới không tuỳ
tiện:

| Đứng sau | *"máy đã thấy lỗi"* — một phép đo đã đỏ vẫn là câu trả lời; hỏi thêm một model lúc đó chỉ mở đường cho một `ACCEPT` che mất nó |
| Đứng trước | *"việc máy móc"* — máy móc không miễn được luật này |

Chiều khác-họ ở dưới đã có sẵn (`ho_tac_gia` + `doi_doc_lap` trong
`hoi_dong.py`), nên mảnh còn thiếu đúng là **có bắt buộc hay không**.

**Một lỗi im lặng bị chặn trước khi kịp chạy.** Chỗ gọi đầu tiên tôi viết
`"implement"`, mà `VIEC_SUA_MA` chứa `"implementation"`. Lệch một chữ giữa
hai tệp là cả luật thành lệnh rỗng — và không ai báo. Đúng hình dạng §5a, chỉ
khác là lần này bắt được trước khi nó chạy. Có bài kiểm đọc chuỗi **từ mã
nguồn** rồi đối chiếu với tập luật, nên một lần đổi tên sau này không lặng lẽ
phá nó.

**Và một bài kiểm của chính tôi không đủ.** Bài neo CẤU TRÚC bắt được việc
XOÁ lời gọi, nhưng với đột biến *"vẫn gọi, không dùng kết quả"* nó vẫn XANH.
Đã thêm bài HÀNH VI hỏi thẳng cổng: mọi phép đo xanh, không tiêu chí ngữ
nghĩa, không chạm production, rủi ro thấp — mà mã do Gemini viết thì vẫn phải
gọi phản biện; còn `claude-sonnet-5` thì không (luật hẹp có chủ đích).

## 10. MA TRẬN ĐỘT BIẾN — 10/10

Cây gốc xanh trước và sau mỗi lần.

| # | Đột biến | Bài kiểm bắt được |
|---|---|---|
| A | vân tay lấy lại từ văn xuôi model | `test_22`, `test_22c` |
| B | engine thôi truyền bằng chứng làm vân tay | `test_22d` |
| C | bỏ mã máy khỏi mẫu `VERIFICATION_FAILURE` | `test_21` |
| D | hạ tầng xét SAU verification | `test_21b` |
| E | `kiem_du_an` thôi phát mã | `test_21c` |
| F | bỏ mũi tên `FAILED -> BLOCKED` | `test_23`, `test_23b`, `test_23c` |
| G | leo thang thôi ghi sự kiện có tên | `test_24` |
| H | luật B5 bị vô hiệu hoá (vẫn gọi, không dùng) | `test_11c` |
| I | chỗ gọi thôi truyền model đã viết mã | `test_11` |
| J | lệch một chữ ở loại việc | `test_11b` |

Hai trong số đó (`H`, và `A` ở lần đầu) ban đầu **XANH** — bộ kiểm chưa đủ,
không phải mã đã đúng. Cả hai nay có bài HÀNH VI.

## 10b. KHỞI ĐỘNG LẠI GIỮA LÚC ĐANG PHỤC HỒI — **8/8**

Kịch bản thật, không giả lập sổ: chạy một lần thực thi sẽ hỏng, **giết tiến
trình Router** ngay khi hồ sơ sự cố vừa được ghi, rồi bật một tiến trình MỚI
đọc lại mọi thứ từ sổ chính tắc.

| Khẳng định | Kết quả |
|---|---|
| hồ sơ sự cố đọc lại được sau khởi động lại | OK |
| CÙNG `incident_id` | `sc_567e7bc1b2f8` |
| mục tiêu GỐC còn nguyên | OK |
| **ngân sách KHÔNG bị nạp lại** | `{'sua_tai_cho': 1}` → `{'sua_tai_cho': 1}` |
| đếm chữ ký KHÔNG bị nạp lại | `{VERIFICATION_FAILURE:0c2d236598: 1}` → y nguyên |
| `vong()` dựng lại TỪ hồ sơ | `{'sua_tai_cho': 1}` |
| KHÔNG sinh việc trùng | 18 → 18 |
| vẫn CÙNG một hồ sơ sự cố | `sc_567e7bc1b2f8` |

Hai chi tiết đáng ghi riêng:

* Chữ ký `VERIFICATION_FAILURE:0c2d236598` **trùng khít** với lượt §6 — hai
  tiến trình khác nhau, hai lần chạy khác nhau, cùng một vân tay. Đó là xác
  nhận ĐỘC LẬP rằng bản sửa §5b có hiệu lực, không chỉ trong một tiến trình.
* Sổ ghi `RUNNING -> QUEUED (phiên chủ không còn sau khởi động lại)` —
  `recover()` nhận việc mồ côi và trả nó về hàng đợi, không đánh `FAILED`
  oan.

### 10c. Và lượt ấy phơi ra một khoảng trống THẬT — cùng họ với §7a

Lượt tiếp tục gặp **hết hạn mức trên TÀI KHOẢN đang chạy** (AG02). Đo lại bể
ngay sau đó cho thấy bể vẫn khoẻ — Gemini còn **92%** hạn tuần và **92%** hạn
5 giờ, `paid_overage_risk_zero: true`. Nói "hết hạn mức Antigravity" là biến
một phép đo của MỘT khe thành một câu về cả tám; luật ấy có từ V0.8 và nó áp
cho chính báo cáo này.

Vòng sự cố xử đúng:

```
loai=QUOTA_EXHAUSTED  chien_luoc=CHO_QUOTA  trang_thai=DANG_MO
"hết hạn mức nhà cung cấp — CHỜ hoặc dùng bể khác.
 KHÔNG mua thêm credit, không bật overage"
```

Đúng luật: không thử lại mù, **không mua thêm credit**, giữ sự cố MỞ để còn
tiếp tục.

Nhưng trạng thái việc là **`FAILED`**, và `blocked_reason` RỖNG.

Người vận hành mở bảng điều khiển đọc được **"hỏng"**, trong khi sự thật là
**"đang chờ hạn mức"**. Đó đúng là khuyết tật §7a — *quyết định của vòng sự
cố không tới được trạng thái việc* — chỉ khác nhánh: §7a là nhánh leo thang
(đã sửa), đây là nhánh `CHO_QUOTA` (CHƯA sửa).

**Tôi KHÔNG sửa nó đêm nay, và lý do là kỹ thuật chứ không phải hết giờ.**
`BLOCKED` nghĩa là *cần người*; hạn mức thì tự hồi theo thời gian. Đánh
`BLOCKED` mà không có đường tự mở lại là biến một lần CHỜ hồi được thành một
lần DỪNG vĩnh viễn — tệ hơn hiện trạng. Việc này cần một trạng thái "chờ tài
nguyên, tự xét lại" cùng với người đánh thức nó, và đó là một quyết định
thiết kế thuộc về chủ sở hữu, không phải một bản vá lúc nửa đêm.

Ghi lại làm **hạng mục mở số 1**.

## 11. CÒN GÌ CHƯA ĐƯỢC CẮM — quét cả gói `v10/`

Vì câu *"tested but not wired"* đã đúng HAI lần (vòng sự cố, rồi chính sách
review), tôi quét nốt cả gói thay vì chờ nó đúng lần thứ ba:

| Mô-đun | Chỗ gọi trong mã sản phẩm | Trạng thái |
|---|---|---|
| `su_co.py` | `engine._dieu_phoi_su_co` | **ĐÃ CẮM**, có dặm đường thật (§6) |
| `su_co_ben.py` | `engine._dieu_phoi_su_co`, `_con_da_ket_thuc` | **ĐÃ CẮM**, có dặm đường thật |
| `su_kien.py` | `engine._dieu_phoi_su_co` | **ĐÃ CẮM**, sự kiện có kiểu hiện trong sổ |
| `vai_tro.py` | `kiem_dinh.nen_goi_reviewer` | **ĐÃ CẮM** đêm nay (§9) |
| `phien_leader.py` | *(không có)* | **NỀN MÓNG — CHƯA CẮM** |
| `han_muc.py` | *(không có)* | **NỀN MÓNG — CHƯA CẮM** |

Hai dòng cuối là **mã chết**: có bài kiểm, không có một chỗ gọi nào trong mã
sản phẩm. Chúng KHÔNG được tính là năng lực V1.0 đang chạy.

Và một cái bẫy đáng ghi riêng: `scripts/control_center/leader.py` có sẵn một
lớp **cùng tên** `PhienLeader`, và lớp ấy THẬT SỰ được dùng
(`engine.py:1936`). Một phép tìm theo tên lớp sẽ trả về kết quả và cho cảm
giác `v10/phien_leader.py` đã được cắm — nó chưa. Hai thứ khác nhau trùng
tên, đúng cái hình dạng đã gây ra gần hết khuyết tật của đêm nay.

**Tôi không cắm hai mô-đun ấy đêm nay.** Chủ sở hữu chỉ định phạm vi là vòng
sự cố; cắm thêm hai hệ con vào lúc này, không có dặm đường thật để xác minh,
đúng là cách đẻ ra khuyết tật thứ năm — và bốn khuyết tật trước đều do một
lượt chạy thật phát hiện chứ không phải do bài kiểm.

## 12. HỒI QUY ĐẦY ĐỦ BẮT ĐƯỢC THỨ MÀ BÀI NHẮM ĐÍCH KHÔNG BẮT

129 bài nhắm đích xanh, ma trận đột biến 10/10, hai dogfood thật đều đạt — và
hồi quy đầy đủ vẫn ra **4 bài đỏ**. Cả bốn ở `test_control_center_slice.py`,
và cả bốn CÙNG MỘT gốc:

```
_can_luot()  chờ  state is FAILED  làm chỗ nghỉ
```

Từ khi vòng sự cố sở hữu chính sách phục hồi, một việc cạn bậc thang sẽ LEO
THANG và nghỉ ở `BLOCKED`. Chờ một trạng thái không bao giờ tới nữa = hết 60s
rồi báo đỏ, bốn lần — bộ kiểm ấy vì thế chạy 541s; sau khi sửa còn 300s.

Đây là **cùng một sự thay đổi ngữ nghĩa** đã làm treo việc cha ở §7b, chỉ
hiện ra ở một mặt khác. Một thay đổi trạng thái nhỏ chạm tới mọi chỗ từng
coi `FAILED` là chỗ nghỉ cuối cùng — và chỉ hồi quy ĐẦY ĐỦ mới liệt kê hết
được những chỗ ấy.

### 12b. Và lượt hồi quy THỨ HAI bắt được thứ tôi đã tự cho qua

Sau khi sửa bốn bài trên, hồi quy đầy đủ lần hai ra **1 bài đỏ** — chính
`test_mot_con_hong_khong_huy_anh_em`, bài tôi vừa đo **15/15 tất định** khi
chạy riêng. Lần này con hỏng đọc ra `QUEUED` sau khi cha đã chốt xong.

Nguyên nhân là một khe hở tôi đã NHÌN THẤY lúc viết và tự đánh giá là *"hẹp,
chấp nhận được"*:

```
_chay:  ghi FAILED  ─┐
                     ├── khe hở: chưa có hồ sơ sự cố nào để đọc,
                     │            nên "không tìm thấy hồ sơ" = "nghỉ rồi"
        _dieu_phoi_su_co ─> mở hồ sơ ─> xếp lại hàng đợi
```

Đánh giá ấy **sai**. Khe hở tới được, và **chỉ hồi quy đầy đủ** — 2698 bài,
đủ tải — mới làm nó hiện ra. Chạy riêng 15/15 không phải bằng chứng; đó đúng
là bài học §7c lặp lại, lần này với chính tôi ở phía sai.

Sửa bằng đúng phép kiểm mà `_can_luot` của bộ kiểm lát cắt đã dùng từ V0.9:
**luồng của chính con ấy còn bay = CHƯA kết thúc.**

**Và một lần vấp ngay sau đó, ghi lại vì nó đáng giá.** Bản sửa đầu tiên kiểm
"còn bay" cho MỌI con, làm bộ kiểm `toa` đi từ 2s sang hết giờ ở cả 10 lượt:
`_tong_hop_toa` chạy TRONG luồng của con vừa xong, nên con ấy LUÔN còn trong
`_dang_chay` ở đúng lúc ấy — không trừ nó ra thì **không lần gộp nào xảy ra
nữa**, và cha treo với MỌI lần toả, không riêng lần có con hỏng. Một bản sửa
làm hỏng rộng hơn thứ nó sửa. Nay chỗ gọi truyền `con_goi` để con ấy tự miễn.

### 12c. Lượt hồi quy THỨ BA — bản sửa của tôi làm CÂM một lưới an toàn

Lần ba ra một bài đỏ khác: `test_bon_con_CHI_DOC_chay_dong_thoi_tren_bon_tai_
khoan` hết 40s rồi đỏ — **và nó đỏ cả khi chạy riêng**, nên không phải tại
tải máy.

Thủ phạm vẫn là bản sửa §12b. Bộ kiểm khoá đọc/ghi V0.6.1 **thay**
`_tong_hop_toa` bằng một bản DO THÁM hai tham số, để canh đúng một điều:
*"khoá của con đã nhả TRƯỚC khi gộp vào cha chưa"*. Tôi thêm một tham số
`con_goi` vào chữ ký, nên chỗ gọi ném `TypeError`, `_chay` nuốt mất, và việc
cha **không bao giờ được gộp**.

Nói cho đúng tên: **bản sửa của tôi đã biến một lưới an toàn của bộ kiểm
thành một lệnh rỗng** — đúng loại hỏng mà cả đêm nay đi sửa, lần này do chính
tôi gây ra, và lại do một `except` nuốt ngoại lệ che đi.

Sửa bằng cách bỏ hẳn tham số: nhận ra *"luồng của chính con đang gọi"* bằng
**đối tượng luồng** — `_dang_chay` vốn đã giữ sẵn luồng của từng việc, nên so
với `threading.current_thread()` là đủ. Cách này đúng ở MỌI chỗ gọi (kể cả
lưới an toàn trong `tick()`) và **không chạm chữ ký**, nên không bản do thám
nào gãy.

Bài học, và nó đáng ghi: **đổi chữ ký một hàm mà bộ kiểm có quyền thay thế
là một thay đổi giao diện công khai.** Bốn lượt hồi quy đầy đủ, bốn kết quả
khác nhau, không lượt nào thừa.

### 12e. Số cuối

```
hồi quy đầy đủ   2698 bài · 2697 đạt · 1 đỏ
                 (bài đỏ = §12d, KHÔNG thuộc V1.0, có từ trước đêm nay)
các bộ liên quan 418 bài · 418 đạt · 0 đỏ
V1.0             sự cố 34 · nền móng 42 · kiểm định 20 · review 13
V0.9.3           năng lực 19 · phạm vi ghi 46 · mốc git 11
tầng bị chạm     toả 22 · khoá đọc/ghi 23 · lát cắt 90 · thực thi 97
đột biến         10/10 đỏ (cây gốc xanh trước và sau mỗi lần)
```

### 12d. Lượt thứ tư — một bài đỏ KHÔNG thuộc về V1.0

Lượt hồi quy thứ tư: `test_beam_operator.test_real_repo_payload_is_under_
threshold` đỏ. Nó **không liên quan gì tới đêm nay**, và quy trách được chắc
chắn mà không cần chạy thêm lượt nào:

* bài này đo **payload của THƯ MỤC LÀM VIỆC**: 903.8 MB / 2118 tệp;
* phần áp đảo là `build/` và `dist/` — đầu ra PyInstaller của bản desktop
  RCC, **ngày 2026-09-09 … 09-10**, tức có từ trước đêm nay nhiều ngày;
* cả hai thư mục ấy `.gitignore` bỏ qua và KHÔNG được theo dõi, nên chúng có
  mặt ở **mọi** commit trong thư mục này — kể cả commit gốc `1133a2d`;
* toàn bộ thay đổi đêm nay là tệp văn bản được theo dõi, cỡ ~60 KB.

Nó cũng **skip ở hai lượt trước** (`skipped=4`) vì cần gói `beta9`, và chỉ
chạy ở lượt này (`skipped=1`) — nên nó không hề "mới đỏ".

Nhưng nó đang chỉ đúng một khuyết tật THẬT, và là khuyết tật **cùng họ** với
sự cố 2.64 GB mà chính nó sinh ra để canh: `.beamignore` liệt kê `.router`,
`.claude/worktrees`, `web`, `server`, `scripts`, `desktop_app`, `tests`,
`docs`… mà **thiếu `build/` và `dist/`**. Một lưới canh payload không phủ
đúng thư mục lớn nhất của kho.

**Tôi KHÔNG sửa `.beamignore`, và KHÔNG xoá `build/`/`dist/`.** Cả hai là
thao tác thuộc đường ĐÓNG GÓI/TRIỂN KHAI của một sản phẩm khác (Beam apps),
nằm ngoài phạm vi chủ sở hữu giao đêm nay; xoá thư mục dựng của người khác
lại càng không phải việc tôi tự quyết lúc nửa đêm. Ghi lại làm **hạng mục mở
số 3**, kèm cách sửa đã rõ (thêm hai dòng vào `.beamignore`; khối chú thích
sẵn có trong tệp đã chứng minh KHÔNG gì ngoài `beam_apps/` cần cho Beam
runtime, nên loại trừ chúng là an toàn theo đúng lập luận đã ghi ở đó).

**Không hạ chuẩn để cho xanh.** Điều các bài ấy canh vẫn nguyên vẹn:

* `_can_luot` vẫn đòi `attempts >= MAX_ATTEMPTS`, nên một lần thử lại vô hạn
  vẫn làm nó treo tới hết giờ đúng như trước;
* `test_thu_lai_CO_TRAN_khong_lap_vo_han` vẫn khẳng định `attempts <= 3` — đó
  mới là thứ nó canh — và nay đòi hỏi **THÊM**: nếu nghỉ ở `BLOCKED` thì phải
  có hồ sơ sự cố ĐÃ ĐÓNG, tức leo thang thật, chứ không phải một việc bị chặn
  vì lý do khác lẫn vào.

## 13. NHỮNG GÌ TÔI **KHÔNG** CHỨNG MINH ĐƯỢC ĐÊM NAY

| Hạng mục | Trạng thái |
|---|---|
| Gemini **viết mã** trên đường thật | ✅ AG02/`gemini-3.1-pro-low` sửa tệp thật, `npm` thật |
| Luật review B5 **chạy** trên đường thật | ✅ xem §14 |
| nhánh `CHO_QUOTA` tới được trạng thái việc | ❌ hạng mục mở số 1 (§10c) |
| `phien_leader.py`, `han_muc.py` | ❌ mã chết (§11) |
| Claude Opus 5 làm runtime worker | ❌ **CHƯA XÁC MINH** — không đổi, và KHÔNG đụng vào trạng thái riêng của Claude Code để giả vờ ngược lại |

## 14. LUẬT B5 TRÊN ĐƯỜNG THẬT — Gemini viết mã, Codex phản biện

Mục này ban đầu ghi *"chưa chứng minh được"*: lượt §10b hết hạn mức trên tài
khoản đang chạy trước khi có một lượt kiểm định nào đi qua cổng. Đo lại bể
thì bể vẫn khoẻ (92%), nên tôi chạy một lượt riêng cho đúng câu hỏi này.

Kịch bản dựng để **chỉ còn MỘT lý do** có thể mở cổng:

* tiêu chí nghiệm thu **tất định hết** — không câu nào đòi phán đoán ngữ
  nghĩa (có thì mệnh đề `tieu_chi_can_ngu_nghia` mở cổng và bài mất nghĩa);
* **không** chạm production, rủi ro **THẤP** — hai mệnh đề còn lại cũng im;
* bước GHI chạy bằng một model họ **gemini**, và nó sửa mã nguồn.

Sổ của `ex_b09e8afd2a6d`:

```
bước ghi_tienich  DONE  model=gemini-3.1-pro-low  files=[src/format_ngay.js]

[REVIEW_GATE]    GỌI Reviewer: (V1.0) mã sản phẩm do họ gemini viết
                 (gemini-3.1-pro-low) — phản biện phải KHÁC họ trước khi
                 chấp nhận
[REVIEW_VERDICT] REVISE · codex/codex-default · độc lập=True

trạng thái cuối: BLOCKED
```

Đọc từng dòng:

| Đòi hỏi | Bằng chứng |
|---|---|
| Gemini THẬT viết mã sản phẩm | `model=gemini-3.1-pro-low`, tệp thật trên đĩa |
| **luật B5** mở cổng, không phải mệnh đề cũ | dấu `(V1.0)` — và ba mệnh đề kia đều bị kịch bản làm im |
| phản biện **KHÁC HỌ** | `codex/codex-default`, `độc lập=True` |
| không phải dấu cao su | phán xử **`REVISE`**, không phải `ACCEPT` |
| `REVISE` dẫn tới hành động | `BLOCKED` — dừng lại, không tự nhận là xong |

Đây là dặm đường thật mà §9 còn thiếu. Luật B5 nay **đã cắm VÀ đã chạy**.
