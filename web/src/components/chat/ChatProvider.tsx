"use client";

/**
 * ChatProvider — nguon trang thai DUY NHAT cua Fanfic Chat V1.
 *
 * Gan o `app/layout.tsx`, BAO NGOAI `{children}`: doi trang chi thay
 * `children`, nen ket noi va drawer SONG XUYEN ROUTE (cung ly do voi
 * `AudioEngineProvider`).
 *
 * BON QUY TAC, moi cai tra gia bang tien that hoac bang long tin:
 *
 * 1. LUOI (lazy). Dang nhap Fanfic KHONG mo chat. Chi `moChat(lyDo)` — goi
 *    tu nut Tin nhan, trang /messages, nut "Nhan tin" o ho so — moi xin phien,
 *    tai dong co va mo luong tin nhan. Nguoi chi doc truyen = 0 luong. Da mo
 *    mot lan trong TAB nay thi tai lai trang se tu mo lai (`sessionStorage`).
 *
 * 2. KHONG VONG LAP VO HAN. Xin phien thu lai toi da 2 lan (1 s, 3 s) cho loi
 *    mang/5xx; 401/429/503 khong thu lai. Mat ket noi thi transport tu noi
 *    lai (lui co tran) va bu khoang trong; ta chi hien trang thai.
 *
 * 3. DA TAB. Du lieu + Realtime o Appwrite (qua API Fanfic): MOI tab mot luong,
 *    khong tab nao day tab nao. Nhanh "bi day" (`kicked`) giu lai cho mot nha
 *    cung cap mot-phien sau nay; transport hien tai khong bao gio phat no.
 *
 * 4. DANH TINH LA CUA FANFIC. Ten/avatar/khung/cap/danh xung lay tu
 *    `POST /api/chat/identities`.
 */

import dynamic from "next/dynamic";
import { usePathname, useRouter } from "next/navigation";
import {
  Component,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { TaiTransport } from "./ChatEngine";
import { ApiError, chatApi, type ChatIdentity, type ChatSessionResponse } from "@/lib/api";
import { useSession } from "@/lib/session";
import { dem, ghiLyDo, ghiSdk, ghiTrangThai } from "@/lib/chat/metrics";
import {
  conversationIdFor,
  type ChatConversation,
  type ChatErrorCode,
  type ChatMessage,
  type ChatStatus,
  type ChatTransport,
  type KickReason,
  type TransportHandlers,
} from "@/lib/chat/types";

/*
  Dong co chat (transport) — `ssr: false` giu no NGOAI bundle server cua
  Worker, va chi render sau khi nguoi dung mo chat. Xem `ChatEngine.tsx`.
*/
const ChatEngine = dynamic(() => import("./ChatEngine"), { ssr: false });
const CHO_DONG_CO_MS = 20_000;

declare global {
  interface Window {
    /** CHI harness QA cuc bo (CDP) dat bien nay — xem `nhaCungCapQa`. */
    __fanficChatQaTransport?: TaiTransport;
  }
}

/**
 * Harness QA cuc bo co the thay nha cung cap bang mot relay gia de kiem GIAO
 * DIEN. CHI co hieu luc khi trang chay tai `localhost` — tren fanfic.world ham
 * nay luon tra `null`, du ai do tu dat bien tren trinh duyet cua chinh ho.
 */
function nhaCungCapQa(): TaiTransport | null {
  if (typeof window === "undefined" || window.location.hostname !== "localhost") return null;
  return window.__fanficChatQaTransport ?? null;
}

/** Chunk dong co tai hong -> bao loi `sdk_load`, KHONG lam sap ca trang. */
class BaoDongCo extends Component<{ onLoi: () => void; children: React.ReactNode }, { hong: boolean }> {
  state = { hong: false };
  static getDerivedStateFromError() {
    return { hong: true };
  }
  componentDidCatch() {
    this.props.onLoi();
  }
  render() {
    return this.state.hong ? null : this.props.children;
  }
}

const CO_PHIEN = "fanfic.chat.active";
const LAM_MOI_TRUOC_MS = 5 * 60 * 1000;
const THU_LAI_PHIEN_MS = [1000, 3000];
const DANG_NHAP_LAI_TOI_DA = 2;
const CUA_SO_DANG_NHAP_LAI_MS = 10 * 60 * 1000;
export const MAN_HINH_CHAT_NHO = "(max-width: 640px)";

export interface ThreadState {
  items: ChatMessage[];
  cursor: string | null;
  loaded: boolean;
  loadingOlder: boolean;
}

export interface DrawerState {
  peerId: string;
  minimized: boolean;
}

interface ChatValue {
  status: ChatStatus;
  errorCode: ChatErrorCode | null;
  kickReason: KickReason | null;
  me: string | null;
  conversations: ChatConversation[];
  unreadTotal: number;
  threads: Record<string, ThreadState>;
  identities: Record<string, ChatIdentity>;
  drawer: DrawerState | null;
  drafts: Record<string, string>;
  /** Mo chat (idempotent). `lyDo` duoc ghi vao bo dem lazy-login. */
  moChat: (lyDo: string) => Promise<boolean>;
  /** Tab bi day ra: dang nhap lai o tab nay (day tab kia). */
  dungOTabNay: () => void;
  thuLai: () => void;
  openThread: (peerId: string) => void;
  /** Nut "Nhan tin" o ho so: tim nguoi theo username roi mo hoi thoai. */
  nhanTinVoi: (username: string) => Promise<void>;
  openDrawer: (peerId: string) => void;
  minimizeDrawer: (min: boolean) => void;
  closeDrawer: () => void;
  send: (peerId: string, text: string) => void;
  retry: (peerId: string, messageId: string) => void;
  loadOlder: (peerId: string) => void;
  markRead: (peerId: string) => void;
  setDraft: (peerId: string, text: string) => void;
  identityOf: (chatUserId: string) => ChatIdentity | undefined;
  /** Nguoi MINH da chan (muc tai khoan, hang `user_blocks`). Khong bao gio lo ai chan minh. */
  blocked: Record<string, true>;
  /** Transport co ho tro tat tieng / chan khong — khong thi giao dien an nut. */
  canMute: boolean;
  canBlock: boolean;
  isMuted: (peerId: string) => boolean;
  /** Nem loi khi may chu tu choi — noi goi tu hien thong bao. */
  setMuted: (peerId: string, muted: boolean) => Promise<void>;
  setBlocked: (peerId: string, blocked: boolean) => Promise<void>;
}

const ChatContext = createContext<ChatValue | null>(null);

export function useChat(): ChatValue {
  const v = useContext(ChatContext);
  if (!v) throw new Error("useChat phải nằm trong <ChatProvider>");
  return v;
}

function maLoi(e: unknown): ChatErrorCode {
  if (e instanceof ApiError) {
    if (e.status === 401 || e.status === 403) return "unauthorized";
    if (e.status === 429) return "rate_limited";
    if (e.status === 503 && e.code === "chat_not_configured") return "not_configured";
    return "network";
  }
  return "network";
}

function coTheThuLai(e: unknown): boolean {
  return e instanceof ApiError && (e.status === 0 || (e.status >= 500 && e.code !== "chat_not_configured"));
}

const cho = (ms: number) => new Promise((r) => setTimeout(r, ms));

function docCo(): boolean {
  try {
    return window.sessionStorage.getItem(CO_PHIEN) === "1";
  } catch {
    return false;
  }
}

function datCo(bat: boolean): void {
  try {
    if (bat) window.sessionStorage.setItem(CO_PHIEN, "1");
    else window.sessionStorage.removeItem(CO_PHIEN);
  } catch {
    /* sessionStorage bi chan — chi mat tinh nang tu mo lai sau khi tai trang */
  }
}

/** Gop hai danh sach tin theo `id`, giu thu tu thoi gian. */
function gopTin(cu: ChatMessage[], moi: ChatMessage[]): ChatMessage[] {
  const theoId = new Map(cu.map((m) => [m.id, m]));
  for (const m of moi) theoId.set(m.id, { ...theoId.get(m.id), ...m });
  return [...theoId.values()].sort((a, b) => a.time - b.time);
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { profile } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  const [status, setStatus] = useState<ChatStatus>("idle");
  const [errorCode, setErrorCode] = useState<ChatErrorCode | null>(null);
  const [kickReason, setKickReason] = useState<KickReason | null>(null);
  const [me, setMe] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ChatConversation[]>([]);
  const [unreadTotal, setUnreadTotal] = useState(0);
  const [threads, setThreads] = useState<Record<string, ThreadState>>({});
  const [identities, setIdentities] = useState<Record<string, ChatIdentity>>({});
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [chan, setChan] = useState<Record<string, true>>({});
  /** Tat tieng mot hoi thoai CHUA co tin (chua nam trong hop thu) — co tin roi thi hop thu la nguon that. */
  const [tatTieng, setTatTieng] = useState<Record<string, boolean>>({});
  const [khaNang, setKhaNang] = useState({ mute: false, block: false });
  /** `true` = da den luc render `ChatEngine` (tai chunk SDK). Chi bat trong `moChat`. */
  const [canDongCo, setCanDongCo] = useState(false);
  const choDongCoRef = useRef<{ p: Promise<TaiTransport>; ok: (t: TaiTransport) => void; hong: () => void } | null>(null);

  const transportRef = useRef<ChatTransport | null>(null);
  const phienRef = useRef<ChatSessionResponse | null>(null);
  const dangMoRef = useRef<Promise<boolean> | null>(null);
  const hengioRef = useRef<number | null>(null);
  const dangNhapLaiRef = useRef<number[]>([]);
  const dangHoiDanhTinhRef = useRef<Set<string>>(new Set());
  /** id -> luc hoi danh tinh HONG gan nhat; hoan 60 s de mot loi khong thanh vong lap goi lai. */
  const hongDanhTinhRef = useRef<Map<string, number>>(new Map());
  /**
   * THE HE phien Fanfic. Tang moi lan dang xuat/doi tai khoan: moi luot mo
   * chat/dang nhap lai dang do dang (dang cho phien, tai chunk SDK, login)
   * tu HUY sau moi `await` khi the he da doi — khong bao gio gan phien chat
   * cua nguoi truoc cho nguoi sau tren mot may dung chung.
   */
  const theHeRef = useRef(0);
  const dangNhapLaiDangChayRef = useRef(false);
  const identitiesRef = useRef(identities);
  const drawerRef = useRef(drawer);
  const profileIdRef = useRef<string | null>(null);

  useEffect(() => {
    identitiesRef.current = identities;
  }, [identities]);
  useEffect(() => {
    drawerRef.current = drawer;
  }, [drawer]);

  const doiTrangThai = useCallback((s: ChatStatus) => {
    setStatus(s);
    ghiTrangThai(s);
  }, []);

  /* ---------------------------------------------------------------- danh tinh */
  const hoiDanhTinh = useCallback((ids: string[]) => {
    const bay = Date.now();
    const can = [...new Set(ids)].filter(
      (id) => id && !identitiesRef.current[id] && !dangHoiDanhTinhRef.current.has(id)
        && bay - (hongDanhTinhRef.current.get(id) ?? 0) > 60_000,
    );
    if (!can.length) return;
    for (const id of can) dangHoiDanhTinhRef.current.add(id);
    const lo: string[][] = [];
    for (let i = 0; i < can.length; i += 50) lo.push(can.slice(i, i + 50));
    for (const phan of lo) {
      chatApi
        .identities({ chat_user_ids: phan })
        .then((r) => {
          setIdentities((cu) => {
            const moi = { ...cu };
            r.items.forEach((it, i) => {
              moi[phan[i]] = it.found ? it : { found: false, chat_user_id: phan[i] };
            });
            return moi;
          });
        })
        .catch(() => {
          // Moi su kien hoi thoai goi lai ham nay: khong hoan thi mot lo loi
          // se bi gui lai lien tuc va an vao han muc chung cua may chu.
          const luc = Date.now();
          for (const id of phan) hongDanhTinhRef.current.set(id, luc);
        })
        .finally(() => {
          for (const id of phan) dangHoiDanhTinhRef.current.delete(id);
        });
    }
  }, []);

  /* ------------------------------------------------------ dong co (chunk SDK) */
  /** Render `ChatEngine` va cho no giao ham tao transport; hong/qua han -> reject. */
  const layDongCo = useCallback((): Promise<TaiTransport> => {
    if (!choDongCoRef.current) {
      let ok: (t: TaiTransport) => void = () => {};
      let hong: () => void = () => {};
      const p = new Promise<TaiTransport>((giai, tuChoi) => {
        const hen = window.setTimeout(() => {
          // Qua han: go ChatEngine + quen promise nay, de "Thu lai" tai lai that
          // su thay vi nhan lai dung promise da reject cho toi khi tai trang.
          choDongCoRef.current = null;
          setCanDongCo(false);
          tuChoi(new Error("sdk_load_timeout"));
        }, CHO_DONG_CO_MS);
        ok = (t) => {
          window.clearTimeout(hen);
          giai(t);
        };
        hong = () => {
          window.clearTimeout(hen);
          choDongCoRef.current = null; // lan "Thu lai" sau se tai lai tu dau
          tuChoi(new Error("sdk_load"));
        };
      });
      choDongCoRef.current = { p, ok, hong };
    }
    setCanDongCo(true);
    return choDongCoRef.current.p;
  }, []);
  const onDongCo = useCallback((tai: TaiTransport) => choDongCoRef.current?.ok(tai), []);
  const onLoiDongCo = useCallback(() => {
    choDongCoRef.current?.hong();
    setCanDongCo(false);
  }, []);

  /* ------------------------------------------------------------ phien + SDK */
  const xinPhien = useCallback(async (): Promise<ChatSessionResponse> => {
    for (let lan = 0; ; lan += 1) {
      try {
        dem("sessionRequests");
        const p = await chatApi.session();
        phienRef.current = p;
        return p;
      } catch (e) {
        if (lan >= THU_LAI_PHIEN_MS.length || !coTheThuLai(e)) throw e;
        await cho(THU_LAI_PHIEN_MS[lan]);
      }
    }
  }, []);

  /** Hen lam moi phien TRUOC khi het han: chi giu san phien moi, khong dang nhap lai. */
  const henLamMoi = useCallback((p: ChatSessionResponse) => {
    const theHe = theHeRef.current;
    const hen = (phien: ChatSessionResponse) => {
      if (theHeRef.current !== theHe) return; // da dang xuat: khong hen gi nua
      if (hengioRef.current !== null) window.clearTimeout(hengioRef.current);
      // TTL dai: lam moi truoc 5 phut. TTL ngan (gan muc toi thieu 300 s):
      // lam moi o NUA TTL — khong de moi tab xin mot phien moi 30 giay.
      const conLai = phien.expiresAt - Date.now();
      const sau = Math.max(30_000, conLai > 2 * LAM_MOI_TRUOC_MS ? conLai - LAM_MOI_TRUOC_MS : conLai / 2);
      hengioRef.current = window.setTimeout(() => {
        if (theHeRef.current !== theHe) return;
        xinPhien().then(hen).catch(() => {
          /* van dang ket noi thi khong sao; het han thi nhanh `session_expired` lo */
        });
      }, sau);
    };
    hen(p);
  }, [xinPhien]);

  const dangNhapLai = useCallback(async () => {
    const t = transportRef.current;
    // Mot luot mo/dang nhap lai dang chay thi KHONG chay chong len no.
    if (!t || dangMoRef.current || dangNhapLaiDangChayRef.current) return;
    const theHe = theHeRef.current;
    const bay = Date.now();
    dangNhapLaiRef.current = dangNhapLaiRef.current.filter((x) => bay - x < CUA_SO_DANG_NHAP_LAI_MS);
    if (dangNhapLaiRef.current.length >= DANG_NHAP_LAI_TOI_DA) {
      setErrorCode("expired");
      doiTrangThai("error");
      return;
    }
    dangNhapLaiRef.current.push(bay);
    dangNhapLaiDangChayRef.current = true;
    doiTrangThai("connecting");
    try {
      let p = phienRef.current;
      if (!p || p.expiresAt - Date.now() < 60_000) p = await xinPhien();
      if (theHeRef.current !== theHe) return;
      await t.login(p.userId);
      if (theHeRef.current !== theHe) return;
      dem("logins");
      henLamMoi(p);
    } catch (e) {
      if (theHeRef.current !== theHe) return;
      dem("loginFailures");
      setErrorCode(e instanceof ApiError ? maLoi(e) : "expired");
      doiTrangThai("error");
    } finally {
      dangNhapLaiDangChayRef.current = false;
    }
  }, [doiTrangThai, henLamMoi, xinPhien]);

  const ganTin = useCallback((ds: ChatMessage[]) => {
    setThreads((cu) => {
      const moi = { ...cu };
      for (const m of ds) {
        const th = moi[m.conversationId] ?? { items: [], cursor: null, loaded: false, loadingOlder: false };
        moi[m.conversationId] = { ...th, items: gopTin(th.items, [m]) };
      }
      return moi;
    });
  }, []);

  const moChatThat = useCallback(async (lyDo: string): Promise<boolean> => {
    const theHe = theHeRef.current;
    /** Sau moi `await`: nguoi dung da dang xuat/doi tai khoan thi luot nay HUY. */
    const conHieuLuc = () => theHeRef.current === theHe;
    ghiLyDo(lyDo);
    setErrorCode(null);
    setKickReason(null);
    doiTrangThai("connecting");
    ghiSdk("loading");
    let p: ChatSessionResponse;
    try {
      p = await xinPhien();
    } catch (e) {
      if (!conHieuLuc()) return false;
      setErrorCode(maLoi(e));
      doiTrangThai("error");
      ghiSdk("idle");
      return false;
    }
    if (!conHieuLuc()) return false;
    let t = transportRef.current;
    if (!t) {
      try {
        dem("sdkLoads");
        const tai = nhaCungCapQa() ?? (await layDongCo());
        const handlers: TransportHandlers = {
          onReady: () => {
            doiTrangThai(typeof navigator !== "undefined" && navigator.onLine === false ? "offline" : "ready");
            ghiSdk("logged-in");
            const tt = transportRef.current;
            setKhaNang({ mute: !!tt?.setMuted, block: !!tt?.setBlocked });
            tt?.blockedPeers?.()
              .then((ds) => setChan(Object.fromEntries(ds.map((id) => [id, true as const]))))
              .catch(() => {});
            transportRef.current
              ?.conversations()
              .then((ds) => {
                setConversations(ds);
                hoiDanhTinh(ds.map((c) => c.peerId));
              })
              .catch(() => {});
          },
          onNotReady: () => {
            /* logout/kick da tu dat trang thai rieng; o day khong doan them */
          },
          onMessages: (ds) => {
            ganTin(ds);
            hoiDanhTinh(ds.map((m) => (m.flow === "in" ? m.from : m.to)));
            const dang = drawerRef.current;
            if (dang && !dang.minimized && document.visibilityState === "visible"
              && ds.some((m) => m.conversationId === conversationIdFor(dang.peerId))) {
              transportRef.current?.markRead(conversationIdFor(dang.peerId)).catch(() => {});
            }
          },
          onConversations: (ds) => {
            setConversations(ds);
            hoiDanhTinh(ds.map((c) => c.peerId));
          },
          onUnread: (n) => setUnreadTotal(n),
          onKicked: (lyDoDay) => {
            if (lyDoDay === "session_expired") {
              void dangNhapLai();
              return;
            }
            setKickReason(lyDoDay);
            doiTrangThai("kicked");
            datCo(false); // KHONG tu dang nhap lai — tranh hai tab day nhau mai
          },
          onNetState: (s) => {
            if (s === "connected") doiTrangThai("ready");
            else if (typeof navigator !== "undefined" && navigator.onLine === false) doiTrangThai("offline");
            else doiTrangThai("reconnecting");
          },
        };
        const moi = await tai(p, handlers);
        if (!conHieuLuc()) {
          void moi.destroy().catch(() => {});
          return false;
        }
        t = moi;
        transportRef.current = t;
        ghiSdk("loaded");
      } catch {
        if (!conHieuLuc()) return false;
        setErrorCode("sdk_load");
        doiTrangThai("error");
        ghiSdk("idle");
        return false;
      }
    }
    try {
      await t.login(p.userId);
      if (!conHieuLuc()) {
        // Dang xuat trong luc dang mo luong: dong ngay phien vua mo.
        void t.logout().catch(() => {}).finally(() => t?.destroy().catch(() => {}));
        return false;
      }
      dem("logins");
      setMe(p.userId);
      datCo(true);
      henLamMoi(p);
      return true;
    } catch {
      if (!conHieuLuc()) return false;
      dem("loginFailures");
      setErrorCode("login");
      doiTrangThai("error");
      return false;
    }
  }, [dangNhapLai, doiTrangThai, ganTin, henLamMoi, hoiDanhTinh, layDongCo, xinPhien]);

  /*
    Doc `profile` tu CLOSURE, khong tu `profileIdRef`: effect cua trang CON
    (vd /messages goi `moChat` ngay khi co phien) chay TRUOC effect cua
    provider nay — luc do ref chua duoc gan va lan mo dau tien bi bo qua.
  */
  const coPhienFanfic = !!profile?.user_id;

  /** CHOT CHUNG: moi luot mo (ke ca "Thu lai", "Dung o tab nay") di qua day — khong bao gio hai luot song song. */
  const chayMo = useCallback((lyDo: string): Promise<boolean> => {
    if (dangMoRef.current) return dangMoRef.current;
    const lan: Promise<boolean> = moChatThat(lyDo).finally(() => {
      if (dangMoRef.current === lan) dangMoRef.current = null;
    });
    dangMoRef.current = lan;
    return lan;
  }, [moChatThat]);

  const moChat = useCallback(async (lyDo: string): Promise<boolean> => {
    if (!coPhienFanfic) return false;
    // Bi day sang noi khac: KHONG tu chiem lai (se day tab/thiet bi kia ra) —
    // de giao dien hien lua chon "Dung o tab nay", nguoi dung tu quyet.
    if (status === "kicked") return false;
    if (status === "ready" || status === "reconnecting" || status === "offline") return true;
    if (dangMoRef.current) return dangMoRef.current;
    return chayMo(lyDo);
  }, [chayMo, coPhienFanfic, status]);

  const dungOTabNay = useCallback(() => {
    void chayMo("take-over");
  }, [chayMo]);

  const thuLai = useCallback(() => {
    void chayMo("retry");
  }, [chayMo]);

  /* ------------------------------------------------ phien Fanfic doi / dang xuat */
  useEffect(() => {
    const id = profile?.user_id ?? null;
    const cu = profileIdRef.current;
    profileIdRef.current = id;
    if (cu && cu !== id) {
      // Dang xuat hoac doi tai khoan: go ket noi chat cua nguoi truoc. Tang THE
      // HE truoc tien — moi luot mo/dang nhap lai dang do dang se tu huy.
      theHeRef.current += 1;
      dangMoRef.current = null;
      dangNhapLaiDangChayRef.current = false;
      dangNhapLaiRef.current = [];
      const t = transportRef.current;
      transportRef.current = null;
      phienRef.current = null;
      if (hengioRef.current !== null) window.clearTimeout(hengioRef.current);
      datCo(false);
      void t?.logout().catch(() => {}).finally(() => t?.destroy().catch(() => {}));
      queueMicrotask(() => {
        doiTrangThai("idle");
        ghiSdk("idle");
        setErrorCode(null);
        setKickReason(null);
        setIdentities({});
        setMe(null);
        setConversations([]);
        setThreads({});
        setUnreadTotal(0);
        setDrawer(null);
        setDrafts({});
        setChan({});
        setTatTieng({});
        setKhaNang({ mute: false, block: false });
      });
    }
    // Da bat tin nhan trong tab nay truoc khi tai lai trang -> mo lai.
    if (id && !cu && docCo()) queueMicrotask(() => void moChat("resume"));
  }, [profile?.user_id, doiTrangThai, moChat]);

  /* ------------------------------------------------------- mang cua trinh duyet */
  useEffect(() => {
    const off = () => setStatus((s) => (s === "ready" || s === "reconnecting" ? "offline" : s));
    const on = () => setStatus((s) => (s === "offline" ? "reconnecting" : s));
    window.addEventListener("offline", off);
    window.addEventListener("online", on);
    return () => {
      window.removeEventListener("offline", off);
      window.removeEventListener("online", on);
    };
  }, []);

  useEffect(() => () => {
    if (hengioRef.current !== null) window.clearTimeout(hengioRef.current);
  }, []);

  /* ------------------------------------------------------------- hoi thoai */
  const napLichSu = useCallback((peerId: string, cu = false) => {
    const t = transportRef.current;
    if (!t) return;
    const cid = conversationIdFor(peerId);
    setThreads((ds) => {
      const th = ds[cid] ?? { items: [], cursor: null, loaded: false, loadingOlder: false };
      return { ...ds, [cid]: { ...th, loadingOlder: cu } };
    });
    const conTro = cu ? threads[cid]?.cursor ?? null : null;
    t.history(cid, conTro)
      .then((trang) => {
        setThreads((ds) => {
          const th = ds[cid] ?? { items: [], cursor: null, loaded: false, loadingOlder: false };
          return { ...ds, [cid]: { items: gopTin(th.items, trang.messages), cursor: trang.cursor, loaded: true, loadingOlder: false } };
        });
      })
      .catch(() => {
        setThreads((ds) => {
          const th = ds[cid] ?? { items: [], cursor: null, loaded: false, loadingOlder: false };
          return { ...ds, [cid]: { ...th, loaded: true, loadingOlder: false } };
        });
      });
  }, [threads]);

  const markRead = useCallback((peerId: string) => {
    transportRef.current?.markRead(conversationIdFor(peerId)).catch(() => {});
  }, []);

  const openThread = useCallback((peerId: string) => {
    hoiDanhTinh([peerId]);
    const th = threads[conversationIdFor(peerId)];
    if (!th?.loaded) napLichSu(peerId);
    markRead(peerId);
  }, [hoiDanhTinh, markRead, napLichSu, threads]);

  const openDrawer = useCallback((peerId: string) => {
    setDrawer({ peerId, minimized: false });
    openThread(peerId);
  }, [openThread]);

  const nhanTinVoi = useCallback(async (username: string) => {
    const ok = await moChat("profile-dm");
    if (!ok) {
      // Loi da nam trong trang thai; mo /messages de nguoi dung THAY no.
      router.push("/messages");
      return;
    }
    try {
      const r = await chatApi.identities({ usernames: [username] });
      const it = r.items[0];
      if (!it?.found || !it.chat_user_id) {
        router.push("/messages");
        return;
      }
      setIdentities((cu) => ({ ...cu, [it.chat_user_id as string]: it }));
      const nho = window.matchMedia(MAN_HINH_CHAT_NHO).matches;
      if (nho) router.push(`/messages?c=${encodeURIComponent(it.chat_user_id)}`);
      else openDrawer(it.chat_user_id);
    } catch {
      router.push("/messages");
    }
  }, [moChat, openDrawer, router]);

  const send = useCallback((peerId: string, text: string) => {
    const t = transportRef.current;
    const sach = text.replace(/\s+$/u, "");
    if (!t || !sach.trim()) return;
    const tin = t.sendText(peerId, sach, (m) => ganTin([m]));
    ganTin([tin]);
    setDrafts((cu) => ({ ...cu, [peerId]: "" }));
  }, [ganTin]);

  const retry = useCallback((_peerId: string, messageId: string) => {
    const t = transportRef.current;
    if (!t) return;
    setThreads((ds) => {
      const moi = { ...ds };
      for (const k of Object.keys(moi)) {
        moi[k] = { ...moi[k], items: moi[k].items.map((m) => (m.id === messageId ? { ...m, status: "sending" } : m)) };
      }
      return moi;
    });
    t.resend(messageId, (m) => ganTin([m]));
  }, [ganTin]);

  const loadOlder = useCallback((peerId: string) => napLichSu(peerId, true), [napLichSu]);

  const minimizeDrawer = useCallback((min: boolean) => {
    setDrawer((d) => (d ? { ...d, minimized: min } : d));
  }, []);
  const closeDrawer = useCallback(() => setDrawer(null), []);
  const setDraft = useCallback((peerId: string, text: string) => {
    setDrafts((cu) => ({ ...cu, [peerId]: text }));
  }, []);
  const identityOf = useCallback((id: string) => identities[id], [identities]);

  const isMuted = useCallback(
    (peerId: string) => conversations.find((c) => c.peerId === peerId)?.muted ?? tatTieng[peerId] ?? false,
    [conversations, tatTieng],
  );
  const setMuted = useCallback(async (peerId: string, muted: boolean) => {
    const t = transportRef.current;
    if (!t?.setMuted) return;
    await t.setMuted(peerId, muted);
    setTatTieng((cu) => ({ ...cu, [peerId]: muted }));
  }, []);
  const setBlocked = useCallback(async (peerId: string, blocked: boolean) => {
    const t = transportRef.current;
    if (!t?.setBlocked) return;
    await t.setBlocked(peerId, blocked);
    setChan((cu) => {
      const moi = { ...cu };
      if (blocked) moi[peerId] = true;
      else delete moi[peerId];
      return moi;
    });
  }, []);

  // Vao /messages thi drawer nhuong cho khong gian lam viec day du.
  const drawerHien = drawer && !pathname?.startsWith("/messages") ? drawer : null;

  const value = useMemo<ChatValue>(() => ({
    status, errorCode, kickReason, me, conversations, unreadTotal, threads, identities,
    drawer: drawerHien, drafts, moChat, dungOTabNay, thuLai, openThread, nhanTinVoi, openDrawer,
    minimizeDrawer, closeDrawer, send, retry, loadOlder, markRead, setDraft, identityOf,
    blocked: chan, canMute: khaNang.mute, canBlock: khaNang.block, isMuted, setMuted, setBlocked,
  }), [status, errorCode, kickReason, me, conversations, unreadTotal, threads, identities, drawerHien,
    drafts, moChat, dungOTabNay, thuLai, openThread, nhanTinVoi, openDrawer, minimizeDrawer, closeDrawer,
    send, retry, loadOlder, markRead, setDraft, identityOf, chan, khaNang, isMuted, setMuted, setBlocked]);

  return (
    <ChatContext.Provider value={value}>
      {children}
      {canDongCo ? (
        <BaoDongCo onLoi={onLoiDongCo}>
          <ChatEngine onLoaded={onDongCo} />
        </BaoDongCo>
      ) : null}
    </ChatContext.Provider>
  );
}
