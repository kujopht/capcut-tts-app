# Smart App Control chặn bản EXE dựng lại — chẩn đoán đo được và chiến lược ký (V0.6.1, 2026-09-10)

Phạm vi: bản đóng gói Router Control Center (`scripts/build_desktop_exe.py`,
PyInstaller onedir). Không đụng logic lập lịch, không đụng production. Không
tắt Smart App Control, không sửa chính sách/registry, không cài gốc tự ký.

## 1. Hiện tượng

`dist-v061\Router Control Center\Router Control Center.exe` dựng lại sạch lúc
19:05 bị Windows chặn ở cả ba cách mở (PowerShell trực tiếp, `Start-Process`,
bấm đôi Explorer): *"Smart App Control blocked an app that may be unsafe"*,
*"we could not verify its publisher"*. Các bản trước (`dist-v04/05/06`, `dist-v0611`,
`dist-v0612`) mở được.

## 2. Bằng chứng đo được (chỉ đọc)

Trạng thái máy: `HKLM\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`
(Smart App Control **đang cưỡng chế**). Nhật ký `Microsoft-Windows-CodeIntegrity/Operational`:

| Lúc (UTC) | Sự kiện | Tệp | Tiến trình mở |
|---|---|---|---|
| 09-09 17:23:42 → 17:27:11 | 3033 + 3077 ×5 | `dist-v04\…\Router Control Center.exe` | `python.exe` (bộ nghiệm thu) — sau đó bản này CHẠY ĐƯỢC |
| 09-10 19:05:25, :29, :32 | 3033 + 3077 ×3 | `dist-v061\…` | `powershell.exe` |
| 09-10 19:10:51, :56 | 3033 + 3077 ×2 | `dist-v061\…` | `explorer.exe` |
| 09-10 19:11:18 | 3033 + 3077 | `dist-v061\…` | `powershell.exe` |
| 09-10 ~20:45 (thí nghiệm §2.2) | 3077 | `dist-v061\…` | `ShellExecuteW` trả 5 = ACCESS_DENIED |

Mọi sự kiện cùng một Policy ID `{0283ac0f-fff1-49ae-ada1-8a933130cad6}` — chính
sách Smart App Control. **Không** có sự kiện nào cho `dist-v05/06/0611/0612`: chúng
được cho chạy ngay lần đầu.

### 2.1 So sánh sáu bản (`python scripts/kiem_ban_dong_goi.py dist-v04 … dist-v061 --so-sanh`)

| Bản | sha256 (16 đầu) | cỡ | bootloader (tới hết section) | `.rsrc` | overlay | chữ ký | MOTW | EA `$KERNEL.PURGE.ESBCACHE` | mở được lúc đo |
|---|---|---|---|---|---|---|---|---|---|
| dist-v04 | `38fcfbd971763241` | 11 400 471 | `6360ce3b…` | `eae4611c…` | 11 054 871 | không | không | **có** (87 byte) | có |
| dist-v05 | `d63a639833ae2acd` | 11 442 149 | `41c906ae…` | `eae4611c…` | 11 096 549 | không | không | **có** | có |
| dist-v06 | `6e049cce490593e1` | 11 533 341 | `2cdd503e…` | `eae4611c…` | 11 187 741 | không | không | **có** | có (thí nghiệm) |
| dist-v0611 | `3cdb5438fbe27f5f` | 11 653 545 | `97a71c7a…` | `eae4611c…` | 11 307 945 | không | không | **có** | có |
| dist-v0612 | `5e6d0ab7b86de202` | 11 665 222 | `88682cc6…` | `eae4611c…` | 11 319 622 | không | không | **có** | **có** (thí nghiệm) |
| dist-v061 (bị chặn) | `aa5ffbea9a38be5e` | 11 665 222 | `1543628a…` | `eae4611c…` | 11 319 622 | không | không | **KHÔNG có EA nào** | **không** (thí nghiệm) |

Đọc bảng:

* **Chữ ký Authenticode: cả sáu bản đều KHÔNG KÝ** (`TRUST_E_NOSIGNATURE`,
  0x800B0100). Không có bản nào "ký được" rồi bản này "mất chữ ký".
* **Mark-of-the-Web: không bản nào có `Zone.Identifier`** — đều sinh cục bộ.
  MOTW không phải yếu tố.
* **Công cụ dựng giống nhau**: cả sáu bản dùng cùng PyInstaller 6.22.2, cùng
  bootloader `…\PyInstaller\bootloader\Windows-64bit-intel\runw.exe`
  (`build/desktop-*/…/EXE-00.toc`), cùng subsystem GUI, cùng `.rsrc`
  (`eae4611c…` — manifest/icon/version **y hệt**). Phần "bootloader" khác nhau
  chỉ vì PyInstaller ghi **mốc dựng** vào `TimeDateStamp` của đầu PE
  (`mốc dựng` = đúng mtime của tệp), và overlay (CArchive/PYZ) khác theo mã.
  `dist-v0612` và `dist-v061` cùng cỡ byte, cùng commit `7b9e377` — khác nhau
  đúng ở mốc dựng và băm.
* **Điểm khác duy nhất có ý nghĩa**: năm bản chạy được đều mang EA nhân
  `$KERNEL.PURGE.ESBCACHE` (87 byte, cùng nội dung); bản bị chặn **không có EA**.
  EA này do Code Integrity ghi lên tệp khi đám mây trả lời **thuận**, để các lần
  mở sau không phải hỏi lại. Bản bị chặn chưa bao giờ nhận được câu trả lời thuận.

### 2.2 Thí nghiệm mở có kiểm soát (cùng cách người dùng: `ShellExecuteW "open"`, `--root` thư mục tạm)

| Bản | Kết quả | Sự kiện 3077 mới |
|---|---|---|
| dist-v061 (dựng 19:05) | `ShellExecuteW` trả **5 (ACCESS_DENIED)**, không có tiến trình | **1** |
| dist-v0612 (dựng 18:15, cùng mã) | chạy, pid 21492, đóng nhẹ bằng WM_CLOSE | 0 |
| dist-v06 | chạy, pid 16652 | 0 |
| `pythonw.exe -m scripts.control_center.desktop` (từ mã nguồn) | chạy, cửa sổ lên sau 4 s | 0 |

## 3. Nguyên nhân gốc — chính xác

Smart App Control là một chính sách App Control (WDAC) có bật uỷ quyền theo
**Intelligent Security Graph**. Tài liệu Microsoft (trích nguyên văn):

> "App Control will check the file's reputation by sending its hash and signing
> information to the cloud. If the ISG reports that the file has a 'known good'
> reputation, then the file will be allowed to run. Otherwise, it will be blocked
> by App Control." — *Authorize reputable apps with the ISG*

> "This cloud-based AI is based on trillions of signals … and processed every
> 24 hours. As a result, the decision from the cloud can change."

> "Smart App Control selectively allows apps and binaries to run only if they're
> likely to be safe. … If the app intelligence service is unable to make a
> prediction, then Smart App Control will still allow an app to run if it is
> signed with a certificate issued by a certificate authority (CA) within the
> Trusted Root Program. Malware, Potentially Unwanted Apps (PUA), and unknown,
> unsigned code are blocked by default." — *Smart App Control (Windows apps)*

Ghép với bằng chứng §2:

1. Bản Router **không ký**, nên SAC chỉ còn một đường: đám mây phải trả
   "known good" cho **đúng băm tệp**.
2. **Mỗi lần dựng PyInstaller là một băm mới** (mốc dựng trong đầu PE + overlay),
   nên mỗi bản là **một lần tra danh tiếng mới**, không thừa hưởng gì từ bản trước.
3. Với `dist-v05/06/0611/0612`, đám mây trả thuận ngay → Code Integrity ghi EA
   `$KERNEL.PURGE.ESBCACHE` → chạy ổn từ đó. Với `dist-v04` (09-09) đám mây
   chưa trả thuận trong ~4 phút (5 lần chặn) rồi mới thuận → chạy. Với
   `dist-v061` (09-10 19:05) đám mây trả **"không rõ"** — chặn ở 7 lần mở trải
   trên 100 phút, không EA.
4. Vì vậy **"bản cũ chạy, bản mới bị chặn" không phải do cách mở, không do MOTW,
   không do PyInstaller/bootloader/manifest đổi** (tất cả giống nhau, §2.1), mà
   do quyết định theo băm của đám mây ISG cho một tệp không ký — một quyết định
   heuristic, có thể đổi theo ngày, và ta không điều khiển được. Với bản không
   ký, "chạy được" là **xổ số**, không phải thuộc tính của bản dựng.

Điều KHÔNG được làm và vì sao: EA `$KERNEL.PURGE.ESBCACHE` do nhân quản lý —
tự ghi nó là cách nhân mã độc lách App Control (tài liệu Microsoft nói thẳng),
không có đường hợp lệ từ user-mode và cũng không nên có.

## 4. Chữ ký tự ký (self-signed) có thoả Smart App Control không? — KHÔNG

Quy tắc của SAC là "signed with a certificate issued by a CA within the
**Microsoft Trusted Root Program**" (§3). Chứng chỉ tự ký không do CA nào trong
chương trình đó cấp. Cài gốc tự ký vào `Trusted Root Certification Authorities`
của máy chỉ đổi kết quả `WinVerifyTrust`/hộp thoại SmartScreen của **máy đó**;
Code Integrity/SAC đánh giá theo bộ gốc của chương trình Microsoft và danh tiếng
ISG, **không tra kho gốc cục bộ**. Kết luận: **tự ký KHÔNG mở được cửa SAC**, và
việc cài một gốc tự ký vào kho tin cậy là một thay đổi bảo mật hệ thống (mọi
thứ ký bằng khoá đó trở thành "tin cậy") — không thực hiện, không khuyến nghị.
Vì lý do đó, vỏ ký `scripts/ky_ban_dong_goi.py` **không có** nhánh tự ký/PFX.

Ta không "đo" điều này bằng cách cài gốc rồi mở thử: (a) đó là nới rào an
toàn; (b) phép đo vô nghĩa vì quy tắc đã được Microsoft công bố tường minh.

## 5. Chiến lược ký bền vững

### 5.1 Phát hành (release): chứng chỉ ký mã của CA trong Trusted Root Program

Bất kỳ CA công cộng nào trong chương trình (DigiCert, Sectigo, GlobalSign,
Certum/Asseco, SSL.com, Entrust…). Từ 6/2023 CA/B Forum bắt buộc khoá riêng nằm
trên **token phần cứng hoặc HSM đám mây** — không có PFX mềm để "export" nữa.
Hai đường:

| Đường | Điều kiện | Chi phí (kiểm lại trước khi mua) | Ghi chú SAC |
|---|---|---|---|
| **Microsoft Artifact Signing** (trước là Trusted Signing) | Thuê bao Azure **trả tiền** (không nhận free/trial); xác minh danh tính; **Public Trust chỉ cho tổ chức ở US/CA/EU/UK/AU/NZ/JP/KR/SG/CH/NO/IL và cá nhân ở US/CA** | Trang giá hiện yêu cầu báo giá; khi ra mắt 2024 công bố Basic ≈ 9,99 USD/tháng (5 000 chữ ký), Premium ≈ 99,99 USD/tháng | Chuỗi tới "Microsoft ID Verified Code Signing PCA 2021" — thuộc chương trình, khoá trong HSM dịch vụ, chứng chỉ sống 3 ngày, ký bằng `signtool /dlib` |
| **Chứng chỉ OV (tổ chức) / IV (cá nhân)** của CA thương mại | Xác minh doanh nghiệp (OV) hoặc giấy tờ tuỳ thân (IV); nhận token USB hoặc dùng ký đám mây của CA | Từ vài chục EUR/năm (Certum Open Source cho cá nhân) tới vài trăm USD/năm (OV DigiCert/Sectigo) + token | Thoả quy tắc SAC ngay khi ký hợp lệ; SmartScreen (khác SAC) có thể vẫn cảnh báo cho tệp tải về tới khi có danh tiếng |

Với người vận hành **ở Việt Nam**, Artifact Signing Public Trust **hiện không
mở** (danh sách vùng ở trên, nguồn: Quickstart Artifact Signing 2026-05) → đường
thực tế là **chứng chỉ IV/OV của CA thương mại**. Không cần bất kỳ thông tin
xác thực nào nằm trong kho: chứng chỉ ở kho `CurrentUser\My`/token, kho mã chỉ
biết **vân tay SHA1**.

Quy trình ký một bản (đã có sẵn vỏ, không giữ bí mật):

```
python scripts/ky_ban_dong_goi.py dist-v061 --thumbprint <sha1 40 hex> --dry-run   # xem lệnh
python scripts/ky_ban_dong_goi.py dist-v061 --thumbprint <sha1 40 hex>             # ký + tự kiểm
python scripts/kiem_ban_dong_goi.py dist-v061 --ghi                                # báo cáo
```

Cần `signtool.exe` (Windows SDK → "Windows SDK Signing Tools for Desktop Apps",
miễn phí) — **máy này chưa cài**.

### 5.2 Phát triển (dev): không có chữ ký cục bộ nào thoả SAC

* **Không** có "chứng chỉ dev tự ký" hợp lệ với SAC (§4). Nói thẳng, không giả vờ.
* Nếu đã có chứng chỉ CA (5.1): ký **mọi** bản dev định bấm đôi — với HSM/đám
  mây thì đó là một lệnh, và chữ ký không có phí theo lần (trừ Artifact Signing
  tính theo hạn mức).
* Chưa có chứng chỉ: đường **chắc chắn** là chạy vỏ desktop từ mã nguồn bằng
  launcher **đã được tin** — `pythonw.exe` của Python Software Foundation (ký
  hợp lệ, chuỗi CA công cộng, và đã chạy trên máy này hàng ngày). Đo §2.2: cửa
  sổ lên sau 4 s, **0** sự kiện Code Integrity. Bấm đôi: `router-cc-desktop.cmd`
  (có từ V0.2 — nay là đường dev khuyến nghị; `pythonw.exe` trong venv cũng là
  launcher PSF ký). Bản EXE PyInstaller dev vẫn dựng được, nhưng phải đọc
  `KIEM_DONG_GOI.txt` và coi "mở được" là kết quả xổ số.

### 5.3 Điều ta KHÔNG làm

Tắt Smart App Control (không thể bật lại nếu không cài lại Windows); triển
khai chính sách App Control tuỳ biến (SAC tự tắt khi có chính sách tuỳ biến);
sửa registry/`CI\Policy`; cài gốc tự ký; tự ghi EA; `--dangerously-…` nào.

## 6. Launcher/bootstrapper đã được tin để mở payload theo phiên bản — đánh giá

| Phương án | Có dùng được không | Vì sao |
|---|---|---|
| **A. `pythonw.exe` (PSF ký) + mã nguồn** — `router-cc-desktop.cmd` | **CÓ, đã đo** (§2.2) | Mọi PE thi hành đều do PSF/Microsoft ký hoặc là DLL wheel PyPI đã có danh tiếng; mã Python không thuộc phạm vi WDAC. Không dựng lại EXE nào. |
| **B. Python nhúng (embeddable) + thư mục payload theo phiên bản** (bản phát hành không ký) | Có, chưa dựng | Cùng lý do A nhưng tự chứa (≈ 15 MB Python + wheels). `pythonw.exe`/`python312.dll`/`*.pyd` của PSF đều ký; 18 DLL wheel không ký (xem §7) y hệt hôm nay. Đổi mã = đổi payload, launcher không đổi. |
| **C. Dùng lại EXE PyInstaller cũ đã được tin cho payload mới** | **KHÔNG** | Bootloader và kho CArchive/PYZ nằm trong **một** tệp; đổi payload là đổi băm → mất EA, tra lại từ đầu. |
| **D. Stub EXE riêng, byte không bao giờ đổi, gọi B** | Chỉ khi đã có chữ ký | Không ký thì stub vẫn phải qua xổ số **một lần**, sau đó ổn nếu byte không đổi; kém B (B không có PE lạ nào cả). |

Đánh giá an toàn: A/B **không nới** gì — SAC vẫn kiểm mọi EXE/DLL; mã Python
chưa bao giờ được SAC kiểm ở bản PyInstaller (PYZ nằm sau bootloader, ngoài
phạm vi Code Integrity). Điều đổi là bỏ đi một PE **không ký, đổi băm mỗi lần
dựng** — chính cái tệp làm ta phụ thuộc xổ số. Rủi ro còn lại giống hôm nay:
ai ghi được vào thư mục payload thì đổi được hành vi (ACL thư mục).

## 7. Báo cáo/metadata sau khi đóng gói (mới)

`scripts/kiem_ban_dong_goi.py` (chỉ đọc; `build_desktop_exe.py` tự gọi ở cuối
và ghi `<dist>/KIEM_DONG_GOI.txt`) báo: **SHA256**; cỡ, mốc dựng PE,
subsystem; băm bootloader/`.rsrc`/overlay; **trạng thái chữ ký** theo
`WinVerifyTrust` (không ký / hợp lệ / gốc không tin cậy / hết hạn / hỏng);
**người ký + nhà phát hành + vân tay**; **MOTW** (`Zone.Identifier`); **dự đoán
tương thích Smart App Control** (`cao` Microsoft ký · `kha` CA công cộng ·
`chan` tự ký/hỏng · `khong_dam_bao` không ký). `--dll` quét `_internal`:

```
dist-v0612/_internal: Microsoft Corporation 141 · Python Software Foundation 25 ·
(không ký) 18 · Microsoft Windows Software Compatibility Publisher 2
không ký: _cffi_backend, clr_loader ClrLoader.dll (x2), cryptography _rust.pyd,
PIL *.pyd (7), pydantic_core, …
```

18 DLL/PYD không ký là tệp wheel PyPI **y hệt** bản phân phối rộng → ISG biết
chúng ("known good" theo mức phổ biến) và chúng đã chạy ở mọi bản; chúng KHÔNG
liên quan tới ca chặn này (sự kiện 3077 chỉ nêu tệp EXE). Ký EXE không đổi
điều đó — nhưng nếu một wheel đổi phiên bản, DLL mới cũng qua đám mây như mọi
máy khác trên thế giới, không riêng gì ta.

Bộ kiểm: `scripts/tests/test_kiem_ban_dong_goi.py` (12) — oracle là
`python.exe` (PSF ký), bootloader PyInstaller (không ký), tệp tạm có
`Zone.Identifier`, bảng quyết định SAC, vỏ ký không có nhánh PFX/tự ký.

## 8. Bảo toàn bản cũ

`dist-v04 38fcfbd9…`, `dist-v05 d63a6398…`, `dist-v06 6e049cce…`, `dist-v0611
3cdb5438…`, `dist-v0612 5e6d0ab7…` — **không đổi**, đối chiếu đúng
`BAN_TOT_*.txt`. Đừng di chuyển/sao chép lại các thư mục này: EA
`$KERNEL.PURGE.ESBCACHE` nằm **trên tệp** đó. `dist-v061` (bị chặn) để nguyên
làm bằng chứng; muốn có `dist-v061` mở được bằng cùng mã `7b9e377`, sao chép
`dist-v0612` sang (cùng băm `5e6d0ab7…` — băm này đã được đám mây trả thuận)
rồi kiểm bằng `kiem_ban_dong_goi` + mở thử; nếu đám mây đổi ý, bản đó cũng
không còn chắc — chỉ chữ ký CA mới chắc.

## 9. Chi phí / thông tin xác thực cần có

* Chứng chỉ CA (IV cá nhân hoặc OV tổ chức): giấy tờ danh tính hoặc đăng ký
  doanh nghiệp; token USB do CA gửi hoặc dịch vụ ký đám mây của CA; phí năm
  (kiểm giá hiện hành); `signtool` từ Windows SDK. **Không** có thứ nào trong đó
  vào kho git, sổ SQLite, log hay prompt — chỉ vân tay SHA1.
* Artifact Signing: thuê bao Azure trả tiền + xác minh danh tính — **không mở
  cho Việt Nam** ở thời điểm tra (2026-05 Quickstart).
* Không tốn gì: đường A (§6) với Python đã cài.

## 10. Trả lời gọn

| Câu hỏi | Trả lời |
|---|---|
| Nguyên nhân gốc | EXE không ký; SAC chỉ tra băm ở đám mây ISG; băm của `dist-v061` bị trả "không rõ" → chặn; mỗi bản dựng là băm mới |
| Vì sao bản cũ chạy, bản mới bị chặn | Bản cũ được đám mây trả thuận (có EA `$KERNEL.PURGE.ESBCACHE`), bản mới thì không — cùng công cụ, cùng mã, khác băm và khác câu trả lời heuristic của đám mây |
| So sánh chữ ký | 6/6 bản KHÔNG ký, 0/6 MOTW, `.rsrc` giống nhau, bootloader `runw.exe` cùng PyInstaller 6.22.2 |
| Tự ký có thoả SAC? | **Không.** SAC chỉ tin CA trong Microsoft Trusted Root Program, không tra kho gốc cục bộ |
| Giải pháp dev | `router-cc-desktop.cmd` (`pythonw.exe` PSF ký chạy vỏ desktop từ mã nguồn — đo 0 sự kiện); EXE dev không ký = xổ số, luôn đọc `KIEM_DONG_GOI.txt` |
| Giải pháp phát hành | Ký bằng chứng chỉ CA công cộng (IV/OV) qua `ky_ban_dong_goi.py --thumbprint`; Artifact Signing nếu ở vùng được hỗ trợ |
| Chi phí/credential | Phí chứng chỉ theo năm + token/HSM; giấy tờ danh tính; không lưu bí mật trong kho |
| EXE mở được hiện tại | `dist-v0612\Router Control Center\Router Control Center.exe` (sha `5e6d0ab7…`, đo chạy 20:47) và `router-cc-desktop.cmd` (từ mã nguồn) |

| Hạng mục | Trước khi sửa | Sau khi sửa |
|---|---|---|
| Biết vì sao một bản bị chặn | không (không có báo cáo chữ ký/băm/MOTW) | `KIEM_DONG_GOI.txt` sau mỗi lần dựng, `kiem_ban_dong_goi.py --so-sanh --dll` |
| Đường chạy dev chắc chắn dưới SAC | không (chỉ EXE không ký) | `router-cc-desktop.cmd` — launcher PSF ký, 0 sự kiện Code Integrity |
| Ký phát hành | không có quy trình | `ky_ban_dong_goi.py` (signtool, vân tay/Artifact Signing, không PFX) + tài liệu chiến lược |
| Bản cũ | nguyên | nguyên (băm đối chiếu đúng) |
