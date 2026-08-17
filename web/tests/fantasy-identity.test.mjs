/*
 * BAN SAC HUYEN AO cua chinh giao dien, khong chi cua tranh nen.
 *
 * VAN DE DA CO: tranh nen la huyen ao / isekai, con ban than giao dien van la
 * mot bang dieu khien SaaS hien dai dat len tren. Hai thu khong cung mot the
 * gioi, va cho vach ra thay ro nhat la cac be mat kinh: sach, vuong, khong mot
 * dau vet nao cua noi chung dang dung.
 *
 * Bo test nay giu mot dieu duy nhat, va no la dieu de mat nhat: trang tri phai
 * la 10-15% CUOI CUNG cua ban sac. Moi bai duoi day dat mot NGUONG — khong phai
 * de kiem tra "co dep khong" (test khong lam duoc viec do) ma de bat luc co ai
 * pha tran: vang tran ra thanh mau nen, moi cai the deu duoc cham tro, hoac mot
 * hieu ung chuyen dong bo vao trang doc chuong.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** Than cua quy tac dau tien co selector khop CHINH XAC o dau dong. */
function rule(text, selector) {
  const re = new RegExp(
    `^${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*(,|\\{)`,
    "m",
  );
  const m = re.exec(text);
  if (!m) return null;
  const at = text.indexOf("{", m.index);
  return text.slice(at, text.indexOf("}", at));
}

/* ============================================ 1. sac vang: PHAI it */

test("vang la mau CHI TIET, khong bao gio la mau nen cua mot be mat", () => {
  /*
    Rang buoc that su cua ban nay. Vang de lam net trang tri; ngay khi no thanh
    `background` cua mot nut hay mot the thi ca trang doi ton, va "hien dai +
    huyen ao" thanh "trang web giay da co".

    Ngoai le DUY NHAT: dau vien 5x5px o `.hang-muc::before` — no la mot hinh
    dac co canh 5 pixel, khong phai mot be mat.
  */
  const text = codeOnly(css());
  const dong = text.split("\n");
  const nen_vang = [];
  dong.forEach((d, i) => {
    // CHI cac khai bao `background*`. Khoi dinh nghia token (`--vang: #d8b56a;`)
    // va cac `box-shadow: inset 0 -1px 0 #d8b56a3d` deu KHONG phai la nen: cai
    // dau la ten mau, cai sau la mot net day mot pixel.
    if (!/^\s*background(-color|-image)?:\s*[^;]*(var\(--vang|#(d8b56a|e4c982))/i.test(d)) return;
    /*
      DANH SACH CHO PHEP, khong phai mot phep noi long.

      Luat that su la: vang khong bao gio la nen cua mot NUT, mot THE, hay mot
      TRANG. Cac cho duoi day deu nho hon the — mot net, mot huy hieu cao 22px,
      mot khoi trich dan — va deu la cho de bai dat vang ("huy hieu tac gia:
      vang mem, quang nhe"; "hang: mau tiet che").

      Them mot ten vao danh sach nay phai la mot viec CO Y. Do la ca cong dung
      cua no: mot ngay nao do co ai to nen mot cai the bang vang, va bai test se
      do thay vi im lang cho qua.
    */
    const CHO_PHEP = [
      ".hang-muc::before",   // dau vien 5x5px sau nhan muc
      ".sao-bang {",         // vet sang day 1.5px o trang dang nhap
      ".hh-tacgia {",        // huy hieu tac gia — chinh cho de bai dat vang
      '.hh-hang[data-bac="5"]',
      '.hh-hang[data-bac="6"]',
      ".ghi-chu-duyet {",    // khoi trich dan ghi chu cua nguoi duyet
      ".admin-nhac {",       // loi nhac "co N don dang cho" o khu quan tri
    ];
    const truoc = dong.slice(Math.max(0, i - 14), i).join("\n");
    if (CHO_PHEP.some((ten) => truoc.includes(ten))) return;
    nen_vang.push(`${i + 1}: ${d.trim()}`);
  });
  assert.deepEqual(nen_vang, [], `vàng bị dùng làm nền:\n  ${nen_vang.join("\n  ")}`);

  /*
    Va KHONG bao gio la mau CHU cua noi dung.

    Hai ngoai le, ca hai deu la NHAN chu khong phai van ban: chu "Tác giả" trong
    chinh huy hieu, va dau cham dau dong 4px cua danh sach quy dinh. Mot doan van
    mau vang thi ca trang doi ton — do la thu bai test nay chan.
  */
  const CHU_CHO_PHEP = [".hh-tacgia {", ".quy-dinh li::marker"];
  const dong_chu = text.replace(/border-color:[^;]*;/g, "").split("\n");
  const chu_vang = [];
  dong_chu.forEach((d, i) => {
    if (!/^\s*color:\s*var\(--vang/.test(d)) return;
    const truoc = dong_chu.slice(Math.max(0, i - 8), i).join("\n");
    if (CHU_CHO_PHEP.some((ten) => truoc.includes(ten))) return;
    chu_vang.push(`${i + 1}: ${d.trim()}`);
  });
  assert.deepEqual(chu_vang, [],
    `vàng bị dùng làm màu chữ:\n  ${chu_vang.join("\n  ")}`);
});

test("so lan dung vang co GIOI HAN — day la 10-15% cuoi, khong phai lop son", () => {
  /*
    Mot con so tuyet doi thay cho mot phan doan tham my. Neu mot ban sau nay
    them vang vao ba muoi cho thi bai test nay do, va nguoi sua se phai doc lai
    doan tren truoc khi nang nguong.

    Tran duoc nang MOT lan, khi V2 them huy hieu tac gia va sau bac hang — do la
    cho de bai dat vang tuong minh, va sau bac thi can sau sac do. Lan nang nay
    phai kem mot ly do; lan sau cung vay.

    Lan nang THU HAI (Themed Page Hero V1, 48 -> 49): theme "Library — Arcane
    Archive" dung DUNG MOT `--hero-accent-secondary: var(--vang)` — day la ban
    sac "antique gold" that su cua rieng khu vuc Thu vien (dac ta yeu cau ro),
    khong phai vang rai rac. Ca 7 theme con lai (home/explore/animation/
    community/audio/image-studio/creator) deu KHONG dung --vang cho token nao
    — da chu y tai su dung mau phu cua chinh tung theme thay vi mo rong ngan
    sach vang o nhieu noi.
  */
  const text = css();
  const bien = (text.match(/var\(--vang[a-z-]*\)/g) ?? []).length;
  const hex = (text.match(/#(d8b56a|e4c982)/gi) ?? []).length;
  assert.ok(bien + hex <= 49,
    `vàng xuất hiện ${bien + hex} lần (biến ${bien} + hex ${hex}) — cần ≤ 49`);

  // Va tim VAN la mau chinh: no phai xuat hien nhieu han vang han han.
  const tim = (text.match(/#8b6cff|var\(--brand/gi) ?? []).length;
  assert.ok(tim > (bien + hex) * 2,
    `tím ${tim} lần so với vàng ${bien + hex} — vàng đang tranh vai với màu chính`);
});

/* ================================== 2. dau muc: dau an + chu + duong ngan */

test("duong ngan sau dau muc la CSS, khong phai ky tu ke", () => {
  /*
    Mot dau muc `[Icon] Truyện mới ─────` viet bang ky tu U+2500 se duoc trinh
    doc man hinh doc thanh mot chuoi "gach ngang" lap lai, va no khong co gian
    theo be rong con lai. Duong ngan phai la mot lop ve.
  */
  for (const f of readdirSync(new URL("../src/app", import.meta.url), {
    recursive: true,
  })) {
    if (typeof f !== "string" || !f.endsWith(".tsx")) continue;
    const src = read(`../src/app/${f}`);
    assert.ok(!/[─│┈━┄╌]/.test(src), `${f} dùng ký tự kẻ làm hoa văn`);
  }

  const than = rule(css(), ".section-title-icon::after");
  assert.ok(than, "thiếu đường ngăn sau đầu mục");
  assert.match(than, /flex: 1 1 auto/, "đường ngăn không ăn hết chỗ còn lại");
  assert.match(than, /height: 1px/, "đường ngăn dày hơn 1px");
  assert.match(than, /linear-gradient\(90deg/, "đường ngăn không tan dần");
});

test("dau muc dung DAU AN co that, khong emoji", () => {
  // Bo icon noi tuyen o `components/Icons.tsx` — khong goi phu thuoc nao.
  const trang = ["../src/app/page.tsx", "../src/app/studio/page.tsx",
                 "../src/app/write/page.tsx", "../src/app/account/page.tsx"];
  for (const f of trang) {
    const src = read(f);
    for (const m of src.matchAll(
      /className="section-title section-title-icon"[^>]*>\s*([^\n]*)/g,
    )) {
      assert.match(m[1], /<Icon\w+ size=\{\d+\} \/>/,
        `${f}: đầu mục không mở đầu bằng một icon SVG`);
    }
  }
});

/* ============================ 3. hoa van kinh: CHI be mat lon */

test("hoa van goc CHI len be mat lon, khong len tung the nho", () => {
  /*
    Day la rang buoc de pha nhat: them mot selector vao danh sach thi mot luoi
    sau cai the deu co khung cham tro, va luc do khong con cai nao la trang tri.

    Danh sach duoi day do de bai dat: hero trang chu, khoi nghe, ho so tai khoan,
    the dang nhap, panel chinh cua Studio va Write.
  */
  const text = css();
  // V4 visual completion: `.home-hero` (hero cao nua trang) bi loai bo, thay
  // bang `.story-card-featured` — be mat "lon" duy nhat con lai o trang chu.
  const at = text.indexOf(".story-card-featured::after");
  assert.notEqual(at, -1, "thiếu hoa văn góc trên thẻ nổi bật trang chủ");
  const dau = text.lastIndexOf("\n", at);
  // `codeOnly` TRUOC khi tach: chu thich giai thich tung be mat co chua dau
  // phay, va tach truoc thi moi cau chu thich thanh mot "selector".
  const selector = codeOnly(text.slice(dau, text.indexOf("{", at)));
  const ds = selector.split(",").map((x) => x.trim()).filter(Boolean);

  assert.ok(ds.length <= 7, `${ds.length} bề mặt được chạm trổ — cần ≤ 7`);
  for (const s of ds) {
    assert.match(s, /::after$/);
  }

  // Va cac be mat KHONG duoc cham tro.
  const cam = [".story-card", ".stat", ".audio-row", ".quick-card", ".hist-item",
               ".novel-pick", ".filter-bar", ".cta-band"];
  for (const c of cam) {
    assert.ok(
      !ds.some((s) => s.startsWith(`${c}:`) || s === `${c}::after`),
      `${c} bị chạm trổ — đó là hàng trong một danh sách`,
    );
  }
});

test("hoa van khong lam TANG do mo cua kinh", () => {
  // Ban nay duoc phep them net, KHONG duoc phep lam mo them: do mo la thu da
  // duoc chot o ban truoc va tranh nen phai giu sac.
  const text = css();
  assert.match(text, /--blur-the: 13px/, "độ mờ kính bị đổi");
  // Co HAI quy tac `.page-bg-lop::before`: mot khoi gop dat `content`/`inset`,
  // mot khoi rieng dat anh. Tim khoi RIENG theo dau `{` ngay sau ten.
  const at2 = text.indexOf(".page-bg-lop::before {");
  const than = codeOnly(text.slice(at2, text.indexOf("}", at2)));
  assert.match(than, /filter: none/, "tranh nền bị làm mờ trở lại");
});

test("hoa van KHONG chan chuot va KHONG chuyen dong", () => {
  const text = css();
  const at = text.indexOf(".story-card-featured::after");
  const than = text.slice(text.indexOf("{", at), text.indexOf("}", at));
  assert.match(than, /pointer-events: none/, "hoa văn chặn được cú bấm");
  assert.ok(!/animation|transition/.test(than), "hoa văn góc có chuyển động");
});

/* ================================ 4. bia du phong: nam lop */

test("bia du phong co DU nam lop, va lop dau an nen ve bang NET", () => {
  /*
    Ban truoc la "mot mang gradient cong mot hinh nho o giua": hai truyen khac
    nhau chi khac mau va khac hinh giua, nen ca luoi doc ra nhu mot bo the sinh
    tu mot cai khuon.

    Lop dau an nen phai la NET, khong phai khoi dac. Ban dac phong to 2.35 lan
    cho ra mot mang sang co mep cat ngang giua tam bia, va mep do di thang qua
    khung huy hieu — do duoc bang anh chup, va no trong ra nhu loi ket xuat.
  */
  const src = read("../src/components/StoryCoverFallback.tsx");
  assert.match(src, /fill="none"/, "dấu ấn nền vẫn là khối đặc");
  assert.match(src, /stroke="currentColor"/);
  assert.match(src, /preserveAspectRatio="xMidYMid slice"/,
    "dấu ấn nền không tràn mép — nó sẽ ngồi gọn trong một ô vuông giữa bìa");
  // Lech tam: neu dat dung (32 32) thi hai lop thanh hai vong dong tam.
  const m = src.match(/translate\((\d+) (\d+)\) rotate/);
  assert.ok(m, "không tìm thấy phép dịch của dấu ấn nền");
  assert.ok(m[1] !== "32" || m[2] !== "32", "dấu ấn nền đặt đúng giữa");

  const text = css();
  assert.match(text, /\.cover-pattern/, "thiếu lớp hoa văn/đốm sáng");
  assert.match(text, /\.cover-sigil-sau/, "thiếu lớp dấu ấn nền");
  assert.match(text, /\.cover-crest/, "thiếu khung huy hiệu");
  const phu = rule(text, ".cover-fallback::after");
  assert.match(phu, /radial-gradient/, "thiếu vignette");
  assert.match(phu, /inset 0 1px 0/, "thiếu quầng sáng ở mép");

  // O co thumb thi lop nen phai tat: hai hinh long nhau trong 56px la mot mang bui.
  assert.match(text, /\.cover-thumb \.cover-sigil-sau \{ display: none; \}/);
});

test("bia du phong VAN khong co chu cai dau, va van on dinh theo truyen", async () => {
  const { boCucFor, COVER_SIGILS } = await import("../src/lib/cover.ts");
  const cover = read("../src/components/NovelCover.tsx");
  assert.ok(!cover.includes("coverInitial"), "chữ cái đầu quay lại làm bìa");

  const a = boCucFor("nov_abc");
  assert.deepEqual(a, boCucFor("nov_abc"), "cùng truyện ra hai bìa khác nhau");
  assert.ok(COVER_SIGILS.includes(a.truoc) && COVER_SIGILS.includes(a.sau));
  // Hai lop KHONG bao gio cung mot hinh: long vao nhau thi trong ra nhu ve hai lan.
  for (let i = 0; i < 400; i += 1) {
    const bc = boCucFor(`nov_${i.toString(36)}`);
    assert.notEqual(bc.sau, bc.truoc, `hạt nov_${i.toString(36)}: hai lớp cùng hình`);
  }
});

test("bo cuc bia co DU bien the, khong don ve vai to hop", () => {
  // 5 dau an truoc x 4 dau an sau x 5 goc = 100 to hop co the. Neu ham bam lech
  // thi so to hop THUC TE se tut xuong con vai chuc — do la luc ca luoi truyen
  // lai trong nhu sinh tu mot khuon.
  return import("../src/lib/cover.ts").then(({ boCucFor }) => {
    const gap = new Set();
    for (let i = 0; i < 1200; i += 1) {
      const b = boCucFor(`nov_${i.toString(16).padStart(12, "0")}`);
      gap.add(`${b.truoc}|${b.sau}|${b.goc}`);
    }
    assert.ok(gap.size >= 70, `chỉ ${gap.size} tổ hợp bố cục trên 1200 hạt giống`);
  });
});

/* ================================ 5. chuyen dong: rat it, va dung cho */

test("hat sang CHI o ba trang, va KHONG o trang doc chuong", () => {
  /*
    Khong bao gio dat chuyen dong sau mot doan van dai: mot thu dang troi phia
    sau chu la thu keo mat di khoi cau dang doc.
  */
  const text = css();
  const at = text.indexOf(".hat[data-bg=");
  const selector = text.slice(at, text.indexOf("{", at));
  const trang = [...selector.matchAll(/data-bg="(\w+)"/g)].map((m) => m[1]).sort();
  assert.deepEqual(trang, ["account", "auth", "home"],
    `hạt sáng bật ở ${trang.join(", ")}`);

  const than = text.slice(text.indexOf("{", at), text.indexOf("}", at));
  // "Khoang 5-10 phan tu trang tri": o day la cac lop `radial-gradient`, khong
  // phai the DOM — vai tram the cho vai tram dom sang la mot cai gia vo ly.
  const dom = (than.match(/radial-gradient/g) ?? []).length;
  assert.ok(dom >= 4 && dom <= 10, `${dom} đốm sáng — cần 4–10`);
});

test("nhip tho cua nen CHI o trang chu, rat cham, va bien do rat nho", () => {
  const text = css();
  const at = text.indexOf('.page-bg-lop[data-bg="home"][data-vao]::before');
  assert.notEqual(at, -1, "thiếu nhịp thở của nền trang chủ");
  const than = text.slice(text.indexOf("{", at), text.indexOf("}", at));

  /*
    NHIP THO NAM O `::before`, KHONG o the.

    Ly do: the dung `transform` cho cu truot ngang cua chuyen canh co huong, va
    hai hieu ung tranh cung mot thuoc tinh thi mot cai bien mat.

    BAY DA DAT MOT LAN: `::before` da co `nen-lang`. Mot quy tac rieng cho trang
    chu ma chi khai `tho-nen` se GHI DE khai bao do, va lop anh trang chu mat luon
    hieu ung lang xuong — khong ai nhan ra ngay, vi trang chu thuong la trang mo
    dau tien nen khong co gi de chuyen canh tu.
  */
  assert.match(than, /nen-lang/, "khai báo riêng cho trang chủ ghi đè hiệu ứng lắng xuống");
  assert.match(than, /tho-nen/);

  const giay = Number(than.match(/tho-nen (\d+)s/)?.[1]);
  assert.ok(giay >= 40, `nhịp thở ${giay}s — cần ≥ 40s để không ai thấy nó chạy`);

  const den = Number(
    css().match(/@keyframes tho-nen \{[\s\S]*?to\s*\{ transform: scale\(([\d.]+)\)/)?.[1],
  );
  assert.ok(den > 1 && den <= 1.02, `phóng tới ${den} — cần ≤ 1.02`);

  // Va KHONG trang lam viec nao co nhip nay.
  for (const t of ["studio", "write", "library", "reader", "explore"]) {
    assert.ok(!text.includes(`[data-bg="${t}"][data-vao] {`),
      `${t} có chuyển động nền liên tục`);
  }
});

test("moi hieu ung moi deu TAT khi nguoi dung chon giam chuyen dong", () => {
  const text = css();
  const than = text.slice(text.indexOf("@media (prefers-reduced-motion: reduce)"));
  assert.match(than, /\.hat \{ display: none; \}/);
  assert.match(than, /\.page-bg-lop\[data-bg="home"\]\[data-vao\]::before \{ animation: none; \}/,
    "nhịp thở của nền không được tắt khi giảm chuyển động");

  /*
    Va cu TRUOT NGANG cua chuyen canh cung phai tat. Phai ghi de tung `data-huong`:
    quy tac `[data-vao][data-huong="tien"]` co do cu the cao han, nen chi dat lai
    `animation` o `[data-vao]` thi cu truot van chay.
  */
  for (const h of ["tien", "lui", "nhe"]) {
    assert.match(than, new RegExp(`\[data-vao\]\[data-huong="${h}"\]`),
      `hướng ${h} vẫn còn trượt ngang khi giảm chuyển động`);
  }
});

/* ================================ 6. nut chinh */

test("chi NUT CHINH duoc trang tri, khong phai moi cai nut", () => {
  const text = css();
  const than = rule(text, ".btn-primary");
  assert.ok(than);
  // Vet sang quet ngang giu RIENG cho nut chinh — mot trang chi co mot cai.
  const quet = (text.match(/animation: sweep/g) ?? []).length;
  assert.equal(quet, 1, `${quet} chỗ dùng vệt sáng quét — chỉ nút chính được dùng`);
  // Bam xuong thi thu nho: phan hoi tuc thi, khong rung, khong nay.
  assert.match(text, /:active:not\(:disabled\)[\s\S]{0,80}transform: scale\(0\.98\)/);
});

/* ================================ 7. cac phan KHONG duoc cham */

test("ban nay KHONG cham vao logic phat, tien do hay dang nhap", () => {
  /*
    Day la mot ban ve MAT, va cac tep duoi day la nhung cho de bi sua "nhan"
    nhat khi dang doi giao dien. Chung phai giu nguyen hinh dang API cua minh.
  */
  const canh = {
    "../src/components/AudioEngine.tsx": ["useAudioEngine", "TrangThaiAudio", "TOC_DO"],
    "../src/components/ChapterPlayer.tsx": ["useAudioEngine", "listen-hero", "play-btn"],
    "../src/components/MiniPlayer.tsx": ["IntersectionObserver", "co-mini"],
    "../src/lib/useJobTracker.ts": ["gopNhipPoll", "khoaTheoDoi", "POLL_MS"],
    "../src/components/JobProgress.tsx": ["tienDoJob"],
  };
  for (const [tep, moc] of Object.entries(canh)) {
    const src = read(tep);
    for (const m of moc) {
      assert.ok(src.includes(m), `${tep} thiếu ${m} — luồng phát/tiến độ bị sửa`);
    }
    // Va khong the nao trong so do duoc mang mau vang vao.
    assert.ok(!/--vang|d8b56a|e4c982/.test(src),
      `${tep} tự đặt màu — sắc phải đến từ CSS`);
  }
});
