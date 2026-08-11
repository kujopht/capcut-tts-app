/*
 * TANG XA HOI cua giao dien: bang tin, bai dang, thich, binh luan, thong bao,
 * theo doi, bao cao, va hai man kiem duyet.
 *
 * Bo nay giu BON dieu, moi cai tung bi vi pham o dau do trong lich su du an
 * hoac trong chinh phien nay:
 *
 *   1. MAY CHU la nguon su that — khong hang so nao duoc chep tay, khong co
 *      `user_id` nao di trong body.
 *   2. Khong N+1 moi: chuong chi hoi CON SO, binh luan chi tai khi mo.
 *   3. Tiep can khong phai trang tri: `aria-pressed` co that, tablist co dieu
 *      huong mui ten, hop thoai quan ly tieu diem.
 *   4. Nhung dieu KHONG duoc xay ra: bao cao khong tu go noi dung, khoa doi
 *      tuong khong chua email, hai khoi binh luan khong hien cung luc.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

/**
 * Bo chu thich truoc khi khang dinh mot thu KHONG co mat.
 *
 * Da vap dung mot lan trong phien nay o Phase 0: khoi CSS cua nhan nav co chu
 * thich giai thich vi sao KHONG dung `background-clip` — va bai test quet ca
 * khoi nen bat trung loi giai thich. O day y het: chu thich cua cai chuong ke
 * ve `setInterval` de noi vi sao khong dung no.
 */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const api = () => read("../src/lib/api.ts");
const feed = () => read("../src/app/community/page.tsx");
const postCard = () => read("../src/components/PostCard.tsx");
const composer = () => read("../src/components/PostComposer.tsx");
const comments = () => read("../src/components/CommentThread.tsx");
const bell = () => read("../src/components/NotificationBell.tsx");
const followBtn = () => read("../src/components/FollowButton.tsx");
const reportDlg = () => read("../src/components/ReportDialog.tsx");
const tbPage = () => read("../src/app/notifications/page.tsx");
const postPage = () => read("../src/app/posts/[postId]/page.tsx");
const tabs = () => read("../src/app/u/[username]/ProfileTabs.tsx");
const adminReports = () => read("../src/app/admin/reports/page.tsx");
const adminPosts = () => read("../src/app/admin/posts/page.tsx");
const css = () => read("../src/app/globals.css");

/* ===================================================== lop API va hop dong */

test("moi ham xa hoi deu co, va khong ham nao nhan user_id trong body", () => {
  const a = api();
  for (const fn of ["followUser:", "unfollowUser:", "followStory:",
                    "unfollowStory:", "feed:", "userPosts:", "createPost:",
                    "editPost:", "deletePost:", "like:", "unlike:",
                    "comments:", "createComment:", "replies:", "editComment:",
                    "deleteComment:", "notifications:", "unreadCount:",
                    "markRead:", "markAllRead:", "report:", "accountSocial:"]) {
    assert.ok(a.includes(fn), `mất ${fn}`);
  }
  /*
    AI la nguoi goi luon lay tu TOKEN. Mot body co `user_id` la mot route ai
    cung dong vai duoc — backend co the van kiem, nhung frontend gui no len la
    moi mot nguoi doc nham rang no co y nghia.
  */
  const xaHoi = a.slice(a.indexOf("export const social"));
  assert.ok(!/body: JSON\.stringify\(\{[^}]*user_id/.test(xaHoi),
    "không được gửi user_id trong body — người gọi lấy từ token");
});

test("kieu Post cong khai KHONG co image_key hay removed_by", () => {
  const a = api();
  const khoi = a.slice(a.indexOf("export interface Post {"),
                       a.indexOf("export interface Comment {"));
  /*
    `image_key` la khoa doi tuong tho — kho la rieng tu nen no vo dung voi trinh
    duyet, va no lo cau truc khong gian ten. `removed_by` bien mot quyet dinh
    kiem duyet thanh mot muc tieu ca nhan. Ca hai chi co o kieu AdminPost.
  */
  assert.ok(!/^\s*image_key:/m.test(khoi), "Post công khai lộ image_key");
  assert.ok(!/^\s*removed_by:/m.test(khoi), "Post công khai lộ removed_by");
  assert.match(khoi, /has_image: boolean/);
  assert.match(khoi, /image_url\?: string/);
});

test("gioi han lay tu MAY CHU qua /api/limits, khong chep tay", () => {
  const a = api();
  assert.match(a, /limits: \(\) => request<ServerLimits>\("\/api\/limits"\)/);
  // Hop soan bai dung `limits?.post_max_chars`, chi co con so DU PHONG khi
  // chua tai duoc — va du phong phai giong con so that cua may chu.
  assert.match(composer(), /limits\?\.post_max_chars \?\? 2000/);
  assert.match(comments(), /limits\?\.comment_max_chars \?\? 1000/);
});

/* ============================================================== bang tin */

test("bang tin khong doi dang nhap, va noi ro khi chua ca nhan hoa", () => {
  const src = feed();
  // Khong co cong chan dang nhap quanh phan doc
  assert.match(src, /social\s*\.feed\(\)/);
  assert.match(src, /personalized/);
  assert.match(src, /Bài mới nhất từ khắp Fanfic World/);
  // Nguoi chua dang nhap thay loi moi, khong thay loi
  assert.match(src, /Đăng nhập<\/Link> để đăng bài/);
});

test("bang tin noi ro khi danh sach theo doi bi cat", () => {
  // `following_truncated` den tu backend khi vuot tran truy van IN. Im lang
  // bo bot la noi doi bang cach im lang.
  assert.match(feed(), /following_truncated/);
  assert.match(feed(), /bạn theo dõi gần nhất/);
});

test("phan trang bang offset that, khong tai het", () => {
  const src = feed();
  assert.match(src, /social\.feed\(trang\.limit, trang\.items\.length\)/);
  assert.match(src, /trang\.items\.length < trang\.total/);
});

test("chi tac gia da duyet moi bi hoi danh sach truyen cua minh", () => {
  /*
    Voi moi nguoi khac day la mot truy van chac chan tra ve rong — va no chay
    o MOI lan mo trang cong dong.
  */
  const src = feed();
  assert.match(src, /profile\?\.author_status === "approved"/);
  assert.match(src, /if \(!laTacGia\) return;/);
});

/* ============================================================ the bai dang */

test("binh luan CHI tai khi duoc mo — khong phai 20 truy van cho 20 bai", () => {
  const src = postCard();
  assert.match(src, /\{moBinhLuan && !commentsElsewhere \? \(/);
  // Va khoi binh luan tu tai du lieu cua no khi mount
  assert.match(comments(), /social\s*\n?\s*\.comments\(postId\)/);
});

test("thich la aria-pressed + cap nhat lac quan + hoan lai khi loi", () => {
  const src = postCard();
  assert.match(src, /aria-pressed=\{bai\.liked\}/);
  // Lac quan: doi truoc...
  assert.match(src, /liked: !truoc/);
  // ...va hoan lai bang trang thai cu khi may chu tu choi.
  assert.match(src, /capNhat\(bai\);/);
  // Con so cua MAY CHU thang phep doan.
  assert.match(src, /like_count: ra\.like_count/);
});

test("trang mot bai le khong hien HAI khoi binh luan", () => {
  /*
    Loi tu viet ra tu bat duoc trong phien nay: trang /posts/[id] mo san khoi
    binh luan, nhung nut tren the van bat/tat mot khoi thu hai. `commentsElsewhere`
    ton tai vi dieu do — va bai test nay giu cho no khong bi don di.
  */
  assert.match(postPage(), /commentsElsewhere/);
  assert.match(postCard(), /commentsElsewhere \? \(/);
});

test("nut sua/xoa chi hien voi chinh chu, nut bao cao voi nguoi khac", () => {
  const src = postCard();
  assert.match(src, /\{bai\.can_edit \? \(/);
  // Bao cao nam o nhanh NGUOC lai cua can_edit — khong ai bao cao chinh minh.
  assert.match(src, /\) : profile \? \(/);
});

test("anh bai co max-height — mot anh doc khong day bang tin xuong ba man", () => {
  const than = css();
  const khoi = than.slice(than.indexOf(".bai-anh {"),
                          than.indexOf("}", than.indexOf(".bai-anh {")));
  assert.match(khoi, /max-height:\s*70vh/);
  assert.match(khoi, /loading="lazy"/.test(postCard()) ? /max-width/ : /max-width/);
  assert.match(postCard(), /loading="lazy"/);
});

/* ============================================================ hop soan bai */

test("anh duoc ve lai qua canvas va xuat WebP truoc khi gui", () => {
  const src = composer();
  assert.match(src, /canvas\.getContext\("2d"\)/);
  assert.match(src, /canvas\.toBlob\(xong, "image\/webp"/);
  // Va noi ro voi nguoi dung rang metadata (ke ca GPS) bi bo.
  assert.match(src, /bỏ hết metadata/);
  assert.match(src, /GPS/);
});

test("anh qua tran bi chan O TRINH DUYET kem con so that", () => {
  /*
    Gui thang roi de may chu tu choi la bat nguoi dung cho het duong truyen
    roi moi biet cong sua vua roi vo ich.
  */
  const src = composer();
  assert.match(src, /ra\.bytes > tranByte/);
  assert.match(src, /MB sau khi nén/);
});

test("URL xem truoc duoc thu hoi — khong ro ri blob theo tung anh", () => {
  const src = composer();
  assert.match(src, /URL\.revokeObjectURL\(nguon\)/);
  assert.match(src, /if \(url\) URL\.revokeObjectURL\(url\)/);
});

test("o chon tep den duoc bang ban phim — khong display:none", () => {
  const than = css();
  const khoi = than.slice(than.indexOf('.soan-bai-tep input[type="file"]'));
  assert.match(khoi.slice(0, 300), /opacity: 0/);
  assert.ok(!/display:\s*none/.test(khoi.slice(0, 300)),
    "input tệp display:none thì không nhận tiêu điểm bàn phím");
});

test("chon lai CUNG mot tep van kich hoat onChange", () => {
  assert.match(composer(), /oTep\.current\.value = ""/);
});

/* ============================================================== binh luan */

test("tra loi DUNG mot cap: mang phang, khong de quy", () => {
  const src = comments();
  // Cau truc: replies la mot mang trong binh luan goc, khong goi lai chinh no.
  assert.ok(!/CommentThread[\s\S]{0,200}CommentThread/.test(
    src.slice(src.indexOf("export function CommentThread"))),
    "CommentThread không được gọi đệ quy chính nó");
  assert.match(src, /c\.replies \?\? \[\]/);
});

test("binh luan bi go van hien dong 'da bi go', khong bien mat", () => {
  const src = comments();
  assert.match(src, /Bình luận này đã bị gỡ/);
  assert.match(src, /bl\.state !== "visible"/);
});

test("con thieu bao nhieu tra loi thi noi ro con so", () => {
  const src = comments();
  assert.match(src, /c\.reply_count > \(c\.replies\?\.length \?\? 0\)/);
  assert.match(src, /Xem thêm \{c\.reply_count - \(c\.replies\?\.length \?\? 0\)\} trả lời/);
});

test("so binh luan cua bai duoc bao nguoc len the qua onCountChange", () => {
  assert.match(comments(), /onCountChange\?\.\(1\)/);
  assert.match(comments(), /onCountChange\?\.\(-1\)/);
  assert.match(postCard(), /onCountChange=\{\(delta\)/);
});

/* ============================================================== thong bao */

test("cai chuong chi hoi CON SO va khong polling", () => {
  const src = bell();
  assert.match(src, /social\s*\.unreadCount\(\)/);
  // `codeOnly`: chu thich cua chinh tep nay ke ve setInterval de giai thich vi
  // sao KHONG dung no.
  assert.ok(!/setInterval/.test(codeOnly(src)),
    "không polling — một truy vấn mỗi 30s cho MỖI tab đang mở");
  // Danh sach chi tai khi bam
  assert.match(src, /if \(ds !== null\) return;/);
});

test("cai chuong an hoan toan khi chua dang nhap", () => {
  assert.match(bell(), /if \(!profile\) return null;/);
});

test("nhan chuong kem CON SO cho trinh doc man hinh", () => {
  assert.match(bell(), /aria-label=\{\s*chuaDoc > 0 \? `Thông báo, \$\{chuaDoc\} chưa đọc` : "Thông báo"\s*\}/);
});

test("Escape dong bang thong bao va tra tieu diem ve nut mo", () => {
  const src = bell();
  assert.match(src, /e\.key !== "Escape"/);
  assert.match(src, /nut\.current\?\.focus\(\)/);
});

test("trang thong bao doi dang nhap — khac /community", () => {
  const src = tbPage();
  assert.match(src, /Cần đăng nhập/);
  assert.match(src, /login\?next=%2Fnotifications/);
});

test("bam vao thong bao la danh dau da doc, va loi khong chan dieu huong", () => {
  const src = tbPage();
  assert.match(src, /void social\.markRead\(n\.notification_id\)\.catch\(\(\) => \{\}\)/);
});

test("chuong va trang thong bao dung CUNG bang cau mo ta", () => {
  /*
    Hai bang cau o hai tep — chung PHAI noi cung mot thu cho cung mot loai.
    So khop tung loai mot de mot lan sua o mot cho khong troi khoi cho kia.
  */
  const a = bell();
  const b = tbPage();
  for (const cau of ["đã theo dõi bạn", "đã thích bài của bạn",
                     "đã bình luận bài của bạn", "đã trả lời bình luận của bạn",
                     "vừa đăng chương mới",
                     "Đơn tác giả của bạn đã được duyệt",
                     "Đơn tác giả của bạn chưa được duyệt"]) {
    assert.ok(a.includes(cau), `chuông thiếu: ${cau}`);
    assert.ok(b.includes(cau), `trang thông báo thiếu: ${cau}`);
  }
});

/* ================================================================ theo doi */

test("nut theo doi: aria-pressed, lac quan, hoan lai, va con so may chu thang", () => {
  const src = followBtn();
  assert.match(src, /aria-pressed=\{dangTheoDoi\}/);
  assert.match(src, /setDangTheoDoi\(!truoc\)/);
  assert.match(src, /setDangTheoDoi\(truoc\);\s*\r?\n\s*setSo\(soTruoc\)/);
  assert.match(src, /setSo\(ra\.follower_count\)/);
});

test("chua dang nhap thi nut theo doi DAN toi dang nhap kem next", () => {
  const src = followBtn();
  assert.match(src, /loginHref\(pathname\)/);
});

test("trang truyen: nut theo doi khong hien voi chu so huu va ban nhap", () => {
  const novel = read("../src/app/novels/[id]/page.tsx");
  assert.match(novel, /!isOwner && data\?\.follow \? \(/);
  assert.match(novel, /label="Theo dõi truyện"/);
});

test("trang ca nhan: khong co nut theo doi tro vao chinh minh", () => {
  const trang = read("../src/app/u/[username]/page.tsx");
  assert.match(trang, /\{xh\.is_self \? null : \(/);
});

/* ================================================================= bao cao */

test("hop thoai bao cao NOI RO no khong tu go noi dung", () => {
  const src = reportDlg();
  assert.match(src, /không tự gỡ<\/strong> nội dung/);
});

test("hop thoai quan ly tieu diem: nhan focus khi mo, Escape dong", () => {
  const src = reportDlg();
  assert.match(src, /hop\.current\?\.focus\(\)/);
  assert.match(src, /aria-modal="true"/);
  assert.match(src, /e\.key === "Escape"/);
});

test("nam ly do khop enum cua backend", () => {
  const src = reportDlg();
  for (const key of ["spam", "harassment", "inappropriate", "copyright",
                     "other"]) {
    assert.ok(src.includes(`"${key}"`), `thiếu lý do ${key}`);
  }
});

/* ======================================================= tab trang ca nhan */

test("tablist that: role, aria-selected, va mui ten chuyen tab", () => {
  const src = tabs();
  assert.match(src, /role="tablist"/);
  assert.match(src, /role="tab"/);
  assert.match(src, /role="tabpanel"/);
  assert.match(src, /aria-selected=\{tab === t\.key\}/);
  assert.match(src, /ArrowRight/);
  // Dung mau tablist: chi tab dang chon nam trong luong Tab.
  assert.match(src, /tabIndex=\{tab === t\.key \? 0 : -1\}/);
});

test("tab Bai viet chi tai khi duoc mo, va chi MOT lan", () => {
  const src = tabs();
  assert.match(src, /if \(tab !== "bai" \|\| bai !== null\) return;/);
});

/* ========================================================== kiem duyet */

test("hang doi bao cao hien NOI DUNG THAT ngay tai cho", () => {
  const src = adminReports();
  assert.match(src, /bc\.content/);
  assert.match(src, /blockquote className="bc-noi-dung"/);
  // Noi dung da bi chinh chu xoa that thi noi ro, khong de o trong.
  assert.match(src, /đã được chính chủ xoá/);
});

test("go va dong bao cao la HAI thao tac rieng", () => {
  const src = adminReports();
  assert.match(src, /Gỡ nội dung/);
  assert.match(src, /Đánh dấu đã xử lý/);
  assert.match(src, /Bỏ qua/);
});

test("khong co nut xoa that o duong kiem duyet — chi go/phuc hoi", () => {
  for (const [ten, src] of [["reports", adminReports()],
                            ["posts", adminPosts()]]) {
    assert.ok(!/deletePost|deleteComment/.test(src),
      `${ten} không được xoá thật — gỡ giữ lại bằng chứng`);
    assert.match(src, /restorePost|restoreComment|Phục hồi/);
  }
});

test("hai trang admin moi dung DanhSachTrangThai dung chung", () => {
  // Ba trang thai tai/loi/rong qua MOT component — moi trang tu viet thi se
  // co trang quen mot nhanh, va nhanh bi quen luon la "loi".
  assert.match(adminReports(), /DanhSachTrangThai/);
  assert.match(adminPosts(), /DanhSachTrangThai/);
});

test("hang doi mac dinh loc 'dang mo' va cu nhat truoc", () => {
  const src = adminReports();
  assert.match(src, /useState\("open"\)/);
  assert.match(src, /Cũ nhất hiện trước/);
});

/* ========================================================= thoi gian doc */

test("khiNao: doc duoc, on dinh, va khong bao gio 'Invalid Date'", async () => {
  const { khiNao } = await import("../src/lib/time.ts");
  const moc = new Date("2026-08-11T12:00:00Z");
  assert.equal(khiNao("2026-08-11T11:59:30Z", moc), "vừa xong");
  assert.equal(khiNao("2026-08-11T11:30:00Z", moc), "30 phút trước");
  assert.equal(khiNao("2026-08-11T09:00:00Z", moc), "3 giờ trước");
  assert.equal(khiNao("2026-08-09T12:00:00Z", moc), "2 ngày trước");
  // Qua 7 ngay: NGAY THAT, khong phai "12 tuan truoc".
  assert.match(khiNao("2026-05-01T12:00:00Z", moc), /2026/);
  // Lech am (dong ho may khach cham hon may chu) khong duoc doc ra tuong lai.
  assert.equal(khiNao("2026-08-11T12:00:02Z", moc), "vừa xong");
  // Moc rac bien mat, khong hien "Invalid Date".
  assert.equal(khiNao("khong-phai-ngay", moc), "");
});

/* ===================================================== khong khi va mobile */

test("khu cong dong co sac rieng va khong co canh troi dong", () => {
  const than = css();
  assert.match(than, /--sac-community-1/);
  assert.match(than, /--sac-community-2/);
  /*
    AmbientScene KHONG co canh cho "community" — bang tin la noi doc va cuon,
    mot thu troi ben canh se lam met mat. Kiem bang cach doc component.
  */
  const ambient = read("../src/components/AmbientScene.tsx");
  assert.ok(!/community/.test(ambient),
    "khu cộng đồng không có cảnh trời động");
});

test("mobile: anh bai thap hon, tra loi thut it hon, tab cuon ngang", () => {
  const than = css();
  const mobile = than.slice(than.lastIndexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.bai-anh \{ max-height: 50vh; \}/);
  assert.match(mobile, /\.binh-luan\.tra-loi \{ margin-left: 12px; \}/);
  assert.match(mobile, /\.tab-hang \{[^}]*overflow-x: auto/);
});

test("mobile: bang thong bao GHIM vao khung nhin, khong neo theo chuong", () => {
  /*
    LOI THAT do QA tren khung nhin 430px tim ra: `.menu-panel` goc neo
    `right: 0` theo cai chuong — ma chuong dung gan mep phai. Mot bang rong
    `100vw - 20px` neo o do tran CHIN MUOI PIXEL khoi mep trai man hinh, va
    dong dau cua moi thong bao bi cat cut.

    `position: fixed` + hai mep trai/phai la cach duy nhat giu bang trong man
    hinh ma khong phai biet chuong dung o dau. Nen cung phai DAC: lop kinh dep
    tren nen trong, nhung o day bang nam de len hang dieu huong va chu "Khám
    phá" xuyen qua tron vao chu cua thong bao.
  */
  const than = css();
  const mobile = than.slice(than.lastIndexOf("@media (max-width: 640px)"));
  const at = mobile.indexOf(".bell-panel {");
  assert.notEqual(at, -1, "thiếu ghi đè .bell-panel ở mobile");
  const khoi = mobile.slice(at, mobile.indexOf("}", at) + 1);
  assert.match(khoi, /position: fixed/);
  assert.match(khoi, /left: 10px/);
  assert.match(khoi, /right: 10px/);
  assert.match(khoi, /backdrop-filter: none/);
});

test("reduced-motion tat het chuyen dong cua tang xa hoi", () => {
  const than = css();
  const khoi = than.slice(than.lastIndexOf("@media (prefers-reduced-motion: reduce)"));
  assert.match(khoi, /\.bai-dang/);
  assert.match(khoi, /animation: none !important/);
});

/* ============================================== vien thuoc nav — hoi quy */

test("HOI QUY: /community vao truc khong pha vien thuoc va nhan /write", () => {
  /*
    Phase 0 cua nhiem vu nay sua nhan "Viết truyện" trong suot va vien thuoc
    khong hien khi tai thang. Them mot muc nav MOI la dung loai thay doi co the
    lam tai phat — nen ghim lai ca hai o day, ngay canh tinh nang moi.
  */
  const nav = read("../src/components/NavAuth.tsx");
  // "Cộng đồng" co mat va van du cau truc ref map cho vien thuoc.
  assert.match(nav, /href: "\/community", label: "Cộng đồng"/);
  assert.match(nav, /bang\.current\.set\(link\.href, el\)/);
  assert.match(nav, /<NavIndicator bao=\{hop\} bang=\{bang\} moc=\{dangXem\} \/>/);

  // Nhan muc dang xem van la mau DAC, khong background-clip.
  const than = css();
  const at = than.indexOf('.nav-link[aria-current="page"]');
  assert.notEqual(at, -1);
  const khoi = than.slice(at, than.indexOf("}", at) + 1)
    .replace(/\/\*[\s\S]*?\*\//g, "");
  assert.ok(!/background-clip/.test(khoi));
  assert.match(khoi, /color: var\(--sac-2/);
});

test("HOI QUY: sections.ts van tinh dung huong quanh community", async () => {
  const { huongDi, viTri } = await import("../src/lib/sections.ts");
  assert.equal(viTri("/community"), "community");
  assert.equal(viTri("/posts/pst_1"), "long");
  assert.equal(viTri("/notifications"), "long");
  // Kham pha -> Cong dong la TIEN (sang phai), Cong dong -> Thu vien cung tien.
  assert.equal(huongDi("/fanfic", "/community"), 1);
  assert.equal(huongDi("/community", "/library"), 1);
  assert.equal(huongDi("/library", "/community"), -1);
});

/* ==================================================== tim kiem toan cuc */

test("bai dang la muc PHU cua tim kiem, va loi cua no khong keo sap ca hop", () => {
  const src = read("../src/components/SearchOverlay.tsx");
  // Ba ket qua, dung SAU truyen va nguoi — uu tien khong doi.
  assert.match(src, /social\.searchPosts\(tu, 3\)/);
  const viTri = [src.indexOf("Truyện"), src.indexOf("Người dùng"),
                 src.indexOf("Bài viết")];
  assert.ok(viTri[0] < viTri[2] && viTri[1] < viTri[2],
    "khu Bài viết phải đứng sau Truyện và Người dùng");
  /*
    `.catch` tra ve rong: truyen va nguoi la ly do nguoi ta mo hop tim nay, va
    mot loi cua rieng muc bai dang khong duoc keo sap ca hai. Da thay THAT khi
    backend cu chua co route: hop van hien truyen, chi thieu muc bai.
  */
  assert.match(src, /searchPosts\(tu, 3\)\.catch\(\(\) => \(\{ items: \[\], total: 0 \}\)\)/);
});

test("ket qua bai dang di duoc bang ban phim nhu hai muc kia", () => {
  const src = read("../src/components/SearchOverlay.tsx");
  assert.match(src, /\.\.\.bai\.map\(\(b\) => \(\{ loai: "bai" as const, bai: b \}\)\)/);
  assert.match(src, /if \(k\.loai === "bai"\) return `\/posts\/\$\{k\.bai\.post_id\}`;/);
});
