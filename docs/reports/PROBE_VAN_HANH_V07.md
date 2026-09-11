# V0.7 — MÔI GIỚI PROBE VẬN HÀNH (đọc production an toàn, không shell)

Khuyết tật chặn đường: một câu hỏi vận hành THẬT của người dùng biến thành
một việc worker, rồi worker chết vì `tool_permission_denied`. Báo cáo này ghi
nguyên nhân đo được, kiến trúc thay thế, và kết quả chạy thật.

---

## 1. Nguyên nhân gốc — lần theo sổ, không phỏng đoán

Toàn bộ chuỗi dưới đây đọc ra từ `control.db` của gốc dữ liệu chính tắc, không
phải dựng lại từ trí nhớ.

| Mốc | Sự việc |
|---|---|
| `06:25:57` | Người dùng gõ: *"Kiểm tra READ-ONLY vì sao từ hôm qua tới giờ tôi không thấy production artifact mới được mirror lên Google Drive."* |
| `06:26:37` | Bộ phân rã (`planner=rule`, **không** phải Leader) dựng **một** việc `fanfic.t2efd-1` |
| | `type=analysis` · `requirements.shell=false` · tài nguyên `READ:FILESYSTEM:.` |
| | Danh sách lệnh cấp cho worker: **đúng hai dòng** `cc_agent_tool.py changes` và `cc_agent_tool.py compile` |
| `06:30:37` | AG03/`claude-sonnet-4-6` → `FAILED`, `failure_reason=tool_permission_denied`, 23,86s, 2 lượt thử |

Nguyên văn stderr của `agy`:

> `no output produced — a tool required the "command" permission that headless
> mode cannot prompt for, so it was auto-denied.`

**Công cụ gây hỏng: `command`** — công cụ shell chung của `agy`. Không phải
`read_file`, không phải `read_url`.

Vì sao worker phải gọi nó: câu hỏi nằm ở **production** (systemd, rclone,
Drive, R2, Appwrite), nhưng việc lại được xếp vào lớp **phân tích kho**. Hai
lệnh trong danh sách cho phép đều thao tác trên kho mã; **không lệnh nào chạm
được tới máy production**, và không thể thêm vào đó một lệnh nào làm được
điều ấy — vì đích không nằm trong kho. Worker chỉ còn một đường: công cụ
`command` chung. Headless không hiện được hộp thoại hỏi quyền nên tự chối, và
lượt kết thúc rỗng.

Đây là **lần thứ tư** cùng một bài học (`command` → `read_file` → `read_url` →
`command`). Lời giải đã được chốt từ V0.6.1 và vẫn đúng: **Router làm phép đọc
an toàn rồi đưa BẰNG CHỨNG CÓ CẤU TRÚC cho worker**; quyền của agent không
đổi, và `--dangerously-skip-permissions` không xuất hiện ở đâu cả.

Ghi chú về bằng chứng: worker không in ra chữ nào trước khi bị chối, và tệp
nhật ký thô `fanfic.t2efd-1-402b4de9.log` không còn trên đĩa. Nên xác định
được **công cụ** (`command`) nhưng **không** xác định được argv chính xác mà
nó định chạy. Nói rõ giới hạn này thay vì dựng lại một dòng lệnh nghe hợp lý.

---

## 2. Kiến trúc thay thế — `scripts/control_center/probe_van_hanh.py`

Một môi giới probe **có kiểu**, không có lối thoát ra shell.

```
MoiGioiProbe.chay("systemd.is_active", don_vi="fanfic-farmer")
        -> KetQuaProbe(op, dich, trang_thai, gia_tri, nguon, do_luc, tuoi, ly_do, bang_chung)
```

### Bốn luật

1. **API công khai không nhận chuỗi lệnh.** Nó nhận TÊN THAO TÁC + tham số.
   `chay("rm …")` không phải một lời gọi hợp lệ mà là `OpKhongHopLe`.
2. **Tham số kiểm theo cấu hình dự án**, không theo câu chữ người dùng: unit
   phải là unit đã khai; đường dẫn phải nằm dưới gốc đã khai (so theo **đoạn**,
   nên `/var/lib/fanfic-farmer-evil` không lọt qua `/var/lib/fanfic-farmer`);
   thuộc tính systemd phải nằm trong bảng — và bảng **không có** `Environment*`
   (thuộc tính đó in thẳng biến môi trường, tức là bí mật).
3. **Lưới thứ hai trên chuỗi lệnh cuối.** `_kiem_chi_doc()` từ chối mọi động
   từ đột biến (`restart`/`rm`/`chmod`/`sudo`/`rclone sync`/`git push`…) và mọi
   ký tự nối/chuyển hướng. Một mẫu lệnh viết sai trong tương lai vẫn bị chặn.
4. **Không leo thang quyền.** Trên farmer thật, `ubuntu` **có** sudo không mật
   khẩu (đo được: `sudo -n true` → rc=0). Gói này vẫn không dùng. Một lớp quan
   sát không được nâng quyền trên máy production; chỗ sửa đúng nằm phía máy chủ
   và được **báo cáo** chứ không tự làm.

### Chín thao tác

| Thao tác | Lệnh dựng ra |
|---|---|
| `systemd.is_active` | `systemctl is-active <unit>` |
| `systemd.show` | `systemctl show <unit> --property=<allowlist> --no-pager` |
| `systemd.journal_tail` | `journalctl -u <unit> --since '<n> <đv> ago' -o short-iso -n <k>` (+ bộ lọc CÓ TÊN) |
| `filesystem.stat` | `stat -c …` |
| `filesystem.list_dir` | `ls -1t <đường> \| head -n <k>` |
| `filesystem.read_text` | `tail -n <k> <đường>` |
| `filesystem.disk_usage` | `df -Pk <đường> \| tail -n 1` |
| `rclone.listremotes` | `rclone --config <conf> listremotes` |
| `rclone.lsjson` | `rclone --config <conf> lsjson --max-depth 1 <remote>:<đường>` |

**Phơi shell tuỳ ý cho worker: KHÔNG.** Không có `command(*)`, `shell(*)`,
`bash(*)`, `powershell(*)` ở bất kỳ đâu trong đường này.

### Nguồn gốc (Phần 8 của đặc tả)

`KetQuaProbe` mang: nguồn (`ssh:<host>`), thao tác, đích, mốc đo, tuổi, mã
thoát, trạng thái sáu bậc của V0.5 (`ACTIVE`/`DEGRADED`/`DOWN`/`UNKNOWN`/
`UNAVAILABLE`/`STALE`), bằng chứng đã lọc bí mật, và lý do khi không đo được.
`UNAVAILABLE` **không bao giờ** mang giá trị — cùng luật với
`observability/model.py`.

Một sửa nhỏ nhưng thật: bộ lọc bí mật dùng `memory.bi_mat.loc` chứ **không**
dùng `packet.redact`, vì bộ của `packet` **không có** khoá AWS `AKIA…`/`ASIA…`
— đúng hình dạng dễ gặp nhất trong log của một máy EC2. Bài kiểm `TestLocBiMat`
bắt được khoảng trống này.

---

## 3. Probe nào DÙNG ĐƯỢC trên Fanfic, probe nào KHÔNG

Đo thật ngày 2026-09-11 trên `13.212.224.218` bằng tài khoản quan sát `ubuntu`.

### Dùng được

| Năng lực | Bằng chứng |
|---|---|
| Trạng thái service | `active` |
| MainPID / NRestarts / mốc khởi động | `350714` · `0` · `Tue 2026-09-08 15:55:31 UTC` |
| Nhật ký journald | đọc được (7 ngày: 2.803 dòng) |
| Siêu dữ liệu tệp | `stat` chạy được **kể cả khi nội dung bị từ chối** |
| Liệt kê thư mục | `/var/lib/fanfic-farmer` → `status.json rclone.conf _verify.py _diag.py _plan.py work` |
| Dung lượng đĩa | `/` dùng 21% |
| Nhịp tim suy ra | `status.json` được ghi lại đều (mtime tiến theo mỗi lần đo) |

### KHÔNG dùng được — và chính xác vì sao

| Năng lực | Lý do ĐO ĐƯỢC |
|---|---|
| Nội dung `status.json` (bộ đếm round/harvest/archive) | tệp `600 fanfic:fanfic`; `ubuntu` không thuộc nhóm `fanfic` → `Permission denied` |
| Liệt kê Drive qua rclone | `rclone.conf` cũng `600 fanfic:fanfic` → `Failed to load config file … permission denied` |
| Hàng đợi Appwrite | chưa có adapter đọc; truy vấn đòi API key production |
| Artifact R2 | chưa có adapter đọc; đòi token production |

**Adapter còn thiếu, nói thẳng:** thứ chặn đường không phải thiếu mã, mà là
**quyền tệp phía máy chủ**. Để trả lời trọn vẹn câu hỏi Drive, cần một trong
hai, và cả hai đều là **quyết định của người vận hành**:

* cho `status.json` (và một bản chỉ-đọc của cấu hình rclone) đọc được theo
  nhóm, rồi thêm tài khoản quan sát vào nhóm đó; **hoặc**
* một endpoint `--status` chỉ-đọc do chính farmer phát ra, không cần đọc tệp
  thô.

Router **không tự làm** thay đổi đó: nó là một đột biến trên máy production.

---

## 4. Kết quả chẩn đoán THẬT cho câu hỏi Drive

```
Phân loại: F — Chưa đủ bằng chứng để kết luận.
```

Đo được, và đây là những khẳng định có chống lưng:

* `fanfic-farmer` = **active**, MainPID **350714**, **NRestarts = 0**, chạy
  liên tục từ **2026-09-08 15:55:31 UTC** (~2 ngày 8 giờ) — tiến trình **không**
  chết, **không** bị đập lại.
* `status.json` vẫn **đang được ghi** (nhịp tim tiến theo mỗi lần đo) — vòng
  lặp farmer còn sống.
* **Không một dòng nhật ký nào** về `archive|rclone|drive|mirror|upload` trong
  cửa sổ đã soi (48h). `grep` trả mã 1 = *không có dòng khớp*, và đó là một
  phép đo THẬT chứ không phải một lần đo hỏng.
* `work/` chỉ có `farmer.lock` — không có việc nào đang dở.

Không đo được: bộ đếm archive/round, hàng đợi Appwrite, artifact R2, listing
Drive. Thiếu đúng những thứ đó thì **không phân biệt được A/B/C/D/E**, nên câu
trả lời đúng là **F**, kèm danh sách cụ thể thứ còn thiếu.

Nói cách khác: *farmer còn sống và vẫn thở, nhưng không có dấu vết nào của
hoạt động archive, và những bộ đếm cho biết vì sao thì tài khoản quan sát
không đọc được.* Chọn bừa "A — chưa có việc nào đạt chuẩn" nghe rất hợp lý và
có thể đúng — nhưng nó sẽ là một câu **bịa**, nên hệ thống không nói thế.

---

## 5. Định tuyến ở Leader

`leader.la_cau_hoi_van_hanh()` (tất định, không LLM) tách hai lớp:

* câu **trạng thái đơn** ("production farmer đang chạy không?") → đi đường
  quan sát sống V0.5 như cũ, không gom 11 probe;
* câu **chẩn đoán** ("vì sao Drive 24h chưa có file mới?") → Router gom bằng
  chứng trước, gắn `LUAT_VAN_HANH`, và nếu có uỷ thác worker thì **đính chính
  khối bằng chứng đó vào hợp đồng** (`_kem_probe_vao_hd`) — cùng khuôn với
  `_kem_nhat_ky_git` và `_kem_web_vao_hd`.

`LUAT_VAN_HANH` nói rõ với Leader: bằng chứng vận hành là bậc thẩm quyền cao
nhất cho câu "bây giờ thế nào"; `UNAVAILABLE` **không** phải `DOWN`; chỉ chọn
A–E khi có số chống lưng; và **không** đề xuất thao tác đột biến.

---

## 6. Nghiệm thu THẬT trên ứng dụng đang chạy

`scripts/control_center_v07_probe_acceptance.py`, chạy trên app source-mode,
gốc dữ liệu chính tắc.

### Hỏi lại ĐÚNG câu đã làm hỏng việc

| Kiểm | Kết quả |
|---|---|
| Việc chết vì `tool_permission_denied` | **0** (trước: 1, `fanfic.t2efd-1`) |
| Việc mới sinh ra | **0** — Leader trả lời thẳng từ bằng chứng, 124s |
| Câu trả lời dựa trên số đo | ĐẠT — dẫn `ssh:13.212.224.218` + mốc đo |
| Nói thẳng phần chưa đo được | ĐẠT |
| Nêu phân loại A–F | ĐẠT |
| Router ghi `PROBE_AUDIT` vào sổ | ĐẠT — `F (11/12 quan sát đo được)` |

### Worker headless THẬT (Phần 9)

| Kiểm | Kết quả |
|---|---|
| Việc được tạo | `fanfic.tc093-1` |
| Trạng thái | **DONE**, 18,85s |
| Chạy ở đâu | **AG02 · antigravity · gemini-3.1-pro-low** — *không* phải Codex |
| Hợp đồng mang bằng chứng | ĐẠT (khối 10,7 KB) |
| Cần công cụ `command`? | **KHÔNG** |
| `--dangerously-skip-permissions`? | **KHÔNG** |
| Rò bí mật | **không** |
| Đột biến production | **0** |

Worker tự kết luận **F**, trùng với phân loại của Router, và nêu đúng 5 phát
hiện có thật — trong đó có cả hai chỗ tắc:

> *"File status.json được cập nhật gần đây (mtime cách 37s) nhưng không có
> quyền đọc nội dung (mode=600, owner=fanfic:fanfic)…"*
> *"Không có quyền đọc rclone.conf (permission denied) nên không kiểm tra
> được trạng thái Drive/rclone."*

### Một khuyết tật khác bị bắt trong lúc nghiệm thu

Lần chạy đầu, việc worker `fanfic.t78ce-1` **BLOCKED** với
`codex_security_shaped_refusal`. Truy ra: `pool/adapters.py` từ chối gói việc
"mang hình dạng bảo mật" trước khi gửi Codex, nhưng lý do đó nằm trong
`KHONG_THU_LAI`, nên việc **chết tại chỗ** dù thông báo hứa "định tuyến sang
worker khác".

Nặng hơn thế: danh sách từ khoá gồm `"quyền"`, mà **lời nhắc công cụ tiêu
chuẩn của MỌI việc** đều chứa chữ đó — nên gần như mọi việc xếp vào Codex đều
chết như vậy. Đây là khuyết tật CÓ SẴN, không do lớp probe sinh ra.

Sửa: kiểm hình dạng **trước khi xếp chỗ** và thêm runtime Codex vào
`tranh_runtime` (cơ chế đã có sẵn của toả đa agent) — tránh là ưu tiên, không
phải rào, nên khi không còn chỗ nào khác thì `decide()` vẫn rơi về như cũ.
Sau khi sửa, đúng việc đó chạy ở AG02 và DONE.

Một bài học nhỏ đi kèm: bản đầu của phép kiểm này dùng `json.dumps` trong
`engine.py` — tệp **không import `json`** — và `except Exception` đã **nuốt
gọn** `NameError`, tắt lặng lẽ cả tính năng. Bài kiểm bắt được; nay dùng
`str(dict)` và `except` hẹp lại.

**Rủi ro còn lại, nói rõ:** `tranh_runtime` là một **ưu tiên, không phải một
rào** (`sessions.decide` cố ý như vậy, để toả đa agent vẫn chạy được khi bể
cạn chỗ). Nghĩa là nếu MỌI runtime khác đều bận, một việc mang hình dạng bảo
mật vẫn có thể rơi vào Codex và chết ở `BLOCKED` như cũ. Sửa triệt để là làm
cho `codex_security_shaped_refusal` **định tuyến lại thật** thay vì nằm trong
`KHONG_THU_LAI` — việc đó chạm bộ lập lịch nên **cố ý để ngoài** phạm vi lần
này, và ghi lại ở đây để không bị quên.

## 7. Bài kiểm

`scripts/tests/test_probe_van_hanh_v07.py` — **48 bài, 82 subtest**, không bài
nào chạm mạng (lớp vận chuyển bị thay bằng bản giả có ghi lại lệnh, nên một
lệnh đột biến lọt lưới sẽ bị bắt tại bài kiểm chứ không phải trên production).

Phủ đúng những gì đặc tả đòi: danh sách thao tác cho phép · từ chối lệnh tuỳ ý
· từ chối lệnh đột biến · tên service hợp lệ · đường dẫn hợp lệ · rclone chỉ
đọc · provider không khả dụng · lỗi đã lọc bí mật · nguồn gốc + độ tươi ·
worker headless nhận bằng chứng mà không cần công cụ `command` · không đột
biến production · phân loại A–F.

Ba bài bắt được lỗi thật khi viết:

* `TestLocBiMat` — `packet.redact` không lọc khoá AWS.
* `test_goi_bang_chung_co_JSON_nguon_goc_va_bi_chan_do_dai` — cắt thẳng chuỗi
  JSON đã tuần tự hoá tạo ra **JSON gãy**; nay cắt theo NỘI DUNG rồi mới tuần
  tự hoá, nên khối gửi cho worker luôn parse được.
* `test_hop_dong_bao_mat_thi_TRANH_codex` — bắt được `NameError` bị
  `except Exception` nuốt mất (xem mục 6).
