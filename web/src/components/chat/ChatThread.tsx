"use client";

/**
 * Noi dung mot cuoc tro chuyen 1:1.
 *
 * Cuon: dang o CUOI thi tin moi keo xuong theo; dang doc lai tin cu thi KHONG
 * giat trang — hien nut "Tin mới ↓" thay vao. Keo nguoi dung khoi cho ho dang
 * doc de khoe mot tin vua toi la mot kieu lam phien.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { conversationIdFor, type ChatMessage } from "@/lib/chat/types";
import { useChat } from "./ChatProvider";
import { ChatEmptyState } from "./ChatEmptyState";

const gio = (ms: number) => new Date(ms).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
const ngay = (ms: number) => new Date(ms).toLocaleDateString("vi-VN", { weekday: "long", day: "numeric", month: "numeric", year: "numeric" });
const cungNgay = (a: number, b: number) => new Date(a).toDateString() === new Date(b).toDateString();

function TrangThaiTin({ m, onRetry }: { m: ChatMessage; onRetry: () => void }) {
  if (m.status === "sending") return <span className="chat-tin-tt" aria-live="polite">Đang gửi…</span>;
  if (m.status === "failed") {
    return (
      <span className="chat-tin-tt chat-tin-hong" role="alert">
        Không gửi được{m.failCode ? ` (mã ${m.failCode})` : ""}.{" "}
        <button type="button" className="chat-tin-thu-lai" onClick={onRetry}>Thử lại</button>
      </span>
    );
  }
  return null;
}

export function ChatThread({ peerId }: { peerId: string }) {
  const { threads, retry, loadOlder } = useChat();
  const th = threads[conversationIdFor(peerId)];
  const items = th?.items ?? [];
  const hop = useRef<HTMLDivElement | null>(null);
  const oCuoi = useRef(true);
  const [coTinMoi, setCoTinMoi] = useState(false);
  const idCuoi = items.length ? items[items.length - 1].id : null;
  const cuoiLaCuaMinh = items.length ? items[items.length - 1].flow === "out" : false;

  const xuongCuoi = useCallback((muot = false) => {
    const el = hop.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: muot ? "smooth" : "auto" });
    oCuoi.current = true;
  }, []);

  // Tin moi: dang o cuoi (hoac tin CUA MINH vua gui) thi keo theo; khong thi bao.
  useLayoutEffect(() => {
    if (!idCuoi) return;
    if (oCuoi.current || cuoiLaCuaMinh) {
      xuongCuoi();
      requestAnimationFrame(() => setCoTinMoi(false));
    } else {
      requestAnimationFrame(() => setCoTinMoi(true));
    }
  }, [idCuoi, cuoiLaCuaMinh, xuongCuoi]);

  // Doi nguoi -> bat dau o cuoi cuoc tro chuyen moi.
  useEffect(() => {
    oCuoi.current = true;
  }, [peerId]);

  const onScroll = () => {
    const el = hop.current;
    if (!el) return;
    oCuoi.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    if (oCuoi.current && coTinMoi) setCoTinMoi(false);
  };

  if (!th || !th.loaded) {
    return (
      <div className="chat-tin-hop chat-tin-hop-trong" role="status">
        <span className="spinner" aria-hidden="true" /> Đang tải tin nhắn…
      </div>
    );
  }

  return (
    <div className="chat-tin-khung">
      <div className="chat-tin-hop" ref={hop} onScroll={onScroll} role="log" aria-live="polite" aria-label="Tin nhắn">
        {th.cursor ? (
          <div className="chat-tin-cu">
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => loadOlder(peerId)} disabled={th.loadingOlder}>
              {th.loadingOlder ? "Đang tải…" : "Tải tin cũ hơn"}
            </button>
          </div>
        ) : null}
        {!items.length ? (
          <ChatEmptyState icon="👋" title="Bắt đầu cuộc trò chuyện" hint="Gửi lời chào đầu tiên — tin nhắn chỉ hai người thấy." />
        ) : (
          items.map((m, i) => {
            const truoc = items[i - 1];
            const moNgay = !truoc || !cungNgay(truoc.time, m.time);
            const noiTiep = !!truoc && !moNgay && truoc.flow === m.flow && m.time - truoc.time < 3 * 60 * 1000;
            return (
              <div key={m.id} className="chat-tin-o">
                {moNgay ? <div className="chat-tin-ngay"><span>{ngay(m.time)}</span></div> : null}
                <div className={`chat-tin chat-tin-${m.flow}${noiTiep ? " chat-tin-noi" : ""}${m.status === "failed" ? " chat-tin-loi" : ""}`}>
                  <div className={`chat-tin-bong${m.unsupported ? " chat-tin-la" : ""}`}>{m.text}</div>
                  <div className="chat-tin-duoi">
                    <time className="chat-tin-gio" dateTime={new Date(m.time).toISOString()}>{gio(m.time)}</time>
                    <TrangThaiTin m={m} onRetry={() => retry(peerId, m.id)} />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
      {coTinMoi ? (
        <button type="button" className="chat-tin-moi-nut" onClick={() => { xuongCuoi(true); setCoTinMoi(false); }}>
          Tin mới ↓
        </button>
      ) : null}
    </div>
  );
}
