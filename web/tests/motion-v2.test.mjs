/*
 * CHUYEN DONG V2: chuyen canh co huong, vach dieu huong dung chung, khong khi
 * theo trang.
 *
 * VAN DE DA CO: doi trang la mot tam mo ra, mot tam hien vao, va mot vach gach
 * chan bien mat roi mot vach khac xuat hien. Ca hai deu DUNG, va ca hai deu
 * khong noi cho nguoi dung biet ho vua di tu dau sang dau.
 *
 * Bo test nay giu bon dieu:
 *
 *   1. huong duoc tinh tu DUONG DAN, khong tu mot co "vua bam Back" nao ca —
 *      nho vay lich su trinh duyet tu dong dung huong;
 *   2. van DUNG HAI lop, khong bao gio tich lai;
 *   3. vach dieu huong dung `transform`, khong dung `left`;
 *   4. khong khi co TRAN so luong, va khong bao gio nam sau doan van.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const css = () => read("../src/app/globals.css");

/** Bo chu thich truoc khi quet — xem `job-recovery.test.mjs`. */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/**
 * Than cua mot khoi CSS, cat bang cach DEM DAU NGOAC.
 *
 * Khong dung `indexOf` voi mot chuoi co xuong dong: tep nay dung CRLF, nen mot
 * moc nhu dau ngoac dong kem `\n` khong bao gio khop, `indexOf` tra `-1`, va
 * `slice(at, -1)` khi do lay gan het ca tep — bai test doc duoc moi thu tru cai
 * no dinh doc. Da mat mot vong de tim ra.
 */
function khoi(text, moc) {
  const at = text.indexOf(moc);
  if (at === -1) return "";
  let i = text.indexOf("{", at);
  if (i === -1) return "";
  let sau = 0;
  for (let j = i; j < text.length; j += 1) {
    if (text[j] === "{") sau += 1;
    else if (text[j] === "}") {
      sau -= 1;
      if (sau === 0) return text.slice(i, j + 1);
    }
  }
  return text.slice(i);
}

/* ======================================================== truc va huong di */

test("truc la mot hanh trinh, khong phai thu tu tinh co cua mot cai menu", async () => {
  const { TRUC } = await import("../src/lib/sections.ts");
  // "community" nam GIUA "explore" va "library", khong o cuoi: truc nay la
  // hanh trinh doc -> nghe -> viet, va bang tin thuoc nua DOC. Dat no sau
  // `write`/`studio` se lam mot cu bam tu "Khám phá" sang "Cộng đồng" quay may
  // di qua ca khu sang tac.
  assert.deepEqual([...TRUC],
    ["home", "explore", "animation", "community", "library", "write", "studio",
     "account"]);
});

test("moi duong dan roi dung khu vuc", async () => {
  const { viTri } = await import("../src/lib/sections.ts");
  const mong_doi = [
    ["/", "home"],
    ["/fanfic", "explore"],
    ["/fanfic?tag=One%20Piece", "explore"],
    ["/animation", "animation"],
    ["/library", "library"],
    ["/write", "write"],
    ["/studio", "studio"],
    ["/account", "account"],
    // Trang long: BEN TRONG the gioi, khong phai mot khu vuc rieng.
    ["/novels/nov_1", "long"],
    ["/chapters/chp_1", "long"],
    ["/login", "ngoai"],
    ["/auth/callback", "ngoai"],
    ["/khong-he-co", "ngoai"],
  ];
  for (const [duong, ten] of mong_doi) {
    assert.equal(viTri(duong), ten, `${duong} -> ${viTri(duong)}, cần ${ten}`);
  }
});

test("'/' khop CHINH XAC, khong bat moi trang", async () => {
  const { viTri } = await import("../src/lib/sections.ts");
  assert.equal(viTri("/fanfic"), "explore");
  assert.equal(viTri("/"), "home");
});

test("huong di theo dung thu tu tren truc", async () => {
  const { huongDi } = await import("../src/lib/sections.ts");
  assert.equal(huongDi("/", "/fanfic"), 1);
  assert.equal(huongDi("/fanfic", "/library"), 1);
  assert.equal(huongDi("/account", "/"), -1);
  assert.equal(huongDi("/studio", "/write"), -1);
});

test("LICH SU TRINH DUYET tu dong dung huong", async () => {
  /*
    Day la ca ly do huong duoc tinh tu HAI DUONG DAN chu khong tu mot co "nguoi
    dung vua bam Back". Mot cai co nhu vay phai duoc dat va xoa dung cho, va no
    se sai ngay lan dau co ai dieu huong bang code thay vi bang chuot.

    Di `/` -> `/fanfic` la tien; quay lai la `/fanfic` -> `/`, va phep tinh y
    nguyen tra ve lui. Khong co trang thai nao de quen dat.
  */
  const { huongDi } = await import("../src/lib/sections.ts");
  assert.equal(huongDi("/", "/fanfic"), 1);
  assert.equal(huongDi("/fanfic", "/"), -1);
});

test("trang long va trang ngoai KHONG co huong", async () => {
  /*
    Bia ra mot huong cho chung se lam nguoi dung hoc sai ban do: `/novels/x`
    khong nam "ben phai" cua `/fanfic`, no nam BEN TRONG.
  */
  const { huongDi } = await import("../src/lib/sections.ts");
  assert.equal(huongDi("/fanfic", "/novels/nov_1"), 0);
  assert.equal(huongDi("/chapters/chp_1", "/library"), 0);
  assert.equal(huongDi("/", "/login"), 0);
  assert.equal(huongDi("/fanfic", "/fanfic"), 0);
});

test("ten huong la CHU, khong phai so", async () => {
  // `data-huong="1"` bat CSS phai viet `[data-huong="1"]`, va sau sau thang
  // khong ai con nho `1` la tien hay lui.
  const { tenHuong } = await import("../src/lib/sections.ts");
  assert.equal(tenHuong(1), "tien");
  assert.equal(tenHuong(-1), "lui");
  assert.equal(tenHuong(0), "nhe");
});

/* ==================================================== chuyen canh co huong */

test("moi huong co MOT cap keyframes rieng, va bien do nho", () => {
  const text = css();
  for (const ten of ["vao-tu-phai", "ra-sang-trai", "vao-tu-trai",
                     "ra-sang-phai", "vao-nhe", "ra-nhe"]) {
    assert.ok(text.includes(`@keyframes ${ten}`), `thiếu @keyframes ${ten}`);
  }

  /*
    Truot ca man hinh 100vw doc ra nhu mot slide PowerPoint. Bien do phai nho —
    de bai dat 5vw ra / 8vw vao — va bai test nay giu tran do.
  */
  for (const m of text.matchAll(/translate3d\((-?[\d.]+)vw, 0, 0\)/g)) {
    assert.ok(Math.abs(Number(m[1])) <= 10,
      `dịch ${m[1]}vw — quá lớn, đọc ra như một slide`);
  }
});

test("chi dung transform va opacity — khong thuoc tinh nao lam tinh lai bo cuc", () => {
  const text = css();
  for (const ten of ["vao-tu-phai", "ra-sang-trai", "vao-nhe"]) {
    const than = khoi(text, `@keyframes ${ten}`);
    assert.ok(!/\b(left|right|top|bottom|margin|width|height):/.test(than),
      `${ten} động vào thuộc tính làm tính lại bố cục`);
  }
});

test("thoi luong 450-650ms va KHOP giua CSS va component", () => {
  // Lech nhau thi lop cu bi bo TRUOC khi mo het (thay mot nhay) hoac o lai SAU
  // khi da mo het (mot lop `fixed` thua nam do).
  const ms = Number(css().match(/--dur-nen: (\d+)ms/)?.[1]);
  const js = Number(read("../src/components/PageBackground.tsx")
    .match(/const THOI_LUONG = (\d+);/)?.[1]);
  assert.equal(ms, js, `CSS ${ms}ms nhưng component ${js}ms`);
  assert.ok(ms >= 450 && ms <= 650, `${ms}ms — cần 450–650`);
});

test("huong duoc tinh tu DUONG DAN, khong tu ten tam nen", () => {
  /*
    Hai duong dan khac nhau co the dung cung mot tam (`/fanfic` va `/novels/x`
    deu la `explore`). Lay huong tu ten tam se lam moi buoc di vao mot trang
    truyen thanh "khong co huong", va con te han: `/library` -> `/chapters/x`
    dung tam `reader`, ma `reader` khong nam tren truc.
  */
  const src = read("../src/components/PageBackground.tsx");
  assert.match(src, /huongDi\(duongTruoc\.current \?\? "\/", duongDan\)/,
    "hướng không được tính từ hai đường dẫn");
  assert.match(src, /duongTruoc\.current = duongDan/);
});

test("VAN dung HAI lop, khong bao gio nhieu hon", () => {
  const src = read("../src/components/PageBackground.tsx");
  assert.match(src, /tenCu \? \(/, "lớp cũ không được vẽ có điều kiện");
  assert.match(src, /setTenCu\(null\)/, "không dọn lớp cũ sau khi chuyển cảnh");
  assert.match(src, /clearTimeout\(hen\.current\)/,
    "không huỷ hẹn cũ — hai lần điều hướng nhanh sẽ chồng nhau");
});

/* ================================================ vach dieu huong dung chung */

test("MOT vach dung chung, khong phai moi muc mot vach", () => {
  const text = css();
  // Quy tac cu: `.nav-link[aria-current="page"]::after` ve vach cua rieng no.
  assert.ok(!text.includes('.nav-link[aria-current="page"]::after'),
    "mỗi mục vẫn tự vẽ vạch của nó — vạch sẽ biến mất rồi xuất hiện");
  assert.ok(text.includes(".nav-vach"), "thiếu vạch dùng chung");
});

test("vach truot bang transform, KHONG bang left", () => {
  /*
    Doi `left` buoc trinh duyet tinh lai bo cuc moi khung. `transform` chay tren
    tang ghep va khong cham vao bo cuc.
  */
  const src = read("../src/components/NavIndicator.tsx");
  assert.match(src, /transform: `translateX\(/);
  assert.ok(!/left: `/.test(src), "vạch được đặt bằng `left`");

  const text = css();
  const at = text.indexOf(".nav-vach {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /transition:\s*\n?\s*transform/, "vạch không có chuyển tiếp");
});

test("lan do dau tien thi vach hien NGAY tai cho", () => {
  // Mot cu truot tu goc trai man hinh vao luc moi mo trang doc ra nhu mot loi ve.
  const src = read("../src/components/NavIndicator.tsx");
  assert.match(src, /data-dung-yen=/);
  assert.match(css(), /\.nav-vach\[data-dung-yen\] \{ transition: none; \}/);
});

test("vach do lai khi be rong doi VA khi hang bi cuon", () => {
  /*
    Hai truong hop da lam vach lech o cac ban truoc cua nhung thu tuong tu:
    chu tai xong muon lam cac muc rong ra (`resize` khong bao gio phat), va o
    mobile hang cuon ngang duoc (toa do do theo khung nhin, khong theo hang).
  */
  const src = read("../src/components/NavIndicator.tsx");
  assert.match(src, /ResizeObserver/);
  assert.match(src, /scrollLeft/, "không cộng scrollLeft — vạch lệch khi hàng cuộn");
  assert.match(src, /addEventListener\("scroll"/);
});

test("vach KHONG doc ref trong than render", () => {
  /*
    React khong dam bao dieu do: `ref.current` khong tinh la mot phu thuoc, nen
    ban ve co the dung gia tri cu. ESLint cua du an nay bat loi do — bai test giu
    lai ly do de lan sau khong ai "sua" no bang cach tat quy tac.
  */
  const src = read("../src/components/NavIndicator.tsx");
  const sau = src.slice(src.indexOf("if (!o) return null;"));
  assert.ok(!/\.current/.test(sau), "đọc ref trong thân render");
});

/* ==================================================== khong khi theo trang */

test("khong khi co TRAN so phan tu", () => {
  /*
    "Toi da 5-10 phan tu trang tri moi trang" la mot rang buoc that: vai tram
    the `<div>` cho vai tram dom sang la mot cai gia vo ly, va no do bang pin
    cua nguoi doc.
  */
  const src = read("../src/components/AmbientScene.tsx");
  for (const [, ten, than] of src.matchAll(
    /const (CANH_HOA|SAO_BANG|DOM_NGHE): Hat\[\] = \[([\s\S]*?)\];/g,
  )) {
    const so = (than.match(/\{ t:/g) ?? []).length;
    assert.ok(so >= 1 && so <= 10, `${ten} có ${so} phần tử — cần 1–10`);
  }
});

test("KHONG canvas, KHONG WebGL, KHONG goi thu vien chuyen dong", () => {
  const src = read("../src/components/AmbientScene.tsx");
  assert.ok(!/canvas|WebGL|requestAnimationFrame/i.test(codeOnly(src)));
  const pkg = JSON.parse(read("../package.json"));
  const tat_ca = { ...pkg.dependencies, ...pkg.devDependencies };
  for (const goi of ["framer-motion", "motion", "gsap", "three",
                     "react-spring", "@react-spring/web", "tsparticles",
                     "react-tsparticles", "lottie-react"]) {
    assert.ok(!(goi in tat_ca), `đã thêm gói chuyển động ${goi}`);
  }
});

test("KHONG gi chuyen dong sau doan van cua trang doc chuong", () => {
  /*
    Rang buoc quan trong nhat cua ca khoi nay. Lop dom sang o trang doc chuong bi
    cat con mot dai o dinh trang, va doan van bat dau ngay duoi do.
  */
  const text = css();
  const at = text.indexOf(".canh-nghe {");
  assert.notEqual(at, -1, "thiếu lớp giới hạn cho trang đọc chương");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /height: \d+px/, "lớp đốm sáng không bị giới hạn chiều cao");
  assert.match(than, /mask-image/, "không tan dần — sẽ thấy một đường cắt ngang");

  // Va component chi ve dom sang cho `/chapters/*`, khong cho `/novels/*`.
  const src = read("../src/components/AmbientScene.tsx");
  assert.match(src, /duongDan\.startsWith\("\/chapters\/"\)/);
});

test("cac khu LAM VIEC khong co gi chuyen dong", () => {
  /*
    Danh sach nay da THU HEP mot lan, co y: `/library` va `/fanfic` gio co bui
    phep va dom sang — chung la khu DOC, khong phai khu lam viec.

    Hai cai con lai thi khong bao gio: mot thu dang troi ben canh mot o soan
    thao la thu lam met mat sau nam phut.
  */
  const src = codeOnly(read("../src/components/AmbientScene.tsx"));
  for (const noi of ["studio", "write"]) {
    assert.ok(!new RegExp(`noi === "${noi}"`).test(src),
      `${noi} có lớp trang trí động`);
  }
});

test("moi phan tu trang tri deu KHONG chan chuot", () => {
  const text = css();
  const at = text.indexOf(".canh-troi {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /pointer-events: none/);
  assert.match(read("../src/components/AmbientScene.tsx"), /aria-hidden="true"/);
});

test("cac con so duoc VIET TAY, khong sinh ngau nhien", () => {
  /*
    Mot mang ngau nhien doi moi lan ve lai, va tren Next thi ban may chu va ban
    trinh duyet se ra hai ket qua khac nhau — React bao "hydration mismatch".
  */
  const src = codeOnly(read("../src/components/AmbientScene.tsx"));
  assert.ok(!/Math\.random/.test(src), "sinh ngẫu nhiên — sẽ lệch giữa máy chủ và trình duyệt");
});

test("sao bang phai THUA, khong phai mot cai den bao", () => {
  // Vet chi song mot phan rat nho cua moi nhip; nhip thi 17-29 giay.
  const text = css();
  const at = text.indexOf("@keyframes sao-bay");
  const than = text.slice(at, text.indexOf("\n}", at));
  const moc = [...than.matchAll(/^\s*(\d+)%/gm)].map((m) => Number(m[1]));
  const tat = moc.find((v) => v > 1 && v < 100);
  assert.ok(tat <= 8, `vệt sáng sống tới ${tat}% của mỗi nhịp — quá dày`);

  const src = read("../src/components/AmbientScene.tsx");
  const nhip = [...src.matchAll(/nhip: (\d+) \}/g)].map((m) => Number(m[1]));
  assert.ok(nhip.some((n) => n >= 12), "không có nhịp nào đủ dài");
});

/* ==================================================== giam chuyen dong */

test("MOI chuyen dong moi deu tat khi nguoi dung chon giam chuyen dong", () => {
  const than = khoi(css(), "@media (prefers-reduced-motion: reduce)");
  // Khong khi: bo HAN, khong phai lam cham. Mot canh hoa dung yen giua man hinh
  // doc ra nhu mot vet ban tren kinh.
  assert.match(than, /\.canh-troi \{ display: none; \}/);
  // Vach dieu huong: nhay thang sang muc moi.
  assert.match(than, /\.nav-vach \{ transition: none; \}/);
});

test("chuc nang KHONG doi khi giam chuyen dong", () => {
  /*
    Chi chuyen dong bi tat. Neu khoi giam chuyen dong an mot phan tu nao mang
    noi dung hay mot cai nut thi do la mot loi tiep can, khong phai mot tuy chon.
  */
  const than = khoi(css(), "@media (prefers-reduced-motion: reduce)");
  for (const m of than.matchAll(/^\s*([^{@}\n][^{\n]*)\{([^}]*)\}/gm)) {
    if (!/display: none/.test(m[2])) continue;
    const sel = m[1].trim();
    assert.ok(/hat|canh-troi|progress-bar::after|btn-primary::after|nav-vach-streak/.test(sel),
      `${sel} bị ẩn khi giảm chuyển động — có thể đang giấu nội dung`);
  }
});

/* ================================================ V3: vien thuoc + khong khi */

test("MOT vien thuoc, khong phai mot vach cho moi muc", () => {
  /*
    Vach 2px cu doc ra la mot gach ngang doi cho. Mot vien thuoc co THE TICH,
    nen mat theo duoc no di qua khoang trong giua hai muc.
  */
  const than = khoi(css(), ".nav-vach {");
  // Navigation Motion Correction V3: bo goc doi tu `--r-full` (vien tron,
  // "nut thuoc") sang `--r2` — mot dau hieu vuong vuc, dung tinh than
  // "modern anime UI marker" thay vi "nut phat sang". Van la MOT hinh co
  // the tich (khong phai gach ngang), chi khac bo goc.
  assert.match(than, /border-radius: var\(--r2\)/, "vẫn là một hình có thể tích");
  assert.match(than, /height: 32px/);
  assert.match(than, /transition:[\s\S]*transform/);
  // Navigation Motion Correction V2: doi sang cubic-bezier(.22,.8,.2,1) —
  // van la ease-out co kiem soat, KHONG nay lai.
  assert.match(than, /cubic-bezier\(\.22, \.8, \.2, 1\)/);
  const ms = Number(than.match(/transform (\d+)ms/)?.[1]);
  assert.ok(ms >= 350 && ms <= 560, `${ms}ms — cần 350–560`);
});

test("vien thuoc nam DUOI chu", () => {
  // Neu khong thi no phu len chinh cai chu no dang danh dau.
  assert.match(khoi(css(), ".nav-vach {"), /z-index: 0/);
  assert.match(css(), /\.nav-link \{ z-index: 1; \}/);
});

test("sac cua tung khu vuc nam o MOT cho", () => {
  /*
    Rai mau vao tung component la cach chac chan de sau ba thang khong ai biet
    `/library` dang mau gi, va de hai cho ve hai mau khac nhau.
  */
  const text = css();
  for (const k of ["home", "explore", "library", "write", "studio", "account"]) {
    assert.match(text, new RegExp(`--sac-${k}-1:`), `thiếu sắc cho ${k}`);
    assert.match(text, new RegExp(`--sac-${k}-2:`), `thiếu sắc phụ cho ${k}`);
  }
  // Va component KHONG duoc tu dat ma mau nao.
  for (const f of ["../src/components/NavIndicator.tsx",
                   "../src/components/NavAuth.tsx"]) {
    assert.ok(!/#[0-9a-f]{6}/i.test(codeOnly(read(f))), `${f} tự đặt mã màu`);
  }
});

test("chuyen canh nen MANH HON nhung van trong khoang cho phep", () => {
  const text = css();
  const ms = Number(text.match(/--dur-nen: (\d+)ms/)?.[1]);
  assert.ok(ms >= 500 && ms <= 650, `${ms}ms — cần 500–650`);
  assert.equal(
    ms,
    Number(read("../src/components/PageBackground.tsx")
      .match(/const THOI_LUONG = (\d+);/)?.[1]),
    "CSS và component lệch thời lượng",
  );
  // Bien do van phai NHO: truot ca man hinh doc ra nhu mot slide.
  for (const m of text.matchAll(/translate3d\((-?[\d.]+)vw, 0, 0\)/g)) {
    assert.ok(Math.abs(Number(m[1])) <= 10, `dịch ${m[1]}vw — quá lớn`);
  }
  // Chieu sau: rat nho. CHI quet trong cac keyframes cua NEN — `scale(1.04)` cua
  // bia truyen khi ro chuot la mot thu khac han.
  for (const ten of ["vao-tu-phai", "ra-sang-trai", "vao-tu-trai", "ra-sang-phai"]) {
    for (const m of khoi(text, `@keyframes ${ten}`).matchAll(/scale\((1\.\d+)\)/g)) {
      assert.ok(Number(m[1]) <= 1.02, `${ten} phóng ${m[1]} — quá nhiều`);
    }
  }
});

test("khong khi V2: moi khu vuc mot bo, va co TRAN", () => {
  const src = read("../src/components/AmbientScene.tsx");
  /*
    Dem MOT lan vao mot bang tra, thay vi ghep mot bieu thuc chinh quy dong cho
    tung ten. Mot bieu thuc ghep chuoi rat de mat dau gach cheo khi tep di qua
    mot buoc xu ly nao do, va khi do bai test do vi CHINH NO chu khong vi ma
    nguon — da mat mot vong de tim ra dung dieu do.
  */
  const so_luong = new Map();
  for (const [, ten, than] of src.matchAll(
    /const ([A-Z_]+): Hat\[\] = \[([\s\S]*?)\];/g,
  )) {
    const so = (than.match(/\{ t:/g) ?? []).length;
    assert.ok(so >= 1 && so <= 10, `${ten} có ${so} phần tử — cần 1–10`);
    so_luong.set(ten, so);
  }

  // Trang giau nhat (trang chu) khong duoc vuot 14 phan tu.
  const home = src.slice(src.indexOf('noi === "home"'), src.indexOf('noi === "explore"'));
  const bo = [...home.matchAll(/([A-Z_]+)(?:\.slice\([^)]*\))?\.map/g)].map((m) => m[1]);
  const tong = bo.reduce((n, ten) => n + (so_luong.get(ten) ?? 0), 0);
  assert.ok(tong >= 1 && tong <= 14, `trang chủ có ${tong} phần tử — cần 1–14`);
});

test("cac khu LAM VIEC van khong co gi chuyen dong", () => {
  const src = codeOnly(read("../src/components/AmbientScene.tsx"));
  for (const noi of ["studio", "write"]) {
    assert.ok(!new RegExp(`noi === "${noi}"`).test(src), `${noi} có lớp động`);
  }
});

test("mobile cat bot so phan tu, va cat bang CSS chu khong bang React", () => {
  /*
    So luong phan tu KHONG duoc phu thuoc vao be rong man hinh luc ve: ban may
    chu va ban trinh duyet se lech nhau va React bao "hydration mismatch".
  */
  // Co NHIEU khoi `@media (max-width: 900px)` trong tep. Lay dung khoi CHUA
  // `.la-troi` thay vi khoi dau tien.
  const text = css();
  const at = text.lastIndexOf("@media (max-width: 900px)");
  const than = khoi(text.slice(at), "@media (max-width: 900px)");
  for (const lop of ["la-troi", "vet-gio", "chim"]) {
    assert.ok(than.includes(`.${lop}`), `${lop} không bị cắt ở mobile`);
  }
  assert.match(than, /\.dom:nth-child\(n \+ \d+\) \{ display: none; \}/);

  const src = codeOnly(read("../src/components/AmbientScene.tsx"));
  assert.ok(!/innerWidth|matchMedia|window\./.test(src),
    "số phần tử phụ thuộc bề rộng lúc vẽ");
});

test("MOI hieu ung khong khi deu nam trong .canh-troi", () => {
  // `.canh-troi { display: none }` o khoi giam chuyen dong tat het. Mot lop
  // khong khi nam NGOAI phan tu do la mot cho quen tat.
  const src = read("../src/components/AmbientScene.tsx");
  for (const m of src.matchAll(/return \(\s*<div className="([^"]+)"/g)) {
    assert.ok(m[1].startsWith("canh-troi"),
      `lớp không khí "${m[1]}" nằm ngoài .canh-troi`);
  }
});

/* ================================================ hoi quy: nhan muc dang xem */

test("nhan muc dang xem KHONG BAO GIO trong suot", () => {
  /*
    LOI DA XAY RA tren `/write`: nhan duoc to bang gradient qua
    `background-clip: text` cong `color: transparent`. Muc "Viết truyện" la mot
    CTA co quy tac `.nav-cta` rieng dat `background` cua no; quy tac do ghi de
    gradient nhung KHONG ghi de `color`, nen chu con lai trong suot tren mot nen
    dac — nhan bien mat hoan toan.

    Bai hoc chung: `background-clip: text` bien mot thuoc tinh TRANG TRI thanh
    thu quyet dinh chu co nhin thay hay khong, va no mat AM THAM.
  */
  // `codeOnly`: chinh chu thich trong khoi do giai thich vi sao KHONG dung
  // `background-clip: text`, nen quet ca khoi se bat trung loi giai thich.
  const than = codeOnly(khoi(css(), '.nav-link[aria-current="page"] {'));
  assert.ok(!/background-clip/.test(than),
    "nhãn mục đang xem lại phụ thuộc background-clip: text");
  assert.ok(!/color: transparent/.test(than), "nhãn mục đang xem trong suốt");
  // Navigation Motion Correction V2: chu doi tu mau theo khu vuc (`--sac-2`)
  // sang `--text` co dinh (gan-trang) — nhung van phai la MOT MAU DAC.
  assert.match(than, /color: var\(--text\)/, "nhãn không có màu đặc");
});

test("vien thuoc do tu BANG THAM CHIEU, khong tu querySelector", () => {
  /*
    Doc trang thai DOM (`[aria-current]`, `a[href=...]`) la doc mot thu React co
    the cap nhat o mot lan ve den sau. Bang tham chieu thi duoc dien ngay o buoc
    gan tham chieu.
  */
  const src = read("../src/components/NavIndicator.tsx");
  assert.match(src, /bang\.current\.get\(moc\)/);
  assert.ok(!/querySelector/.test(codeOnly(src)),
    "vẫn tìm mục đang xem bằng querySelector");
  assert.match(src, /useLayoutEffect/, "đo bằng useEffect — sẽ trễ một khung");
  assert.match(src, /ResizeObserver/);
  assert.ok(!/requestAnimationFrame/.test(codeOnly(src)),
    "còn phụ thuộc rAF — không chạy khi tab bị ẩn");
});

test("doc bao.current BEN TRONG callback, khong o than effect", () => {
  /*
    React gan ref TU DUOI LEN: `NavIndicator` la con cua the `<nav>`, nen o lan
    commit dau tien layout effect cua no chay TRUOC khi ref cua `<nav>` duoc gan.
    Doc `bao.current` o than effect thay `null` va thoat som — roi khong bao gio
    chay lai. Trieu chung: TAI THANG `/library` thi vien thuoc khong hien ra.
  */
  const src = read("../src/components/NavIndicator.tsx");
  const at = src.indexOf("const do_lai = () => {");
  const than = src.slice(at, src.indexOf("queueMicrotask", at));
  assert.match(than, /const hop = bao\.current;/,
    "không đọc bao.current bên trong callback");
});
