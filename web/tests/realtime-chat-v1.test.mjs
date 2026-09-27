/**
 * Fanfic Chat V1 (Tencent Chat) — cac bat bien KHONG DUOC hong lang le.
 *
 * Quan trong nhat: LAZY LOGIN. Tencent tinh MAU theo lan dang nhap SDK; mot
 * nguoi chi doc/nghe truyen phai tao 0 phien chat. Neu ai do vo tinh
 * `import "@tencentcloud/chat"` o dau file, hoac goi `moChat()` luc mount,
 * app van chay binh thuong — chi la moi doc gia bat dau bi tinh tien. Hong
 * lang le thi phai co test canh.
 *
 * Quet MA NGUON (quy uoc repo: khong jsdom). Hanh vi that duoc do trong Chrome
 * (xem bao cao PR): `window.__fanficChat` dem so phien/tai SDK/dang nhap.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const codeOnly = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "").replace(/\s\/\/.*$/gm, "");

function moiTep(dir = SRC) {
  const ra = [];
  for (const ten of readdirSync(dir)) {
    const p = join(dir, ten);
    if (statSync(p).isDirectory()) ra.push(...moiTep(p));
    else if (/\.(tsx?|mjs|js)$/.test(ten)) ra.push(p);
  }
  return ra;
}
const tuongDoi = (p) => p.slice(SRC.length).replace(/\\/g, "/");

const provider = () => codeOnly(read("components/chat/ChatProvider.tsx"));
const transport = () => codeOnly(read("lib/chat/tencentTransport.ts"));

test("1a. SDK Tencent CHI xuat hien o tencentTransport.ts, va chi qua import() dong", () => {
  const dung = moiTep().filter((p) => /@tencentcloud\/chat/.test(codeOnly(readFileSync(p, "utf8"))));
  assert.deepEqual(dung.map(tuongDoi), ["lib/chat/tencentTransport.ts"], "SDK bị import ở nơi khác — sẽ vào bundle chung và chạy cho MỌI trang");
  const t = transport();
  assert.match(t, /await import\("@tencentcloud\/chat"\)/);
  // `import type` duoc phep (bi xoa luc bien dich); import GIA TRI thi khong.
  assert.ok(!/^import (?!type\b)[^;]*@tencentcloud\/chat/m.test(t), "import giá trị tĩnh của SDK = tải SDK cho mọi người");
});

test("1b. SDK ngoai bundle SERVER: tencentTransport chi o ChatEngine, ChatEngine chi qua next/dynamic ssr:false", () => {
  /*
    Do that tren `cf:build`: mot `import()` dong thuong trong ChatProvider
    van keo SDK vao `handler.mjs` cua Worker (+897 KB). `ssr: false` la cach
    Next chinh thuc giu module ngoai bundle server.
  */
  for (const p of moiTep()) {
    const ten = tuongDoi(p);
    const s = codeOnly(readFileSync(p, "utf8"));
    if (ten !== "components/chat/ChatEngine.tsx") {
      assert.ok(!/chat\/tencentTransport/.test(s), `${ten} nhắc tới tencentTransport — chỉ ChatEngine được import nó`);
    }
    if (ten !== "components/chat/ChatProvider.tsx") {
      assert.ok(!/from "\.\/ChatEngine"|from "@\/components\/chat\/ChatEngine"/.test(s.replace(/^import type [^;]*;/gm, "")),
        `${ten} import ChatEngine`);
    }
  }
  const p = provider();
  assert.match(p, /const ChatEngine = dynamic\(\(\) => import\("\.\/ChatEngine"\), \{ ssr: false \}\);/);
  assert.ok(!/^import (?!type\b)[^;]*"\.\/ChatEngine"/m.test(p), "ChatProvider import GIÁ TRỊ ChatEngine tĩnh");
  assert.match(p, /\{canDongCo \? \(/, "ChatEngine chỉ render SAU khi mở chat");
  // Seam QA: chi khi trang chay tai `localhost` — khong bao gio tren fanfic.world.
  assert.match(p, /if \(typeof window === "undefined" \|\| window\.location\.hostname !== "localhost"\) return null;/);
});

test("1c. dang nhap Fanfic KHONG mo chat: phien Fanfic va cai dat nut khong goi moChat", () => {
  assert.ok(!/chat/i.test(codeOnly(read("lib/session.tsx"))), "lib/session.tsx không được biết gì về chat");
  const p = provider();
  // Duong tu mo DUY NHAT luc co phien la "resume", va no bi khoa sau co sessionStorage.
  const tuMo = [...p.matchAll(/moChat\("([a-z-]+)"\)/g)].map((m) => m[1]).sort();
  assert.deepEqual(tuMo, ["profile-dm", "resume"], "chỉ hai lời mở trong provider: bấm \"Nhắn tin\" và mở lại tab ĐÃ bật");
  // "profile-dm" CHI nam trong `nhanTinVoi` (nguoi dung bam nut o ho so).
  const nhanTin = p.slice(p.indexOf("const nhanTinVoi = useCallback"), p.indexOf("const send = useCallback"));
  assert.match(nhanTin, /await moChat\("profile-dm"\)/);
  assert.match(p, /if \(id && !cu && docCo\(\)\) queueMicrotask\(\(\) => void moChat\("resume"\)\)/);
  // chatApi.session CHI trong xinPhien.
  assert.equal((p.match(/chatApi\s*\.session\(/g) ?? []).length, 1);
  const launcher = codeOnly(read("components/chat/ChatLauncher.tsx"));
  const truocReturn = launcher.slice(0, launcher.indexOf("const bam"));
  assert.ok(!/moChat\(/.test(truocReturn), "ChatLauncher gọi moChat lúc render/mount");
  assert.match(launcher, /const bam = \(\) => \{[\s\S]*void moChat\("inbox"\)/);
});

test("2. mo /messages khoi tao chat MOT lan (co khoa), moChat idempotent", () => {
  const trang = codeOnly(read("app/messages/page.tsx"));
  assert.match(trang, /if \(!profile \|\| daMoRef\.current\) return;\s*daMoRef\.current = true;\s*void moChat\("messages-page"\)/);
  const p = provider();
  assert.match(p, /if \(status === "ready" \|\| status === "reconnecting" \|\| status === "offline"\) return true;/);
  assert.match(p, /if \(dangMoRef\.current\) return dangMoRef\.current;/, "hai lần bấm liền nhau phải dùng CHUNG một lần mở");
  /*
    Loi THAT tim thay qua QA: effect cua trang con chay TRUOC effect cua
    provider, nen mot `moChat` doc `profileIdRef` bo qua lan mo dau tien khi
    vao thang /messages. `moChat` phai doc phien tu closure.
  */
  const moChat = p.slice(p.indexOf("const moChat = useCallback"), p.indexOf("const dungOTabNay"));
  assert.match(moChat, /if \(!coPhienFanfic\) return false;/);
  assert.ok(!/profileIdRef/.test(moChat), "moChat không được dựa vào ref do effect của provider gán");
});

test("7b. di dong: cuoc tro chuyen phu man hinh THAT — bo transform/backdrop-filter cua to tien", () => {
  const css = readFileSync(new URL("../src/app/chat.css", import.meta.url), "utf8");
  assert.match(css, /\.chat-trang:has\(\.chat-co-hoi-thoai\) \{ transform: none; animation: none; \}/);
  assert.match(css, /\.chat-co-hoi-thoai \{ -webkit-backdrop-filter: none; backdrop-filter: none; \}/);
});

test("3+6. provider + drawer gan o LAYOUT (song xuyen route), khong o trang nao", () => {
  const layout = codeOnly(read("app/layout.tsx"));
  assert.match(layout, /<ChatProvider>/);
  assert.match(layout, /<ChatDrawer \/>/);
  assert.ok(layout.indexOf("<ChatProvider>") < layout.indexOf("<main id=\"main\">"), "ChatProvider phải bao ngoài {children}");
  for (const p of moiTep(join(SRC, "app"))) {
    if (tuongDoi(p) === "app/layout.tsx") continue;
    assert.ok(!/<ChatProvider|<ChatDrawer/.test(readFileSync(p, "utf8")), `${tuongDoi(p)} tự gắn ChatProvider/ChatDrawer — sẽ mất kết nối khi đổi trang`);
  }
});

test("4. khong bi mat nao o frontend: khong khoa, khong NEXT_PUBLIC cho Tencent", () => {
  for (const p of moiTep()) {
    const s = readFileSync(p, "utf8");
    assert.ok(!/SECRET_KEY|SDKSecretKey|secretKey/i.test(s), `${tuongDoi(p)} nhắc tới khoá bí mật`);
    assert.ok(!/NEXT_PUBLIC_[A-Z_]*(TENCENT|CHAT)/.test(s), `${tuongDoi(p)} đưa cấu hình chat ra biến NEXT_PUBLIC_`);
  }
  // SDKAppID chi den tu phien may chu, khong chep cung.
  assert.ok(!/2004736[23]/.test(moiTep().map((p) => readFileSync(p, "utf8")).join("\n")), "SDKAppID bị chép cứng vào frontend");
});

test("5. so chua doc cap nhat sau khi khoi tao: su kien SDK -> state -> nut", () => {
  assert.match(transport(), /EV\.TOTAL_UNREAD_MESSAGE_COUNT_UPDATED, \(e\) => h\.onUnread\(/);
  assert.match(provider(), /onUnread: \(n\) => setUnreadTotal\(n\)/);
  const launcher = codeOnly(read("components/chat/ChatLauncher.tsx"));
  assert.match(launcher, /unreadTotal > 0 \? \(/);
  assert.match(launcher, /aria-label=\{unreadTotal > 0 \? `Tin nhắn, \$\{unreadTotal\} chưa đọc` : "Tin nhắn"\}/);
});

test("7. di dong khong tran: drawer an, bang/khung co tran chieu rong, mot cot", () => {
  const css = readFileSync(new URL("../src/app/chat.css", import.meta.url), "utf8");
  const mobile = css.slice(css.indexOf("@media (max-width: 640px)"));
  assert.match(mobile, /\.chat-drawer, \.chat-drawer-thu \{ display: none; \}/);
  assert.match(mobile, /\.chat-khong-gian \{ grid-template-columns: minmax\(0, 1fr\);/);
  assert.match(mobile, /\.chat-nut \{ width: 44px; height: 44px; \}/, "nút chạm tối thiểu 44px");
  assert.match(mobile, /env\(safe-area-inset-bottom/, "ô soạn tin phải tránh vùng an toàn đáy");
  assert.match(css, /\.chat-inbox \{\s*width: min\(360px, calc\(100vw - 32px\)\);/);
  assert.match(css, /\.chat-drawer \{[\s\S]*?width: min\(440px, calc\(100vw - 32px\)\);/);
});

test("8. loi phien co giao dien TRUNG THUC cho moi ma loi", () => {
  const types = codeOnly(read("lib/chat/types.ts"));
  const ma = [...types.slice(types.indexOf("export type ChatErrorCode"), types.indexOf("export type MessageStatus")).matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  assert.ok(ma.length >= 7);
  const loi = read("components/chat/ChatErrorState.tsx");
  for (const m of ma) assert.match(loi, new RegExp(`\\b${m}: \\{\\s*title:`), `thiếu câu cho mã lỗi "${m}"`);
  const p = provider();
  assert.match(p, /e\.status === 401 \|\| e\.status === 403\) return "unauthorized"/);
  assert.match(p, /e\.status === 429\) return "rate_limited"/);
  assert.match(p, /e\.status === 503 && e\.code === "chat_not_configured"\) return "not_configured"/);
});

test("khong vong lap vo han: thu lai co tran, tab bi day khong tu dang nhap lai", () => {
  const p = provider();
  assert.match(p, /const THU_LAI_PHIEN_MS = \[1000, 3000\];/);
  assert.match(p, /const DANG_NHAP_LAI_TOI_DA = 2;/);
  assert.match(p, /setKickReason\(lyDoDay\);\s*doiTrangThai\("kicked"\);\s*datCo\(false\);/);
  assert.match(p, /e\.status === 0 \|\| \(e\.status >= 500 && e\.code !== "chat_not_configured"\)/, "401/429/503 không được thử lại");
});

test("review doc lap: dang xuat giua chung khong gan phien nguoi truoc cho nguoi sau; mot chot cho moi luot mo", () => {
  const p = provider();
  // The he tang TRUOC khi go ket noi; luot mo dang do tu huy sau moi await.
  const teardown = p.slice(p.indexOf("if (cu && cu !== id)"), p.indexOf("if (id && !cu && docCo())"));
  assert.ok(teardown.length > 50, "không tìm thấy khối teardown");
  assert.match(teardown, /theHeRef\.current \+= 1;\s*dangMoRef\.current = null;/);
  const mo = p.slice(p.indexOf("const moChatThat = useCallback"), p.indexOf("const coPhienFanfic"));
  assert.ok((mo.match(/if \(!conHieuLuc\(\)\)/g) ?? []).length >= 5, "mỗi await trong moChatThat phải kiểm thế hệ");
  assert.match(mo, /void moi\.destroy\(\)/, "transport tạo xong sau khi đăng xuất phải bị huỷ, không gắn vào ref");
  const lai = p.slice(p.indexOf("const dangNhapLai = useCallback"), p.indexOf("const ganTin"));
  assert.match(lai, /if \(!t \|\| dangMoRef\.current \|\| dangNhapLaiDangChayRef\.current\) return;/);
  // "Thu lai" / "Dung o tab nay" khong duoc bo qua chot.
  assert.match(p, /const dungOTabNay = useCallback\(\(\) => \{\s*void chayMo\("take-over"\);/);
  assert.match(p, /const thuLai = useCallback\(\(\) => \{\s*void chayMo\("retry"\);/);
  assert.ok(!/void moChatThat\(/.test(p), "không lời gọi nào được đi thẳng vào moChatThat");
  // Bi day ra: khong tu chiem lai.
  const moChat = p.slice(p.indexOf("const moChat = useCallback"), p.indexOf("const dungOTabNay"));
  assert.match(moChat, /if \(status === "kicked"\) return false;/);
  // Qua han tai dong co: quen promise + go ChatEngine de "Thu lai" tai lai that.
  assert.match(p, /choDongCoRef\.current = null;\s*setCanDongCo\(false\);\s*tuChoi\(new Error\("sdk_load_timeout"\)\)/);
  // Danh tinh loi: hoan 60 s, khong goi lai lien tuc.
  assert.match(p, /bay - \(hongDanhTinhRef\.current\.get\(id\) \?\? 0\) > 60_000/);
});

test("o soan tin: Enter gui, Shift+Enter xuong dong, KHONG gui khi bo go tieng Viet dang soan", () => {
  const c = codeOnly(read("components/chat/ChatComposer.tsx"));
  assert.match(c, /if \(e\.key !== "Enter" \|\| e\.shiftKey\) return;/);
  assert.match(c, /if \(e\.nativeEvent\.isComposing \|\| e\.keyCode === 229\) return;/);
});

test("danh tinh la cua Fanfic: ten/avatar lay tu /api/chat/identities, khong tu Tencent", () => {
  const t = transport();
  assert.ok(!/\.nick\b|\.avatar\b/.test(t.replace(/userProfile\?\.userID/g, "")), "adapter đọc nickname/avatar của Tencent");
  assert.match(provider(), /chatApi\s*\.identities\(\{ chat_user_ids: phan \}\)/);
  const hoSo = codeOnly(read("components/chat/ChatUserHeader.tsx"));
  assert.match(hoSo, /`\/u\/\$\{identity\.username\}`/, "bấm tên phải mở hồ sơ FANFIC");
});

test("hoi thoai mo ra o TIN MOI NHAT ca khi tin truc tiep den truoc lich su (do that tren Chrome QA)", () => {
  const t = codeOnly(read("components/chat/ChatThread.tsx"));
  // Chi dua vao id tin cuoi thi khong du: lich su chen PHIA TRUOC, id cuoi khong doi.
  assert.match(t, /const daTai = !!th\?\.loaded;\s*useLayoutEffect\(\(\) => \{\s*if \(daTai\) xuongCuoi\(\);\s*\}, \[daTai, peerId, xuongCuoi\]\);/);
});

test("lam muot tin nhan: vach ngay Hôm nay/Hôm qua, gio o tin CUOI cum, emoji lon, khung cho", () => {
  const t = codeOnly(read("components/chat/ChatThread.tsx"));
  assert.match(t, /if \(cungNgay\(ms, bay\)\) return "Hôm nay";/);
  assert.match(t, /if \(cungNgay\(ms, bay - 86_400_000\)\) return "Hôm qua";/);
  assert.match(t, /const cuoiCum = !sau \|\| !cungCum\(m, sau\);/);
  assert.match(t, /chiEmoji\(m\.text\) \? " chat-tin-emoji" : ""/);
  assert.match(t, /export function KhungCho\(\)/);
  const css = read("app/chat.css");
  // Neo tin o day ma van cuon duoc: vach dem co gian, KHONG justify-content: flex-end.
  assert.match(css, /\.chat-tin-hop::before \{ content: ""; flex: 1 1 auto; \}/);
  assert.ok(!/\.chat-tin-hop \{[^}]*justify-content: flex-end/.test(css));
  // /messages vua man hinh (do: luoi bat dau ~208px).
  assert.match(css, /height: max\(520px, calc\(100dvh - 228px\)\);/);
});

test("khong bay o soan vo dung khi loi/bi day; danh xung cung thu tu voi trang ca nhan", () => {
  for (const f of ["components/chat/ChatDrawer.tsx", "app/messages/page.tsx"]) {
    assert.match(codeOnly(read(f)), /\{status === "error" \|\| status === "kicked" \? null : \(\s*<ChatComposer/, f);
  }
  const avt = codeOnly(read("components/chat/ChatAvatar.tsx"));
  assert.match(avt, /`✦ \$\{it\.equipped_title\} · Lv\. \$\{it\.level\}`/);
  assert.match(codeOnly(read("app/u/[username]/page.tsx")), /\{gam\.equipped_title\} · Lv\. \{gam\.level\}/);
  // Nguoi khong xac dinh: "?" trung tinh, khong phai chu cai dau "NG".
  assert.match(avt, /name=\{identity && !identity\.found \? "\?" : tenHien\(identity\)\}/);
});

test("nut Nhan tin o ho so: khong cho khach, khong cho chinh minh", () => {
  const trang = codeOnly(read("app/u/[username]/page.tsx"));
  assert.match(trang, /\{xh\.is_self \? null : \(\s*<StartChatButton/);
  const nut = codeOnly(read("components/chat/StartChatButton.tsx"));
  assert.match(nut, /if \(!profile\) return null;/);
});
