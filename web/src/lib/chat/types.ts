/**
 * Fanfic Chat V1 — kieu dung chung cho giao dien chat.
 *
 * Giao dien KHONG BAO GIO cham kieu cua SDK Tencent: moi thu di qua
 * `ChatTransport` (xem `tencentTransport.ts`). Nho vay component khong biet
 * Tencent la ai, va doi nha cung cap sau nay chi thay mot tep.
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
  | "sdk_load" //       khong tai duoc thu vien chat
  | "login" //          Tencent tu choi dang nhap
  | "expired"; //       UserSig het han va lam moi that bai

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
  /** Dang Tencent "C2C<userID>". */
  id: string;
  /** userID chat cua nguoi kia. */
  peerId: string;
  unread: number;
  lastText: string;
  /** Mili-giay; 0 = chua co tin. */
  lastTime: number;
  lastFromMe: boolean;
}

export interface HistoryPage {
  messages: ChatMessage[];
  /** `null` = da het lich su. */
  cursor: string | null;
}

export type NetState = "connected" | "connecting" | "disconnected";
export type KickReason = "multi_instance" | "multi_device" | "usersig_expired" | "server" | "unknown";

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
  login(userId: string, userSig: string): Promise<void>;
  logout(): Promise<void>;
  conversations(): Promise<ChatConversation[]>;
  history(conversationId: string, cursor?: string | null): Promise<HistoryPage>;
  /** Tra ve tin da tao (trang thai "sending"); cap nhat qua `onStatus`. */
  sendText(peerId: string, text: string, onStatus: (m: ChatMessage) => void): ChatMessage;
  resend(messageId: string, onStatus: (m: ChatMessage) => void): void;
  markRead(conversationId: string): Promise<void>;
  destroy(): Promise<void>;
}

export function conversationIdFor(peerId: string): string {
  return `C2C${peerId}`;
}

export function peerIdFromConversation(conversationId: string): string {
  return conversationId.startsWith("C2C") ? conversationId.slice(3) : conversationId;
}
