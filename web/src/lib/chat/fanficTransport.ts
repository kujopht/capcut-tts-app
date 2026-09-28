/**
 * Transport Fanfic — TEP DUY NHAT giao dien dung de nhan tin. Du lieu + Realtime nam o APPWRITE, nhung
 * trinh duyet CHI noi chuyen voi API Fanfic (`NEXT_PUBLIC_API_BASE`): REST cho lich su/gui/da doc, va
 * MOT luong SSE (`/api/chat/stream`, qua `fetch` de mang header Authorization — token khong bao gio len
 * URL). May chu xac thuc Realtime cua Appwrite bang chinh session cua nguoi dung, nen Appwrite tu loc
 * su kien theo quyen doc cua tung hang. Khong SDK nao, khong WebSocket nao tu trinh duyet, 0 byte
 * Tencent. Nhieu tab: moi tab mot luong, khong tab nao "day" tab nao.
 *
 * Noi lai: lui 1 s -> 30 s (co tran). Sau MOI lan noi lai: tai lai hop thu + BU KHOANG TRONG cho moi
 * hoi thoai da mo (`after=<tin moi nhat da biet>`) — tin den luc mat mang khong mat, khong trung (giao
 * dien gop theo `id`, va ID tin "dang gui" = ID may chu luu: `m_<client_id>`).
 */
import { ApiError, chatApi, openChatStream } from "@/lib/api";
import {
  choNoiLai,
  doiHoiThoai,
  doiTin,
  taoClientId,
  tachKhungSse,
  tongChuaDoc,
  type ConversationDto,
  type MessageDto,
} from "./fanficProtocol";
import {
  conversationIdFor,
  peerIdFromConversation,
  type ChatMessage,
  type ChatTransport,
  type StickerRef,
  type TransportHandlers,
} from "./types";
import type { ChatSessionResponse } from "@/lib/api";

interface DangGui {
  peerId: string;
  clientId: string;
  text: string;
  time: number;
  /** Tin nhan dan: gui LAI cung ma (cung `client_id`) — khong bao gio gui anh. */
  sticker?: StickerRef;
}

/**
 * May chu gui nhip tim moi ~15 s. Khong nhan BYTE nao trong 45 s = ket noi chet ma khong ai bao
 * (TCP nua song sau khi doi Wi-Fi/ngu may) -> cat va noi lai. `fetch` KHONG tu co thoi han cho luong.
 */
export const IM_LANG_TOI_DA_MS = 45_000;

export async function taiFanficTransport(_phien: ChatSessionResponse, h: TransportHandlers): Promise<ChatTransport> {
  let toi = "";
  let dong = false;
  let ctrl: AbortController | null = null;
  let lanNoi = 0;
  let daSanSang = false;
  let lanCuoiCoByte = Date.now();
  /** Goi de cat ngang giac cho noi lai (su kien `online`). */
  let danhThuc: (() => void) | null = null;
  const hoiThoai = new Map<string, ConversationDto>();
  /** peerId -> ID tin moi nhat da biet (bu khoang trong + "da doc toi dau"). */
  const moiNhat = new Map<string, { id: string; time: number }>();
  const daMo = new Set<string>();
  const dangGui = new Map<string, DangGui>();

  const ghiMoiNhat = (peer: string, id: string, time: number) => {
    const cu = moiNhat.get(peer);
    if (!cu || time >= cu.time) moiNhat.set(peer, { id, time });
  };

  const phatHopThu = () => {
    const ds = [...hoiThoai.values()].sort((a, b) => b.last_time - a.last_time).map(doiHoiThoai);
    h.onConversations(ds);
    h.onUnread(tongChuaDoc(hoiThoai.values()));
  };

  const nhanTin = (ds: MessageDto[]) => {
    if (!ds.length) return;
    for (const d of ds) ghiMoiNhat(d.peer_id, d.id, d.time);
    h.onMessages(ds.map((d) => doiTin(toi, d)));
  };

  const taiHopThu = async () => {
    const r = await chatApi.conversations();
    hoiThoai.clear();
    for (const d of r.items) hoiThoai.set(d.peer_id, d);
    phatHopThu();
    return r.items;
  };

  /** Sau khi noi lai: lay moi tin sau tin moi nhat da biet, cho tung hoi thoai DA MO. */
  const buKhoangTrong = async () => {
    for (const peer of daMo) {
      const moc = moiNhat.get(peer);
      if (!moc) continue;
      for (let trang = 0; trang < 10; trang += 1) {
        const r = await chatApi.history(peer, { after: moiNhat.get(peer)?.id, limit: 50 });
        nhanTin(r.messages);
        if (!r.cursor) break;
      }
    }
  };

  /** Tra `true` neu luong da `ready` (dong binh thuong -> noi lai ngay); `false` = dong truoc khi san sang. */
  const docLuong = async (signal: AbortSignal): Promise<boolean> => {
    const res = await openChatStream(signal);
    if (!res.ok || !res.body) throw new ApiError(`stream ${res.status}`, res.status);
    const doc = res.body.getReader();
    const giai = new TextDecoder();
    let boDem = "";
    let sanSang = false;
    for (;;) {
      const { value, done } = await doc.read();
      if (done) return sanSang;
      lanCuoiCoByte = Date.now();
      boDem += giai.decode(value, { stream: true });
      const { khung, conLai } = tachKhungSse(boDem);
      boDem = conLai;
      for (const k of khung) {
        if (k.event === "ready") {
          sanSang = true;
          lanNoi = 0;
          if (!daSanSang) {
            daSanSang = true;
            h.onNetState("connected");
            h.onReady(); // lan DAU: provider tu tai hop thu
          } else {
            // NOI LAI: bu trang thai TRUOC khi bao "da ket noi".
            await taiHopThu().catch(() => {});
            await buKhoangTrong().catch(() => {});
            h.onNetState("connected");
          }
        } else if (k.event === "bye") {
          return true; // may chu dong theo han song — noi lai NGAY
        } else if (k.event === "error") {
          throw new ApiError("stream error", 503);
        } else if (k.event === "message" && k.data) {
          let d: { type?: string; message?: MessageDto; conversation?: ConversationDto };
          try {
            d = JSON.parse(k.data);
          } catch {
            continue;
          }
          if (d.type === "message" && d.message) nhanTin([d.message]);
          else if (d.type === "conversation" && d.conversation) {
            hoiThoai.set(d.conversation.peer_id, d.conversation);
            phatHopThu();
          }
        }
      }
    }
  };

  const vongLuong = async () => {
    while (!dong) {
      // Trinh duyet bao mat mang: KHONG thu (se hong ngay) — cho su kien `online` danh thuc.
      while (!dong && typeof navigator !== "undefined" && navigator.onLine === false) {
        h.onNetState("disconnected");
        await ngu(30_000);
      }
      if (dong) return;
      ctrl = new AbortController();
      lanCuoiCoByte = Date.now();
      let cho = 0;
      try {
        if (!(await docLuong(ctrl.signal))) {
          // Dong ma chua tung san sang: coi nhu loi — LUI, khong vong lap dap may chu.
          cho = choNoiLai(lanNoi);
          lanNoi += 1;
        }
      } catch (e) {
        if (dong) return;
        // 401 (phien het) / 503 (tat) / 429: KHONG dap may chu — bao mat ket noi va dung.
        if (e instanceof ApiError && (e.status === 401 || e.status === 403 || (e.status === 503 && !daSanSang))) {
          h.onNetState("disconnected");
          return;
        }
        cho = choNoiLai(lanNoi);
        lanNoi += 1;
      }
      if (dong) return;
      h.onNetState(daSanSang ? "connecting" : "disconnected");
      if (cho) await ngu(cho);
    }
  };

  /** Ngu `ms`, nhung `danhThuc()` (su kien `online`) cat ngang — co mang lai thi noi NGAY. */
  const ngu = (ms: number) =>
    new Promise<void>((xong) => {
      const hen = setTimeout(() => {
        danhThuc = null;
        xong();
      }, ms);
      danhThuc = () => {
        clearTimeout(hen);
        danhThuc = null;
        xong();
      };
    });

  const khiOffline = () => ctrl?.abort();
  const khiOnline = () => {
    lanNoi = 0;
    danhThuc?.();
  };
  let choTim: ReturnType<typeof setInterval> | null = null;
  const batNghe = () => {
    if (typeof window === "undefined") return;
    window.addEventListener("offline", khiOffline);
    window.addEventListener("online", khiOnline);
    choTim = setInterval(() => {
      if (Date.now() - lanCuoiCoByte > IM_LANG_TOI_DA_MS) {
        lanCuoiCoByte = Date.now();
        ctrl?.abort(); // luong "im lang" qua lau = da chet — noi lai (va bu khoang trong)
      }
    }, 10_000);
  };
  const tatNghe = () => {
    if (typeof window === "undefined") return;
    window.removeEventListener("offline", khiOffline);
    window.removeEventListener("online", khiOnline);
    if (choTim !== null) clearInterval(choTim);
    choTim = null;
  };

  /** Tin "dang gui"/"hong" hien NGAY (lac quan) — cung ID ma may chu se luu (`m_<client_id>`). */
  const tinTam = (id: string, g: DangGui, status: ChatMessage["status"], failCode?: number): ChatMessage => ({
    id,
    conversationId: conversationIdFor(g.peerId),
    from: toi,
    to: g.peerId,
    flow: "out",
    text: g.text,
    time: g.time,
    status,
    ...(failCode !== undefined ? { failCode } : {}),
    ...(g.sticker ? { kind: "sticker" as const, sticker: g.sticker } : {}),
  });

  const guiThat = (id: string, g: DangGui, onStatus: (m: ChatMessage) => void) => {
    chatApi
      .send(g.peerId, g.sticker
        ? { client_id: g.clientId, kind: "sticker", sticker_id: g.sticker.id }
        : { client_id: g.clientId, text: g.text })
      .then((r) => {
        dangGui.delete(id);
        ghiMoiNhat(r.message.peer_id, r.message.id, r.message.time);
        onStatus(doiTin(toi, r.message));
      })
      .catch((e: unknown) => {
        onStatus(tinTam(id, g, "failed", e instanceof ApiError ? e.status : undefined));
      });
  };

  const guiMoi = (g: DangGui, onStatus: (m: ChatMessage) => void): ChatMessage => {
    const id = `m_${g.clientId}`;
    dangGui.set(id, g);
    daMo.add(g.peerId);
    guiThat(id, g, onStatus);
    return tinTam(id, g, "sending");
  };

  return {
    async login(userId) {
      toi = userId;
      dong = false;
      tatNghe();
      batNghe();
      void vongLuong();
    },
    async logout() {
      dong = true;
      tatNghe();
      danhThuc?.();
      ctrl?.abort();
    },
    async conversations() {
      const ds = await taiHopThu();
      return ds.sort((a, b) => b.last_time - a.last_time).map(doiHoiThoai);
    },
    async history(conversationId, cursor) {
      const peer = peerIdFromConversation(conversationId);
      daMo.add(peer);
      const r = await chatApi.history(peer, { before: cursor ?? undefined, limit: 30 });
      for (const d of r.messages) ghiMoiNhat(d.peer_id, d.id, d.time);
      return { messages: r.messages.map((d) => doiTin(toi, d)), cursor: r.cursor };
    },
    sendText(peerId, text, onStatus) {
      return guiMoi({ peerId, clientId: taoClientId(), text, time: Date.now() }, onStatus);
    },
    sendSticker(peerId, sticker, onStatus) {
      // `text` tam = nhan thay the (giong may chu luu) — ban xem truoc/doc man hinh dung ngay luc gui.
      return guiMoi({ peerId, clientId: taoClientId(), text: `Nhãn dán: ${sticker.alt}`, time: Date.now(), sticker },
        onStatus);
    },
    resend(messageId, onStatus) {
      const g = dangGui.get(messageId);
      if (g) guiThat(messageId, g, onStatus); // CUNG client_id -> may chu khong tao tin thu hai
    },
    async markRead(conversationId) {
      const peer = peerIdFromConversation(conversationId);
      const r = await chatApi.read(peer, moiNhat.get(peer)?.id);
      if (r.conversation) {
        hoiThoai.set(r.conversation.peer_id, r.conversation);
        phatHopThu();
      }
    },
    async setMuted(peerId, muted) {
      await chatApi.mute(peerId, muted);
      const cu = hoiThoai.get(peerId);
      if (cu) {
        hoiThoai.set(peerId, { ...cu, muted });
        phatHopThu(); // tong tren nut Tin nhan doi ngay (tat tieng khong tinh)
      }
    },
    async setBlocked(peerId, blocked) {
      await chatApi.block(peerId, blocked);
    },
    async blockedPeers() {
      return (await chatApi.blocks()).items;
    },
    async destroy() {
      dong = true;
      tatNghe();
      danhThuc?.();
      ctrl?.abort();
      hoiThoai.clear();
      moiNhat.clear();
      daMo.clear();
      dangGui.clear();
    },
  };
}
