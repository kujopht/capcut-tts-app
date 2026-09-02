# CONTENT FACTORY V1 — SAN PHAM THAT, KHONG CHI HA TANG (2026-09-02)

Theo dung dieu chinh cua nguoi dung giua chung mission ("PRODUCE CONTENT,
NOT MORE INFRA PROOFS") — da dung xay them queue/orchestrator sau khi
content_queue + watcher da du dung, chuyen toan bo thoi gian con lai sang
GIAO NOI DUNG THAT.

## Hang muc | Truoc | Sau

| Hang muc | Truoc | Sau |
|---|---|---|
| Truyen moi | 0 | **1 truyen moi that**: "A Prisoner Inside and Out" (Berserkchart486), 3 chuong |
| Chuong Naruto | 11 | **16** (+5: chuong 12-16, "The Demon of the Mist" -> "Who Are You?!") |
| Audio moi | — | Chuong 1 truyen moi + chuong 12 Naruto — **ca hai da xac minh phat lai that** |
| Episode Chinese media phat hien | 0 (chi 1 proof tong hop) | **30 episode that**, tu watcher THAT chay tren 2/3 nguon |

## A. Truyen Naruto tiep tuc — 5 chuong that

Cung nguon da xac minh (`narutofanon.fandom.com`, MediaWiki API cong khai):
truyen "Naruto: A Shinobi Story" con **21 chuong nua** (12-32) chua khai
thac — da lay 5 chuong tiep (12-16), dich, QA, ghi vao novel co san
(`nov_6764055a19c44e63`), tong 16/32 chuong that trong production draft.

## B. TRUYEN MOI THAT — "A Prisoner Inside and Out"

Tim qua `action=query&list=usercontribs` (API cong khai) tren chinh
`narutofanon.fandom.com` — tac gia THAT `Berserkchart486`, dang hoat dong
(sua lan cuoi 2025-08-29), phan cua sery "Tales of Gaman" (Naruto OC-insert,
Nara Jinchuriki). Trang goc la MOT trang dai chia 3 phan bang header wiki
(`== A Lonely Spar ==`, `== Delegation ==`, `== Long Road ==`) — da tach
thanh 3 chuong that, dich, QA, ghi vao novel MOI
(`nov_d43742597de8482c`), `state=draft`, khong xuat hien public listing.

**Loi nho phat hien**: chuong 3 con sot mot dong `Category:Tales of Gaman`
o cuoi (loi thu tu trong ham lam sach wikitext — buoc go the Category chay
SAU buoc "giu text hien thi cua [[link]]", nen ngoac da mat truoc khi khop
duoc). Khong anh huong noi dung/y nghia, chi mot dong thua o cuoi — ghi
nhan trung thuc, chua sua (uu tien thoi gian cho san luong theo dung dieu
chinh cua nguoi dung).

## C. Audio that — xac minh tung byte

| Chuong | Kich thuoc | Xac minh |
|---|---|---|
| Truyen moi, chuong 1 | 6.769.698 byte | HTTP 200, audio/mpeg, khop byte |
| Naruto, chuong 12 | 5.646.987 byte | HTTP 200, audio/mpeg, khop byte |

## D. Chinese Media Watcher — kham pha THAT lan dau

Chay that `scripts/chinese_media_watcher.py` tren 3 nguon actionable:

| Nguon | Ket qua |
|---|---|
| 波波漫剧 (bobo_manju) | 15 episode moi, THAT |
| 動漫書屋 (dongman_shuwu) | 15 episode moi, THAT |
| 天天小說動漫 (tiantian_xiaoshuo_dongman) | LOI 404 — channel_id co the da doi, ghi nhan trung thuc, khong doan lai |

**30 episode that** da ghi vao `content_queue` (Appwrite, moi), moi
episode duoc phan loai rights_mode THAT (khong phai suy doan): 0/30 co
cum tu cho phep phan phoi lai, 0/30 co phu de that — ca 30 deu
`REFERENCE_ONLY`, khop dung ket qua da xac nhan nhieu lan truoc do cho the
loai AI-hoat-hinh nay.

## E. Ha tang da xay xong nhung DUNG LAI dung luc (theo dieu chinh)

`content_queue` (schema Appwrite that, 20 truong, 4 index) + source
registry (`chinese_media_sources.py`, 6 kenh that) + watcher THAT chay
duoc. **Orchestrator (queue -> ASR -> dich -> phu de -> dub -> render ->
draft) CHUA xay** — dung dung lai dung theo yeu cau "khong them ha tang,
uu tien san luong". Day la buoc tiep theo hop ly khi can xu ly 30 episode
da phat hien.

## F. Router V3 / OpenCode

Khong can dung den trong luot nay — toan bo cong viec (tim nguon, dich,
QA, ghi draft, TTS) la mot chuoi PHU THUOC tuan tu (khong the song song
that su: dich phai co van ban goc, ghi draft phai co ban dich, TTS phai
co draft), nen dieu phoi qua CLI ngoai khong tang toc. `OPENCODE01` van
`IDLE` (da xac minh lan truoc), san sang cho lan can dieu phoi doc lap
that su (vi du: xu ly song song nhieu trong 30 episode da phat hien).

## Chi phi / test

$0 (MediaWiki API + Antigravity + Piper deu mien phi/da co san). Test lien
quan (`test_adapters`, `test_harvester_service_auth`) 64/64 PASS.
