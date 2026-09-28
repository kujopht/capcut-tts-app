/**
 * Fanfic Chat V1 — cac bat bien KHONG DUOC hong lang le.
 *
 * Tu 2026-09-28 tin nhan chu KHONG con dung Tencent: du lieu + Realtime o
 * APPWRITE, trinh duyet chi noi chuyen voi API Fanfic (REST + mot luong SSE
 * qua `fetch`). Giao dien Chat V1 GIU NGUYEN — chi transport doi.
 *
 * Quan trong nhat van la LAZY: mot nguoi chi doc/nghe truyen phai tao 0 phien
 * chat, 0 luong. Moi luong mo la mot ket noi toi may chu + Appwrite Realtime;
 * mo luong luc mount la ton tai nguyen cho MOI doc gia. Hong lang le thi phai
 * co test canh.
 *
 * Quet MA NGUON (quy uoc repo: khong jsdom) + test THAT cho phan thuan
 * (`lib/chat/fanficProtocol.ts`). Hanh vi that duoc do trong Chrome (xem bao
 * cao PR): `window.__fanficChat` dem so phien/tai dong co/mo luong.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  choNoiLai,
  doiHoiThoai,
  doiTin,
  khoaHoiThoai,
  taoClientId,
  tachKhungSse,
  tongChuaDoc,
} from "../src/lib/chat/fanficProtocol.ts";
import { conversationIdFor } from "../src/lib/chat/types.ts";

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
const transport = () => codeOnly(read("lib/chat/fanficTransport.ts"));

test("1a. tin nhan chu KHONG can Tencent va trinh duyet KHONG noi chuyen thang voi Appwrite", () => {
  const dung = moiTep().filter((p) => /@tencentcloud\/|tencentTransport|TencentCloudChat/.test(codeOnly(readFileSync(p, "utf8"))));
  assert.deepEqual(dung.map(tuongDoi), [], "còn mã Tencent Chat ở frontend");
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.ok(!Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).some((k) => k.startsWith("@tencentcloud/")),
    "package.json vẫn phụ thuộc Tencent Chat");
  const t = transport();
  // Chi API Fanfic: khong SDK, khong WebSocket/EventSource tu trinh duyet, khong URL Appwrite.
  assert.ok(!/new WebSocket\(|new EventSource\(|appwrite/i.test(t), "transport mở kết nối trực tiếp / biết Appwrite");
  assert.ok(!/\bfetch\(/.test(t), "transport tự gọi fetch — phải đi qua lib/api (token, API_BASE, lỗi)");
  assert.match(t, /from "@\/lib\/api"/);
  for (const p of moiTep()) {
    assert.ok(!/NEXT_PUBLIC_APPWRITE/.test(readFileSync(p, "utf8")), `${tuongDoi(p)} đưa Appwrite ra trình duyệt`);
  }
});

test("1b. transport ngoai bundle SERVER: fanficTransport chi o ChatEngine, ChatEngine chi qua next/dynamic ssr:false", () => {
  /*
    Do that tren `cf:build`: mot `import()` dong thuong trong ChatProvider
    van keo SDK vao `handler.mjs` cua Worker (+897 KB). `ssr: false` la cach
    Next chinh thuc giu module ngoai bundle server.
  */
  for (const p of moiTep()) {
    const ten = tuongDoi(p);
    const s = codeOnly(readFileSync(p, "utf8"));
    if (ten !== "components/chat/ChatEngine.tsx") {
      assert.ok(!/chat\/fanficTransport/.test(s), `${ten} nhắc tới fanficTransport — chỉ ChatEngine được import nó`);
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
  assert.match(moChat, /if \(!CHAT_V1_ENABLED \|\| !coPhienFanfic\) return false;/);
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

test("4. khong bi mat nao o frontend, va token KHONG BAO GIO len URL cua luong", () => {
  for (const p of moiTep()) {
    const s = readFileSync(p, "utf8");
    assert.ok(!/SECRET_KEY|SDKSecretKey|secretKey/i.test(s), `${tuongDoi(p)} nhắc tới khoá bí mật`);
    // Duy nhat MOT co bat/tat (boolean, khong phai cau hinh) duoc phep, va chi o `lib/features.ts`.
    const conLai = s.replace(/NEXT_PUBLIC_CHAT_V1_ENABLED/g, tuongDoi(p) === "lib/features.ts" ? "" : "NEXT_PUBLIC_CHAT_V1_ENABLED");
    assert.ok(!/NEXT_PUBLIC_[A-Z_]*(TENCENT|CHAT)/.test(conLai), `${tuongDoi(p)} đưa cấu hình chat ra biến NEXT_PUBLIC_`);
  }
  assert.ok(!/2004736[23]/.test(moiTep().map((p) => readFileSync(p, "utf8")).join("\n")), "SDKAppID bị chép cứng vào frontend");
  // EventSource khong gui duoc Authorization -> ai do se "tien" dat token vao query. Chan tu goc.
  const api = codeOnly(read("lib/api.ts"));
  const luong = api.slice(api.indexOf("export function openChatStream"), api.indexOf("const peerPath"));
  assert.match(luong, /fetch\(`\$\{API_BASE\}\/api\/chat\/stream`, \{/);
  assert.match(luong, /Authorization: `Bearer \$\{token\}`/);
  assert.ok(!/stream\?|token=|access_token/.test(luong), "token/credential trên URL của luồng");
});

test("5. so chua doc cap nhat sau khi khoi tao: su kien luong -> state -> nut (tat tieng khong tinh)", () => {
  assert.match(transport(), /h\.onUnread\(tongChuaDoc\(hoiThoai\.values\(\)\)\)/);
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

test("danh tinh la cua Fanfic: ten/avatar lay tu /api/chat/identities, khong tu transport", () => {
  const t = transport();
  assert.ok(!/\.nick\b|\.avatar\b|display_name|avatar_url/.test(t), "transport tự đọc tên/ảnh — danh tính chỉ từ /api/chat/identities");
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

test("SSE: tach khung dung, bo nhip tim, giu khung do dang cho lan doc sau", () => {
  const a = tachKhungSse(": ping\n\nevent: ready\ndata: {}\n\ndata: {\"type\":\"message\"}\n\ndata: {\"ty");
  assert.deepEqual(a.khung, [{ event: "ready", data: "{}" }, { event: "message", data: "{\"type\":\"message\"}" }]);
  assert.equal(a.conLai, "data: {\"ty");
  const b = tachKhungSse(a.conLai + "pe\":\"x\"}\r\n\r\n");
  assert.deepEqual(b.khung, [{ event: "message", data: "{\"type\":\"x\"}" }]);
  assert.equal(tachKhungSse("event: bye\ndata: {}\n\n").khung[0].event, "bye");
});

test("anh xa may chu -> giao dien: chieu tin, khoa hoi thoai, tong chua doc TRU tat tieng", () => {
  const m = doiTin("fw_toi", { id: "m_1", client_id: "x", peer_id: "fw_ban", from_me: false, text: "chào", time: 5 });
  assert.deepEqual([m.id, m.conversationId, m.from, m.to, m.flow, m.status], ["m_1", "C2Cfw_ban", "fw_ban", "fw_toi", "in", "sent"]);
  const minh = doiTin("fw_toi", { id: "m_2", client_id: "y", peer_id: "fw_ban", from_me: true, text: "ừ", time: 6 });
  assert.deepEqual([minh.from, minh.to, minh.flow], ["fw_toi", "fw_ban", "out"]);
  const c = doiHoiThoai({ peer_id: "fw_ban", unread: 2, muted: false, last_text: "t", last_time: 9, last_from_me: false, last_message_id: "m_2" });
  assert.deepEqual([c.id, c.peerId, c.unread, c.lastTime], ["C2Cfw_ban", "fw_ban", 2, 9]);
  assert.equal(tongChuaDoc([{ unread: 2, muted: false }, { unread: 5, muted: true }, { unread: 1, muted: false }]), 3);
  for (const p of ["fw_a", "fwh_0123"]) assert.equal(khoaHoiThoai(p), conversationIdFor(p), "khoá hội thoại lệch types.ts");
});

test("noi lai co tran va client_id hop le voi may chu (idempotent theo m_<client_id>)", () => {
  assert.deepEqual([0, 1, 2, 5, 50].map(choNoiLai), [1000, 2000, 5000, 30_000, 30_000]);
  const id = taoClientId();
  assert.match(id, /^[A-Za-z0-9]{16,32}$/, "phải khớp SendIn.client_id ở server/messaging/routes.py");
  assert.notEqual(taoClientId(), id);
  const t = transport();
  // Tin "dang gui" dung CUNG ID may chu se luu -> giao dien gop, khong nhan doi; gui lai = cung client_id.
  assert.match(t, /const id = `m_\$\{clientId\}`;/);
  assert.match(t, /resend\(messageId, onStatus\) \{\s*const g = dangGui\.get\(messageId\);\s*if \(g\) guiThat\(messageId, g, onStatus\);/);
  // Sau noi lai: tai lai hop thu + bu khoang trong TRUOC khi bao da ket noi.
  assert.match(t, /await taiHopThu\(\)\.catch\(\(\) => \{\}\);\s*await buKhoangTrong\(\)\.catch\(\(\) => \{\}\);\s*h\.onNetState\("connected"\);/);
  assert.match(t, /chatApi\.history\(peer, \{ after: moiNhat\.get\(peer\)\?\.id, limit: 50 \}\)/);
  // Dong truoc khi san sang = loi -> LUI; 401/403 -> dung han, khong dap may chu.
  assert.match(t, /if \(!\(await docLuong\(ctrl\.signal\)\)\) \{\s*cho = choNoiLai\(lanNoi\);/);
  assert.match(t, /e\.status === 401 \|\| e\.status === 403/);
  // Nhieu tab: transport KHONG BAO GIO "day" tab khac.
  assert.ok(!/onKicked\(/.test(t), "transport phát kicked — nhiều tab phải cùng chạy");
  // `fetch` KHONG co thoi han cho luong: im lang qua lau (TCP nua song) -> cat + noi lai; mang tat/bat
  // -> cat ngay / noi NGAY (Chrome offline KHONG tu cat ket noi dang mo — do that trong QA).
  assert.match(t, /export const IM_LANG_TOI_DA_MS = 45_000;/);
  assert.match(t, /if \(Date\.now\(\) - lanCuoiCoByte > IM_LANG_TOI_DA_MS\) \{\s*lanCuoiCoByte = Date\.now\(\);\s*ctrl\?\.abort\(\);/);
  assert.match(t, /window\.addEventListener\("offline", khiOffline\);\s*window\.addEventListener\("online", khiOnline\);/);
  assert.match(t, /const khiOnline = \(\) => \{\s*lanNoi = 0;\s*danhThuc\?\.\(\);/);
  assert.match(t, /async destroy\(\) \{\s*dong = true;\s*tatNghe\(\);/, "gỡ listener/interval khi huỷ");
});

test("chan / tat tieng: nut THAT o drawer + /messages, chan qua ConfirmDialog (portal), bo chan thay o soan", () => {
  const menu = codeOnly(read("components/chat/ChatThreadMenu.tsx"));
  // Chan la thao tac manh -> hop thoai xac nhan danger; tat tieng/bo chan lam ngay.
  assert.match(menu, /<ConfirmDialog\s+open\s+danger/);
  assert.match(menu, /await setBlocked\(peerId, true\);/);
  assert.match(menu, /await setBlocked\(peerId, false\);/);
  assert.match(menu, /await setMuted\(peerId, !tatTieng\);/);
  // `.chat-drawer` co backdrop-filter: position:fixed ben trong bi giam -> hop thoai PHAI portal ra body.
  assert.match(menu, /createPortal\(\s*<ConfirmDialog[\s\S]*?document\.body,?\s*\)/);
  // Escape trong menu chi dong menu; Escape trong hop thoai khong dong ca drawer.
  assert.match(menu, /e\.key === "Escape"\) \{\s*e\.stopPropagation\(\);/);
  assert.match(codeOnly(read("components/chat/ChatDrawer.tsx")), /e\.key === "Escape" && !\(e\.target as Element \| null\)\?\.closest\?\.\("\.modal"\)/);
  assert.match(menu, /role="menu"/);
  assert.match(menu, /aria-haspopup="menu"/);
  for (const p of ["components/chat/ChatDrawer.tsx", "app/messages/page.tsx"]) {
    // `key` = nguoi kia: doi cuoc tro chuyen thi menu/hop thoai/loi cu KHONG mang sang.
    assert.match(codeOnly(read(p)), /<ChatThreadMenu key=\{(drawer\.peerId|peer)\} peerId=\{\1\}/, `${p} thiếu menu chặn/tắt tiếng`);
  }
  // Minh da chan: khong co o soan — thay bang dong thong bao + Bo chan.
  const soan = codeOnly(read("components/chat/ChatComposer.tsx"));
  assert.match(soan, /if \(blocked\[props\.peerId\]\) return <DaChan/);
  // Provider: danh sach chan tai MOT lan khi san sang; transport khong ho tro -> an nut.
  const p = provider();
  assert.match(p, /setKhaNang\(\{ mute: !!tt\?\.setMuted, block: !!tt\?\.setBlocked \}\);/);
  assert.match(p, /tt\?\.blockedPeers\?\.\(\)/);
  assert.match(menu, /if \(!canMute && !canBlock\) return null;/);
  // Ngay sau khi tai lai trang, hop thu/danh sach chan CHUA ve: khong duoc hien trang thai doan (do that
  // tren Chrome QA — menu tung hien "Tắt thông báo" cho mot hoi thoai DA tat tieng).
  assert.match(menu, /disabled=\{!inboxLoaded\}/);
  assert.match(menu, /!blocksLoaded \? \(/);
  assert.match(p, /\.finally\(\(\) => setDaTaiChan\(true\)\);/);
  // Dang xuat: xoa trang thai chan/tat tieng cua nguoi truoc.
  assert.match(p, /setChan\(\{\}\);\s*setTatTieng\(\{\}\);/);
  // Transport: tat tieng cap nhat hop thu NGAY (tong tren nut Tin nhan tru hoi thoai tat tieng).
  const t = transport();
  assert.match(t, /await chatApi\.mute\(peerId, muted\);[\s\S]*?hoiThoai\.set\(peerId, \{ \.\.\.cu, muted \}\);\s*phatHopThu\(\);/);
  assert.match(t, /await chatApi\.block\(peerId, blocked\);/);
  assert.equal(doiHoiThoai({ peer_id: "fw_b", unread: 1, muted: true, last_text: "", last_time: 1, last_from_me: false, last_message_id: "m" }).muted, true);
  // Danh sach: dau tat tieng + doc cho trinh doc man hinh.
  assert.match(codeOnly(read("components/chat/ConversationList.tsx")), /c\.muted \? ", đã tắt thông báo" : ""/);
});

test("co web CHAT_V1_ENABLED TAT mac dinh: khong nut, khong khung, khong request chat nao", () => {
  const f = codeOnly(read("lib/features.ts"));
  assert.match(f, /export const CHAT_V1_ENABLED = process\.env\.NEXT_PUBLIC_CHAT_V1_ENABLED === "1";/);
  assert.match(codeOnly(read("components/chat/ChatLauncher.tsx")), /if \(!CHAT_V1_ENABLED\) return null;/);
  assert.match(codeOnly(read("components/chat/StartChatButton.tsx")), /if \(!CHAT_V1_ENABLED\) return null;/);
  const trang = codeOnly(read("app/messages/page.tsx"));
  assert.match(trang, /if \(!CHAT_V1_ENABLED\) \{\s*return \(/);
  // Moi duong mo chat (nut, /messages, ho so, tu mo lai sau khi tai trang) deu qua `moChat`.
  assert.match(provider(), /if \(!CHAT_V1_ENABLED \|\| !coPhienFanfic\) return false;/);
});

test("nut Nhan tin o ho so: khong cho khach, khong cho chinh minh", () => {
  const trang = codeOnly(read("app/u/[username]/page.tsx"));
  assert.match(trang, /\{xh\.is_self \? null : \(\s*<StartChatButton/);
  const nut = codeOnly(read("components/chat/StartChatButton.tsx"));
  assert.match(nut, /if \(!profile\) return null;/);
});
