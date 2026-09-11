# V0.8 — Strategist + Reviewer + bộ định tuyến model động

Nhánh `feat/v08-strategist-reviewer-model-router`, dựng từ
`router-control-center-v0.7.0` (`88a2056`). **Chưa merge, chưa gắn thẻ.**

## 1. Vấn đề v0.7 để lại

V0.7 cho Leader ký ức vô hạn, viên nang dự án, quan sát sống, bằng chứng vận
hành chỉ-đọc. Cái nó KHÔNG cho: **một bộ não thứ hai**.

Mọi câu — từ `ê bro` tới `có nên migrate kiến trúc lưu trữ không` — đi qua
ĐÚNG một lượt của ĐÚNG một model rẻ (`gemini-3.8-flash-high`, ghim cứng
trong `leader.MODEL_LEADER`).

Với câu hỏi trạng thái thì thế là đúng và rẻ. Với một câu hỏi kiến trúc thì
đó là một model nhanh **đóng vai chuyên gia** — và không có ai phản biện nó.

## 2. Kiến trúc

```
                       PROJECT LEADER
              (sở hữu hội thoại · tổng hợp · quyết có cần sâu hơn)
                             |
        +--------------------+--------------------+
        |                    |                    |
   STRATEGIST            REVIEWER             EXECUTOR
   kiến trúc             phản biện            Router V4
   lộ trình              độc lập              (nguyên vẹn)
   đánh đổi              accept/revise/reject
        |                    |
        +--------- Leader tổng hợp ---------+
```

Người dùng vẫn nói chuyện với **một** Project Leader. Vai và model bên trong
được chọn tự động.

Gói `scripts/control_center/reasoning/`, 10 mô-đun:

| Tệp | Trách nhiệm |
|---|---|
| `vai.py` | bốn vai + hồ sơ NHU CẦU của từng vai (không phải tên model) |
| `phan_loai.py` | đặc trưng có cấu trúc → độ khó/tác động/phạm vi + kế hoạch vai |
| `chinh_sach.py` | chính sách model cao cấp, TRA TỪ KÝ ỨC dự án |
| `dinh_tuyen.py` | vai → (runtime, model) qua `router_v4.Scheduler` |
| `ngu_canh.py` | gói ngữ cảnh CÓ TRẦN + kê khai theo vai |
| `hop_dong.py` | lược đồ đầu ra Strategist/Reviewer + nhắc nhở |
| `goi.py` | gọi vai thật (agy ấm / codex một lượt / provider ngoài) + `BoGoiGia` |
| `that_bai.py` | phân loại thất bại + thử lại CÓ TRẦN |
| `ngan_sach.py` | bậc chi phí, bản ghi định tuyến, hạn mức đo được |
| `hoi_dong.py` | ghép tất cả, trả khối cho Leader |

**Không viết bộ lập lịch thứ hai.** `dinh_tuyen.py` dịch một VAI thành một
`Requirements` rồi gọi chính `router_v4.Scheduler` — thứ đã có lọc cứng, cho
điểm nhiều chiều, sức khoẻ runtime, bể quota, khan hiếm theo hàng đợi thật,
và rào chặn bậc cao cấp. Một bộ chọn thứ hai là đúng cái nguồn sự thật thứ
hai mà `nang_luc.py` đã ghi lại hậu quả (hai danh sách song song lệch nhau →
mọi việc xếp vào Codex đều chết).

## 3. Bộ phân loại — đặc trưng có cấu trúc, không phải một túi từ khoá

18 đặc trưng có tên, mỗi cái đo được và ghi lại dấu hiệu đã bắt. Điểm khó =
tổng có trọng số; điểm tác động tính riêng (một câu dễ vẫn có thể tác động
lớn). Tất định: cùng đầu vào → cùng phân loại, không LLM, không mạng.

**Hai khuyết tật hiệu chuẩn đo được, và cả hai là hỏng câm** — chúng là lý do
mục này không chỉ là "một bộ từ khoá tốt hơn":

| Câu | Bị nuốt vì | Hậu quả |
|---|---|---|
| `hãy đề xuất một redesign lớn cho production architecture và phản biện chính đề xuất đó` | `la_cau_hoi_van_hanh` bắt chữ **"production"** → xếp thành tra cứu trạng thái | cổng tầm thường chặn → KHÔNG vai nào chạy |
| `project Fanfic nên ưu tiên phát triển phần nào tiếp theo **và tại sao**` | `la_cau_hoi_lich_su` bắt chữ **"tại sao"** → xếp thành câu hỏi lịch sử | −2.0 điểm → tụt xuống `THUONG` → không leo thang |

Sửa: hai bộ nhận dạng đó bị **ĐẢO** khi lượt có tín hiệu suy luận (xin tư
vấn / chiến lược / đánh đổi / kiến trúc / đòi phản biện). Một câu xin PHÁN
ĐOÁN không phải một câu tra cứu, dù nó có nhắc tới production hay có chữ "tại
sao" trong đó.

Hai sửa nhỏ hơn, cùng loại: `chạy` trần bị bỏ khỏi từ vựng thực thi
(`production farmer hiện chạy không?` từng bị đọc thành một mệnh lệnh), và
`do_tin` được làm tròn trước khi so ngưỡng (`0.6 - 0.15` ra
`0.44999999999999996` trong dấu phẩy động, nên một lượt đáng leo thang im
lặng không leo thang).

### Bảng hiệu chuẩn

| Câu | Bậc | Tác động | AUTO |
|---|---|---|---|
| A `production farmer hiện chạy không?` | TAM_THUONG | THAP | Leader |
| B `vụ SSH key trước đây là gì?` | TAM_THUONG | THAP | Leader |
| C `tại sao mấy hôm nay Drive không có production mới?` | THUONG | TRUNG | Leader |
| D `… nên ưu tiên phát triển phần nào tiếp theo và tại sao?` | KHO | THAP | Leader + Strategist |
| E `… redesign lớn cho production architecture và phản biện …` | RAT_KHO | CAO | Leader + Strategist + Reviewer |
| F `ê bro` | TAM_THUONG | THAP | Leader |
| `commit gần nhất là gì?` | TAM_THUONG | THAP | Leader |
| `kiến trúc Fanfic nên thay đổi thế nào để scale?` | RAT_KHO | TRUNG | + Strategist + Reviewer |
| `có nên migrate Appwrite/storage architecture không?` | RAT_KHO | CAO | + Strategist + Reviewer |

## 4. Bốn chế độ chất lượng — khác nhau bằng SỐ, không bằng nhãn

`CheDo` (ECO/AUTO/STRONG/MAX) đã có từ `router_v4/premium.py`. V0.8 làm nó
có hiệu lực THẬT qua hai bảng hệ số nhân vào `Weights` của kho:

* **Hệ số VAI** — Leader ưu tiên độ trễ/chi phí (nó chạy MỌI lượt, kể cả câu
  chào); Strategist/Reviewer ưu tiên `benchmark_quality` ×2.2–2.5 và hạ
  `latency`/`expected_cost` xuống ¼–⅓.
* **Hệ số CHẾ ĐỘ** — ECO nâng `expected_cost` ×2.5, MAX hạ nó xuống ×0.3 và
  nâng `benchmark_quality` ×1.8.

Nhân chứ không thay: một kho chỉnh `weights` trong `.router/v4/fabric.json`
vẫn giữ được ý định của mình.

**Đo được trên fabric thật** (câu E, sau khi áp hạn mức thật):

| Chế độ | Strategist | Reviewer |
|---|---|---|
| ECO | `gemini-3.8-flash-high` [TRUNG] | `claude-sonnet-4-6` [DAT] |
| AUTO | `gemini-3.8-flash-high` [TRUNG] | `claude-opus-4-6-thinking` [CAO_CAP] |
| STRONG | `claude-opus-4-6-thinking` [CAO_CAP] | `gemini-3.8-flash-high` [TRUNG] |
| MAX | `claude-opus-4-6-thinking` [CAO_CAP] | `gemini-3.8-flash-high` [TRUNG] |

Ngưỡng gọi vai theo chế độ: ECO `RAT_KHO`, AUTO `KHO`, STRONG/MAX `THUONG`.
ECO còn **không tự thêm Reviewer** (chỉ khi người dùng xin tường minh) — nếu
không thì ECO và AUTO giống hệt nhau trên mọi câu RẤT KHÓ, tức là ECO không
tiết kiệm gì.

## 5. Chính sách GPT-6 Astra — tra từ ký ức, không chép vào mã

Quyết định THẬT đang nằm trong ký ức dự án Fanfic (đo 2026-09-11, sổ chính
tắc, ns `fanfic-dcf29d1141`):

```
qd_0001  [hieu_luc]  ku_dd605f187deff41e  tin_cay=user_explicit
"GPT-6 Astra chỉ được dùng cho các task đặc biệt khó hoặc cần reasoning cao,
 không dùng mặc định cho task thường."
```

`doc_chinh_sach()` TRA nó. Mặc định khi không tra được là **HẠN CHẾ**
(`nguon=fail_closed`) — và điều đó KHÁC việc chép cứng:

```
chép cứng   = "luật là thế này, bất kể dự án ghi gì"
fail closed = "chưa đọc được luật của dự án này, nên chọn phía không tốn tiền"
              — và bản ghi nói rõ nguồn, nên một dự án thiếu quyết định HIỆN RA
```

Một quyết định **nới lỏng** vẫn được tôn trọng (có bài kiểm): chính sách là
của dự án, không phải của mô-đun. Mâu thuẫn thì giữ HẠN CHẾ.

**Bốn rào phải cùng mở** mới tới được bậc cao cấp: chính sách dự án →
`LyDoLeoThang` tường minh → `GacAstra.xin_phep` (trần song song, trần mỗi
việc, cấm đệ quy, ECO cấm tuyệt đối) → bậc độ khó `RAT_KHO`. Cộng rào TƯƠNG
XỨNG CHI PHÍ chặn một model đắt nhận một lượt thường.

Trạng thái thật hiện nay: `gpt-6-astra` có trong `fabric.json` nhưng **không
runtime nào khai nó trong `supported_models`**, nên không placement nào tồn
tại — "đã chuẩn bị", chưa "đã bật". Bản ghi định tuyến nói đúng điều đó:
`leo thang phan_xu_kien_truc; … ; chính sách dự án qd_0001 — nhưng không
placement nào chạy được gpt-6-astra; đã hạ về bậc thường`.

## 6. Độc lập của Reviewer

Với Reviewer, đa dạng họ model là **rào CỨNG**, không phải điểm thưởng.
`Scheduler.independence_bonus` là một tín hiệu cho điểm — đủ cho một việc
thường, không đủ ở đây: một bản phản biện do CÙNG model viết chỉ là một lần
tự đọc lại.

Vòng MỘT: `exclude_families=(họ của Strategist,)`. Không ai thoả → vòng HAI
bỏ rào, bản ghi mang `doc_lap=False, suy_giam=True`, khối gửi Leader mang
dòng `(!) ĐỘ ĐỘC LẬP SUY GIẢM`, giao diện hiện DEGRADED.

Đo được: Strategist `gemini` → Reviewer `claude`, `doc_lap=True`. Trên một
fabric chỉ còn một họ: `suy_giam=True` + lý do đọc được.

## 7. Ảo hoá ngữ cảnh theo vai

Mỗi vai nhận một gói CÓ TRẦN (Leader 2500 token, Reviewer 3400, Strategist
4200) — **độc lập với kích thước lịch sử dự án**: Fanfic có 8231 sự kiện L0
(số thật) và vẫn nạp trong trần.

Thứ tự nạp theo VAI, không theo một bảng dùng chung: Reviewer cần BẢN CHIẾN
LƯỢC và RÀNG BUỘC trước hết; Strategist cần viên nang và bằng chứng.

`ke_khai()` ghi lại **vai nào đã được cho xem những gì** — đi vào bản ghi
định tuyến và lên API, nên câu hỏi đó trả lời được SAU ĐÓ.

**Dòng báo cắt NÊU TÊN.** Đây là khuyết tật V0.7 lặp lại ở một cửa mới: khi
mục "Tài nguyên agent" bị cắt và dòng cắt chỉ ĐẾM, một lượt đã trả lời "5
Antigravity account" trong khi sổ ghi 8. Khối bị cắt ở đây liệt kê ĐÚNG TÊN
kèm câu "KHÔNG phải giấy phép để đoán". Câu người dùng KHÔNG BAO GIỜ bị cắt.

## 8. Thất bại và thử lại

Năm loại, mỗi loại xử lý KHÁC nhau — gộp chúng thành "hỏng thì thử chỗ khác"
là cách sinh ra đúng cái vòng lặp nhà cung cấp vô tận mà §13 cấm:

| Loại | Xử lý |
|---|---|
| `NANG_LUC` | ĐỊNH TUYẾN LẠI (cùng chỗ sẽ hỏng tiếp) |
| `QUOTA` | ĐỊNH TUYẾN LẠI, loại cả chỗ vừa hỏng |
| `XAC_THUC` | **DỪNG** — không đường tự động nào sửa được, cần người |
| `RUNTIME` | thử lại CÙNG CHỖ đúng MỘT lần, rồi đổi chỗ |
| `VIEC` | **DỪNG** — xem dưới |

`VIEC` = vai đã chạy, đã tiêu một lượt, và trả về thứ không dùng được (hoặc
bất đồng). **Bất đồng ý kiến của model KHÔNG phải lỗi vận chuyển.** Một
Reviewer trả `REJECT` đã làm ĐÚNG việc của nó; định tuyến lại để xin một ý
kiến dễ chịu hơn sẽ luôn tìm được, vì lúc nào cũng còn một model nữa.

Trần là HAI con số: mỗi vai 2 lượt, toàn lượt hội thoại 4 lượt. Thiếu con số
thứ hai thì ba vai cùng quay vòng và cộng lại thành mười lần gọi cho một câu
hỏi.

## 9. Hạn mức: đo được thì ĐO

§7 đòi "If provider API exposes this information: measure it." Antigravity
CÓ lộ ra — `agy --print /usage` trả một bảng phân cách tab, đọc được bằng
máy. Đo thật 2026-09-11:

```
Gemini Models          Weekly Limit Remaining   40%   2026-09-12T05:39:35Z
Gemini Models          Five Hour Limit Remaining 91%  2026-09-11T09:26:01Z
Claude and GPT models  Weekly Limit Remaining   10%   2026-09-14T19:58:56Z
Claude and GPT models  Five Hour Limit Remaining 100% 2026-09-11T11:38:43Z
Remaining credits      0
```

Trước v0.8 `fabric.json` khai hai bể này `source: declared`, nên bộ lập lịch
thấy `remaining_estimate = 1.0` cho một bể THẬT SỰ còn 10% tuần. Không phải
bịa số (nhãn `declared` và `QuotaPool.health` đã chiết khấu), nhưng là một
con số TỆ HƠN con số đo được miễn phí.

**Cửa sổ NHỎ NHẤT thắng**: còn 100% trong năm giờ nhưng 10% trong tuần thì
ràng buộc thật là 10%.

**Chỉ áp cho ĐÚNG tài khoản đã đo.** `agy` báo hạn mức của tài khoản đang
đăng nhập — MỘT, không phải tám. Áp cho cả tám sẽ biến một phép đo thật
thành bảy con số bịa mang nhãn `probed`. `ap_han_muc()` đòi `account_id`
tường minh; có bài kiểm khoá lại.

Hiệu quả đo được: sau khi áp, `health` của bể AG01 tụt 1.00 → 0.10, và định
tuyến chuyển từ AG01 sang AG02. Đó là định tuyến nhận biết hạn mức chạy trên
một phép đo thật, không phải một hằng số.

Mọi thứ khác: `None` + `UNAVAILABLE`, không bao giờ `0`.

### Tài nguyên đo được (2026-09-11, fabric thật)

| Hạng mục | Số |
|---|---|
| Tài khoản Antigravity | **8**, cả 8 đã cấp phát, cả 8 nhận dispatch, **8 hồ sơ xác thực RIÊNG** |
| Tổng khe Antigravity | 10 (AG01 ×3, AG02–AG08 ×1) |
| Runtime khác | `CODEX01` (đã đăng nhập), `OPENCODE01` (v1.18.25), `CLAUDE_LEAD` (`dispatchable=False`) |
| Model / placement | 10 model · **51 placement** |
| Bể quota đọc được | 16 bể Antigravity (`declared`, thành `probed` sau khi đo) |
| Bể **KHÔNG** đọc được | 3 — `codex_chatgpt`, `opencode_zen`, `claude_code` → `quota_con_lai = None` |

**Alibaba / Tencent**: `providers/preset.py` đã có sẵn `alibaba_dashscope` và
`tencent_hunyuan` (nền móng V0.6.1), nhưng sổ provider hiện có **0 provider
ngoài được cấu hình** — nên v0.8 KHÔNG "biểu diễn" chúng. §7 nói "where
already configured"; chúng chưa được. Đường gọi chung
(`BoGoiThat._goi_ngoai`) nhận chúng khi nào có, và trả một thông điệp đọc
được chứ không ném khi chưa có.

## 10. Giao diện

Thêm đúng thứ cần, giữ nguyên ngôn ngữ tối của V0.4:

* ô chọn **ECO / AUTO / STRONG / MAX** ở thanh trên, BỀN (cột `leader.che_do`),
  đồng bộ từ server nên hai tab đang mở thấy cùng một giá trị;
* thẻ **SUY LUẬN** ở cột phải: vai · model/provider · lý do · trạng thái ·
  cờ DEGRADED — đi qua `snapshot()` nên tới giao diện bằng CÙNG nhịp
  WebSocket, không thêm một lần gọi;
* nút ↻ mở bản đầy đủ: năng lực từng model, chính sách cao cấp, hạn mức ĐO
  ĐƯỢC. Phép đo CHẬM nên nó chỉ chạy khi người bấm.

Hiện **mô tả quyết định**, không hiện chuỗi suy nghĩ. Đầu ra thô của
Strategist/Reviewer không lên giao diện — người dùng đọc câu trả lời của
Leader, không đọc biên bản nội bộ.

API: `GET /api/reasoning` (+`refresh=1` để đo hạn mức), `POST
/api/reasoning/mode`. Cả hai sau cổng token + kiểm `Host`, không CORS — ba
bất biến §11 không đổi.

## 11. chatgpt-web (`miuuyy/codex-chatgpt-web`) — ĐÁNH GIÁ: HOÃN

Khảo sát 2026-09-11 (README công khai). Kết luận: **không tích hợp vào
v0.8**, và đây là lối ra mà §14 nêu sẵn ("document and defer it rather than
forcing it into v0.8").

| Hạng mục | Đo được | Ý nghĩa cho Router |
|---|---|---|
| Xác thực | cookie phiên trình duyệt trong hồ sơ Chromium nhúng của launcher | §14 CẤM đưa cookie/phiên vào sổ, log, ký ức, nhắc nhở — nên Router chỉ được gọi qua ống loopback và TUYỆT ĐỐI không chạm hồ sơ |
| API | **không có API tương thích OpenAI** | adapter provider ngoài sẵn có KHÔNG bọc được; phải viết một adapter riêng |
| Bề mặt tích hợp | "loopback listener", cổng 17841 nhắc trong một câu về `dev:chat`; **không có tài liệu endpoint/định dạng request** | không có hợp đồng ổn định để bọc |
| Bản chất | "unofficial browser automation… ChatGPT UI changes can break selectors" | độ tin cậy thấp về CẤU TRÚC, không phải tạm thời |
| Điều khoản | "not affiliated with or endorsed by OpenAI… use only with your own account and in accordance with applicable Terms of Use" | rủi ro điều khoản thuộc về NGƯỜI DÙNG, không phải một quyết định kỹ thuật |
| Giấy phép / độ sống | MIT, 6.4k sao, 316 commit | dự án thật, đang sống |

**Điểm mở rộng đã có sẵn và không cần sửa gì để dùng sau này.** Giao thức
`BoGoi` trong `goi.py` đã là đúng hình dạng §14 mô tả (`invoke` + đường
provider ngoài + hỏng thì trả lỗi rõ chứ không ném), và `BoGoiThat._goi_ngoai`
trả một thông điệp đọc được khi provider chưa bật — có bài kiểm rằng một
provider hỏng KHÔNG làm vỡ Router.

**Điều kiện để xem lại**: (a) có tài liệu endpoint loopback ổn định, hoặc
(b) dự án phơi ra một API tương thích OpenAI. Lúc đó nó vào như một provider
ngoài `status=EXPERIMENTAL`, không nhận dispatch tự động — cùng khuôn provider
ngoài của V0.6.1.

## 12. Nghiệm thu

`python scripts/control_center_v08_acceptance.py --do-han-muc` → **25/25 ĐẠT**
trên fabric thật (11 runtime, 10 model, 51 placement, 8 tài khoản
Antigravity) và ký ức Fanfic thật.

Các vai chạy qua `BoGoiGia` (kịch bản cố định). Đó là chủ ý: thứ v0.8 cần
chứng minh là **quyết định định tuyến**, và mọi quyết định đó nằm trọn ở tầng
`Scheduler` — tầng CỐ Ý tách khỏi thực thi. Gọi model thật cho 6 tình huống ×
4 chế độ là ~20 lượt Antigravity không thêm thông tin nào về định tuyến, và
bể Claude/GPT đang ở 10% hạn mức tuần.

Bài kiểm: `scripts/tests/test_reasoning_v08.py`, **109 bài + 98 subtest**,
cộng 7 bài mới ở `test_control_center_webapi.py` (hai endpoint mới nằm trong
danh sách cưỡng chế token/`Host`).

Smoke giao diện trên **Chrome thật qua CDP**: bộ smoke sẵn có 18/18 (0 lỗi
JS), cộng một lượt riêng cho ô chọn chế độ + thẻ SUY LUẬN, 9/9.

### Ba khuyết tật tự tìm ra trước khi commit

Ghi lại vì cả ba đều là lớp lỗi CÂM — chúng không làm bài kiểm nào đỏ:

1. **`RecursionError` sau ~990 tầng** trong đường hạ cấp của Astra: khi ghim
   một model không placement nào chạy được, hàm gọi lại chính nó với hai cờ
   người-yêu-cầu đã tắt — nhưng `ly_do_leo_thang` vẫn SUY DIỄN được một lý
   do từ đặc trưng của lượt, nên `ghim` được đặt lại mỗi tầng. Sửa: một cờ
   `cho_ghim_cao_cap=False` tường minh.
2. **Chính sách dự án đọc ra nhưng KHÔNG truyền xuống.** `HoiDong.chay()`
   nhận `chinh_sach` rồi chỉ ghi vào báo cáo; tầng định tuyến vẫn thấy
   `None` → mọi lượt rơi vào `fail_closed`, và `qd_0001` chỉ là trang trí.
   Sửa: truyền THEO LƯỢT xuống `chon()` — không gắn vào `self`, vì một
   `BoDinhTuyenVai` dùng chung sẽ áp quyết định của dự án A cho lượt của dự
   án B.
3. **`BenchmarkStore(self.root)`** — tham số vị trí đầu là một ĐƯỜNG DẪN
   TỆP, còn `self.root` là một THƯ MỤC. Nó ném `PermissionError [Errno 13]`,
   `_khoi_hoi_dong` nuốt vào `REASONING_ERROR`, và **hội đồng không bao giờ
   chạy** trong khi 102 bài kiểm khác vẫn xanh — vì mọi bài kiểm đều dựng
   `HoiDong` bằng tay, không đi qua `engine.hoi_dong`. Tìm ra bằng một phép
   kiểm đường dây trên `ControlCenter` thật; nay có lớp `Test14DuongDayEngine`
   khoá lại, và nó khẳng định KHÔNG có `REASONING_ERROR` nào được ghi.

### KHÔNG dựng bản đóng gói cho v0.8

Cố ý. Mỗi bản PyInstaller dựng lại là một **băm mới**, và Smart App Control
quyết định theo từng băm qua đám mây — `dist-v0612` chạy được trong khi
`dist-v061` dựng lại 50 phút sau từ CÙNG mã bị chặn vĩnh viễn (xem
`CLAUDE.md` mục "Đặc thù môi trường máy này"). Đổi một lần xổ số đó lấy một
nhánh tính năng chưa merge là đánh đổi sai. Đường chạy để thử v0.8 là
source-mode: `router-cc-web.cmd`.

## 13. Giới hạn còn lại

1. ~~**Chưa có lượt model THẬT nào của Strategist/Reviewer được đo.**~~
   **ĐÃ ĐÓNG** — xem `docs/reports/REASONING_V08_REAL.md`: bảy lượt model
   thật trên ứng dụng thật + sổ chính tắc + dự án Fanfic thật, rubric
   **37/38 = 0.974**, và 6/6 khẳng định trạng thái được xác minh bằng một
   lần ĐO LẠI độc lập.
2. ~~**`benchmark_profile` vẫn là tiên nghiệm cấu hình.**~~ **CƠ CHẾ ĐÃ
   SỐNG** — lượt vai nay ghi vào `.router/v4/benchmark-reasoning.jsonl` và
   `BoDinhTuyenVai` đọc chính tệp đó. Chưa đủ `MAU_TOI_THIEU = 3` mẫu cho
   cùng `(model, task_type)` nên tiên nghiệm vẫn đang được dùng — đúng thiết
   kế, không phải thiếu sót.
3. **`gpt-6-astra` chưa có placement nào.** Đường leo thang đã kiểm được đầu
   -cuối bằng fabric của bài kiểm, nhưng chưa bật trên fabric thật.
4. **Bộ phân loại là tất định và tiếng Việt/Anh.** Một cách diễn đạt lạ sẽ
   rơi về `do_tin` thấp → không leo thang (phía an toàn), nhưng nó sẽ im
   lặng. Bản ghi `REASONING_SKIPPED` ghi lại mọi lần như vậy.
5. **Chưa đo hạn mức cho AG02–AG08.** `agy` chỉ báo tài khoản đang đăng
   nhập; đo cả tám cần tám lần `switch`, mỗi lần một lượt.

## 14. Bước v0.9 đề xuất

**Đóng vòng phản hồi chất lượng.** Ghi kết quả từng lượt vai vào
`router_v4/history.py` với `task_type=reasoning_strategist|reviewer`, để
`benchmark_quality` chuyển từ tiên nghiệm cấu hình sang lịch sử THỰC ĐO —
đúng cơ chế `Scheduler` đã có sẵn và hiện chưa có dữ liệu. Kèm một phép đo
đầu-cuối có kiểm soát (một câu E thật, một lượt, ghi lại) để đóng giới hạn
số 1.
