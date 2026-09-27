/**
 * Adapter Tencent Chat — TEP DUY NHAT biet toi `@tencentcloud/chat`.
 *
 * SDK (~470 KB) chi duoc tai bang `import()` BEN TRONG `taiTencentTransport`,
 * va ham nay chi duoc goi tu `ChatProvider.moChat()` — tuc la khi nguoi dung
 * THAT SU mo tin nhan. Trang doc/nghe truyen khong bao gio tai byte nao cua
 * SDK, khong mo WebSocket nao, khong tao lan dang nhap nao (0 MAU).
 *
 * Moi kieu cua SDK dung lai o day; giao dien chi thay `lib/chat/types.ts`.
 */
import type { Conversation, Message } from "@tencentcloud/chat";
import {
  peerIdFromConversation,
  type ChatConversation,
  type ChatMessage,
  type ChatTransport,
  type KickReason,
  type NetState,
  type TransportHandlers,
} from "./types";

/** Nhan thay the cho tin khong phai van ban — V1 chi gui/nhan chu. */
const KHONG_HO_TRO = "Tin nhắn này chưa hiển thị được trên web.";

export async function taiTencentTransport(sdkAppId: number, h: TransportHandlers): Promise<ChatTransport> {
  const mod = await import("@tencentcloud/chat");
  const TencentCloudChat = mod.default;
  const chat = TencentCloudChat.create({ SDKAppID: sdkAppId });
  // 1 = release: chi canh bao/loi — khong do nhat ky dang nhap ra console.
  chat.setLogLevel(1);
  const EV = TencentCloudChat.EVENT;
  const T = TencentCloudChat.TYPES;

  let toi = "";
  /** Tin goc cua SDK, de gui lai dung doi tuong (resendMessage can no). */
  const tinGoc = new Map<string, Message>();

  const doiTin = (m: Message): ChatMessage => {
    const laChu = m.type === T.MSG_TEXT;
    return {
      id: m.ID,
      conversationId: m.conversationID,
      from: m.from,
      to: m.to,
      flow: m.flow === "out" ? "out" : "in",
      text: laChu ? String((m.payload as { text?: string } | undefined)?.text ?? "") : KHONG_HO_TRO,
      unsupported: !laChu || undefined,
      time: (m.time || 0) * 1000,
      status: m.status === "fail" ? "failed" : m.status === "unSend" ? "sending" : "sent",
    };
  };

  const doiHoiThoai = (c: Conversation): ChatConversation | null => {
    if (c.type !== T.CONV_C2C) return null; // V1: chi 1:1
    const cuoi = (c.lastMessage ?? {}) as { messageForShow?: string; lastTime?: number; fromAccount?: string };
    return {
      id: c.conversationID,
      peerId: c.userProfile?.userID || peerIdFromConversation(c.conversationID),
      unread: c.unreadCount || 0,
      lastText: cuoi.messageForShow || "",
      lastTime: (cuoi.lastTime || 0) * 1000,
      lastFromMe: !!toi && cuoi.fromAccount === toi,
    };
  };

  const doiDs = (ds: Conversation[]) => ds.map(doiHoiThoai).filter((c): c is ChatConversation => c !== null);

  const lyDoBiDay = (t: unknown): KickReason =>
    t === T.KICKED_OUT_MULT_ACCOUNT ? "multi_instance"
      : t === T.KICKED_OUT_MULT_DEVICE ? "multi_device"
        : t === T.KICKED_OUT_USERSIG_EXPIRED ? "usersig_expired"
          : t === T.KICKED_OUT_REST_API ? "server" : "unknown";

  const trangThaiMang = (s: unknown): NetState =>
    s === T.NET_STATE_CONNECTED ? "connected" : s === T.NET_STATE_CONNECTING ? "connecting" : "disconnected";

  const nghe: Array<[string, (e: { data: unknown }) => void]> = [
    [EV.SDK_READY, () => h.onReady()],
    [EV.SDK_NOT_READY, () => h.onNotReady()],
    [EV.MESSAGE_RECEIVED, (e) => {
      const ds = (e.data as Message[]).filter((m) => m.conversationType === T.CONV_C2C);
      if (ds.length) h.onMessages(ds.map(doiTin));
    }],
    [EV.CONVERSATION_LIST_UPDATED, (e) => h.onConversations(doiDs(e.data as Conversation[]))],
    [EV.TOTAL_UNREAD_MESSAGE_COUNT_UPDATED, (e) => h.onUnread(Number(e.data) || 0)],
    [EV.KICKED_OUT, (e) => h.onKicked(lyDoBiDay((e.data as { type?: unknown })?.type))],
    [EV.NET_STATE_CHANGE, (e) => h.onNetState(trangThaiMang((e.data as { state?: unknown })?.state))],
  ];
  for (const [ten, f] of nghe) chat.on(ten, f);

  const ketQuaGui = (msg: Message, onStatus: (m: ChatMessage) => void) =>
    (p: Promise<{ data?: { message?: Message } }>) => {
      p.then((r) => onStatus(doiTin(r.data?.message ?? msg))).catch((err: { code?: number }) => {
        onStatus({ ...doiTin(msg), status: "failed", failCode: typeof err?.code === "number" ? err.code : undefined });
      });
    };

  return {
    async login(userId, userSig) {
      toi = userId;
      await chat.login({ userID: userId, userSig });
    },
    async logout() {
      await chat.logout();
    },
    async conversations() {
      const r = await chat.getConversationList();
      return doiDs((r?.data?.conversationList ?? []) as Conversation[]);
    },
    async history(conversationId, cursor) {
      const r = await chat.getMessageList({ conversationID: conversationId, nextReqMessageID: cursor || undefined });
      const d = r?.data ?? {};
      const ds = ((d.messageList ?? []) as Message[]);
      for (const m of ds) tinGoc.set(m.ID, m);
      return { messages: ds.map(doiTin), cursor: d.isCompleted ? null : (d.nextReqMessageID || null) };
    },
    sendText(peerId, text, onStatus) {
      const msg = chat.createTextMessage({ to: peerId, conversationType: T.CONV_C2C, payload: { text } });
      tinGoc.set(msg.ID, msg);
      ketQuaGui(msg, onStatus)(chat.sendMessage(msg));
      return { ...doiTin(msg), status: "sending" };
    },
    resend(messageId, onStatus) {
      const msg = tinGoc.get(messageId);
      if (!msg) return;
      ketQuaGui(msg, onStatus)(chat.resendMessage(msg));
    },
    async markRead(conversationId) {
      await chat.setMessageRead({ conversationID: conversationId });
    },
    async destroy() {
      for (const [ten, f] of nghe) chat.off(ten, f);
      await chat.destroy();
    },
  };
}
