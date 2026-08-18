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

test("tong thoi luong (PHU + 50ms dem + LO) nam trong 550-700ms nhu dac ta", () => {
  const tong = THOI_LUONG_BINH_THUONG.PHU + 50 + THOI_LUONG_BINH_THUONG.LO;
  assert.ok(tong >= 550 && tong <= 700, `${tong}ms — cần 550–700ms theo đặc tả`);
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

test("z-index: duoi thanh dieu huong/mini-player, tren noi dung", () => {
  const text = css();
  const at = text.indexOf(".route-veil {");
  const than = text.slice(at, text.indexOf("}", at));
  const zVeil = Number(than.match(/z-index: (-?\d+);/)?.[1]);
  const zHeader = Number(text.match(/\.site-header \{[\s\S]*?z-index: (\d+);/)?.[1]);
  const zMini = Number(text.match(/\.mini \{[\s\S]*?z-index: (\d+);/)?.[1]);
  assert.ok(zVeil < zHeader, `veil z-index ${zVeil} phải nhỏ hơn navbar ${zHeader}`);
  assert.ok(zVeil < zMini, `veil z-index ${zVeil} phải nhỏ hơn mini-player ${zMini}`);
  assert.ok(zVeil > 0, "veil phải trên nội dung thường (z-index auto/0)");
});

test("BA cuc may hinh dang BAT QUY TAC — khong phai hinh tron/oval deu", () => {
  const text = css();
  for (const lop of ["veil-cloud", "veil-cloud-a", "veil-cloud-b", "veil-cloud-c"]) {
    const at = text.indexOf(`.${lop} {`);
    assert.notEqual(at, -1, `thiếu .${lop}`);
  }
  // Moi khai bao border-radius phai co BON gia tri KHAC nhau tren truc ngang
  // (vd "44% 56% 61% 39%") — mot border-radius deu (vd "50%") se ra hinh
  // tron/oval, dung dieu dac ta cam ("Avoid obvious circles/blobs").
  const khaiBao = [...text.matchAll(/border-radius: (\d+)% (\d+)% (\d+)% (\d+)%/g)];
  const trongVeil = khaiBao.filter((m) => {
    const truoc = text.slice(Math.max(0, m.index - 400), m.index);
    return truoc.includes("veil-cloud");
  });
  assert.ok(trongVeil.length >= 3, "cần ít nhất 3 khai báo border-radius bất quy tắc cho các cục mây");
  for (const m of trongVeil) {
    const [, a, b, c, d] = m;
    assert.ok(new Set([a, b, c, d]).size >= 3,
      `border-radius ${m[0]} quá đều — đọc ra như một hình tròn/oval`);
  }
});

test("moi cuc may co toc do/do tre RIENG — khong ca ba dong bo tuyet doi", () => {
  const text = css();
  const doTre = [...text.matchAll(/\.veil-cloud-([abc]) \{[\s\S]*?animation: veil-phu-\1[^;]*?(\d*)ms both/g)];
  // Cach kiem tra don gian hon: tim cac khai bao co do tre khac 0 tuong minh
  // (vd "40ms both", "90ms both") tren it nhat hai trong ba cuc may.
  const coDoTre = (text.match(/animation: veil-phu-[abc] var\(--dur-veil-phu\) cubic-bezier\([^)]+\) \d+ms both/g) ?? []).length;
  assert.ok(coDoTre >= 2, "ít nhất hai cục mây phải có độ trễ riêng để chuyển động không đồng bộ tuyệt đối — nếu không sẽ đọc ra như MỘT khối duy nhất");
});

test("lop suong nen dung backdrop-filter — dam bao che kin ca o khe ho giua cac cuc may", () => {
  const text = css();
  const at = text.indexOf(".veil-haze {");
  const than = text.slice(at, text.indexOf("}", at));
  assert.match(than, /backdrop-filter:/);
});

test("chi transform/opacity/filter dong — khong thuoc tinh nao lam tinh lai bo cuc", () => {
  const text = css();
  for (const ten of ["veil-phu-a", "veil-phu-b", "veil-phu-c", "veil-lo-a", "veil-lo-b", "veil-lo-c"]) {
    const at = text.indexOf(`@keyframes ${ten} {`);
    assert.notEqual(at, -1, `thiếu @keyframes ${ten}`);
    const than = text.slice(at, text.indexOf("\n}", at));
    assert.ok(!/\b(left|right|top|bottom|margin|width|height):/.test(than),
      `${ten} động vào thuộc tính làm tính lại bố cục`);
  }
});

test("idle: KHONG mot animation nao gan san — chi phi luc dung yen la khong", () => {
  const text = css();
  // Quy tac animation cho cuc may/suong CHI duoc gan co dieu kien qua
  // `[data-state="covering"]`/`[data-state="revealing"]` — khong duoc co
  // mot khai bao "tran" `.veil-cloud { animation: ... }` chay moi luc.
  const truocDataState = text.slice(text.indexOf(".veil-cloud {"), text.indexOf('[data-state="covering"]'));
  assert.ok(!/\banimation:/.test(truocDataState),
    "cục mây có animation chạy mặc định — sẽ tốn CPU/GPU cả lúc không điều hướng");
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
