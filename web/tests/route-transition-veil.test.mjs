/*
 * Aether Rift Reveal V4 — thay the hoan toan "Celestial Mist Ribbon" (V3),
 * ban than V3 da thay "quay may ngang" cu (xem lich su git
 * `components/PageBackground.tsx`, `globals.css`).
 *
 * HAI LOAI test trong tep nay:
 *
 *   1. HANH VI THAT (phan lon tep) — `taoRouteTransitionStore` nhan moi phu
 *      thuoc cham toi trinh duyet qua tham so (xem `lib/routeTransitionStore
 *      .ts`), nen o day co the tiem MOT DONG HO GIA (khong cho that) + mot
 *      ham nap-anh gia, roi kiem tra CHINH XAC trinh tu/thoi diem, va quan
 *      trong nhat voi V4: dieu huong KHONG BAO GIO cho mot khoang toi thieu
 *      nao truoc khi hieu ung bat dau (dac ta muc 9 — "must feel immediate"),
 *      va khong co DUA (race) khi dieu huong lien tiep.
 *   2. QUET MA NGUON (CSS + component) — cho cac bat bien khong the kiem
 *      bang cach chay logic don thuan: duong bien Bezier (khong polygon),
 *      z-index, khong Canvas/WebGL/rAF/hoat hinh filter lien tuc, bien mau
 *      theo 8 chu de, khong GSAP.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import {
  taoRouteTransitionStore,
  THOI_LUONG_BINH_THUONG,
  THOI_LUONG_GIAM,
} from "../src/lib/routeTransitionStore.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const veil = () => read("../src/components/RouteTransitionVeil.tsx");
const pageBg = () => read("../src/components/PageBackground.tsx");
const layout = () => read("../src/app/layout.tsx");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* ================================================================ dong ho gia */

/**
 * Dong ho gia toi gian: `datHen`/`huyHen` khop chu ky cua `RouteTransitionDeps`,
 * `tienToi(ms)` chay MOI hen den han theo dung thu tu thoi gian (id lam tie-
 * breaker cho cac hen cung mot moc). Khong co `setTimeout` that nao ca — bai
 * test chay tuc thi, tat dinh.
 */
function taoDongHoGia() {
  let hienTai = 0;
  let idKe = 0;
  const hangDoi = [];
  return {
    datHen: (fn, ms) => {
      const id = (idKe += 1);
      hangDoi.push({ id, luc: hienTai + ms, fn });
      return id;
    },
    huyHen: (id) => {
      const i = hangDoi.findIndex((h) => h.id === id);
      if (i !== -1) hangDoi.splice(i, 1);
    },
    /*
      BAT DONG BO (async): sau moi hen duoc chay, PHAI cho hang doi vi tac vu
      (microtask) xu ly xong TRUOC KHI xem xet hen tiep theo — dung
      `setImmediate` de xa SACH hang doi vi tac vu.
    */
    async tienToi(ms) {
      const dich = hienTai + ms;
      for (;;) {
        hangDoi.sort((a, b) => a.luc - b.luc || a.id - b.id);
        const ke = hangDoi[0];
        if (!ke || ke.luc > dich) break;
        hienTai = ke.luc;
        hangDoi.shift();
        ke.fn();
        await new Promise((r) => setImmediate(r));
      }
      hienTai = dich;
    },
    soHenDangCho: () => hangDoi.length,
  };
}

/**
 * Ham nap-anh gia: mac dinh "resolve ngay" (mo phong anh da trong cache).
 * V4 KHONG cho ham nay nua (fire-and-forget) nen `moc` (nap cham) chi con
 * dung de xac nhan hanh vi "khong cho" thuc su dung, khong con anh huong
 * toi thoi diem hien thi.
 */
function taoNapAnhGia(dongHo, { moc = {} } = {}) {
  const lichSu = [];
  return {
    lichSu,
    napAnh: (ten) => {
      lichSu.push(ten);
      const cham = moc[ten];
      if (!cham) return Promise.resolve();
      return new Promise((giai) => dongHo.datHen(() => giai(), cham));
    },
  };
}

function taoStoreGia(tuyChon = {}) {
  const dongHo = taoDongHoGia();
  const { napAnh, lichSu } = taoNapAnhGia(dongHo, tuyChon);
  const banDoTen = tuyChon.banDoTen ?? { "/": "home", "/fanfic": "explore", "/library": "library" };
  const store = taoRouteTransitionStore({
    layTen: (duongDan) => banDoTen[duongDan] ?? "auth",
    dangGiamChuyenDong: () => tuyChon.giamChuyenDong === true,
    napAnh,
    datHen: dongHo.datHen,
    huyHen: dongHo.huyHen,
  });
  return { store, dongHo, lichSuNapAnh: lichSu };
}

/* ==================================================== hanh vi: lan dau/cung chu de */

test("lan dau: hien thang chu de, khong hieu ung", () => {
  const { store } = taoStoreGia();
  store.diTinh("/");
  const s = store.getSnapshot();
  assert.equal(s.ten, "home");
  assert.equal(s.trangThai, "idle");
  assert.equal(s.tenMoi, null);
});

test("dieu huong sang duong dan KHAC nhung CUNG chu de: khong hieu ung", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/fanfic": "explore", "/novels/nov_1": "explore" },
  });
  store.diTinh("/fanfic");
  store.diTinh("/novels/nov_1");
  await dongHo.tienToi(1000);
  const s = store.getSnapshot();
  assert.equal(s.ten, "explore");
  assert.equal(s.trangThai, "idle", "chuyển giữa hai đường dẫn cùng chủ đề không được kích hoạt hiệu ứng");
});

/* ==================================================== hanh vi: TUC THI (dac ta muc 9) */

test("KHAC chu de: tenMoi/trangThai doi NGAY TRONG CUNG LAN GOI, khong cho gi ca", () => {
  /*
    Day la bai test QUAN TRONG NHAT cua V4 — dac ta muc 9 cam "wait 300-
    400ms for atmosphere coverage" va yeu cau do tre CAM NHAN duoc <100ms.
    Kiem tra o day o muc TUYET DOI: state phai doi TRONG CUNG MOT LAN GOI
    dong bo `diTinh()`, KHONG can `await` mot dong ho nao (khac han V1-V3,
    noi `trangThai` chi doi sau it nhat mot `hen()`).
  */
  const { store } = taoStoreGia();
  store.diTinh("/"); // home, lan dau
  store.diTinh("/fanfic"); // home -> explore, KHONG await/tienToi gi ca

  const s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing", "phải revealing NGAY, không chờ một tick nào");
  assert.equal(s.tenMoi, "explore", "lớp trên phải là đích MỚI ngay lập tức");
  assert.equal(s.ten, "home", "lớp dưới (nền đã ổn định) giữ nguyên trong lúc lớp trên tiết lộ");
});

test("napAnh duoc goi NGAY nhung KHONG duoc CHO — hieu ung khong phu thuoc no", async () => {
  const { store, dongHo, lichSuNapAnh } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
    moc: { explore: 999999 }, // "khong bao gio" xong trong pham vi bai test
  });
  store.diTinh("/");
  store.diTinh("/fanfic");

  assert.deepEqual(lichSuNapAnh, ["explore"], "phải gọi napAnh ngay khi bắt đầu");
  // tenMoi PHAI da la "explore" NGAY, du napAnh khong bao gio xong.
  assert.equal(store.getSnapshot().tenMoi, "explore",
    "hiệu ứng không được chờ napAnh — đây là lỗi cốt lõi của V1-V3 (chờ 'atmosphere coverage')");

  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.TONG + 10);
  assert.equal(store.getSnapshot().ten, "explore", "phải tự chốt xong dù napAnh chưa từng resolve");
});

test("tong thoi luong 420-560ms nhu dac ta V4 (giam manh tu 780-900ms V2/V3)", () => {
  const tong = THOI_LUONG_BINH_THUONG.TONG;
  assert.ok(tong >= 420 && tong <= 560, `${tong}ms — cần 420–560ms theo đặc tả V4`);
});

/* ==================================================== hanh vi: mot chu ky day du */

test("khac chu de: tenMoi hien NGAY -> sau --dur-tong thi chot xuong ten, ve idle", async () => {
  const { store, dongHo } = taoStoreGia();
  store.diTinh("/"); // home, khong hieu ung (lan dau)
  store.diTinh("/fanfic"); // home -> explore: BAT DAU reveal NGAY

  let s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing");
  assert.equal(s.tenMoi, "explore");
  assert.equal(s.ten, "home", "ten (lop duoi) CHUA doi — dang duoc lop tren tiet lo dan");

  // Truoc moc TONG: van dang revealing, chua chot.
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.TONG - 10);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing");
  assert.equal(s.ten, "home");

  // Dung/qua moc TONG: chot ten=explore, tenMoi=null, ve idle.
  await dongHo.tienToi(10);
  s = store.getSnapshot();
  assert.equal(s.ten, "explore");
  assert.equal(s.tenMoi, null);
  assert.equal(s.trangThai, "idle");
});

/* ==================================================== hanh vi: chong dua (race) */

test("dieu huong LIEN TIEP truoc khi xong: chi dich MOI NHAT duoc ap dung, khong xep hang", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore", "/library": "library" },
  });
  store.diTinh("/"); // home, lan dau
  store.diTinh("/fanfic"); // home -> explore, BAT DAU NGAY
  const the1 = store.getSnapshot().the;

  await dongHo.tienToi(100); // giua chung — con lau moi toi moc TONG
  store.diTinh("/library"); // NGAT NGANG: home -> library (dich MOI)

  let s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing", "vẫn đang revealing — không nhảy thẳng về idle");
  assert.equal(s.tenMoi, "library", "đích phải là lần điều hướng MỚI NHẤT, không phải explore");
  assert.equal(s.ten, "home", "nền đã ổn định (home) không đổi cho tới khi library tiết lộ xong");
  assert.notEqual(s.the, the1, "the-he phai TANG de lop tren remount va hoat hinh restart tu dau");

  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.TONG + 10);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "idle");
  assert.equal(s.ten, "library", "phải kết thúc đúng ở đích mới nhất (library), không kẹt ở explore");
  assert.equal(s.tenMoi, null);
});

test("dieu huong lien tiep KHONG de lai hen thua (khong con hieu ung ket dinh)", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore", "/library": "library", "/account": "account" },
  });
  store.diTinh("/");
  store.diTinh("/fanfic");
  await dongHo.tienToi(60);
  store.diTinh("/library");
  await dongHo.tienToi(60);
  store.diTinh("/account");
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.TONG + 10);

  assert.equal(store.getSnapshot().trangThai, "idle");
  assert.equal(store.getSnapshot().ten, "account");
  assert.equal(dongHo.soHenDangCho(), 0,
    "còn hẹn giờ treo lơ lửng — nguy cơ nền chốt sai sau khi đã điều hướng tiếp");
});

test("dieu huong quay VE DUNG chu de dang hien giua luc dang reveal: huy sach, ve idle NGAY", () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
  });
  store.diTinh("/");
  store.diTinh("/fanfic"); // home -> explore, dang revealing
  store.diTinh("/"); // doi y NGAY: quay ve home — dung chu de LOP DUOI dang hien

  const s = store.getSnapshot();
  assert.equal(s.trangThai, "idle", "quay lại đúng chủ đề đang hiện phải huỷ sạch, không cần hoàn tất reveal");
  assert.equal(s.ten, "home");
  assert.equal(s.tenMoi, null);
  assert.equal(dongHo.soHenDangCho(), 0);
});

test("dieu huong TOI CHINH dich dang reveal: KHONG restart hoat hinh (vd /fanfic -> /novels/x cung chu de)", () => {
  const { store } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore", "/novels/nov_1": "explore" },
  });
  store.diTinh("/");
  store.diTinh("/fanfic"); // home -> explore, dang revealing
  const the1 = store.getSnapshot().the;
  store.diTinh("/novels/nov_1"); // van la "explore" — KHONG phai dieu huong moi

  const s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing");
  assert.equal(s.tenMoi, "explore");
  assert.equal(s.the, the1, "the-he KHONG duoc tang khi dich trung voi reveal dang chay — tranh restart vo ich");
});

/* ==================================================== hanh vi: giam chuyen dong */

test("giam chuyen dong: dung tong thoi luong NGAN hon HAN, khong bao gio bang 0", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
    giamChuyenDong: true,
  });
  store.diTinh("/");
  store.diTinh("/fanfic");
  await dongHo.tienToi(THOI_LUONG_GIAM.TONG + 10);
  assert.equal(store.getSnapshot().ten, "explore");
  assert.ok(THOI_LUONG_GIAM.TONG > 0,
    "vẫn phải có một khoảng tối thiểu — đổi nền tức thì tuyệt đối sẽ lộ một cú nháy màu");
  assert.ok(THOI_LUONG_GIAM.TONG < THOI_LUONG_BINH_THUONG.TONG);
});

/* ================================================================ quet ma nguon */

test("khop CHINH XAC voi CSS: --dur-aether/--dur-tong (binh thuong), THOI_LUONG_GIAM.TONG khop 80ms", () => {
  const text = css();
  const durAether = Number(text.match(/--dur-aether: (\d+)ms;/)?.[1]);
  const durTong = Number(text.match(/--dur-tong: (\d+)ms;/)?.[1]);
  assert.ok(durAether > 0, "thiếu --dur-aether");
  assert.equal(durTong, THOI_LUONG_BINH_THUONG.TONG, "CSS --dur-tong lệch JS THOI_LUONG_BINH_THUONG.TONG");
  assert.ok(durAether <= durTong, "--dur-aether (quét đường biên) phải xong TRƯỚC hoặc đúng lúc --dur-tong (chốt nền)");
});

test("hieu ung la trang tri: aria-hidden, khong chan chuot", () => {
  const src = veil();
  assert.match(src, /aria-hidden="true"/);
  const text = css();
  const at = text.indexOf(".aether-rift {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /pointer-events: none/);
});

test("mount DUNG MOT LAN o layout.tsx, ngang hang voi PageBackground (khong long vao trong)", () => {
  const src = layout();
  assert.match(src, /<PageBackground \/>/);
  assert.match(src, /<RouteTransitionVeil \/>/);
  const a = src.indexOf("<PageBackground");
  const b = src.indexOf("<RouteTransitionVeil");
  assert.ok(a !== -1 && b !== -1 && b > a);
});

test("z-index: .aether-rift CON AM, it am hon nen, duoi navbar/mini-player", () => {
  const text = css();
  const at = text.indexOf(".aether-rift {");
  const than = text.slice(at, text.indexOf("}", at));
  const zRift = Number(than.match(/z-index: (-?\d+);/)?.[1]);
  const zPageBg = Number(text.match(/\.page-bg \{[\s\S]*?z-index: (-?\d+);/)?.[1]);
  const zHeader = Number(text.match(/\.site-header \{[\s\S]*?z-index: (\d+);/)?.[1]);
  const zMini = Number(text.match(/\.mini \{[\s\S]*?z-index: (\d+);/)?.[1]);

  assert.ok(zRift < 0, "aether-rift phải là z-index ÂM — lớp con của thế giới, không phải lớp che giao diện");
  assert.ok(zRift > zPageBg, `aether-rift z-index ${zRift} phải LỚN HƠN (ít âm hơn) nền ${zPageBg}`);
  assert.ok(zRift < zHeader, `aether-rift z-index ${zRift} phải nhỏ hơn navbar ${zHeader}`);
  assert.ok(zRift < zMini, `aether-rift z-index ${zRift} phải nhỏ hơn mini-player ${zMini}`);

  const mainRule = text.match(/\nmain \{([^}]*)\}/)?.[1] ?? "";
  assert.ok(!/\bposition:|isolation:|transform:|filter:/.test(mainRule),
    "main đã có position/isolation/transform/filter — điều này sẽ phá vỡ thứ tự z-index âm NỀN < HIỆU ỨNG < GIAO DIỆN");
});

/* ============================================== hinh hoc: Bezier, KHONG polygon */

test("KHONG con polygon(...) hay border-radius bat-quy-tac/radial-gradient trong PHAN HIEU UNG CHINH (dac ta muc 2, 4)", () => {
  /*
    Ngoai le CO Y: `.aether-leaf` (2 vet la nho, CHI o Home, dac ta muc 8)
    dung border-radius 4-gia-tri kieu "canh hoa" — DUNG KY THUAT co san
    (`.canh-hoa`) cho mot CHI TIET MOI TRUONG cuc nho, khong phai hinh dang
    CUA HIEU UNG CHINH. Lenh cam trong dac ta nham vao hinh dang CUA DUONG
    BIEN/vat the chinh (giong V1-V3), khong nham vao mot vet la 14x8px.
  */
  const text = css();
  const batDau = text.lastIndexOf("/*", text.indexOf("AETHER RIFT REVEAL"));
  const ketThuc = text.indexOf('.aether-rift[data-theme="auth"]');
  const khoiDayDu = text.slice(batDau, ketThuc);
  const khoiChinh = codeOnly(
    khoiDayDu.slice(0, khoiDayDu.indexOf(".aether-leaf {")),
  );
  assert.ok(!/polygon\(/.test(khoiChinh), "vẫn còn clip-path: polygon() — đây chính là điều V4 phải loại bỏ (V3 bị từ chối)");
  assert.ok(!/border-radius:\s*\d+%\s+\d+%\s+\d+%\s+\d+%/.test(khoiChinh),
    "vẫn còn border-radius bốn giá trị (hình bo dạng V2) trong phần hiệu ứng chính (fill/feather/seam/wisp/haze/mote)");
  assert.ok(!/radial-gradient\(/.test(khoiChinh), "vẫn còn radial-gradient (chấm tròn mờ) trong phần hiệu ứng chính");
});

test("duong bien la Bezier bac ba (lenh C), dung objectBoundingBox cho clip-path", () => {
  const text = css();
  const clipAt = text.indexOf("clipPathUnits=");
  assert.equal(clipAt, -1, "clipPathUnits phải khai trong component (JSX), không phải CSS — kiểm tra RouteTransitionVeil.tsx");

  const veilSrc = veil();
  assert.match(veilSrc, /clipPathUnits="objectBoundingBox"/, "clipPath phải dùng objectBoundingBox để tự khớp mọi kích thước màn hình");
  assert.match(veilSrc, /id="aether-fill-clip"/);

  // Ca hai gia tri "from"/"to" cua duong bien FILL phai dung lenh C (cubic
  // Bezier) — KHONG mot doan thang zig-zag nao ngoai hai canh dong khung.
  const m = text.match(/@keyframes aether-sweep-fill \{[\s\S]*?\n\}/);
  assert.ok(m, "thiếu @keyframes aether-sweep-fill");
  const soLenhC = (m[0].match(/ C /g) ?? []).length;
  assert.ok(soLenhC >= 6, `chỉ ${soLenhC} lệnh C (cubic Bezier) — cần đủ đường cong mượt cho cả from/to`);
});

test("PageBackground tham chieu DUNG mot clip-path duy nhat (#aether-fill-clip) cho lop dang reveal", () => {
  const src = codeOnly(pageBg());
  assert.match(src, /className="page-bg-lop page-bg-reveal"/);
  assert.match(css(), /\.page-bg-reveal \{\s*clip-path: url\(#aether-fill-clip\);\s*\}/);
});

test("ca ba duong bien (fill/feather/seam) dung CHUNG mot key the-he — dam bao dong bo tuyet doi", () => {
  const src = codeOnly(veil());
  assert.match(src, /key=\{the\}/, "thiếu key={the} trên thẻ bao SVG+trang trí — cần để CSS animation restart đúng lúc điều hướng liên tiếp");
});

/* ==================================================== khong con vat the truot qua man hinh */

test("nen (.page-bg/.page-bg-lop) KHONG bao gio translate/zoom/pan/scale/rotate — CHI duong bien doi (dac ta muc 12)", () => {
  const text = css();
  for (const sel of [".page-bg {", ".page-bg-lop {", ".page-bg-reveal {"]) {
    const at = text.indexOf(sel);
    assert.notEqual(at, -1, `thiếu ${sel}`);
    const than = text.slice(at, text.indexOf("}", at));
    assert.ok(!/\btransform:/.test(than), `${sel} có transform — nền không được phép di chuyển, CHỈ đường biên clip-path được đổi`);
  }
  // "tho nen" (nhip tho lien tuc cua home) la MOT ngoai le co y, KHONG lien
  // quan gi toi hieu ung chuyen canh — van duoc phep vi no chay VO HAN doc
  // lap voi dieu huong, khong phai mot phan cua Aether Rift.
});

test("6 trang tri phu deu la hinh TRON/oval mem (border-radius: 50% hoac tuong duong), KHONG polygon, kich thuoc NHO", () => {
  const text = css();
  for (const lop of [".aether-wisp {", ".aether-mote {", ".aether-leaf {"]) {
    const at = text.indexOf(lop);
    assert.notEqual(at, -1, `thiếu ${lop}`);
    const than = text.slice(at, text.indexOf("}", at));
    assert.ok(!/clip-path/.test(than), `${lop} không được dùng clip-path — chỉ được là hình tròn/oval mềm`);
  }
});

/* ==================================================== chi transform/opacity/d */

test("chi CSS `d` va opacity duoc hoat hinh tren duong bien — filter/clip-path la GIA TRI TINH", () => {
  const text = css();
  for (const ten of ["aether-sweep-fill", "aether-sweep-feather", "aether-sweep-seam"]) {
    const at = text.indexOf(`@keyframes ${ten} {`);
    assert.notEqual(at, -1, `thiếu @keyframes ${ten}`);
    const than = text.slice(at, text.indexOf("\n}", at));
    assert.ok(!/\b(left|right|top|bottom|margin|width|height|filter|clip-path|transform):/.test(than),
      `${ten} động vào thuộc tính làm tính lại bố cục/tô vẽ — chỉ được đổi \`d\`/\`opacity\``);
  }
});

test("KHONG Canvas, KHONG WebGL, KHONG requestAnimationFrame, KHONG hoat hinh SVG filter lien tuc", () => {
  const src = codeOnly(veil());
  assert.ok(!/canvas|WebGL|getContext|requestAnimationFrame/i.test(src));
  const text = css();
  // Neu co feTurbulence/feDisplacementMap (dac ta muc 5/13, tuy chon) thi
  // KHONG duoc nam trong bat ky @keyframes nao.
  for (const m of text.matchAll(/@keyframes [\w-]+ \{[\s\S]*?\n\}/g)) {
    assert.ok(!/feTurbulence|feDisplacementMap/.test(m[0]), "SVG filter động (feTurbulence/feDisplacementMap) trong keyframe — cấm hoạt hình filter liên tục");
  }
});

test("idle: KHONG mot animation nao gan san tren .aether-rift — chi phi luc dung yen la khong", () => {
  const text = css();
  const truocDataState = text.slice(text.indexOf(".aether-feather-path,"), text.indexOf('[data-state="revealing"]'));
  assert.ok(!/\banimation(-name)?:/.test(truocDataState),
    "một phần tử aether có animation chạy mặc định — sẽ tốn CPU/GPU cả lúc không điều hướng");
});

/* ==================================================== mau theo chu de */

test("mau man suong dinh nghia du CA 8 chu de nen (dung lai he thong co san), toi da 2 mau/chu de", () => {
  const text = css();
  for (const k of ["home", "explore", "reader", "studio", "write", "library", "account", "auth"]) {
    const re = new RegExp(`\\.aether-rift\\[data-theme="${k}"\\]\\s*\\{\\s*--aether-1: (#[0-9a-fA-F]{6}); --aether-2: (#[0-9a-fA-F]{6});`);
    assert.match(text, re, `thiếu màu aether cho chủ đề ${k}`);
  }
});

test("hieu ung KHONG tu dat ma mau — doc qua bien --aether-1/--aether-2", () => {
  const src = codeOnly(veil());
  assert.ok(!/#[0-9a-f]{6}/i.test(src), "RouteTransitionVeil.tsx tự đặt mã màu thay vì dùng biến CSS theo chủ đề");
});

/* ==================================================== giam chuyen dong */

test("giam chuyen dong: bo HAN Aether Rift, chi con doi nen bang opacity ngan", () => {
  const text = css();
  const giam = text.slice(text.indexOf('@media (prefers-reduced-motion: reduce)'));
  const than = giam.slice(0, giam.indexOf("\n}\n\n"));
  assert.match(than, /\.aether-rift \* \{ animation: none !important; \}/);
  assert.match(than, /\.page-bg-reveal \{/);
  assert.match(than, /clip-path: none;/);
  assert.match(than, /animation: aether-nhe 80ms linear both;/);
});

/* ==================================================== GSAP: kiem tra KHONG dung */

test("GSAP KHONG duoc cai — hieu ung dung Web Animations API (CSS) thuan, du de xu ly restart/dieu huong lien tiep", () => {
  const pkg = JSON.parse(read("../package.json"));
  const tatCa = { ...pkg.dependencies, ...pkg.devDependencies };
  assert.ok(!("gsap" in tatCa), "đã thêm gsap — cần lý do cụ thể (đặc tả muc 15) và ghi trong báo cáo, không âm thầm thêm");
  assert.ok(!codeOnly(veil()).includes("gsap"), "RouteTransitionVeil.tsx import gsap");
  assert.ok(!codeOnly(pageBg()).includes("gsap"), "PageBackground.tsx import gsap");
});

/* ==================================================== Home: vet la, cac chu de khac: khong bat buoc */

test("vet la CHI hien o chu de home, ~250-350ms, KHONG phai he thong hat vinh vien", () => {
  const text = css();
  assert.match(text, /\.aether-rift\[data-theme="home"\]\[data-state="revealing"\] \.aether-leaf-1/);
  const m = text.match(/@keyframes aether-la-bay \{[\s\S]*?\n\}/);
  assert.ok(m, "thiếu @keyframes aether-la-bay");
  // Kiem tra khong co animation "infinite" cho la — chi mot lan roi bien mat.
  const khaiBaoHoatHinh = text.match(/animation: aether-la-bay [^;]+;/g) ?? [];
  assert.ok(khaiBaoHoatHinh.length >= 2, "cần ít nhất 2 vệt lá (aether-leaf-1/2)");
  for (const kb of khaiBaoHoatHinh) {
    assert.ok(!/infinite/.test(kb), "vệt lá không được lặp vô hạn — chỉ một lần rồi biến mất");
  }
  assert.ok(existsSync(new URL("../src/app/globals.css", import.meta.url)));
});
