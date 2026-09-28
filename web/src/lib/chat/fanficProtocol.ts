/**
 * Phan THUAN cua transport Fanfic (khong fetch, khong React, khong alias `@/`, CHI `import type`) —
 * test chay thang bang `node --test` (Node bo kieu; import GIA TRI tuong doi can duoi tep). Xem
 * `fanficTransport.ts`.
 */
import type { ChatConversation, ChatMessage, StickerRef } from "./types";

/** = `conversationIdFor` o `types.ts` (test ep hai ben khop). */
export const khoaHoiThoai = (peerId: string): string => `C2C${peerId}`;
const conversationIdFor = khoaHoiThoai;

/** Hinh dang may chu tra — lap lai o day (khong import `@/lib/api`) de tep nay thuan. */
export interface MessageDto {
  id: string;
  client_id: string;
  peer_id: string;
  from_me: boolean;
  text: string;
  time: number;
  /** Vang = "text" (may chu cu). */
  kind?: "text" | "sticker";
  /** Tin nhan dan: `null` = ma khong con trong catalog -> hien nhan thay the (`text`). */
  sticker?: StickerRef | null;
}

export interface ConversationDto {
  peer_id: string;
  unread: number;
  muted: boolean;
  last_text: string;
  last_time: number;
  last_from_me: boolean;
  last_message_id: string;
}

export interface SseEvent {
  event: string;
  data: string;
}

/**
 * Tach khung SSE tu bo dem: tra cac khung DA DU (ket thuc bang dong trong) va phan con do dang.
 * Dong `: ...` (nhip tim) bi bo qua; `event:` mac dinh la "message".
 */
export function tachKhungSse(boDem: string): { khung: SseEvent[]; conLai: string } {
  const chuan = boDem.replace(/\r\n/g, "\n");
  const phan = chuan.split("\n\n");
  const conLai = phan.pop() ?? "";
  const khung: SseEvent[] = [];
  for (const p of phan) {
    let event = "message";
    const data: string[] = [];
    for (const dong of p.split("\n")) {
      if (!dong || dong.startsWith(":")) continue;
      const i = dong.indexOf(":");
      const ten = i < 0 ? dong : dong.slice(0, i);
      const giaTri = i < 0 ? "" : dong.slice(i + 1).replace(/^ /, "");
      if (ten === "event") event = giaTri;
      else if (ten === "data") data.push(giaTri);
    }
    if (event !== "message" || data.length) khung.push({ event, data: data.join("\n") });
  }
  return { khung, conLai };
}

export function doiTin(me: string, d: MessageDto, status: ChatMessage["status"] = "sent"): ChatMessage {
  return {
    id: d.id,
    conversationId: conversationIdFor(d.peer_id),
    from: d.from_me ? me : d.peer_id,
    to: d.from_me ? d.peer_id : me,
    flow: d.from_me ? "out" : "in",
    text: d.text,
    time: d.time,
    status,
    ...(d.kind === "sticker" ? { kind: "sticker" as const, sticker: d.sticker ?? null } : {}),
  };
}

export function doiHoiThoai(d: ConversationDto): ChatConversation {
  return {
    id: conversationIdFor(d.peer_id),
    peerId: d.peer_id,
    unread: d.unread,
    lastText: d.last_text,
    lastTime: d.last_time,
    lastFromMe: d.last_from_me,
    muted: !!d.muted,
  };
}

/** Tong chua doc cho nut Tin nhan — hoi thoai TAT TIENG khong tinh. */
export function tongChuaDoc(ds: Iterable<ConversationDto>): number {
  let n = 0;
  for (const d of ds) if (!d.muted) n += d.unread;
  return n;
}

/** Lich cho khi noi lai (ms): tang dan, co tran — khong bao gio vong lap dap may chu. */
export const LUI_NOI_LAI_MS = [1000, 2000, 5000, 10_000, 20_000, 30_000];

export function choNoiLai(lan: number): number {
  return LUI_NOI_LAI_MS[Math.min(lan, LUI_NOI_LAI_MS.length - 1)];
}

const CHU = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";

/** `client_id` ngau nhien 24 ky tu (crypto) — may chu dung `m_<client_id>` lam ID tin: gui lai = idempotent. */
export function taoClientId(rand: (buf: Uint8Array) => Uint8Array = (b) => crypto.getRandomValues(b)): string {
  const b = rand(new Uint8Array(24));
  let s = "";
  for (const x of b) s += CHU[x % CHU.length];
  return s;
}
