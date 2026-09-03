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

> ⚠️ **MỤC NÀY ĐÃ LẠC HẬU — xem mục "ĐỐI CHIẾU LẠI acc1/acc8" ở cuối tệp.**
> Kết luận dưới đây ĐÚNG ở thời điểm đo (2026-09-03, trước 10:25:21Z) và
> **sai từ 12:06:22Z** trở đi, khi lần `acc relogin 8` thật sự hạ cánh. Đo
> lại ngày 2026-09-03 cho thấy **8/8 danh tính khác nhau**. Giữ nguyên văn ở
> đây vì phần *nguyên nhân gốc* bên dưới vẫn đúng và vẫn là lý do sự cố xảy
> ra ngay từ đầu.

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
- ~~**7** tài khoản Google riêng, không phải 8 (acc1 ≡ acc8).~~
  **ĐÃ LẠC HẬU** — đo lại 2026-09-03 sau khi `acc relogin 8` hạ cánh:
  **8/8 danh tính khác nhau**. Xem mục "ĐỐI CHIẾU LẠI acc1/acc8" ở cuối tệp.
- Tất cả 8 chia sẻ **một** khoá credential; cơ chế an toàn **chỉ vì** có
  khoá `switch → spawn`. Bỏ khoá đó đi là mở lại lỗi im lặng.

---

# ĐÓNG HỒ SƠ BẢO MẬT (2026-09-03, sau khắc phục của người vận hành)

## A. ACL — ĐẠT, nhưng lần khắc phục đầu đã làm hỏng launcher

Trạng thái cuối, đã xác minh:

```
C:\Users\nguye\agy-profiles          SYSTEM:(OI)(CI)(F)   KUJOPHT\nguye:(OI)(CI)(F)
...\saved_profiles\accN.bin          SYSTEM:(I)(F)        KUJOPHT\nguye:(I)(F)
icacls ... /T | grep -c CodexSandbox  ->  0
```

`CodexSandboxUsers` **không còn quyền nào** trên toàn bộ cây. Vấn đề đã đóng.

**NHƯNG:** lần khắc phục đầu tiên (`/inheritance:r` áp dụng đệ quy) đã xoá
ACE kế thừa của **mọi tệp** mà không cấp ACE tường minh nào — để lại DACL
**rỗng**. Hệ quả đo được: cả 8 `.bin` **và** chính `agy_profile.py` trở nên
**không đọc được kể cả với chủ sở hữu**:

```
acc1..acc8       : PermissionError
agy_profile.py   : [Errno 13] Permission denied
```

Tức là **toàn bộ launcher đa-tài-khoản đã ngừng hoạt động**. Đã khôi phục
bằng cách cho tệp con kế thừa lại ACL sạch của thư mục cha, rồi bảo vệ lại
thư mục cha (KHÔNG cấp lại gì cho Codex):

```powershell
icacls "C:\Users\nguye\agy-profiles" /reset /T
icacls "C:\Users\nguye\agy-profiles" /inheritance:r ^
       /grant:r "nguye:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F"
```

**Bài học:** `icacls /inheritance:r /T` gỡ quyền kế thừa của con mà không
thay bằng gì. Muốn siết một cây thì siết ở **thư mục** rồi để con **kế thừa**,
đừng phá kế thừa ở từng tệp.

## B. Danh tính riêng biệt — CHƯA ĐẠT: vẫn 7, không phải 8

`acc8.bin` **giống hệt từng byte** so với trước khi báo là đã relogin:

```
profile  bam TRUOC      bam GIO        doi?
acc1     e291e7274e73   e291e7274e73   khong
...
acc8     b20d2ca4264c   b20d2ca4264c   khong      <== KHONG he duoc ghi lai
```

Và dấu hiệu danh tính trong `cli.log` từng phiên vẫn cho `acc1 == acc8`
(băm `0e3bf022f7d3`).

**Nguyên nhân đã xác định:** lệnh `acc relogin 8` được chạy **trong lúc ACL
đang hỏng**, nên Python còn không mở được `agy_profile.py`
(`[Errno 13] Permission denied`) — lệnh **không làm gì cả** và thất bại im
lặng.

Không thể rút định danh tài khoản từ chính tệp profile: nội dung `token` chỉ
có `access_token`, `expiry`, `refresh_token`, `token_type` — **không có
`id_token`, không có `email`, không có `sub`**. Nên cách duy nhất để biết một
profile thuộc tài khoản nào là **dùng nó** và đọc dấu hiệu mà phiên tự ghi.

**Việc cần người vận hành:** ACL giờ đã đúng, hãy chạy lại

```
acc relogin 8
```

và chọn một tài khoản Google **khác**. Sau đó xác minh lại bằng
`scripts/tests/test_router_v4_launcher.py` cộng phép so dấu hiệu phiên.

## C. Mã hoá profile tại chỗ — ĐÃ LÀM

Thiết kế **hẹp nhất**, tương thích ngược:

| Thành phần | Vai trò |
|---|---|
| `scripts/router_v4/profile_crypto.py` | DPAPI phạm vi NGƯỜI DÙNG + magic header `AGYP1\0`; `doc_blob()` tự nhận định dạng; `ghi_blob()` ghi **nguyên tử** qua `os.replace` |
| `scripts/migrate_agy_profiles_dpapi.py` | `--check` / `--apply` / `--rollback`; sao lưu trước, vá launcher **idempotent**, xác minh **vòng tròn từng tệp** ngay sau khi ghi |
| vá trong `agy_profile.py` | thêm `read_profile_blob`/`write_profile_blob` **tự chứa** (chỉ stdlib) và đổi đúng **3** chỗ đọc/ghi/so khớp |

**Tương thích ngược là bắt buộc:** hàm đọc nhìn magic header; không có thì
trả nguyên văn. Nên tệp cũ vẫn chạy, trạng thái nửa-di-trú vẫn chạy, và hoàn
tác chỉ là đặt lại tệp cũ.

Kết quả áp dụng — 8/8, mỗi tệp được xác minh vòng tròn ngay sau khi ghi:

```
acc1..acc8: THUAN (500-503 byte) -> DA MA HOA (732 byte), vong tron OK
```

Chỉ **tài khoản Windows này** giải mã được. Một tài khoản khác — kể cả
`CodexSandbox*` — dù đọc được byte cũng **không dùng được**: khoá nằm trong
dữ liệu bảo vệ của hồ sơ người dùng, không nằm trong tệp. Đây là lớp phòng
thủ thứ hai, độc lập với ACL — đúng thứ đã thiếu khi ACL bị đặt sai.

**Bản lưu dạng thuần đã được XOÁ AN TOÀN** (ghi đè byte ngẫu nhiên rồi xoá)
sau khi di trú được chứng minh — giữ 8 token thuần trong thư mục sao lưu sẽ
vô hiệu hoá toàn bộ việc mã hoá. Bản lưu `agy_profile.py` (không phải bí mật)
được giữ lại cho đường hoàn tác của phần mã.

## D. Bằng chứng 8 tài khoản đồng thời SAU khi mã hoá

Chạy qua **đúng đường của launcher** (`agy_profile.py switch accN`), không tự
CredWrite:

| Phép đo | Kết quả |
|---|---|
| `acc list` (đi qua đường giải mã để so khớp) | 8/8 liệt kê đúng |
| `switch acc3` (đi qua đường giải mã) | ĐẠT |
| 8 tiến trình khởi động lần lượt, giữ cả 8 sống | **8/8** |
| Cả 8 gọi model sau khi slot bị ghi đè 7 lần | **8/8 trả lời đúng** |
| Trôi danh tính | **không** |
| Lập lịch cấp Router (`router_v4_multiaccount_proof.py --tasks 8`) | **8/8 việc trên 8 runtime KHÁC NHAU**, 179.7s |

Ghi chú trung thực về thời gian: 179.7s so với 49.2s ở lần chạy trước khi có
khoá. Nguyên nhân là **khoá `switch → spawn`** nay tuần tự hoá 8 lần khởi
động nguội (~5–12s mỗi lần) — đó là **cái giá đúng** của việc chặn lỗi hai
worker cùng một danh tính. Không phải hồi quy hiệu năng cần sửa.

## E. Kiểm thử

`522` bài kiểm router ĐẠT, gồm 15 bài mới cho mã hoá profile
(vòng tròn, bản mã không chứa bản rõ, tệp thuần vẫn đọc được, nửa-di-trú,
ghi nguyên tử, giải mã hỏng phải NÉM, entropy sai không lọt) và 18 bài
launcher (khoá loại trừ lẫn nhau 8 luồng, thu hồi khoá bỏ hoang, Router
không tự chạm credential, cấm cờ nguy hiểm — kiểm trên cây cú pháp).

## F. Còn lại

- **`acc relogin 8` cần chạy lại** (ACL đã đúng) → mới đạt 8 tài khoản riêng.
- Hành vi **lúc làm mới token** quá hạn ~1 giờ vẫn chưa chứng minh được;
  cần một lần chạy dài > 1 giờ.
- Cả 8 vẫn chia sẻ **một** khoá credential; an toàn **chỉ vì** có khoá
  `switch → spawn`. Bỏ khoá đó là mở lại lỗi im lặng.

---

# NHẬT KÝ XÁC MINH acc8 (đóng phiên Router)

Mục này tồn tại vì việc "đã relogin acc8" đã được báo **hai lần** và cả hai
lần **không hề xảy ra trên đĩa**. Ghi lại bằng chứng để phiên sau không phải
điều tra lại từ đầu.

| Lần | Báo cáo | Bằng chứng kiểm | Kết quả |
|---|---|---|---|
| 1 | "đã relogin acc8" | `acc8.bin` giống hệt từng byte; `cli.log` acc8 vẫn mang danh tính của acc1 | **KHÔNG xảy ra** — nguyên nhân: ACL đang hỏng, Python không mở được `agy_profile.py` |
| 2 | "đã tạo lại/relogin acc8 bằng tài khoản Google khác" | ba nguồn độc lập cùng nói không: (a) băm BẢN RÕ `acc8.bin` vẫn `b20d2ca4264c`; (b) mtime thư mục `saved_profiles` vẫn `15:22:56` = đúng lúc di trú DPAPI, **chưa profile nào được ghi kể từ đó**; (c) `cli.log` acc8 vẫn chỉ có danh tính `0e3bf022f7d3` = của acc1 | **KHÔNG xảy ra** |

Không có tệp `.tmp` sót lại, nên cũng không phải "ghi hỏng giữa đường".

## Cái bẫy khiến việc này lặp lại

Đọc `login_flow` trong `agy_profile.py`:

```python
def login_flow(name, force=False):
    if os.path.exists(prof_path) and not force:
        # CHỈ mở agy với profile CŨ rồi return — KHÔNG đăng nhập lại
        subprocess.run([run-acc.cmd, num]); return
    delete_current_credential()
    subprocess.run(["agy.exe"], env=env)   # TƯƠNG TÁC
    if get_current_credential(): save_profile(name)
```

và bộ điều phối lệnh:

```
acc 8        -> login_flow('8', force=False)   # early return, KHÔNG relogin
acc login 8  -> login_flow('8', force=False)   # early return, KHÔNG relogin
acc relogin 8 -> login_flow('8', force=True)   # DUY NHẤT đường relogin thật
```

Ba điều kiện **đều** phải đúng, nếu thiếu một thì không có gì thay đổi và
**không có thông báo lỗi nào**:

1. Phải gõ đúng `acc relogin 8` — `acc 8` và `acc login 8` chỉ mở lại
   profile cũ.
2. Trong trình duyệt phải chọn một tài khoản Google **KHÁC**.
3. Phải **thoát agy cho đúng** (`/exit` hoặc Ctrl+D) — `save_profile` chỉ
   chạy **sau khi** `agy.exe` kết thúc. Đóng cửa sổ/Ctrl+C thì token mới
   không bao giờ được lưu.

**Giả thuyết CHƯA kiểm chứng, nói rõ là giả thuyết:** `.agy-sessions/acc8`
vẫn giữ trạng thái phiên của lần đăng nhập bằng tài khoản acc1. Nếu `agy`
dùng lại thứ gì trong đó để tự xác thực, nó có thể quay về **đúng tài khoản
cũ** dù đã xoá credential. Nếu bước (1)–(3) làm đúng mà acc8 vẫn trùng, hãy
đổi tên `.agy-sessions/acc8` sang `.agy-sessions/acc8.old` rồi relogin để
`agy` bắt đầu với phiên trắng.

## Khuyến nghị đã nêu, vẫn chưa làm

`save_profile` nên **so blob mới với các profile đã lưu và CẢNH BÁO khi
trùng danh tính**. Nếu có, nó đã bắt được cả hai lần thất bại ngay tại chỗ
thay vì để chúng lọt qua im lặng rồi phát hiện ba lần sau. Tôi cố ý **không**
tự thêm ở lần đóng phiên này (phạm vi là *chỉ xác minh*).

## Trạng thái các hạng mục khác — ĐẠT

| Hạng mục | Kết quả |
|---|---|
| 8 runtime đăng ký + dò sức khoẻ thật | 8/8 |
| 8 tiến trình cùng sống, mỗi cái làm một việc thật qua đường launcher | 8/8 `PONG` |
| Trôi danh tính | **không** |
| ACL với `CodexSandboxUsers` | **0 ACE** toàn cây; chỉ `SYSTEM` + `nguye` |
| 8 profile mã hoá DPAPI | 8/8 header `AGYP1`, giải mã OK |
| Token dạng thuần còn sót trên đĩa | **0** (quét toàn cây `agy-profiles`) |
| Control Room chiếu runtime thật | 11/11 khớp fabric 1:1, 8/8 khe AG hiện ra, **0** worker giả |
| Kiểm thử | 522 Router + 25 Control Room, tất cả ĐẠT |

**Danh tính Google riêng biệt: 7/8.** Đây là hạng mục DUY NHẤT chưa đạt, và
nó cần một hành động tương tác của người vận hành — không thể tự động hoá mà
không có credential của họ.

---

# ĐỐI CHIẾU LẠI acc1/acc8 (2026-09-03, sau xác minh thủ công của người vận hành)

Người vận hành báo: `acc login 8` và `acc login 1` **hiện** xác thực thành hai
tài khoản Google KHÁC NHAU. Đối chiếu lại bằng máy, chỉ dùng **băm** — không
in email, không in token.

## Kết quả: 8/8 danh tính KHÁC NHAU

| Khe | acc | dấu vân tay danh tính (sha256[:12]) | dấu vân tay blob `.bin` |
|---|---|---|---|
| AG01 | acc1 | `0e3bf022f7d3` | `f57dd6abf11f` |
| AG02 | acc2 | `5b6457dc41be` | `1850c36f707f` |
| AG03 | acc3 | `ee27930c1951` | `23379575a0fe` |
| AG04 | acc4 | `db4a5d5511b6` | `9be68db8ab39` |
| AG05 | acc5 | `bdc334d102dc` | `a7364ddff8d6` |
| AG06 | acc6 | `a3a960f5d6c0` | `f23d73e399b3` |
| AG07 | acc7 | `7c342c37b5f5` | `d91b490a131a` |
| AG08 | acc8 | `218b93efc5a7` | `29a0b1efe502` |

`acc1 ∩ acc8 = ∅`. Không một cặp nào trùng, kể cả theo bộ đo CŨ. Cả 8 blob
cũng khác nhau.

## Nguyên nhân kết luận cũ: **hồ sơ acc8 CŨ ở thời điểm đo**

Không phải lỗi của bộ đo về mặt số học — là chuyện **thời điểm**:

| Mốc (UTC) | Việc |
|---|---|
| trước 10:25:21Z | đo danh tính: acc8 còn mang danh tính của acc1 |
| **10:25:21Z** | commit `1aab01b` ghi *"relogin has not landed (2nd time)"* |
| **12:06:22Z** | `acc8.bin` **được ghi lại** — lần relogin THẬT SỰ hạ cánh |
| 2026-09-03 | đo lại (mục này): **8/8 khác nhau** |

Kết luận cũ **đúng vào lúc nó được ghi** và **sai 1h41m sau đó**. Không ai đo
lại, nên nó nằm lại trong báo cáo và bị mang sang cả brief nhiệm vụ.

Vì sao acc8 từng mang danh tính acc1 ngay từ đầu: đúng như mục 5 đã chỉ ra —
`login_flow` gọi `save_profile(name)` lưu **bất kể** credential nào đang có
trong slot sau khi `agy` thoát, **không kiểm** xem một lần đăng nhập MỚI có
hoàn tất hay không. Chẩn đoán đó vẫn đúng; nó giải thích *nguồn gốc*, còn
mục này ghi lại *đã khắc phục xong*.

## Điểm yếu thứ hai của bộ đo cũ (đã vá bằng bài kiểm)

`dau_hieu(acc)` lấy **HỢP TẤT CẢ** email tìm thấy trong
`.agy-sessions/<acc>/.gemini/antigravity-cli/cli.log`. `cli.log` là log **ghi
thêm**, nên một cái hợp như vậy trả lời câu *"tài khoản này TỪNG là ai"*, chứ
không phải *"HIỆN GIỜ là ai"*. Với dữ liệu hiện tại hai câu trùng nhau (mỗi
log chỉ còn đúng một danh tính), nhưng nó là một cái bẫy đang chờ.

Đã thêm `antigravity_launcher.danh_tinh_uu_tien()` — thuần, không đọc tệp,
không gọi mạng, **chỉ nhận dấu vân tay đã băm** nên không thể làm lộ email:

```
bằng chứng từ runtime ĐÃ XÁC THỰC  >  blob đã lưu, KHI blob cũ hơn
blob đã lưu                        >  bằng chứng live, KHI blob mới hơn
bằng điểm                          ->  ưu tiên live
```

Sáu bài kiểm trong `TestUuTienBangChungDanhTinh`
(`scripts/tests/test_router_v4_launcher.py`), trong đó có một bài **tái hiện
đúng các mốc thời gian của sự cố này**, nên một blob cũ không thể lấn át bằng
chứng mạnh hơn từ một runtime đang xác thực được nữa.

## Trạng thái AG08

**KHÔNG còn bị coi là trùng/không khả dụng.** Cả 8 khe AG01..AG08 là 8 runtime
riêng biệt với 8 `auth_profile` riêng, và điều đó vẫn được kiểm bằng máy:

- `Fabric.validate()` — bất biến "một runtime = một tài khoản"
- `test_moi_runtime_AG_la_mot_TAI_KHOAN_rieng` — 8 khe phải là 8 hồ sơ
- `test_khong_khe_nao_dung_chung_acc` — không khe nào dùng chung `accN`
- `scripts/control_room_projection_proof.py` — Control Room chiếu **8/8** khe
  AG từ trạng thái runtime thật, không có worker giả

Lưu ý cách đọc đúng: Control Room **chưa bao giờ** đóng cứng "AG08 offline".
Nó chiếu trạng thái fabric, và khe chỉ được coi là cấp phát khi
`saved_profiles/accN.bin` **có thật trên đĩa** (xem mục 6). Phân loại
"AG08 không khả dụng" là một ghi chú **của người vận hành trong tài liệu**,
không phải một trạng thái trong mã — nên việc bỏ nó đi chỉ cần sửa tài liệu,
không cần sửa mã.
