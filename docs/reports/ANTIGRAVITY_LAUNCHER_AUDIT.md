# Audit launcher đa-tài-khoản Antigravity (2026-09-03)

Kiểm toán độc lập bộ khởi chạy `agy_profile.py` / `run-acc` do người vận
hành tạo, **trước khi** cho Router dùng. Kết luận trước đó của tôi (cô lập
`HOME`/`USERPROFILE` **không** cô lập Windows Credential Manager) vẫn đúng —
nhưng nó **không** kết luận được chuyện quan trọng hơn, và chuyện đó nay đã
được đo.

## 1. Cơ chế thật

```
run-acc <n>:
  1. agy_profile.py switch accN   -> CredWriteW('gemini:antigravity', accN.bin)
  2. set USERPROFILE = HOME = C:\Users\nguye\.agy-sessions\accN
  3. agy.exe ...
```

**MỘT** khoá credential dùng chung, ghi đè trước mỗi lần khởi động.
`.agy-sessions/accN` chỉ cô lập chat/cache/SQLite — **không** cô lập danh
tính. Nên câu hỏi quyết định không phải "có cô lập không" mà là:

> Tiến trình `agy` đọc credential **một lần lúc khởi động**, hay **đọc lại**
> khoá dùng chung trong khi chạy?

## 2. Kết quả đo

| # | Phép đo | Kết quả |
|---|---|---|
| 1 | Xoá hẳn credential khỏi Windows rồi bảo 2 tiến trình đang chạy làm việc | **Cả hai vẫn làm được** → token nằm trong bộ nhớ tiến trình, **KHÔNG đọc lại** |
| 2 | Khởi động acc1..acc8, giữ cả 8 sống, cho cả 8 gọi model **sau khi** slot bị ghi đè 7 lần | **8/8 trả lời đúng**, 0 trôi danh tính |
| 3 | Khởi động lại acc2 trong khi acc1 đang chạy | acc1 **không** bị ảnh hưởng |
| 4 | So dấu hiệu danh tính trong `cli.log` từng phiên, trước/sau | Không phiên nào nhận danh tính của phiên khác |
| 5 | `agy` có ghi ngược token vào slot không | **CÓ, khi token cần làm mới.** Lặp lại được: acc1 (token ~3.5h) khởi động → slot **không còn khớp** `acc1.bin`; acc8 (token mới) → slot không đổi |

**KẾT LUẬN CƠ CHẾ: ĐẠT.** Danh tính được ghim lúc khởi động và ổn định. 8
danh tính đồng thời là thật, không phải suy ra từ vài lần khởi động tuần tự.

## 3. Hệ quả của phép đo #5 — vì sao Router có khoá

Vì bất kỳ tiến trình đang chạy nào cũng có thể làm mới token rồi CredWrite
vào slot **dùng chung**, chuỗi `switch → spawn` **phải nguyên tử**. Nếu hai
luồng đan nhau:

```
switch(acc1) ; switch(acc2) ; spawn ; spawn   ->  CẢ HAI đọc acc2
```

hai worker mang **cùng một danh tính** trong khi sổ đăng ký tưởng là hai tài
khoản — một lần hỏng **im lặng**, đúng loại tệ nhất. `KhoaLauncher`
(`scripts/router_v4/antigravity_launcher.py`) là khoá **liên tiến trình**
(tệp khoá, `O_CREAT|O_EXCL`, có TTL thu hồi khoá bỏ hoang), giữ **cho tới
khi** tiến trình con phát ra `init` — đúng bằng cửa sổ nguy hiểm, không hơn.

Hai hệ quả vận hành khác của #5, không nghiêm trọng nhưng có thật:

- `saved_profiles/accN.bin` **đi lệch** so với token sống sau một lần làm
  mới (đã xảy ra với `acc1.bin`).
- `acc list` phát hiện "đang dùng" bằng cách **so khớp blob**, nên sau một
  lần làm mới nó sẽ báo "không khớp profile nào".

## 4. Audit bảo mật

| Hạng mục | Kết quả |
|---|---|
| Nội dung `accN.bin` | **JSON THUẦN**: `{"auth_method": <8 ký tự>, "token": {…}}` — token OAuth Google **dùng lại được**, **không mã hoá** |
| Vì sao đáng lo | `CredRead` trả blob **đã giải mã cho người dùng hiện tại**. Ghi ra tệp là **bóc lớp bảo vệ DPAPI** — 8 credential sống nằm dạng thô trên đĩa |
| Nằm trong kho git? | **KHÔNG** (`C:\Users\nguye\agy-profiles` không thuộc kho nào) → không commit được |
| Có bị log ra không? | Không thấy đường nào in token; `switch()` của Router cắt đầu ra launcher còn 200 ký tự |
| Launcher có bật bypass quyền nguy hiểm không? | **KHÔNG** — `run-acc.cmd` chỉ chuyển tiếp tham số; không có `--dangerously-skip-permissions` |
| **ACL** | **VẤN ĐỀ** — xem dưới |

### 4.1 VẤN ĐỀ ACL (cần người vận hành xử lý)

```
C:\Users\nguye\agy-profiles   Kujopht\CodexSandboxUsers:(OI)(CI)(RX)
```

ACE này được đặt **tường minh** trên thư mục `agy-profiles` (không phải kế
thừa từ `C:\Users\nguye`, vốn **không** cấp quyền cho nhóm đó), và lan xuống
từng tệp `.bin` dưới dạng `(I)(RX)`.

`CodexSandboxUsers` gồm `CodexSandboxOffline` và `CodexSandboxOnline` — các
tài khoản sandbox của **Codex CLI**.

**Nghĩa là: bất cứ thứ gì chạy trong sandbox Codex đều ĐỌC ĐƯỢC cả 8 token
OAuth Google ở dạng thuần.** Bao gồm mã do chính Codex sinh ra, và bao gồm
cả trường hợp Codex bị chèn chỉ thị qua nội dung nó đọc.

**Khắc phục đề xuất** (người vận hành chạy, tôi không tự đổi ACL vì đó là
thay đổi quyền ngoài phạm vi kho):

```powershell
icacls "C:\Users\nguye\agy-profiles" /remove:g "Kujopht\CodexSandboxUsers" /T
icacls "C:\Users\nguye\agy-profiles" /inheritance:r ^
       /grant:r "%USERNAME%:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
```

Cân nhắc thêm: giữ `.bin` **đã mã hoá** bằng DPAPI (`CryptProtectData`) thay
vì blob thuần, để một lần đọc tệp không đủ để dùng lại token.

## 5. Phát hiện: 8 profile nhưng chỉ **7 tài khoản Google**

So dấu hiệu danh tính ghi trong `cli.log` từng phiên (đối chiếu bằng **băm**,
không in email):

```
acc1 và acc8  ->  CÙNG một danh tính Google
acc2..acc7    ->  6 danh tính riêng biệt
```

8 tệp `.bin` có 8 băm khác nhau (hai lần cấp OAuth khác nhau), nhưng **cùng
một tài khoản**. Không phải trôi danh tính — mỗi `cli.log` chỉ chứa **đúng
một** danh tính, nên đây là chuyện xảy ra **lúc đăng ký**, không phải lúc chạy.

Nguyên nhân gốc nằm trong launcher: `login_flow` gọi `save_profile(name)` để
lưu **bất kể** credential nào đang có trong slot sau khi `agy` thoát, **không
kiểm** xem nó có thuộc tài khoản vừa đăng nhập hay không. Nếu người dùng
không hoàn tất một lần đăng nhập **mới**, bước lưu sẽ chụp lại tài khoản cũ
mà không báo gì.

**Đề xuất:** trước khi lưu, `save_profile` nên so blob mới với các profile đã
có và **cảnh báo** khi trùng danh tính. Muốn 8 tài khoản riêng thì chạy
`acc relogin 8` và chọn một tài khoản Google **khác**.

## 6. Tích hợp Router

- `scripts/router_v4/antigravity_launcher.py` — bọc launcher **CÓ SẴN**.
  Router chạy `agy_profile.py switch accN` qua subprocess và **không bao giờ**
  tự CredRead/CredWrite. Có bài kiểm quét mã để giữ điều đó
  (`TestRouterKhongTuChamCredential`).
- Ánh xạ **cố định** `AG01→acc1 … AG08→acc8`; mỗi khe một `auth_profile`
  riêng (`agy-launcher:accN`), nên bất biến "một runtime = một tài khoản"
  của `Fabric.validate()` vẫn được kiểm bằng máy.
- Khe chỉ được coi là **cấp phát** khi `saved_profiles/accN.bin` **có thật
  trên đĩa** — bằng chứng là tệp, không phải cấu hình.
- **KHÔNG** `--dangerously-skip-permissions` (kiểm trên cây cú pháp).

## 7. Bằng chứng lập lịch đa tài khoản của Router

`python scripts/router_v4_multiaccount_proof.py --tasks 8`

```
Runtime AG đăng ký + dò sức khoẻ thật : 8/8
Việc chạy đồng thời                   : 8/8 thành công
Tài khoản KHÁC NHAU được chọn         : 8  (AG01..AG08)
Thời gian tường                       : 49.2s
Trôi danh tính                        : không
```

Hai lỗi lập lịch **thật** bị lộ ra ở lần chạy đầu (đã sửa, có bài kiểm):

1. 4 việc song song **cùng** gọi `decide()` trước khi việc nào kịp
   `mark_started` → cả 4 thấy AG01 rảnh 0/3 → **cả 4 dồn vào AG01** dù có 8
   tài khoản. Nay `decide → giữ khe → mark_started` là **nguyên tử**.
2. Khi hết khe, retry chỉ loại **placement** chứ không loại **runtime**, nên
   nó nhảy sang `AG01/<model khác>` — vẫn đúng tài khoản vừa hết khe. Nay
   loại cả runtime.

## 8. Giới hạn còn lại (nói rõ, không làm tròn)

- Hành vi **lúc làm mới token** chỉ quan sát được ở thời điểm khởi động.
  Tôi **không** chứng minh được điều gì xảy ra nếu một tiến trình sống qua
  hạn token (~1 giờ) **trong khi** slot đang giữ blob của tài khoản khác.
  Bằng chứng gián tiếp nghiêng về an toàn (tiến trình không đọc lại slot), và
  làm mới dùng refresh token **trong bộ nhớ**. Cần một lần chạy dài > 1 giờ
  mới kết luận được.
- **7** tài khoản Google riêng, không phải 8 (acc1 ≡ acc8).
- Tất cả 8 chia sẻ **một** khoá credential; cơ chế an toàn **chỉ vì** có
  khoá `switch → spawn`. Bỏ khoá đó đi là mở lại lỗi im lặng.
