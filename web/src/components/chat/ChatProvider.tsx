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
  useSyncExternalStore,
} from "react";
import type { TaiTransport } from "./ChatEngine";
import {
  ApiError,
  chatApi,
  social,
  type ChatIdentity,
  type ChatSessionResponse,
  type StickerPackDto,
} from "@/lib/api";
import { CHAT_V1_ENABLED } from "@/lib/features";
import { useSession } from "@/lib/session";
import { dem, ghiLyDo, ghiSdk, ghiTrangThai } from "@/lib/chat/metrics";
import {
  dangXem,
  docDock,
  docNhap,
  dongCuaSo,
  ghiDock,
  moCuaSo,
  soCuaSoHien,
  thuNhoCuaSo,
  type DockWindow,
} from "@/lib/chat/dock";
import {
  conversationIdFor,
  type ChatConversation,
  type ChatErrorCode,
  type ChatMessage,
  type ChatStatus,
  type ChatTransport,
  type KickReason,
  type StickerRef,
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

interface ChatValue {
  status: ChatStatus;
  errorCode: ChatErrorCode | null;
  kickReason: KickReason | null;
  me: string | null;
  conversations: ChatConversation[];
  unreadTotal: number;
  threads: Record<string, ThreadState>;
  identities: Record<string, ChatIdentity>;
  /**
   * Cac cua so chat dang mo (Chat Dock desktop), `dock[0]` = moi nhat (sat mep phai). Rong o `/messages`
   * (khong gian day du thay the). Song xuyen route va sau khi tai lai trang (`sessionStorage`).
   */
  dock: DockWindow[];
  /** So cua so HIEN duoc theo be rong man hinh (0 = di dong: dung `/messages`). Phan con lai vao ngan tran. */
  maxVisible: number;
  /** Nguoi dung CHU DONG mo/khoi phuc mot cua so -> dua tieu diem vao o soan cua no (phuc hoi thi khong). */
  focusRequest: { peerId: string; n: number } | null;
  drafts: Record<string, string>;
  /** Mo chat (idempotent). `lyDo` duoc ghi vao bo dem lazy-login. */
  moChat: (lyDo: string) => Promise<boolean>;
  /** Tab bi day ra: dang nhap lai o tab nay (day tab kia). */
  dungOTabNay: () => void;
  thuLai: () => void;
  openThread: (peerId: string) => void;
  /** Tai danh tinh + lich su (neu chua) ma KHONG danh dau da doc. */
  ensureThread: (peerId: string) => void;
  /** Trang /messages dang ky nguoi dang mo (`null` khi roi trang). */
  setPageThread: (peerId: string | null) => void;
  /** Nut "Nhan tin" o ho so: tim nguoi theo username roi mo hoi thoai. */
  nhanTinVoi: (username: string) => Promise<void>;
  /** Mo (hoac dua len dau + bo thu nho) cua so cua mot nguoi. Di dong: dua sang `/messages?c=`. */
  openChat: (peerId: string) => void;
  minimizeChat: (peerId: string, min: boolean) => void;
  closeChat: (peerId: string) => void;
  send: (peerId: string, text: string) => void;
  /** Nhan dan: CHI gui ma (may chu kiem mo khoa). `false` = transport khong ho tro -> an nut. */
  canSticker: boolean;
  sendSticker: (peerId: string, sticker: StickerRef) => void;
  /** Catalog nhan dan cua NGUOI XEM — tai LUOI lan dau mo bo chon; `null` = chua tai, `[]` = rong/loi. */
  stickerPacks: StickerPackDto[] | null;
  loadStickers: () => void;
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
  /** Bao cao NGUOI DUNG (`ReportDialog` cua Social, capability `user_reports` tu `/api/limits`). */
  canReport: boolean;
  /** Hop thu da tai tu may chu it nhat MOT lan — truoc do `isMuted` chua biet trang thai that. */
  inboxLoaded: boolean;
  /** Danh sach nguoi minh da chan da tai (hoac tai hong — may chu van tu choi 403, nen khong treo nut). */
  blocksLoaded: boolean;
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

const KHONG_CO_CUA_SO: DockWindow[] = [];

/** Cua so + nhap cua TAB nay — `sessionStorage` (moi tab mot dock rieng, dong tab la het). */
const KHOA_DOCK = "fanfic.chat.dock";
const KHOA_NHAP = "fanfic.chat.drafts";

function docPhien(khoa: string): string | null {
  try {
    return window.sessionStorage.getItem(khoa);
  } catch {
    return null;
  }
}

function ghiPhien(khoa: string, gt: string | null): void {
  try {
    if (gt === null) window.sessionStorage.removeItem(khoa);
    else window.sessionStorage.setItem(khoa, gt);
  } catch {
    /* sessionStorage bi chan — chi mat phuc hoi sau khi tai lai trang */
  }
}

function dangKyDoiKichThuoc(bao: () => void): () => void {
  window.addEventListener("resize", bao);
  return () => window.removeEventListener("resize", bao);
}

/** So cua so hien duoc theo be rong CSS that (khong setState trong effect: `useSyncExternalStore`). */
function useSoCuaSoHien(): number {
  return useSyncExternalStore(dangKyDoiKichThuoc, () => soCuaSoHien(window.innerWidth), () => 0);
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
  const [dock, setDock] = useState<DockWindow[]>([]);
  const maxVisible = useSoCuaSoHien();
  const [focusRequest, setFocusRequest] = useState<{ peerId: string; n: number } | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [chan, setChan] = useState<Record<string, true>>({});
  /** Tat tieng mot hoi thoai CHUA co tin (chua nam trong hop thu) — co tin roi thi hop thu la nguon that. */
  const [tatTieng, setTatTieng] = useState<Record<string, boolean>>({});
  const [khaNang, setKhaNang] = useState({ mute: false, block: false, sticker: false });
  const [goiNhanDan, setGoiNhanDan] = useState<StickerPackDto[] | null>(null);
  const dangTaiNhanDanRef = useRef(false);
  const [coBaoCao, setCoBaoCao] = useState(false);
  const [daTaiHopThu, setDaTaiHopThu] = useState(false);
  const [daTaiChan, setDaTaiChan] = useState(false);
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
  const dockRef = useRef(dock);
  const threadsRef = useRef(threads);
  /** Cuoc dang tai lich su lan dau — xoa khi tai xong/hong (xem `napLichSu`). */
  const dangTaiRef = useRef<Set<string>>(new Set());
  const maxVisibleRef = useRef(maxVisible);
  const pathnameRef = useRef(pathname);
  /** Nguoi dang mo o TRANG `/messages` (trang tu dang ky qua `setPageThread`) — "dang xem" cua trang do. */
  const pagePeerRef = useRef<string | null>(null);
  const profileIdRef = useRef<string | null>(null);

  /**
   * Ban luu cua TAB nay (cua so dang mo + nhap) — doc MOT lan luc hydrate. Khong render ra gi nen khong lech
   * hydration; duoc ap vao state khi chat tu mo lai (`resume`, xem effect phien ben duoi).
   */
  const [banLuu] = useState<{ dock: DockWindow[]; nhap: Record<string, string> } | null>(() =>
    typeof window === "undefined" ? null : { dock: docDock(docPhien(KHOA_DOCK)), nhap: docNhap(docPhien(KHOA_NHAP)) });
  /** CHUA phuc hoi thi KHONG ghi de ban luu bang trang thai rong luc mount. */
  const daPhucHoiRef = useRef(false);

  useEffect(() => {
    identitiesRef.current = identities;
  }, [identities]);
  useEffect(() => {
    dockRef.current = dock;
    if (daPhucHoiRef.current) ghiPhien(KHOA_DOCK, dock.length ? ghiDock(dock) : null);
  }, [dock]);
  useEffect(() => {
    maxVisibleRef.current = maxVisible;
  }, [maxVisible]);
  useEffect(() => {
    threadsRef.current = threads;
  }, [threads]);
  useEffect(() => {
    pathnameRef.current = pathname;
  }, [pathname]);
  useEffect(() => {
    if (!daPhucHoiRef.current) return;
    const coNoiDung = Object.fromEntries(Object.entries(drafts).filter(([, v]) => v.trim()));
    ghiPhien(KHOA_NHAP, Object.keys(coNoiDung).length ? JSON.stringify(coNoiDung) : null);
  }, [drafts]);

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
            setKhaNang({ mute: !!tt?.setMuted, block: !!tt?.setBlocked, sticker: !!tt?.sendSticker });
            tt?.blockedPeers?.()
              .then((ds) => setChan(Object.fromEntries(ds.map((id) => [id, true as const]))))
              .catch(() => {})
              .finally(() => setDaTaiChan(true));
            // Nut Bao cao chi hien khi MAY CHU bat `user_reports` (khong doan tu phia web).
            social.limits().then((l) => setCoBaoCao(Boolean(l.capabilities?.user_reports))).catch(() => {});
            transportRef.current
              ?.conversations()
              .then((ds) => {
                setConversations(ds);
                setDaTaiHopThu(true);
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
            // "Da doc" CHI khi cuoc do dang DUOC XEM THAT: mot cua so dang HIEN (khong thu nho, khong o ngan
            // tran) — hoac dang mo o trang /messages — va tab dang hien. Tin den cua so thu nho/tran: van
            // chua doc (cham so tren cua so / ngan tran / nut Tin nhan).
            if (document.visibilityState !== "visible") return;
            const trangTin = pathnameRef.current?.startsWith("/messages") ?? false;
            const nguoi = new Set(ds.filter((m) => m.flow === "in").map((m) => m.from));
            for (const peer of nguoi) {
              const xem = trangTin ? pagePeerRef.current === peer
                : dangXem(dockRef.current, maxVisibleRef.current, peer);
              if (xem) transportRef.current?.markRead(conversationIdFor(peer)).catch(() => {});
            }
          },
          onConversations: (ds) => {
            setConversations(ds);
            setDaTaiHopThu(true);
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
    // Web chua bat Chat V1 (co build o `lib/features.ts`): KHONG xin phien, KHONG mo luong — 0 request.
    if (!CHAT_V1_ENABLED || !coPhienFanfic) return false;
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
      // Cua so + nhap cua nguoi TRUOC khong duoc song sot sang tai khoan sau tren may dung chung.
      ghiPhien(KHOA_DOCK, null);
      ghiPhien(KHOA_NHAP, null);
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
        dangTaiRef.current.clear();
        setUnreadTotal(0);
        setDock([]);
        setDrafts({});
        setChan({});
        setTatTieng({});
        setKhaNang({ mute: false, block: false, sticker: false });
        setGoiNhanDan(null);
        dangTaiNhanDanRef.current = false;
        setCoBaoCao(false);
        setDaTaiHopThu(false);
        setDaTaiChan(false);
      });
    }
    // Da bat tin nhan trong tab nay truoc khi tai lai trang -> mo lai, KEM cac cua so + nhap dang do.
    if (id && !cu) {
      const moLai = docCo();
      queueMicrotask(() => {
        if (moLai && banLuu) {
          setDock(banLuu.dock);
          setDrafts((d) => ({ ...banLuu.nhap, ...d }));
        }
        daPhucHoiRef.current = true;
        if (moLai) void moChat("resume");
      });
    }
  }, [profile?.user_id, doiTrangThai, moChat, banLuu]);

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
    const cid = conversationIdFor(peerId);
    if (!t) {
      dangTaiRef.current.delete(cid);
      return;
    }
    setThreads((ds) => {
      const th = ds[cid] ?? { items: [], cursor: null, loaded: false, loadingOlder: false };
      return { ...ds, [cid]: { ...th, loadingOlder: cu } };
    });
    const conTro = cu ? threadsRef.current[cid]?.cursor ?? null : null;
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
      })
      .finally(() => {
        dangTaiRef.current.delete(cid);
      });
  }, []);

  const markRead = useCallback((peerId: string) => {
    transportRef.current?.markRead(conversationIdFor(peerId)).catch(() => {});
  }, []);

  /** Tai danh tinh + lich su (neu chua) — KHONG danh dau da doc (cua so thu nho/tran/vua phuc hoi). */
  const ensureThread = useCallback((peerId: string) => {
    hoiDanhTinh([peerId]);
    const cid = conversationIdFor(peerId);
    const th = threadsRef.current[cid];
    // Mot luot tai dang bay cho moi cuoc (nhieu cua so / effect goi cung luc khong nhan doi request).
    if (!th?.loaded && !dangTaiRef.current.has(cid)) {
      dangTaiRef.current.add(cid);
      napLichSu(peerId);
    }
  }, [hoiDanhTinh, napLichSu]);

  const openThread = useCallback((peerId: string) => {
    ensureThread(peerId);
    markRead(peerId);
  }, [ensureThread, markRead]);

  const openChat = useCallback((peerId: string) => {
    if (maxVisibleRef.current === 0) {
      // Di dong: KHONG co cua so noi — cuoc tro chuyen toan man hinh o /messages.
      router.push(`/messages?c=${encodeURIComponent(peerId)}`);
      return;
    }
    setDock((ds) => moCuaSo(ds, peerId));
    setFocusRequest((f) => ({ peerId, n: (f?.n ?? 0) + 1 }));
    openThread(peerId);
  }, [openThread, router]);

  const minimizeChat = useCallback((peerId: string, min: boolean) => {
    setDock((ds) => thuNhoCuaSo(ds, peerId, min));
    if (!min) {
      setFocusRequest((f) => ({ peerId, n: (f?.n ?? 0) + 1 }));
      markRead(peerId);
    }
  }, [markRead]);

  const closeChat = useCallback((peerId: string) => {
    setDock((ds) => dongCuaSo(ds, peerId));
  }, []);

  /** Trang /messages dang ky nguoi dang mo (hoac `null` khi roi) — de tin den duoc danh dau da doc dung. */
  const setPageThread = useCallback((peerId: string | null) => {
    pagePeerRef.current = peerId;
  }, []);

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
      openChat(it.chat_user_id);
    } catch {
      router.push("/messages");
    }
  }, [moChat, openChat, router]);

  const send = useCallback((peerId: string, text: string) => {
    const t = transportRef.current;
    const sach = text.replace(/\s+$/u, "");
    if (!t || !sach.trim()) return;
    const tin = t.sendText(peerId, sach, (m) => ganTin([m]));
    ganTin([tin]);
    setDrafts((cu) => ({ ...cu, [peerId]: "" }));
  }, [ganTin]);

  const sendSticker = useCallback((peerId: string, sticker: StickerRef) => {
    const t = transportRef.current;
    if (!t?.sendSticker) return;
    ganTin([t.sendSticker(peerId, sticker, (m) => ganTin([m]))]);
  }, [ganTin]);

  const loadStickers = useCallback(() => {
    if (dangTaiNhanDanRef.current) return;
    dangTaiNhanDanRef.current = true;
    chatApi.stickers()
      .then((r) => setGoiNhanDan(r.packs))
      .catch(() => {
        setGoiNhanDan([]);
        dangTaiNhanDanRef.current = false; // lan mo bo chon sau thu lai
      });
  }, []);

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

  // Vao /messages thi dock nhuong cho khong gian lam viec day du (cac cua so VAN con, hien lai khi roi trang).
  const dockHien = pathname?.startsWith("/messages") ? KHONG_CO_CUA_SO : dock;

  const value = useMemo<ChatValue>(() => ({
    status, errorCode, kickReason, me, conversations, unreadTotal, threads, identities,
    dock: dockHien, maxVisible, focusRequest, drafts, moChat, dungOTabNay, thuLai, openThread, ensureThread, setPageThread,
    nhanTinVoi, openChat, minimizeChat, closeChat, send, canSticker: khaNang.sticker, sendSticker,
    stickerPacks: goiNhanDan, loadStickers, retry, loadOlder, markRead, setDraft, identityOf,
    blocked: chan, canMute: khaNang.mute, canBlock: khaNang.block, canReport: coBaoCao, inboxLoaded: daTaiHopThu,
    blocksLoaded: daTaiChan, isMuted, setMuted, setBlocked,
  }), [coBaoCao,status, errorCode, kickReason, me, conversations, unreadTotal, threads, identities, dockHien, maxVisible,
    focusRequest,
    drafts, moChat, dungOTabNay, thuLai, openThread, ensureThread, setPageThread, nhanTinVoi, openChat,
    minimizeChat, closeChat, send, sendSticker, goiNhanDan, loadStickers, retry, loadOlder, markRead, setDraft,
    identityOf, chan, khaNang, daTaiHopThu,
    daTaiChan, isMuted, setMuted, setBlocked]);

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
