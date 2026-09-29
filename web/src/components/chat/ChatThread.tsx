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
const cungNgay = (a: number, b: number) => new Date(a).toDateString() === new Date(b).toDateString();
/** Vach ngay nhu ung dung nhan tin: "Hôm nay", "Hôm qua", roi thu + ngay (bo nam neu la nam nay). */
function ngay(ms: number): string {
  const bay = Date.now();
  if (cungNgay(ms, bay)) return "Hôm nay";
  if (cungNgay(ms, bay - 86_400_000)) return "Hôm qua";
  const cungNam = new Date(ms).getFullYear() === new Date(bay).getFullYear();
  return new Date(ms).toLocaleDateString("vi-VN", {
    weekday: "long", day: "numeric", month: "numeric", ...(cungNam ? {} : { year: "numeric" }),
  });
}
/** Tin CHI co 1-3 emoji -> hien to, khong bong (nhu ung dung nhan tin). */
const CHI_EMOJI = /^(?:\p{Extended_Pictographic}(?:️|‍\p{Extended_Pictographic}|[\u{1F3FB}-\u{1F3FF}])*\s*){1,3}$/u;
const chiEmoji = (t: string) => CHI_EMOJI.test(t.trim());

/** Tin noi tiep nhau (cung nguoi, cung ngay, cach nhau < 3 phut) gom thanh mot cum. */
const cungCum = (a: ChatMessage, b: ChatMessage) =>
  a.flow === b.flow && cungNgay(a.time, b.time) && Math.abs(b.time - a.time) < 3 * 60 * 1000;

/** Khung cho trong luc ket noi/tai lich su: vai bong tin xen ke hai phia. */
export function KhungCho() {
  return (
    <div className="chat-tin-hop" role="status" aria-label="Đang tải tin nhắn">
      {["in", "out", "in", "out"].map((f, i) => (
        <div key={i} className={`chat-tin chat-sk chat-tin-${f}`} aria-hidden="true">
          <span className="sk chat-sk-bong" style={{ width: `${[62, 44, 70, 38][i]}%` }} />
        </div>
      ))}
    </div>
  );
}

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
  const { threads, retry, loadOlder, identityOf } = useChat();
  const th = threads[conversationIdFor(peerId)];
  // Canary: nguoi kia chua trong nhom duoc dung chat — khong moi "gui loi chao" khi o soan da bi thay bang thong bao.
  const chuaMo = identityOf(peerId)?.chat_enabled === false;
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

  // "Tai tin cu hon": tin chen vao PHIA TREN — giu nguyen dong dang doc (bu phan chieu cao moi them),
  // khong de khung nhay ve tin cu nhat.
  const caoTruocRef = useRef<number | null>(null);
  const idDau = items.length ? items[0].id : null;
  useLayoutEffect(() => {
    const el = hop.current;
    const truoc = caoTruocRef.current;
    caoTruocRef.current = null;
    if (!el || truoc === null) return;
    el.scrollTop += el.scrollHeight - truoc;
  }, [idDau]);
  const taiCu = () => {
    caoTruocRef.current = hop.current?.scrollHeight ?? null;
    loadOlder(peerId);
  };

  // Lich su VUA tai xong (hoac doi nguoi) -> ve tin moi nhat. Khong the chi dua
  // vao `idCuoi`: tin den truc tiep truoc khi lich su tai xong da la tin cuoi,
  // lich su chen vao PHIA TRUOC nen `idCuoi` khong doi va khung dung o DAU —
  // do that tren Chrome QA (cuoc tro chuyen mo ra o tin cu nhat).
  const daTai = !!th?.loaded;
  useLayoutEffect(() => {
    if (daTai) xuongCuoi();
  }, [daTai, peerId, xuongCuoi]);

  const onScroll = () => {
    const el = hop.current;
    if (!el) return;
    oCuoi.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    if (oCuoi.current && coTinMoi) setCoTinMoi(false);
  };

  // Khung cho CHI khi chua co gi de hien. Da co tin (lac quan vua gui / tin den truc tiep) ma lich su chua ve thi
  // HIEN NGAY — do that tren mang cham (RTT ~1 s): tin dau tien bi khung cho giau ~1 s du da chen tuc thi.
  if (!th || (!th.loaded && !items.length)) return <KhungCho />;

  return (
    <div className="chat-tin-khung">
      <div className={`chat-tin-hop${items.length ? "" : " chat-tin-hop-rong"}`} ref={hop} onScroll={onScroll}
        role="log" aria-live="polite" aria-label="Tin nhắn">
        {!th.loaded ? <p className="hint chat-tin-cu" role="status">Đang tải tin trước đó…</p> : null}
        {th.cursor ? (
          <div className="chat-tin-cu">
            <button type="button" className="btn btn-ghost btn-sm" onClick={taiCu} disabled={th.loadingOlder}>
              {th.loadingOlder ? "Đang tải…" : "Tải tin cũ hơn"}
            </button>
          </div>
        ) : null}
        {!items.length && chuaMo ? (
          <ChatEmptyState icon="⏳" title="Chưa nhắn tin được" hint="Người này chưa dùng được Tin nhắn trong giai đoạn thử." />
        ) : !items.length ? (
          <ChatEmptyState icon="👋" title="Bắt đầu cuộc trò chuyện" hint="Gửi lời chào đầu tiên — tin nhắn chỉ hai người thấy." />
        ) : (
          items.map((m, i) => {
            const truoc = items[i - 1];
            const sau = items[i + 1];
            const moNgay = !truoc || !cungNgay(truoc.time, m.time);
            const noiTiep = !!truoc && cungCum(truoc, m);
            // Gio chi o tin CUOI cua cum (nhu ung dung nhan tin); trang thai
            // gui/hong thi luon hien o dung tin do.
            const cuoiCum = !sau || !cungCum(m, sau);
            const coTrangThai = m.status === "sending" || m.status === "failed";
            return (
              <div key={m.id} className="chat-tin-o">
                {moNgay ? <div className="chat-tin-ngay"><span>{ngay(m.time)}</span></div> : null}
                <div className={`chat-tin chat-tin-${m.flow}${noiTiep ? " chat-tin-noi" : ""}${m.status === "failed" ? " chat-tin-loi" : ""}`}>
                  {m.kind === "sticker" && m.sticker ? (
                    <div className="chat-tin-nd" title={cuoiCum ? m.sticker.alt : `${m.sticker.alt} · ${gio(m.time)}`}>
                      {/* eslint-disable-next-line @next/next/no-img-element -- anh tinh nho tu kho tai san */}
                      <img src={m.sticker.url} alt={m.sticker.alt} width={112} height={112} loading="lazy" draggable={false} />
                    </div>
                  ) : (
                    <div className={`chat-tin-bong${m.unsupported ? " chat-tin-la" : ""}${!m.unsupported && m.kind !== "sticker" && chiEmoji(m.text) ? " chat-tin-emoji" : ""}`}
                      title={cuoiCum ? undefined : gio(m.time)}>{m.text}</div>
                  )}
                  {cuoiCum || coTrangThai ? (
                    <div className="chat-tin-duoi">
                      {cuoiCum ? <time className="chat-tin-gio" dateTime={new Date(m.time).toISOString()}>{gio(m.time)}</time> : null}
                      <TrangThaiTin m={m} onRetry={() => retry(peerId, m.id)} />
                    </div>
                  ) : null}
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
