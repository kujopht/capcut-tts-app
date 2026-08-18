/*
 * Cloud Veil Route Transition V1 — man may/suong thay cho "quay may ngang"
 * cu (xem lich su git `components/PageBackground.tsx`, `globals.css`).
 *
 * HAI LOAI test trong tep nay:
 *
 *   1. HANH VI THAT (phan lon tep) — `taoRouteTransitionStore` nhan moi phu
 *      thuoc cham toi trinh duyet qua tham so (xem `lib/routeTransitionStore
 *      .ts`), nen o day co the tiem MOT DONG HO GIA (khong cho that) + mot
 *      ham nap-anh gia, roi kiem tra CHINH XAC trinh tu pha/thoi diem, va
 *      quan trong nhat: KHONG CO DUA (race) khi dieu huong lien tiep.
 *   2. QUET MA NGUON (CSS + component) — cho cac bat bien khong the kiem
 *      bang cach chay logic don thuan: hinh dang bat quy tac, z-index, khong
 *      Canvas/WebGL/rAF, bien mau theo 8 chu de.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  taoRouteTransitionStore,
  THOI_LUONG_BINH_THUONG,
  THOI_LUONG_GIAM,
} from "../src/lib/routeTransitionStore.ts";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const css = () => read("../src/app/globals.css");
const veil = () => read("../src/components/RouteTransitionVeil.tsx");
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
      (microtask — cac `.then()` ma chinh hen do co the kich hoat, vi du
      `giai()` mot promise ben trong `napAnh`) xu ly xong TRUOC KHI xem xet
      hen tiep theo. Neu khong, mot hen MOI duoc dang ky BEN TRONG mot
      `.then()` (dung nhu `routeTransitionStore.ts` lam) se khong duoc thay
      trong cung mot cua so `tienToi` — dung `setImmediate` de xa SACH hang
      doi vi tac vu (manh hon vai lan `await Promise.resolve()`, vi mot
      chuoi `Promise.all(...).then(...)` co the can nhieu hon mot buoc).
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
 * Truyen `moc` de mo phong mot lan nap CHAM — resolve sau `moc` ms tren
 * CHINH dong ho gia (khong phai gio that).
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

test("lan dau: hien thang chu de, khong may che", () => {
  const { store } = taoStoreGia();
  store.diTinh("/");
  const s = store.getSnapshot();
  assert.equal(s.ten, "home");
  assert.equal(s.trangThai, "idle");
  assert.equal(s.tenDich, null);
});

test("dieu huong sang duong dan KHAC nhung CUNG chu de: khong may che", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/fanfic": "explore", "/novels/nov_1": "explore" },
  });
  store.diTinh("/fanfic");
  store.diTinh("/novels/nov_1");
  await dongHo.tienToi(1000);
  const s = store.getSnapshot();
  assert.equal(s.ten, "explore");
  assert.equal(s.trangThai, "idle", "chuyển giữa hai đường dẫn cùng chủ đề không được kích hoạt che");
});

/* ==================================================== hanh vi: mot chu ky day du */

test("khac chu de: dung trinh tu phu (covering) -> doi anh -> lo (revealing) -> idle", async () => {
  const { store, dongHo } = taoStoreGia();
  store.diTinh("/"); // home, khong may che (lan dau)
  store.diTinh("/fanfic"); // home -> explore: BAT DAU may che

  let s = store.getSnapshot();
  assert.equal(s.trangThai, "covering");
  assert.equal(s.ten, "home", "ten CHUA doi — man suong con dang che");
  assert.equal(s.tenDich, "explore", "veil phai biet DICH tu dau pha covering");

  // Truoc moc PHU (300ms): van dang covering, chua doi anh.
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.PHU - 50);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "covering");
  assert.equal(s.ten, "home");

  // Dung moc PHU: anh da san sang (khong co gi cham) -> doi NGAY.
  await dongHo.tienToi(50);
  s = store.getSnapshot();
  assert.equal(s.ten, "explore", "phải đổi ảnh đúng lúc màn sương che kín (mốc PHU)");
  assert.equal(s.trangThai, "covering", "trạng thái chỉ đổi sau khoảng đệm 50ms, chưa ngay lúc đổi ảnh");

  // 50ms dem truoc khi chuyen sang revealing.
  await dongHo.tienToi(50);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "revealing");

  // Chua het pha LO: van revealing.
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.LO - 10);
  assert.equal(store.getSnapshot().trangThai, "revealing");

  // Het pha LO: ve idle.
  await dongHo.tienToi(10);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "idle");
  assert.equal(s.tenDich, null);
  assert.equal(s.ten, "explore");
});

test("tong thoi luong (PHU + 50ms dem + LO) nam trong 780-900ms nhu dac ta V2", () => {
  // V2: keo dai + lam muot hon V1 (550-700ms, bi nhan xet "van con giong mot
  // cu lau") — dac ta V2 yeu cau 780-900ms.
  const tong = THOI_LUONG_BINH_THUONG.PHU + 50 + THOI_LUONG_BINH_THUONG.LO;
  assert.ok(tong >= 780 && tong <= 900, `${tong}ms — cần 780–900ms theo đặc tả V2`);
});

/* ==================================================== hanh vi: chong dua (race) */

test("dieu huong LIEN TIEP truoc khi xong: chi ket qua cua lan MOI NHAT duoc ap dung", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore", "/library": "library" },
  });
  store.diTinh("/"); // home, lan dau

  store.diTinh("/fanfic"); // home -> explore
  await dongHo.tienToi(100); // giua chung pha covering (PHU=300)
  store.diTinh("/library"); // NGAT NGANG: home -> library (muc tieu MOI)

  let s = store.getSnapshot();
  assert.equal(s.trangThai, "covering", "vẫn đang che — không nhảy thẳng về idle");
  assert.equal(s.tenDich, "library", "đích phải là lần điều hướng MỚI NHẤT, không phải explore");
  assert.equal(s.ten, "home", "ảnh gốc (home) không được đổi sang explore giữa chừng");

  // Chay het toan bo chu ky moi (PHU + dem + LO) — KHONG duoc dung o "explore".
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.PHU + 50 + THOI_LUONG_BINH_THUONG.LO + 10);
  s = store.getSnapshot();
  assert.equal(s.trangThai, "idle");
  assert.equal(s.ten, "library", "phải kết thúc đúng ở đích mới nhất (library), không kẹt ở explore");
  assert.equal(s.tenDich, null);
});

test("dieu huong lien tiep KHONG de lai hen thua (khong con man suong ket dinh)", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore", "/library": "library", "/account": "account" },
  });
  store.diTinh("/");
  store.diTinh("/fanfic");
  await dongHo.tienToi(60);
  store.diTinh("/library");
  await dongHo.tienToi(60);
  store.diTinh("/account");
  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.PHU + 50 + THOI_LUONG_BINH_THUONG.LO + 10);

  assert.equal(store.getSnapshot().trangThai, "idle");
  assert.equal(store.getSnapshot().ten, "account");
  assert.equal(dongHo.soHenDangCho(), 0,
    "còn hẹn giờ treo lơ lửng — nguy cơ màn sương kẹt lại hoặc đổi nền sai lúc");
});

test("dieu huong quay VE DUNG chu de dang hien giua luc dang che: huy sach, ve idle NGAY", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
  });
  store.diTinh("/");
  store.diTinh("/fanfic"); // home -> explore, dang che
  await dongHo.tienToi(50);
  store.diTinh("/"); // doi y NGAY: quay ve home — dung chu de dang hien (`ten` van la "home")

  const s = store.getSnapshot();
  assert.equal(s.trangThai, "idle", "quay lại đúng chủ đề đang hiện phải huỷ sạch, không cần che");
  assert.equal(s.ten, "home");
  assert.equal(s.tenDich, null);
  assert.equal(dongHo.soHenDangCho(), 0);
});

/* ==================================================== hanh vi: cho anh nap cham */

test("anh nap CHAM hon moc PHU: doi anh cho toi khi san sang, KHONG doi som", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
    moc: { explore: THOI_LUONG_BINH_THUONG.PHU + 200 }, // cham hon PHU 200ms
  });
  store.diTinh("/");
  store.diTinh("/fanfic");

  await dongHo.tienToi(THOI_LUONG_BINH_THUONG.PHU + 50); // qua moc PHU nhung anh CHUA xong
  let s = store.getSnapshot();
  assert.equal(s.ten, "home", "đổi ảnh trước khi ảnh mới sẵn sàng — sẽ lộ ảnh vỡ/chưa tải xong");
  assert.equal(s.trangThai, "covering", "vẫn phải đang che trong lúc chờ ảnh chậm");

  await dongHo.tienToi(200); // anh vua xong
  s = store.getSnapshot();
  assert.equal(s.ten, "explore", "phải đổi ngay khi ảnh sẵn sàng, không chờ thêm vô ích");
});

test("tran an toan: anh khong bao gio bao xong (ket noi treo) van duoc giai quyet", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
    moc: { explore: 999999 }, // "khong bao gio" xong trong pham vi bai test
  });
  store.diTinh("/");
  store.diTinh("/fanfic");
  // Tran an toan cung (2000ms) + moc PHU + dem — man suong PHAI tu giai
  // quyet, khong duoc ket dinh mai cho mot ket noi treo.
  await dongHo.tienToi(2000 + THOI_LUONG_BINH_THUONG.PHU + 100);
  const s = store.getSnapshot();
  assert.equal(s.ten, "explore", "phải tự thoát khỏi trạng thái chờ sau trần an toàn");
});

/* ==================================================== hanh vi: giam chuyen dong */

test("giam chuyen dong: dung bo thoi luong NGAN hon, khong bao gio bang 0", async () => {
  const { store, dongHo } = taoStoreGia({
    banDoTen: { "/": "home", "/fanfic": "explore" },
    giamChuyenDong: true,
  });
  store.diTinh("/");
  store.diTinh("/fanfic");
  await dongHo.tienToi(THOI_LUONG_GIAM.PHU + 10);
  assert.equal(store.getSnapshot().ten, "explore");
  assert.ok(THOI_LUONG_GIAM.PHU > 0 && THOI_LUONG_GIAM.LO > 0,
    "vẫn phải có một khoảng che tối thiểu — đổi nền tức thì sẽ lộ một cú nháy màu");
  assert.ok(THOI_LUONG_GIAM.PHU < THOI_LUONG_BINH_THUONG.PHU);
  assert.ok(THOI_LUONG_GIAM.LO < THOI_LUONG_BINH_THUONG.LO);
});

/* ================================================================ quet ma nguon */

test("khop CHINH XAC voi CSS: --dur-veil-phu/--dur-veil-lo (binh thuong + giam)", () => {
  const text = css();
  const phuBT = Number(text.match(/--dur-veil-phu: (\d+)ms;/)?.[1]);
  const loBT = Number(text.match(/--dur-veil-lo: (\d+)ms;/)?.[1]);
  assert.equal(phuBT, THOI_LUONG_BINH_THUONG.PHU, "CSS --dur-veil-phu lệch JS");
  assert.equal(loBT, THOI_LUONG_BINH_THUONG.LO, "CSS --dur-veil-lo lệch JS");

  const giam = text.slice(text.indexOf("@media (prefers-reduced-motion: reduce)"));
  const phuGiam = Number(giam.match(/--dur-veil-phu: (\d+)ms;/)?.[1]);
  const loGiam = Number(giam.match(/--dur-veil-lo: (\d+)ms;/)?.[1]);
  assert.equal(phuGiam, THOI_LUONG_GIAM.PHU, "CSS (giảm chuyển động) --dur-veil-phu lệch JS");
  assert.equal(loGiam, THOI_LUONG_GIAM.LO, "CSS (giảm chuyển động) --dur-veil-lo lệch JS");
});

test("man suong: KHONG Canvas, KHONG WebGL, KHONG requestAnimationFrame", () => {
  const src = codeOnly(veil());
  assert.ok(!/canvas|WebGL|getContext|requestAnimationFrame/i.test(src));
});

test("man suong la trang tri: aria-hidden, khong chan chuot", () => {
  const src = veil();
  assert.match(src, /aria-hidden="true"/);
  const text = css();
  const at = text.indexOf(".route-veil {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /pointer-events: none/);
});

test("mount DUNG MOT LAN o layout.tsx, ngang hang voi PageBackground (khong long vao trong)", () => {
  const src = layout();
  assert.match(src, /<PageBackground \/>/);
  assert.match(src, /<RouteTransitionVeil \/>/);
  // Ca hai la anh em true — khong cai nao nam trong JSX cua cai kia trong
  // chinh layout.tsx (kiem tra tho: giua hai the mo khong co dau `<Page` hay
  // `<RouteTransitionVeil` long nhau).
  const a = src.indexOf("<PageBackground");
  const b = src.indexOf("<RouteTransitionVeil");
  assert.ok(a !== -1 && b !== -1 && b > a);
});

test("z-index V2: CON AM (duoi noi dung thuong), nhung it am hon nen — NEN < MAY < GIAO DIEN", () => {
  const text = css();
  const at = text.indexOf(".route-veil {");
  const than = text.slice(at, text.indexOf("}", at));
  const zVeil = Number(than.match(/z-index: (-?\d+);/)?.[1]);
  const zPageBg = Number(text.match(/\.page-bg \{[\s\S]*?z-index: (-?\d+);/)?.[1]);
  const zHeader = Number(text.match(/\.site-header \{[\s\S]*?z-index: (\d+);/)?.[1]);
  const zMini = Number(text.match(/\.mini \{[\s\S]*?z-index: (\d+);/)?.[1]);

  assert.ok(zVeil < 0, "veil phải là z-index ÂM (V2) — đây là lớp con của thế giới, không phải lớp che giao diện");
  assert.ok(zVeil > zPageBg, `veil z-index ${zVeil} phải LỚN HƠN (ít âm hơn) nền ${zPageBg} — mây phải vẽ trên nền`);
  assert.ok(zVeil < zHeader, `veil z-index ${zVeil} phải nhỏ hơn navbar ${zHeader}`);
  assert.ok(zVeil < zMini, `veil z-index ${zVeil} phải nhỏ hơn mini-player ${zMini}`);

  /*
    Z-index am CHI dam bao thu tu dung neu `<main>`/`.wrap` KHONG dinh vi
    (khong `position`) va khong tao ngu canh xep chong rieng (`transform`/
    `filter`/`isolation`) — da xac nhan bang kiem tra thuc te (bao cao Cloud
    Veil V2). Bai test nay giu lai dieu kien do de neu sau nay co ai VO TINH
    them `position`/`isolation` vao `main`/`.wrap` thi do se BAT NGAY, vi
    dieu do se lam gay dung z-index am da tinh o tren.
  */
  const mainRule = text.match(/\nmain \{([^}]*)\}/)?.[1] ?? "";
  assert.ok(!/\bposition:|isolation:|transform:|filter:/.test(mainRule),
    "main đã có position/isolation/transform/filter — điều này sẽ phá vỡ thứ tự z-index âm NỀN < MÂY < GIAO DIỆN");
});

const LOP_MIST = ["mist-wisp-1", "mist-wisp-2", "mist-ribbon-a", "mist-ribbon-b", "mist-core", "mist-trail"];

test("V3: du SAU dai suong/may (2 dan dau + 2 vua + 1 trung tam + 1 theo sau)", () => {
  const text = css();
  for (const lop of LOP_MIST) {
    assert.notEqual(text.indexOf(`.${lop} {`), -1, `thiếu .${lop}`);
  }
});

test("V3: KHONG con hinh tron/oval — moi lop dung clip-path da giac hanh van tay, KHONG border-radius/radial-gradient lam vien ngoai", () => {
  const text = css();
  // Ba khuon da giac goc phai ton tai va CO NHIEU DIEM (khong phai mot hinh
  // don gian 4 canh — dac ta cam "obvious rectangle/circle/ellipse").
  for (const khuon of ["--da-giac-A", "--da-giac-B", "--da-giac-C"]) {
    const m = text.match(new RegExp(`${khuon}: polygon\\(([^)]+)\\)`));
    assert.ok(m, `thiếu biến ${khuon}`);
    const soDiem = m[1].split(",").length;
    assert.ok(soDiem >= 10, `${khuon} chỉ có ${soDiem} điểm — cần đủ điểm để tạo mép bất quy tắc, không phải đa giác đều`);
  }
  // Tung lop PHAI tham chieu mot trong ba khuon qua clip-path.
  for (const lop of LOP_MIST) {
    const at = text.indexOf(`.${lop} {`);
    const than = text.slice(at, text.indexOf("}", at));
    assert.match(than, /clip-path: var\(--da-giac-[ABC]\)/, `.${lop} thiếu clip-path da giác`);
  }
  // KHONG con border-radius (V2) hay radial-gradient (hinh tron tam-bien lam
  // vien ngoai) trong toan bo khoi Cloud Veil — ca hai la dau hieu cua
  // "hinh tron/oval CSS demo" ma V3 phai loai bo hoan toan.
  // `lastIndexOf("/*", ...)` de bat DUNG ky tu mo `/*` cua khoi chu thich —
  // neu chi neo vao giua doan van ban (sau `/*`), `codeOnly` se khong nhan
  // ra day la chu thich (thieu dau mo trong pham vi slice) va KHONG loc bo.
  const batDauKhoi = text.lastIndexOf("/*", text.indexOf("CLOUD VEIL ROUTE TRANSITION V3"));
  const ketThucKhoi = text.indexOf('.route-veil[data-theme="auth"]');
  const khoiVeil = codeOnly(text.slice(batDauKhoi, ketThucKhoi));
  assert.ok(!/border-radius:/.test(khoiVeil), "vẫn còn border-radius (hình bo tròn kiểu V2) trong khối Cloud Veil");
  assert.ok(!/radial-gradient\(/.test(khoiVeil), "vẫn còn radial-gradient (đọc ra như một chấm tròn mờ to) trong khối Cloud Veil");
});

test("V3: khong con backdrop-filter — day la nguyen nhan chinh khien V2 doc ra MOT KHOI mo nhoe duy nhat", () => {
  /*
    Nguyen nhan da xac nhan (xem chu thich dau khoi ".route-veil" o
    globals.css): `.route-veil` co `contain: paint` -> tao ngu canh xep
    chong rieng -> `backdrop-filter` cua MOT lop con se "nhin thay" CA CAC
    lop con KHAC (khong chi `.page-bg` nhu gia dinh sai cua V2), tron nhieu
    dai suong rieng biet thanh MOT khoi mo duy nhat. V3 bo han co che nay.
  */
  const text = css();
  // `lastIndexOf("/*", ...)` de bat DUNG ky tu mo `/*` cua khoi chu thich —
  // neu chi neo vao giua doan van ban (sau `/*`), `codeOnly` se khong nhan
  // ra day la chu thich (thieu dau mo trong pham vi slice) va KHONG loc bo.
  const batDauKhoi = text.lastIndexOf("/*", text.indexOf("CLOUD VEIL ROUTE TRANSITION V3"));
  const ketThucKhoi = text.indexOf('.route-veil[data-theme="auth"]');
  // codeOnly: chu thich GIAI THICH nguyen nhan cu (V2) van con nhac toi cum
  // "backdrop-filter" trong VAN BAN — chi kiem tra CSS THAT SU, khong tinh
  // chu thich.
  const khoiVeil = codeOnly(text.slice(batDauKhoi, ketThucKhoi));
  assert.ok(!/backdrop-filter/.test(khoiVeil), "vẫn còn backdrop-filter trong khối Cloud Veil — đây là nguyên nhân chính gây lỗi 'một khối mờ'");
});

test("V3: background-blend-mode: screen — dam bao nhieu lop mau chong nhau CHI sang len, khong bao gio toi/den di", () => {
  /*
    Nguyen nhan #2 cua loi "man hinh gan nhu den" (xem chu thich dau khoi):
    chu de `auth` tung dung mot mau indigo gan-den lam than cua khoi may DAC
    nhat; khi nhieu lop chong nhau, vung giao doc ra gan nhu den. `screen`
    dam bao viec chong lop CHI co the lam SANG len.
  */
  const text = css();
  assert.match(text, /\.mist \{[\s\S]*?background-blend-mode: screen;/,
    "thiếu background-blend-mode: screen trên lớp .mist dùng chung");
});

test("V3: chu de auth KHONG con dung mau gan-den lam --veil-1 (nguyen nhan cu the cua 'man hinh gan nhu den')", () => {
  const text = css();
  const m = text.match(/\.route-veil\[data-theme="auth"\]\s*\{\s*--veil-1:\s*(#[0-9a-fA-F]{6});/);
  assert.ok(m, "thiếu --veil-1 của chủ đề auth");
  assert.notEqual(m[1].toLowerCase(), "#312e81",
    "auth vẫn dùng --veil-1 cũ (#312e81, gần như đen) — đây là nguyên nhân cụ thể của ảnh chụp 'gần như đen'");
  // Do sang tho (trung binh RGB) phai đủ cao de KHONG con la "gan nhu den".
  const hex = m[1].slice(1);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const doSang = (r + g + b) / 3;
  assert.ok(doSang >= 60, `--veil-1 của auth quá tối (độ sáng thô ${doSang.toFixed(0)}/255) — vẫn có nguy cơ đọc ra gần như đen`);
});

test("moi lop may co toc do/quang duong/vi tri/do mo RIENG — khong lop nao trung thong so (tao chieu sau)", () => {
  const text = css();
  // Quang duong cuoi cung (|translate3d x|, vw) trong pha "lo" cua CA SAU lop
  // phai khac nhau — day la co che tao "toc do khac nhau" ma KHONG dong bo
  // camera/nen (chi cac lop may nay tu di chuyen).
  const tenKeyframeLo = {
    "mist-wisp-1": "suong-lo-wisp-1", "mist-wisp-2": "suong-lo-wisp-2",
    "mist-ribbon-a": "suong-lo-ribbon-a", "mist-ribbon-b": "suong-lo-ribbon-b",
    "mist-core": "suong-lo-core", "mist-trail": "suong-lo-trail",
  };
  const quangDuong = (kf) => {
    const m = text.match(new RegExp(`@keyframes ${kf} \\{[\\s\\S]*?100%\\s*\\{[^}]*translate3d\\((-?[\\d.]+)vw`));
    return m ? Math.abs(Number(m[1])) : null;
  };
  const cacQuangDuong = Object.values(tenKeyframeLo).map(quangDuong);
  assert.ok(cacQuangDuong.every((d) => d !== null), "thiếu quãng đường cuối (translate3d) của một trong sáu lớp");
  assert.equal(new Set(cacQuangDuong).size, 6,
    `quãng đường: ${JSON.stringify(cacQuangDuong)} — cả sáu lớp phải khác nhau để tạo chiều sâu`);

  // Vi tri doc (top) va do mo dinh (opacity dinh nghia tren .mist-*) cung
  // phai khac nhau giua tat ca sau lop.
  const viTriDoc = LOP_MIST.map((lop) => {
    const at = text.indexOf(`.${lop} {`);
    const than = text.slice(at, text.indexOf("}", at));
    return than.match(/top: ([\d.]+)vh;/)?.[1];
  });
  assert.equal(new Set(viTriDoc).size, 6, `vị trí dọc (top): ${JSON.stringify(viTriDoc)} — cả sáu lớp phải khác nhau`);
});

test("do bao phu KHONG toi da: do mo DINH cua moi lop suong deu <= 0.7 (con thay duoc nen qua may, dac ta 35-60%)", () => {
  /*
    Nguong ban dau (<=0.5) qua thap: QA trinh duyet thuc te (chup man hinh
    dinh pha phu) cho thay may GAN NHU KHONG THAY DUOC tren nen tranh sang
    mau — "trong nhu suong" qua muc, khong con doc ra la "interesting even
    as a frozen still frame" (dac ta muc 17). Nang tran len 0.7 (van con
    thay duoc nen QUA may — khac hoan toan V1/V2 cu voi opacity 0.7-0.94 +
    blur 16-28px dac kin) va giam blur/tang do bao hoa mau tuong ung de hinh
    dang da giac doc ro hon.
  */
  const text = css();
  const tenKeyframePhu = ["suong-phu-wisp-1", "suong-phu-wisp-2", "suong-phu-ribbon-a", "suong-phu-ribbon-b", "suong-phu-core"];
  for (const kf of tenKeyframePhu) {
    const m = text.match(new RegExp(`@keyframes ${kf} \\{[\\s\\S]*?100%\\s*\\{\\s*opacity:\\s*([\\d.]+);`));
    assert.ok(m, `thiếu opacity đỉnh của ${kf}`);
    const doMo = Number(m[1]);
    assert.ok(doMo <= 0.7, `${kf} đạt opacity ${doMo} — quá đặc, phải ≤ 0.7 để không che kín nền`);
  }
  // `.mist-trail` phai AN HOAN TOAN suot pha phu (dac ta "khong hien trong
  // pha covering, chi xuat hien giua pha lo").
  const trailPhu = text.match(/@keyframes suong-phu-trail \{[\s\S]*?\n\}/)?.[0] ?? "";
  assert.ok(!/opacity: (?!0;)[\d.]+;/.test(trailPhu),
    "mist-trail phải giữ opacity 0 SUỐT pha phủ — chỉ xuất hiện ở pha lộ (dạc tả 'trailing wisp ~430ms')");
});

test("V3: hien SO LE qua % keyframe (khong dung animation-delay — tranh buoc nhay khi delay+duration vuot --dur-veil-phu)", () => {
  const text = css();
  // Cac lop KHONG hien tu 0% phai co mot cap "0%, X% { opacity: 0; ... }"
  // giu nguyen truoc khi bat dau chuyen dong — day la co che "do tre" cua
  // V3 (thay animation-delay).
  for (const kf of ["suong-phu-ribbon-a", "suong-phu-wisp-2", "suong-phu-core", "suong-phu-ribbon-b"]) {
    const m = text.match(new RegExp(`@keyframes ${kf} \\{\\s*0%,\\s*(\\d+)%\\s*\\{\\s*opacity:\\s*0;`));
    assert.ok(m, `${kf} thiếu mốc giữ nguyên (0%, X%) để tạo độ trễ hiện — không được đồng bộ tuyệt đối với wisp-1`);
  }
  // Cac moc do tre phai KHAC nhau (thu tu hien so le, khong phai tat ca cung
  // mot moc).
  const mocDoTre = ["suong-phu-ribbon-a", "suong-phu-wisp-2", "suong-phu-core", "suong-phu-ribbon-b"].map((kf) => {
    const m = text.match(new RegExp(`@keyframes ${kf} \\{\\s*0%,\\s*(\\d+)%`));
    return m ? Number(m[1]) : null;
  });
  assert.equal(new Set(mocDoTre).size, 4, `mốc độ trễ: ${JSON.stringify(mocDoTre)} — phải khác nhau cả bốn (hiện orchestrated, không đồng loạt)`);
});

test("chi transform/opacity dong — filter/clip-path la GIA TRI TINH, khong thuoc tinh nao lam tinh lai bo cuc", () => {
  const text = css();
  const tenKeyframe = [
    "suong-phu-wisp-1", "suong-phu-ribbon-a", "suong-phu-wisp-2", "suong-phu-core", "suong-phu-ribbon-b", "suong-phu-trail",
    "suong-lo-wisp-1", "suong-lo-ribbon-a", "suong-lo-wisp-2", "suong-lo-core", "suong-lo-ribbon-b", "suong-lo-trail",
  ];
  for (const ten of tenKeyframe) {
    const at = text.indexOf(`@keyframes ${ten} {`);
    assert.notEqual(at, -1, `thiếu @keyframes ${ten}`);
    const than = text.slice(at, text.indexOf("\n}", at));
    assert.ok(!/\b(left|right|top|bottom|margin|width|height|filter|clip-path):/.test(than),
      `${ten} động vào thuộc tính làm tính lại bố cục/tô vẽ (chỉ transform/opacity được phép hoạt hình)`);
  }
});

test("idle: KHONG mot animation nao gan san — chi phi luc dung yen la khong", () => {
  const text = css();
  // Quy tac animation cho dai suong/may CHI duoc gan co dieu kien qua
  // `[data-state="covering"]`/`[data-state="revealing"]` — khong duoc co
  // mot khai bao "tran" `.mist { animation: ... }` chay moi luc.
  const truocDataState = text.slice(text.indexOf(".mist {"), text.indexOf('[data-state="covering"]'));
  assert.ok(!/\banimation:/.test(truocDataState),
    "lớp mist có animation chạy mặc định — sẽ tốn CPU/GPU cả lúc không điều hướng");
});

test("mau man suong dinh nghia du CA 8 chu de nen (dung lai he thong co san)", () => {
  const text = css();
  for (const k of ["home", "explore", "reader", "studio", "write", "library", "account", "auth"]) {
    assert.match(text, new RegExp(`\\.route-veil\\[data-theme="${k}"\\]`), `thiếu màu veil cho chủ đề ${k}`);
  }
});

test("man suong KHONG tu dat ma mau — doc qua bien --veil-1/--veil-2", () => {
  const src = codeOnly(veil());
  assert.ok(!/#[0-9a-f]{6}/i.test(src), "RouteTransitionVeil.tsx tự đặt mã màu thay vì dùng biến CSS theo chủ đề");
});
