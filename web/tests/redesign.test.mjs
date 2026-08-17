/*
 * Ban thiet ke lai 2026-08: rang buoc cua he thiet ke moi.
 *
 * Bo test nay KHONG kiem "trong co dep khong" — khong bai test nao lam duoc
 * viec do. No kiem nhung thu se lang le truot di khi co nguoi sua tiep:
 *
 *   1. mau va kich thuoc chi ton tai MOT cho (khoi token), khong rai ra tung
 *      trang duoi dang hex;
 *   2. moi hieu ung chuyen dong deu tat duoc bang `prefers-reduced-motion`;
 *   3. vung bam tren dien thoai du 44px;
 *   4. ban thiet ke lai khong lam mat mot loi vao dieu huong nao.
 *
 * Cac rang buoc ve HANH VI (tien do, khoi phuc sau reload, dang nhap) nam o
 * `job-progress-shared`, `job-recovery`, `studio-job` va `author-workspace-oauth`
 * — chung khong thuoc ve ban thiet ke lai va khong duoc noi long o day.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// Chuan hoa CRLF -> LF: checkout/merge tren Windows co the ghi lai CRLF cho
// file van la LF trong git blob (xem bai hoc o `admin-trusted-sources.test.mjs`).
// Thieu buoc nay thi cac test so khop chuoi da dong (\n) se vo co hong sau
// mot lan `git checkout`/`merge`, du noi dung logic khong doi.
const read = (p) =>
  readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");

/**
 * Than cua mot quy tac CSS, de rang buoc noi ve DUNG khoi do.
 *
 * Tim tu DAU DONG chu khong phai `indexOf` tran: `.story-title {` cung khop
 * duoc voi duoi cua `.story-card:hover .story-title {`, va bai test se soi
 * nham mot quy tac khac han. Da do that.
 */
function rule(selector) {
  const text = css();
  const at = text.search(
    new RegExp(`^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} \\{`, "m"),
  );
  assert.notEqual(at, -1, `khong tim thay quy tac ${selector}`);
  return text.slice(at, text.indexOf("}", at));
}

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ============================================================ khoi token */

test("bang mau moi la TIM + LO, va ca hai deu la token", () => {
  const text = css();
  assert.match(text, /--brand: #8b6cff;/, "màu hành động không còn là tím");
  assert.match(text, /--accent: #22d3ee;/, "màu bổ trợ không còn là lơ");
  assert.match(text, /--grad-brand: linear-gradient\([^)]*var\(--brand\)/);
});

test("token moi cho kinh mo, quang, chieu cao va nhip deu co mat", () => {
  const text = css();
  for (const token of [
    "--glass:", "--glass-strong:", "--blur:",
    "--edge:", "--lift-brand:", "--lift-accent:",
    "--h-sm:", "--h-md:", "--h-lg:", "--h-input:",
    "--dur-fast:", "--dur:", "--dur-slow:", "--ring:",
  ]) {
    assert.ok(text.includes(token), `thiếu token ${token}`);
  }
});

test("mau chu tren nen tim la token, khong phai hex rai rac", () => {
  // Truoc day moi cho tu viet `#080a10`. Doi do dam cua nut chinh la phai di
  // sua tung cho mot, va chac chan se sot.
  assert.match(css(), /--on-brand: #[0-9a-f]{6,8};/);
});

test("KHONG trang nao hardcode mau tim/lo moi", () => {
  // Hex duoc phep o KHOI TOKEN va o cac quy tac trang tri trong `globals.css`
  // (quang, gradient) — nhung khong duoc lot vao tep JSX.
  for (const f of [
    "../src/app/page.tsx",
    "../src/app/library/page.tsx",
    "../src/app/account/page.tsx",
    "../src/app/login/page.tsx",
    "../src/app/studio/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/fanfic/page.tsx",
    "../src/components/JobProgress.tsx",
    "../src/components/SiteHeader.tsx",
    "../src/components/StoryCard.tsx",
    "../src/components/NavAuth.tsx",
  ]) {
    const hex = read(f).match(/#[0-9a-fA-F]{6,8}\b/g) ?? [];
    assert.deepEqual(hex, [], `${f} còn màu hardcode: ${hex.join(" ")}`);
  }
});

/* =========================================================== dieu huong */

test("header la lop kinh mo va biet trang da cuon chua", () => {
  const head = rule(".site-header");
  // Phase 3.6 Phan F: `--blur` (18px, dung chung cho modal/mini player) qua
  // MANH cho mot khoi noi nho canh logo — doi sang mot gia tri RIENG trong
  // khoang "moderate" 12-18px dac ta yeu cau (14px), khong con qua token
  // dung chung nua.
  const m = head.match(/backdrop-filter: blur\((\d+)px\)/);
  assert.notEqual(m, null, "thiếu backdrop-filter dạng blur(Npx)");
  const px = Number(m[1]);
  assert.ok(px >= 12 && px <= 18, `blur ${px}px ngoài khoảng 12-18px dặc tả`);
  // V6: `color-mix` thay hex tinh — cung mot ly do (nua trong suot de tranh
  // nen lot qua), chi doi CACH bieu dien mau (token dong bo voi --bg thay vi
  // mot hang so tinh rieng).
  assert.match(head, /background: color-mix\(in srgb, var\(--bg\)/, "header không còn nửa trong suốt");
  // Dac them khi da cuon — luc do moi co chu chay qua duoi.
  assert.match(css(), /\.site-header\[data-scrolled="true"\]/);

  const shell = read("../src/components/SiteHeader.tsx");
  assert.match(shell, /window\.addEventListener\("scroll"/);
  assert.match(shell, /\{ passive: true \}/, "listener cuộn phải là passive");
  assert.match(shell, /removeEventListener\("scroll"/, "không gỡ listener");
});

test("'Viết truyện' noi bat hon muc dieu huong thuong", () => {
  const nav = read("../src/components/NavAuth.tsx");
  // Van la muc thu tu trong `LINKS` — thu tu san pham khong doi, va
  // `ui.test.mjs` cung `author-workspace-oauth.test.mjs` khoa lai dieu do.
  assert.match(nav, /href: "\/write", label: "Viết truyện", cta: true/);
  assert.match(nav, /link\.cta \? "nav-link nav-cta" : "nav-link"/);
  const cta = rule(".nav-cta");
  assert.match(cta, /var\(--brand-line\)/, "nút CTA không có viền tím");
});

test("muc dang xem danh dau bang vach duoi, khong to ca nen", () => {
  // To ca nen o mot thanh bon muc thi khoi mau do to ngang mot cai nut va hut
  // mat truoc ca ten san pham.
  //
  // Vach gio la MOT phan tu dung chung truot giua cac muc, khong con la mot
  // `::after` cua tung muc — xem `motion-v2.test.mjs`. Dieu duoc giu o day la
  // phan KHONG doi: muc dang xem khong duoc to ca nen.
  assert.match(css(), /\.nav-vach \{/);
  const active = rule('.nav-link[aria-current="page"]');
  assert.match(active, /background: transparent/);
});

/* ============================================================= trang chu */

test("trang chu co hero, va no LUON ve", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /<Hero daDangNhap=/);
  // Ve TRUOC nhanh loading/error/empty, nen kho trong thi van con thu noi cho
  // nguoi vao lan dau biet ho dang o dau.
  const at = home.indexOf("<Hero daDangNhap=");
  assert.ok(at < home.indexOf('loading ? (\n          <SkeletonCards'),
    "hero nằm sau nhánh loading");
});

test("hero noi ve TRUYEN, khong phai ve cong cu", () => {
  const home = read("../src/app/page.tsx");
  const at = home.indexOf("function Hero(");
  const than = home.slice(at, home.indexOf("function DaiThanhVien"));
  assert.match(than, /href="\/fanfic"/, "thiếu lối vào khám phá truyện");
  assert.match(than, /href="\/write"/, "thiếu lối vào viết truyện");
  // Va van khong dan bang logo khong lo — `ui.test.mjs` giu rang buoc do.
  assert.ok(!than.includes("LogoMark"));
});

test("da dang nhap thi co loi tat vao thu vien", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /daDangNhap \? \(/);
  assert.match(home, /href="\/library"/);
});

test("trang chu VAN lay truyen that, khong thanh landing tinh", () => {
  const home = read("../src/app/page.tsx");
  assert.match(home, /api\.browseNovels/);
  // "featured" thay `StoryHero` cu (V4 visual completion) — mot the noi bat
  // gioi han rong, dung khi kho chi co DUY NHAT mot truyen. Xem
  // `components/StoryCard.tsx::StoryCardVariant`.
  assert.match(home, /variant="featured"/);
  assert.match(home, /<StoryCard key=/);
});

test("trang chu KHONG bia so lieu backend khong co", () => {
  const home = read("../src/app/page.tsx");
  for (const bia of ["lượt đọc", "lượt nghe", "lượt xem", "nổi bật nhất"]) {
    assert.ok(!home.includes(bia), `trang chủ bịa số liệu: ${bia}`);
  }
});

/* ====================================================== chuyen dong co kiem */

test("moi hieu ung deu tat duoc bang prefers-reduced-motion", () => {
  const text = css();
  const at = text.indexOf("@media (prefers-reduced-motion: reduce)");
  assert.notEqual(at, -1, "không còn khối reduced-motion");
  const than = text.slice(at, at + 700);
  assert.match(than, /animation-duration: 0\.01ms !important/);
  assert.match(than, /transition-duration: 0\.01ms !important/);
});

test("do tre cua hieu ung vao trang la CLASS, khong phai style inline", () => {
  // Media query va `prefers-reduced-motion` khong voi toi style inline duoc.
  const text = css();
  assert.match(text, /\.rise-1 \{ animation-delay:/);
  assert.ok(!/style=\{\{/.test(read("../src/app/page.tsx")));
});

/* ======================== ban thiet ke lai KHONG dung vao hanh vi job */

test("JobProgress van lay MOI con so tu tienDoJob", () => {
  /*
    Day la rang buoc quan trong nhat cua ca ban thiet ke lai. Khung tien do
    duoc ve lai — vien, quang, vet sang — nhung khong duoc tu suy ra mot con
    so nao. Neu no bat dau tinh toan thi `/write` va `/studio` lai co hai
    nguon su that, dung kieu lech da mat ba PR de go.
  */
  const src = read("../src/components/JobProgress.tsx");
  assert.match(src, /const tien_do = tienDoJob\(job\);/);
  assert.match(src, /percent=\{tien_do\.percent\}/);
  assert.match(src, /indeterminate=\{!tien_do\.biet_tong\}/);
  assert.ok(!/progress \|\| \d/.test(src), "khung tiến độ bịa tỷ lệ");
  assert.ok(!/job\.done_parts|job\.total_parts|job\.progress\b/.test(src),
    "khung tiến độ đọc thẳng trường của job thay vì qua tienDoJob");
});

test("lop mau cua khung chi theo status, khong theo con so", () => {
  const src = read("../src/components/JobProgress.tsx");
  assert.match(src, /VE_THEO: Record<string, string>/);
  assert.match(src, /VE_THEO\[job\.status\]/);
  for (const cls of ["job-box-live", "job-box-done", "job-box-failed"]) {
    assert.ok(read("../src/app/globals.css").includes(`.${cls}`),
      `thiếu quy tắc .${cls}`);
  }
});

test("hai trang VAN dung hook va khung chung sau khi ve lai", () => {
  for (const [ten, f] of [
    ["/write", "../src/app/write/page.tsx"],
    ["/studio", "../src/app/studio/page.tsx"],
  ]) {
    const src = read(f);
    assert.match(src, /useJobTracker\(/, `${ten} mất hook chung`);
    assert.match(src, /<JobProgress\b/, `${ten} mất khung chung`);
    assert.match(src, /api\.listJobs\(\)/, `${ten} mất đường khôi phục sau F5`);
  }
});

test("ve lai KHONG mang style inline tro lai hai trang cong cu", () => {
  // Ba dong mau lap lai bang `style` inline o `/write` da duoc doi thanh
  // `.novel-pick`. Media query khong voi toi style inline duoc.
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /className="novel-pick"/);
  assert.ok(!/borderColor:\s*\n?\s*novel\.novel_id === selectedId/.test(write));
  assert.match(read("../src/app/globals.css"),
    /\.novel-pick\[aria-current="true"\]/);
});

test("thanh tien do co vet sang khi CHAY, va thoi khi xong", () => {
  const text = css();
  assert.match(text, /\.progress-bar::after/, "thanh tiến độ không có vệt sáng");
  assert.match(text, /\.progress-done \.progress-bar::after \{ display: none; \}/,
    "xong rồi mà vệt sáng vẫn chạy");
  assert.match(text, /\.progress-indeterminate \.progress-bar::after/);
});

test("reduced-motion tat CA hai thu ma rut thoi luong khong tat duoc", () => {
  /*
    Rut thoi luong ve 0.01ms la chua du:
      - hieu ung nhac len van NHAY mot buoc toi vi tri moi;
      - vet sang lap vo han van chay DUNG mot vong roi dung o giua thanh, de
        lai mot vach sang lo lung.
  */
  const text = css();
  const at = text.indexOf("@media (prefers-reduced-motion: reduce)");
  const than = text.slice(at, at + 1200);
  assert.match(than, /\.story-card:hover/, "hiệu ứng nhấc thẻ truyện chưa tắt");
  assert.match(than, /\.quick-card:hover/, "hiệu ứng nhấc thẻ lối tắt chưa tắt");
  assert.match(than, /\.progress-bar::after \{ display: none; \}/,
    "vệt sáng còn đọng lại giữa thanh");
  assert.match(than, /\.rise \{ animation: none; \}/);
});

/* ================================================================ mobile */

test("moi bo cuc luoi moi deu xuong dong o mobile", () => {
  const text = css();
  const at = text.indexOf("@media (max-width: 640px)");
  assert.notEqual(at, -1);
  const mobile = text.slice(at);
  for (const cls of [
    ".hero-v2",
    ".cta-band",
    ".audio-row",
    ".account-hero",
    ".novel-head",
    ".reader",
    ".quick-grid",
  ]) {
    assert.ok(mobile.includes(cls), `${cls} không có quy tắc mobile`);
  }
});

test("nhom nut cua hang audio xuong dong rieng o mobile", () => {
  // Ba thu tren mot hang o man hinh 375px thi ten audio bi nen con vai ky tu.
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  const at = mobile.indexOf(".audio-row-actions");
  assert.notEqual(at, -1);
  assert.match(mobile.slice(at, at + 160), /grid-column: 1 \/ -1/);
});

test("bia truyen KHONG tran ca be ngang khi da xuong dong", () => {
  // Mot bia 3:2 rong ca man hinh cao hon ca khung nhin — nguoi dung phai cuon
  // mot man hinh chi de thay ten truyen.
  const text = css();
  const tablet = text.slice(
    text.indexOf("@media (max-width: 900px)"),
    text.indexOf("@media (max-width: 640px)"),
  );
  assert.match(tablet, /\.novel-head-cover \{ max-width: \d+px; \}/);
});

test("nut bam moi du 44px o mobile", () => {
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  const at = mobile.indexOf("min-height: 44px");
  assert.notEqual(at, -1);
  assert.match(mobile.slice(Math.max(0, at - 220), at), /\.novel-pick/,
    "nút chọn truyện chưa đủ vùng bấm");
});

/* ========================================================= doc duoc */

test("cot chu khi doc chuong co chan tren, va CA trang dat giua", () => {
  /*
    Ban dau cot chu dat theo `ch` (68ch ~ 560px), la nguong doc de kinh dien.
    Chu du an yeu cau 700-800px, nen gio la 720px — rong hon mot chut nhung
    van co chan tren, va chuong fanfic thi doan ngan.

    Phan quan trong hon la CA trang doc dat giua: truoc day moi khoi bam le
    trai cua khung 1180px va ben phai con mot mang trong rong bang ca cot chu.
  */
  const doc = rule(".reader");
  const px = Number(doc.match(/max-width: (\d+)px/)?.[1] ?? 0);
  assert.ok(px >= 700 && px <= 800, `cột chữ ${px || "không đặt"}px, cần 700–800`);
  assert.match(rule(".reader .prose"), /line-height: 1\.9/);
  assert.match(css(), /\.reader-crumb \{ margin-inline: auto; \}|margin-inline: auto;/,
    "trang đọc không được căn giữa");
});

test("truyen dang chon co tin hieu NGOAI mau sac", () => {
  // Khong duoc dung mau lam tin hieu duy nhat.
  const chon = rule('.novel-pick[aria-current="true"]');
  assert.match(chon, /inset 3px 0 0/, "chỉ đổi màu, không có vạch dọc");
});

test("muc dang xem tren thanh dieu huong cung vay", () => {
  // Vach duoi chu la tin hieu hinh dang, khong phai mau. Gio la mot vach dung
  // chung TRUOT giua cac muc — xem `motion-v2.test.mjs`.
  assert.match(css(), /\.nav-vach \{/);
  // Vach 2px da thanh mot VIEN THUOC: mot hinh co the tich, nen mat theo duoc no
  // di qua khoang trong giua hai muc thay vi chi thay mot gach ngang doi cho.
  // Dieu KHONG doi: muc dang xem van khong duoc to ca nen bang mau dac.
  // Navigation Motion Correction V3: `--r-full` (vien tron) doi thanh `--r2`
  // (vuong vuc hon) — van la MOT hinh co the tich, chi doi bo goc.
  assert.match(css(), /\.nav-vach \{[^}]*border-radius: var\(--r2\)/s);
  // Navigation Motion Correction V2: nen doi tu trang mo (#ffffff0f, gay
  // "quang trang") sang navy toi pha tron tu `--bg` — van la MOT be mat
  // rieng (khong phai mau dac cua trang thai), chi khong con trang.
  assert.match(css(), /\.nav-vach \{[^}]*background: color-mix\(in srgb, var\(--bg\)/s);
});

/* ================================ nhung loi CHI thay duoc khi mo trinh duyet */

test("header gop hang tu 900px, KHONG doi toi 640px", () => {
  /*
    DO DUOC tren trinh duyet that: o 768px, ca CHIN route deu tran ngang dung
    188px. Thuong hieu + bon muc + o tim + menu + tai khoan khong du cho tren
    mot hang, ma `.site-header .wrap` luc do chua duoc phep xuong dong nen no
    day ca trang rong ra thay vi tu gap lai.
  */
  const text = css();
  const tablet = text.slice(
    text.indexOf("@media (max-width: 900px)"),
    text.indexOf("@media (max-width: 640px)"),
  );
  assert.match(tablet, /\.site-header \.wrap \{[^}]*flex-wrap: wrap/,
    "header chưa được phép xuống dòng ở breakpoint 900px");
  assert.match(tablet, /\.site-search \{ order: 3; width: 100%; \}/);
  assert.match(tablet, /\.nav-links \{\s*order: 4;/);
});

test("thuong hieu va tai khoan dung CHUNG hang dau", () => {
  // `.spacer` la `flex: 1 1 auto`; de nguyen thi no an het cho con lai cua
  // hang dau va day tai khoan xuong mot hang rieng — header thanh BON hang.
  const text = css();
  const tablet = text.slice(
    text.indexOf("@media (max-width: 900px)"),
    text.indexOf("@media (max-width: 640px)"),
  );
  assert.match(tablet, /\.site-header \.spacer \{ display: none; \}/);
  assert.match(tablet, /\.nav-right \{ order: 2; margin-left: auto; \}/);
});

test("header KHONG dinh tren dien thoai", () => {
  // Ngay ca khi gom con ba hang no van cao 173px — mot phan nam man hinh
  // 844px. Trang de DOC thi cho doc quan trong hon.
  const text = css();
  const mobile = text.slice(text.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.site-header \{ position: static; \}/);
  // Nhung tren may tinh bang tro len thi VAN dinh.
  assert.match(rule(".site-header"), /position: sticky/);
});

test("ten truyen dai khong dau cach KHONG tran ra khoi the", () => {
  // `clamp-2` cat theo chieu DOC. Mot tu dai khong ngat duoc thi tran theo
  // chieu NGANG — do duoc tren trinh duyet that.
  assert.match(rule(".story-title"), /overflow-wrap: anywhere/);
});

test("hang the trong the truyen nam MOT hang o MOI be rong", () => {
  /*
    Chieu cao mot o luoi do o cao nhat quyet dinh. Ba the tieng Viet trong cot
    ~210px de xuong hai dong, va luc do ca hang bi keo cao theo mot the.

    Quy tac phai o NGOAI moi `@media` — luoi o desktop bi rang cua vi dung mot
    ly do voi mobile.
  */
  const text = css();
  const truoc_media = text.slice(0, text.indexOf("@media (prefers-reduced-motion"));
  const than = rule(".story-card .story-tags");
  assert.ok(truoc_media.includes(".story-card .story-tags"),
    "quy tắc chỉ áp cho mobile — lưới desktop vẫn răng cưa");
  assert.match(than, /flex-wrap: nowrap/);
  assert.match(than, /overflow: hidden/);
});

test("va tung THE giu nguyen be rong cua no", () => {
  /*
    Dat `nowrap` cho khoi la CHUA DU: khoi thoi xuong dong, nhung cac the bi co
    lai va chu BEN TRONG chung ngat thanh hai dong — "Đời thường" thanh "Đời" /
    "thường", va hang the lai cao gap doi. Thay tren anh chup that sau khi sua
    loi rang cua.
  */
  const than = rule(".story-card .story-tags > *");
  assert.match(than, /flex: 0 0 auto/);
  assert.match(than, /white-space: nowrap/);
});

test("chu 'Đang chuẩn bị…' KHONG dung font cua CON SO", () => {
  /*
    `.job-percent` la font DEU NET, sinh ra de giu "37%" va "38%" rong bang
    nhau. Do mot CAU chu vao do thi chu bi gian ra tung ky tu va doc nhu bi
    loi — thay rat ro tren anh chup that.
  */
  const src = read("../src/components/JobProgress.tsx");
  assert.match(src, /<span className="job-waiting">\{tien_do\.nhan\}<\/span>/);
  assert.ok(
    !/className="job-percent">\s*\{tien_do\.biet_tong \?/.test(src),
    "chữ chờ vẫn dùng chung class với con số",
  );
  assert.doesNotMatch(rule(".job-waiting"), /--font-mono/);
});

/* ============================================ ngon ngu san pham, khong ky thuat */

test("KHONG lo thuat ngu backend ra giao dien", () => {
  // Nguoi dung khong biet "job" la gi, va ho cung khong sua duoc "cau hinh
  // backend" — noi vay la mot loi khuyen vo dung.
  for (const f of [
    "../src/app/studio/page.tsx",
    "../src/app/write/page.tsx",
    "../src/app/library/page.tsx",
    "../src/app/page.tsx",
  ]) {
    const ma = codeOnly(read(f));
    // Chi soi CHUOI hien ra man hinh.
    for (const m of ma.matchAll(/"([^"\n]{12,})"/g)) {
      const chuoi = m[1];
      if (!/[àáâãèéêìíòóôõùúýăđ]/i.test(chuoi)) continue;
      for (const cam of ["job", "worker", "poll", "fingerprint", "backend"]) {
        assert.ok(
          !new RegExp(`\\b${cam}\\b`, "i").test(chuoi),
          `${f} lộ thuật ngữ "${cam}" ra giao diện: ${chuoi.slice(0, 60)}`,
        );
      }
    }
  }
});

