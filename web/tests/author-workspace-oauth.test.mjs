/*
 * Khu vuc tac gia thanh muc chinh + dang nhap bang Google/Facebook.
 *
 * Hai nhom test o day bao ve hai thu de hong IM LANG:
 *
 *   * mot lan "don dep" dieu huong dua `/write` ve lai menu tai khoan, hoac
 *     gop Audio Studio vao `/write` — hai thu do phuc vu hai viec khac han;
 *   * mot duong dang nhap thu hai moc them ben canh duong cu, roi hai ben
 *     lech nhau ve hinh dang phien.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

/**
 * Bo chu thich truoc khi quet.
 *
 * VI SAO CAN: cac test duoi day tim nhung chuoi KHONG DUOC PHEP xuat hien —
 * `<img`, `localStorage`, `errorMessage(`. Nhung chinh cac chu thich giai
 * thich VI SAO chung bi cam lai chua nguyen van nhung chuoi do, nen mot phep
 * `includes` tho se do vi ly do sai: no bat duoc loi giai thich, khong phai
 * hanh vi. (Da xay ra that o lan chay dau.)
 *
 * Chi bo `//...` va block comment. Du cho muc dich o day, va khong dung toi
 * chuoi ky tu nen khong lam hong cac phep so khac.
 */
const codeOnly = (src) =>
  src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/* =========================================================== dieu huong */

test("'Viết truyện' nam trong dieu huong chinh, ngang hang cac muc khac", async () => {
  const nav = read("../src/components/NavAuth.tsx");
  const order = [...nav.matchAll(/href: "([^"]+)", label: "([^"]+)"/g)].map(
    (m) => [m[1], m[2]],
  );
  // Thu tu day du duoc ghim o `ui.test.mjs`. Bai nay chi giu MOT dieu: "Viết
  // truyện" nam trong thanh chinh, ngang hang cac muc khac — khong phai bi giau
  // trong menu tai khoan. Ghim ca danh sach o hai cho la hai cho phai sua moi
  // lan them mot muc.
  assert.ok(
    order.some(([href, label]) => href === "/write" && label === "Viết truyện"),
    "'Viết truyện' không có trong thanh điều hướng chính",
  );
  assert.equal(order[0][0], "/", "'Trang chủ' phải đứng đầu");
  assert.equal(order.at(-1)?.[0], "/write",
    "'Viết truyện' đứng cuối hàng — nó là điểm đến, không phải điểm ghé qua");
});

test("route cu khong doi: /write va /studio deu con", () => {
  for (const p of ["../src/app/write/page.tsx", "../src/app/studio/page.tsx"]) {
    assert.ok(existsSync(new URL(p, import.meta.url)), `mất ${p}`);
  }
});

test("Audio Studio nam trong menu Cong cu, KHONG trong thanh chinh", () => {
  const nav = read("../src/components/NavAuth.tsx");
  const links = nav.slice(
    nav.indexOf("const LINKS"),
    nav.indexOf("export function NavLinks"),
  );
  assert.ok(!links.includes("/studio"));

  const tools = nav.slice(
    nav.indexOf("function ToolsMenu"),
    nav.indexOf("function AccountMenu"),
  );
  assert.match(tools, /Công cụ/);
  assert.match(tools, /href="\/studio"/);
});

test("menu Cong cu va menu tai khoan la HAI menu tach biet", () => {
  const nav = read("../src/components/NavAuth.tsx");
  assert.match(nav, /function ToolsMenu/);
  assert.match(nav, /function AccountMenu/);
  // Menu tai khoan khong duoc chua cong cu, va nguoc lai.
  const account = nav.slice(nav.indexOf("function AccountMenu"));
  assert.ok(!account.includes("/studio"), "Audio Studio lọt vào menu tài khoản");
});

test("Audio Studio KHONG bi gop vao /write", () => {
  // Hai trang phuc vu hai viec: `/studio` la dan van ban bat ky roi tai MP3,
  // `/write` la quan ly truyen va chuong. Nhan ban form cua Studio sang
  // `/write` la tao ra hai cho lam cung mot viec, roi chung lech nhau.
  const write = read("../src/app/write/page.tsx");
  assert.ok(!write.includes("ensureStudioNovel"), "/write dùng kho chứa Studio");
  assert.ok(!write.includes("MAX_CHARS"), "/write có giới hạn của Studio");

  // Nhung chuc nang audio THEO CHUONG thi phai con nguyen.
  for (const con of ["api.createJob", "AudioPlayer", "audio_outdated"]) {
    assert.ok(write.includes(con), `/write mất chức năng audio theo chương: ${con}`);
  }
});

test("chua dang nhap vao /write thi sang /login?next=/write", () => {
  const write = read("../src/app/write/page.tsx");
  assert.match(write, /router\.replace\(loginHref\("\/write"\)\)/);
  // `replace` chu khong phai `push`: nut Back phai ve trang truoc do, khong
  // phai ve mot trang se lai day ho sang dang nhap.
  assert.ok(!/router\.push\(loginHref/.test(write));
});

/* ================================================= `next` va open redirect */

test("safeNext giu duong dan noi bo", async () => {
  const { safeNext } = await import("../src/lib/nav.ts");
  assert.equal(safeNext("/write"), "/write");
  assert.equal(safeNext("/library"), "/library");
  assert.equal(safeNext("/novels/abc?x=1"), "/novels/abc?x=1");
});

test("safeNext tu choi moi duong ra ngoai mien", async () => {
  const { safeNext, DEFAULT_NEXT } = await import("../src/lib/nav.ts");
  for (const doc_hai of [
    "https://ke-xau.tld",
    "http://ke-xau.tld",
    "//ke-xau.tld", // protocol-relative
    "/\\ke-xau.tld", // mot so trinh duyet doi \ thanh /
    "javascript:alert(1)",
    "write", // thieu dau `/`
    "",
    null,
    undefined,
  ]) {
    assert.equal(safeNext(doc_hai), DEFAULT_NEXT, String(doc_hai));
  }
});

test("safeNext chan vong lap ve chinh trang dang nhap", async () => {
  const { safeNext, DEFAULT_NEXT } = await import("../src/lib/nav.ts");
  assert.equal(safeNext("/login"), DEFAULT_NEXT);
  assert.equal(safeNext("/login?next=/write"), DEFAULT_NEXT);
});

test("DEFAULT_NEXT la trang chu, KHONG phai /studio", async () => {
  const { DEFAULT_NEXT } = await import("../src/lib/nav.ts");
  assert.equal(DEFAULT_NEXT, "/");
});

test("loginHref sinh dung tham so", async () => {
  const { loginHref } = await import("../src/lib/nav.ts");
  assert.equal(loginHref("/write"), "/login?next=%2Fwrite");
  assert.equal(loginHref("/"), "/login");
  assert.equal(loginHref("https://ke-xau.tld"), "/login");
});

test("trang dang nhap KHONG con day nguoi dung sang /studio", () => {
  const login = read("../src/app/login/page.tsx");
  assert.ok(!login.includes('replace("/studio")'), "vẫn redirect cứng /studio");
  assert.match(login, /safeNext\(params\.get\("next"\)\)/);
  // Ca hai duong — dang nhap va dang ky — deu ve cung mot cho.
  assert.equal((login.match(/router\.replace\(next\)/g) ?? []).length, 2);
});

/* ====================================================== OAuth: giao dien */

test("nut nha cung cap doc CO, khong go cung", async () => {
  const login = read("../src/app/login/page.tsx");
  // Ca hai nut van co trong ma nguon — cai quyet dinh hien hay khong la CO.
  assert.match(login, /Tiếp tục với Google/);
  assert.match(login, /Tiếp tục với Facebook/);
  assert.match(login, /<GoogleIcon \/>/);
  assert.match(login, /<FacebookIcon \/>/);
  assert.match(login, /GOOGLE_LOGIN_ENABLED \? \(/);
  assert.match(login, /FACEBOOK_LOGIN_ENABLED \? \(/);
});

test("Google HIEN, Facebook KHONG hien", async () => {
  const { GOOGLE_LOGIN_ENABLED, FACEBOOK_LOGIN_ENABLED } = await import(
    "../src/lib/oauth.ts"
  );
  assert.equal(GOOGLE_LOGIN_ENABLED, true);
  assert.equal(FACEBOOK_LOGIN_ENABLED, false);
});

test("TAT Facebook KHONG co nghia la XOA", () => {
  // Neu ai do "don dep" bang cach go phan hien thuc di, ngay bat lai se thanh
  // mot lan viet lai. Bai nay do truoc khi dieu do xay ra.
  assert.match(
    read("../src/components/ProviderIcons.tsx"),
    /export function FacebookIcon/,
    "đã xoá icon Facebook",
  );
  assert.match(
    read("../src/lib/api.ts"),
    /"google" \| "facebook"/,
    "lớp api không còn nhận facebook",
  );
});

test("dang nhap bang email/mat khau VAN hien, khong bi co nao chi phoi", () => {
  const login = read("../src/app/login/page.tsx");
  // Form email nam NGOAI moi nhanh dieu kien cua co.
  const form = login.indexOf('<form className="card stack" onSubmit={submit}>');
  assert.ok(form > 0, "mất form email/mật khẩu");
  assert.match(login, /id="login-email"/);
  assert.match(login, /id="login-password"/);
  assert.match(login, /hoặc/, "mất vạch ngăn giữa hai đường đăng nhập");
});

test("dang ky bang email VAN con", () => {
  const login = read("../src/app/login/page.tsx");
  assert.match(login, /signUp\(/);
  assert.match(login, /Tạo tài khoản/);
  assert.match(login, /signIn\(/);
});

test("nut nha cung cap DIEU HUONG that, khong fetch", () => {
  // Sau buoc nay la mot chuoi chuyen tiep qua Appwrite roi qua nha cung cap;
  // no phai xay ra trong thanh dia chi, khong phai trong mot `fetch`.
  const login = read("../src/app/login/page.tsx");
  assert.match(login, /window\.location\.href = api\.oauthStartUrl\("google", next\)/);
  assert.match(login, /window\.location\.href = api\.oauthStartUrl\("facebook", next\)/);
});

test("bieu tuong nha cung cap ve noi tuyen, khong tai tu CDN cua ho", () => {
  // Mot the `<img>` tro ra ngoai se bao cho ho biet ai dang xem trang dang
  // nhap cua Fanfic World, ke ca khi nguoi do khong bam nut nao.
  const icons = codeOnly(read("../src/components/ProviderIcons.tsx"));
  assert.match(icons, /<svg/);
  assert.ok(!icons.includes("<img"), "icon tải từ ngoài");
  assert.ok(!/https?:\/\//.test(icons), "icon trỏ ra một địa chỉ ngoài");
});

/* ====================================================== OAuth: hop dong */

test("oauthStartUrl tra ve CHUOI, exchangeOAuth tra ve Promise", async () => {
  const api = read("../src/lib/api.ts");
  assert.match(api, /oauthStartUrl:\s*\(/);
  assert.match(api, /\/api\/auth\/oauth\/\$\{provider\}\?next=\$\{encodeURIComponent\(next\)\}/);
  assert.match(api, /exchangeOAuth:/);
  assert.match(api, /"\/api\/auth\/oauth\/exchange"/);
});

test("OAuth tra ve DUNG hinh dang cua dang nhap thuong", () => {
  const api = read("../src/lib/api.ts");
  // `login` tra `{token, profile}`; `exchangeOAuth` phai khai bao y het, neu
  // khong frontend se can hai duong xu ly phien.
  const kieu = /request<\{ token: string; profile: Profile \}>/g;
  assert.ok((api.match(kieu) ?? []).length >= 3,
    "login/register/exchangeOAuth phải cùng một kiểu trả về");
});

test("khong co he thong phien thu hai: chi mot duong ghi token", () => {
  const session = read("../src/lib/session.tsx");
  assert.match(session, /adoptSession/);
  // `setToken` chi duoc goi trong `session.tsx`, khong o trang nao khac.
  for (const p of [
    "../src/app/auth/callback/page.tsx",
    "../src/app/login/page.tsx",
  ]) {
    assert.ok(!read(p).includes("setToken("), `${p} tự ghi token`);
  }
});

/* ==================================================== OAuth: bao mat callback */

test("trang callback xoa cap dung-mot-lan khoi thanh dia chi TRUOC khi goi mang", () => {
  const cb = read("../src/app/auth/callback/page.tsx");
  const xoa = cb.indexOf("history.replaceState");
  const goi = cb.indexOf("api.exchangeOAuth");
  assert.ok(xoa > 0 && goi > 0);
  assert.ok(xoa < goi, "gọi mạng trước khi xoá — Referer sẽ mang theo secret");
});

test("callback KHONG luu secret vao storage", () => {
  const cb = codeOnly(read("../src/app/auth/callback/page.tsx"));
  for (const cam of ["localStorage", "sessionStorage", "document.cookie"]) {
    assert.ok(!cb.includes(cam), `callback lưu credential vào ${cam}`);
  }
});

test("callback khong doi cap hai lan o che do nghiem ngat", () => {
  // Cap dung-mot-lan thi lan thu hai CHAC CHAN hong, va nguoi dung se thay
  // thong bao loi sau khi da dang nhap thanh cong.
  const cb = read("../src/app/auth/callback/page.tsx");
  assert.match(cb, /daChay\.current/);
});

test("callback xu ly ca thieu tham so lan cap het han", () => {
  const cb = read("../src/app/auth/callback/page.tsx");
  assert.match(cb, /kind: "thieu"/);
  assert.match(cb, /kind: "hong"/);
  assert.match(cb, /Thiếu thông tin đăng nhập/);
  assert.match(cb, /không thành công/);
});

test("callback KHONG hien secret, userId, token hay ngoai le goc", () => {
  const cb = codeOnly(read("../src/app/auth/callback/page.tsx"));
  // Thong bao loi la chuoi co dinh, khong noi chuoi tu ngoai le vao.
  assert.ok(!cb.includes("errorMessage("), "callback hiện lỗi gốc ra màn hình");
  assert.ok(!/setError\([^)]*userId/.test(cb));
  assert.ok(!/setError\([^)]*secret/.test(cb));
  assert.ok(!/setError\([^)]*token/.test(cb));
});

test("callback hien trang thai tam bang tieng Viet, co ten nha cung cap", () => {
  const cb = read("../src/app/auth/callback/page.tsx");
  assert.match(cb, /Đang đăng nhập với \$\{ten\}/);
  assert.match(cb, /google: "Google"/);
  assert.match(cb, /facebook: "Facebook"/);
});

test("callback dung safeNext, khong tin thang tham so tu URL", () => {
  const cb = read("../src/app/auth/callback/page.tsx");
  assert.match(cb, /safeNext\(params\.get\("next"\)\)/);
});

test("khong co bi mat nao cua nha cung cap trong ma trinh duyet", () => {
  // Client Secret cua Google / App Secret cua Facebook / API key cua Appwrite
  // deu CHI duoc song o backend.
  for (const p of [
    "../src/lib/api.ts",
    "../src/lib/session.tsx",
    "../src/app/login/page.tsx",
    "../src/app/auth/callback/page.tsx",
  ]) {
    const src = codeOnly(read(p));
    for (const cam of [
      "client_secret",
      "clientSecret",
      "app_secret",
      "appSecret",
      "APPWRITE_API_KEY",
      "X-Appwrite-Key",
    ]) {
      assert.ok(!src.includes(cam), `${p} chứa ${cam}`);
    }
  }
});
