/**
 * Fanfic Chat V1 — kieu dung chung cho giao dien chat.
 *
 * Giao dien KHONG BAO GIO cham nha cung cap: moi thu di qua `ChatTransport`
 * (hien tai `fanficTransport.ts` — API Fanfic, du lieu + Realtime o Appwrite).
 * Ban Tencent Chat cu da duoc thay CHI bang mot tep do; khong component nao doi.
 */

/**
 * Vong doi ket noi, theo thu tu thuong gap:
 *   idle        chua ai mo tin nhan — CHUA tai SDK, CHUA xin phien (0 MAU)
 *   connecting  dang xin phien / tai SDK / dang nhap
 *   ready       san sang gui/nhan
 *   reconnecting mat mang tam thoi, SDK dang tu noi lai
 *   offline     trinh duyet bao mat mang (`navigator.onLine === false`)
 *   kicked      tab/thiet bi khac dang dung tai khoan chat nay
 *   error       loi khong tu phuc hoi (xem `ChatErrorCode`)
 */
export type ChatStatus = "idle" | "connecting" | "ready" | "reconnecting" | "offline" | "kicked" | "error";

export type ChatErrorCode =
  | "not_configured" // may chu chua bat tin nhan (503 chat_not_configured)
  | "unauthorized" //   phien Fanfic het han / chua dang nhap (401)
  | "rate_limited" //   xin phien qua nhieu lan (429)
  | "network" //        khong toi duoc may chu Fanfic
  | "sdk_load" //       khong tai duoc dong co chat (chunk)
  | "login" //          khong mo duoc luong tin nhan
  | "expired"; //       phien het han va lam moi that bai

export type MessageStatus = "sending" | "sent" | "failed";

export interface ChatMessage {
  id: string;
  conversationId: string;
  /** userID chat cua nguoi gui. */
  from: string;
  /** userID chat cua nguoi nhan (1:1). */
  to: string;
  /** "out" = cua minh. */
  flow: "in" | "out";
  /** Van ban da loc; tin khong phai chu hien mot nhan thay the, khong bao gio rong. */
  text: string;
  /** Mili-giay. */
  time: number;
  status: MessageStatus;
  /** Tin khong phai van ban (V1 chi gui chu) — giao dien hien nhan thay the. */
  unsupported?: boolean;
  /** Ma loi cua nha cung cap khi `status === "failed"` (de hien, khong de doan). */
  failCode?: number;
}

export interface ChatConversation {
  /** Khoa hoi thoai 1:1 PHIA GIAO DIEN (`conversationIdFor(peerId)`) — khong phai ID luu tru. */
  id: string;
  /** userID chat cua nguoi kia. */
  peerId: string;
  unread: number;
  lastText: string;
  /** Mili-giay; 0 = chua co tin. */
  lastTime: number;
  lastFromMe: boolean;
  /** Tat tieng RIENG hoi thoai nay: tin van den, khong tinh vao tong tren nut Tin nhan. */
  muted?: boolean;
}

export interface HistoryPage {
  messages: ChatMessage[];
  /** `null` = da het lich su. */
  cursor: string | null;
}

export type NetState = "connected" | "connecting" | "disconnected";
/** Transport hien tai (Appwrite qua API Fanfic) KHONG phat ly do nao — nhieu tab cung chay. Giu hop dong
 *  cho mot nha cung cap mot-phien sau nay; `session_expired` -> provider tu mo lai phien. */
export type KickReason = "multi_instance" | "multi_device" | "session_expired" | "server" | "unknown";

export interface TransportHandlers {
  onReady: () => void;
  onNotReady: () => void;
  onMessages: (messages: ChatMessage[]) => void;
  onConversations: (list: ChatConversation[]) => void;
  onUnread: (total: number) => void;
  onKicked: (reason: KickReason) => void;
  onNetState: (state: NetState) => void;
}

/** Hop dong duy nhat giua giao dien va nha cung cap chat. */
export interface ChatTransport {
  /** `userId` = ma chat cua minh (tu `/api/chat/session`). Khong co credential rieng nao. */
  login(userId: string): Promise<void>;
  logout(): Promise<void>;
  conversations(): Promise<ChatConversation[]>;
  history(conversationId: string, cursor?: string | null): Promise<HistoryPage>;
  /** Tra ve tin da tao (trang thai "sending"); cap nhat qua `onStatus`. */
  sendText(peerId: string, text: string, onStatus: (m: ChatMessage) => void): ChatMessage;
  resend(messageId: string, onStatus: (m: ChatMessage) => void): void;
  markRead(conversationId: string): Promise<void>;
  /** Tat/bat tieng MOT hoi thoai. Tuy chon: transport khong ho tro thi giao dien an nut. */
  setMuted?(peerId: string, muted: boolean): Promise<void>;
  /** Chan/bo chan o MUC TAI KHOAN (dung chung `user_blocks` voi trang ca nhan). */
  setBlocked?(peerId: string, blocked: boolean): Promise<void>;
  /** Nhung nguoi MINH da chan (khong bao gio lo ai chan minh). */
  blockedPeers?(): Promise<string[]>;
  destroy(): Promise<void>;
}

/** Tien to "C2C" giu tu Chat V1 de moi khoa trang thai giao dien (thread, nhap) khong doi. */
export function conversationIdFor(peerId: string): string {
  return `C2C${peerId}`;
}

export function peerIdFromConversation(conversationId: string): string {
  return conversationId.startsWith("C2C") ? conversationId.slice(3) : conversationId;
}
