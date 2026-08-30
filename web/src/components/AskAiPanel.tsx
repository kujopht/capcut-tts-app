"use client";

/**
 * Hỏi AI — trợ lý hỏi đáp về truyện/chương, cắm vào trang đọc chương
 * (`/chapters/[id]`).
 *
 * V1 SCOPE CỐ Ý: MỘT cuộc trò chuyện trong bộ nhớ cho phiên xem trang này.
 * Không lưu qua lần tải lại trang, không có lịch sử nhiều cuộc, không stream.
 *
 * GIẢI THÍCH `current_chapter_index` / `spoiler_protection_enabled`:
 *   Kho này CHƯA có tính năng "reading progress" — trang đọc tự cung cấp vị
 *   trí CHƯƠNG ĐANG MỞ (`order_index` của chính chương này) làm
 *   `current_chapter_index`. Đó là một lớp bảo vệ TRẢI NGHIỆM (tránh AI vô
 *   tình "lỡ lời" nhân vật/sự kiện ở những chương SAU chương đang đọc),
 *   KHÔNG phải biên giới phân quyền: mọi chương của truyện đã xuất bản vẫn
 *   công khai đọc được bằng cách cuộn xuống phía sau.
 *
 * CHUÔNG/ĐIỀU HƯỚNG theo đúng chuẩn của ConfirmDialog (+ SearchOverlay):
 *   focus tạm giữ trong panel, Escape để đóng, trả focus về nút đã mở khi
 *   đóng, và `createPortal(..., document.body)` vì `.site-header` có
 *   `backdrop-filter` — portal tránh bị tính lại làm `position: fixed` phủ
 *   sai vùng (xem SearchOverlay).
 *
 * GỌI BACKEND theo ĐÚNG quy ước của `lib/api.ts` (`API_BASE` tiền tố +
 * `getToken()` + `Content-Type: application/json` + đọc `detail` khi lỗi).
 * `lib/api.ts` không phơi sẵn một helper POST chung cho contract này, nên
 * file này làm một bản gọi cục bộ theo đúng khuôn đó — không bịa cách gọi
 * mới.
 *
 * CSS: giới hạn write-scope chỉ cho phép hai tệp, nên các class `.ask-ai-*`
 * được khai báo ngay trong chính component (một `<style>` kèm theo panel)
 * và TÁI DỤNG các mốc/font/token có sẵn (.btn/.btn-sm/.hint/.spinner,
 * var(--s*), var(--t*), var(--bg-*), var(--brand-*)). Ngưỡng cột hẹp tái
 * dùng ĐÚNG con số breakpoint `900px` sẵn có trong globals.css (không đặt
 * con số mới).
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE, getToken } from "@/lib/api";
import { IconSparkles } from "@/components/Icons";

export interface ChatCitation {
  novel_id: string;
  chapter_id: string;
  chapter_index: number;
  chapter_title: string;
  excerpt: string;
  chunk_order: number;
}

export interface ChatAnswer {
  answer: string;
  citations: ChatCitation[];
  evidence_insufficient: boolean;
}

type ChatScope =
  | "general"
  | "this_chapter"
  | "this_story"
  | "character"
  | "search"
  | "recommendation"
  | null;

/* ---------------------------------------------------------- gọi backend */

/** Hợp đồng /api/chat/ask — request. */
interface ChatRequest {
  novel_id: string;
  chapter_id: string | null;
  question: string;
  scope: ChatScope;
  selected_text: string | null;
  current_chapter_index: number;
  spoiler_protection_enabled: boolean;
}

/**
 * MỘT lần hỏi AI. Giữ nguyên quy ước gọi của `request()` trong `lib/api.ts`:
 * `API_BASE` làm tiền tố, bearer token (nếu có), body JSON, và khi lỗi thì
 * đọc `detail` (string — 400/429/503 đều bọc theo chuẩn FastAPI) rồi ném ra
 * câu thông báo để panel hiển thị; không bao giờ để lỗi lan ra cả trang.
 */
async function goiChat(payload: ChatRequest): Promise<ChatAnswer> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/chat/ask`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error(
      "Không kết nối được máy chủ. Hãy kiểm tra backend đã chạy chưa.",
    );
  }

  if (!response.ok) {
    let message = `Máy chủ trả về lỗi ${response.status}.`;
    try {
      const body: unknown = await response.json();
      if (
        body &&
        typeof body === "object" &&
        typeof (body as { detail?: unknown }).detail === "string"
      ) {
        message = (body as { detail: string }).detail;
      }
    } catch {
      /* giữ thông báo mặc định */
    }
    throw new Error(message);
  }

  return (await response.json()) as ChatAnswer;
}

/* ------------------------------------------------------------- dữ liệu UI */

const LOI_CHAO =
  "Hỏi tôi về chương này, các nhân vật hoặc một sự kiện trong truyện.";

/**
 * Câu hỏi nhanh — mỗi câu kèm `scope` để backend phân loại đúng.
 * `hoiTen`: hỏi tên nhân vật trước khi gửi (mở một ô nhập nhỏ).
 * `canDoan`: chỉ bật khi có sẵn đoạn văn (text selection hoặc nội dung chương).
 */
const NHANH: ReadonlyArray<{
  nhan: string;
  scope: ChatScope;
  cau: string;
  hoiTen?: boolean;
  canDoan?: boolean;
}> = [
  {
    nhan: "Giải thích chương này",
    scope: "this_chapter",
    cau: "Giải thích nội dung chương này một cách dễ hiểu.",
  },
  {
    nhan: "Tóm tắt các chương gần đây",
    scope: "this_story",
    cau: "Tóm tắt các chương gần đây của câu chuyện.",
  },
  {
    nhan: "Hỏi về nhân vật",
    scope: "character",
    cau: "Hãy giải thích nhân vật này là ai và vai trò của họ trong câu chuyện.",
    hoiTen: true,
  },
  {
    nhan: "Tìm một sự kiện",
    scope: "search",
    cau: "Tìm một sự kiện quan trọng trong truyện và kể lại nó.",
  },
  {
    nhan: "Dịch đoạn đã chọn",
    scope: "general",
    cau: "Dịch và giải thích đoạn văn tôi đã chọn.",
    canDoan: true,
  },
];

type VaiTro = "hoi" | "tra";

interface TinNhan {
  id: number;
  vaiTro: VaiTro;
  noiDung: string;
  trichDan: ChatCitation[];
  evidenceInsufficient: boolean;
}

const CSS_PANEL = `
.ask-ai-backdrop {
  position: fixed;
  inset: 0;
  z-index: 160;
  background: #05070bbf;
  backdrop-filter: blur(3px);
  display: flex;
  justify-content: flex-end;
  align-items: stretch;
  animation: ask-ai-vao 0.16s var(--ease, ease-out);
}
@keyframes ask-ai-vao { from { opacity: 0; } to { opacity: 1; } }
.ask-ai-panel {
  width: min(420px, 94vw);
  height: 100%;
  background: var(--bg-1);
  border-left: 1px solid var(--line);
  box-shadow: var(--shadow-3);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ask-ai-dau {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: var(--s3); padding: var(--s4); border-bottom: 1px solid var(--line-soft);
}
.ask-ai-dau-chu { min-width: 0; }
.ask-ai-tieu-de { font-size: var(--t-md); }
.ask-ai-spoiler {
  display: inline-flex; align-items: center; gap: var(--s2);
  flex-wrap: wrap; font-size: var(--t-xs);
}
.ask-ai-nut-nho {
  font-size: var(--t-xs); line-height: 1; padding: 4px 10px;
  border-radius: var(--r-full); background: var(--bg-3);
  border: 1px solid var(--line); color: var(--text-2); cursor: pointer;
}
.ask-ai-nut-nho:hover { color: var(--text); border-color: var(--line-strong); }
.ask-ai-tin {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: var(--s4); display: flex; flex-direction: column; gap: var(--s3);
}
.ask-ai-bong {
  max-width: 88%;
  padding: var(--s3) var(--s4);
  border-radius: var(--r3);
  font-size: var(--t-sm);
  line-height: 1.55;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}
.ask-ai-hoi {
  align-self: flex-end;
  background: var(--brand);
  color: var(--on-brand);
  border-bottom-right-radius: var(--r1);
}
.ask-ai-tra {
  align-self: flex-start;
  background: var(--bg-2);
  border: 1px solid var(--line);
  border-bottom-left-radius: var(--r1);
}
.ask-ai-gianh { margin-top: var(--s2); }
.ask-ai-trichdan { display: flex; flex-wrap: wrap; gap: var(--s2); margin-top: var(--s2); }
.ask-ai-chip {
  font-size: var(--t-xs); padding: 4px 12px; border-radius: var(--r-full);
  background: var(--brand-soft); border: 1px solid var(--brand-line);
  color: var(--brand-hover); text-decoration: none;
}
.ask-ai-chip:hover { background: var(--brand-line); color: var(--text); }
.ask-ai-loi { margin: 0 var(--s4) var(--s2); color: var(--danger); }
.ask-ai-nhanh { display: flex; flex-wrap: wrap; gap: var(--s2); padding: var(--s3) var(--s4) 0; }
.ask-ai-nhanvat { display: flex; gap: var(--s2); padding: var(--s2) var(--s4) 0; }
.ask-ai-nhap {
  display: flex; gap: var(--s2); padding: var(--s3) var(--s4);
  border-top: 1px solid var(--line-soft); margin-top: var(--s3);
}
.ask-ai-o {
  flex: 1; min-width: 0; height: var(--h-input);
  padding: 0 var(--s3); border: 1px solid var(--line);
  border-radius: var(--r2); background: var(--bg-2); color: var(--text);
}
.ask-ai-o:focus-visible {
  outline: 2px solid var(--brand); outline-offset: 0; border-color: var(--line-strong);
}
@media (max-width: 900px) {
  .ask-ai-backdrop { justify-content: center; align-items: flex-end; background: #05070b99; }
  .ask-ai-panel {
    width: 100%; max-width: none;
    height: min(80dvh, 640px);
    border-left: 0;
    border-top: 1px solid var(--line);
    border-top-left-radius: var(--r4);
    border-top-right-radius: var(--r4);
  }
}
@media (prefers-reduced-motion: reduce) {
  .ask-ai-backdrop { animation: none; }
}
`;

const layLuaChon = (): string =>
  typeof window !== "undefined"
    ? (window.getSelection()?.toString().trim() ?? "")
    : "";

export function AskAiPanel({
  novelId,
  chapterId,
  chapterIndex,
  chapterContent,
}: {
  novelId: string;
  chapterId: string;
  /**
   * Vị trí (`order_index`) của CHÍNH chương này — dùng làm
   * `current_chapter_index` cho mốc chống spoiler (kho chưa có tính năng
   * reading-progress, xem ghi chú đầu tệp).
   */
  chapterIndex: number;
  chapterContent?: string;
}) {
  const idGoc = useId();
  const panel = useRef<HTMLDivElement>(null);
  const danhSach = useRef<HTMLDivElement>(null);
  const nguoiMo = useRef<Element | null>(null);
  const demId = useRef(0);

  const [mo, setMo] = useState(false);
  const [tin, setTin] = useState<TinNhan[]>([
    {
      id: 0,
      vaiTro: "tra",
      noiDung: LOI_CHAO,
      trichDan: [],
      evidenceInsufficient: false,
    },
  ]);
  const [dangGui, setDangGui] = useState(false);
  const [loi, setLoi] = useState<string | null>(null);
  const [baoVeSpoiler, setBaoVeSpoiler] = useState(true);
  const [cauHoi, setCauHoi] = useState("");
  const [dangNhapNhanVat, setDangNhapNhanVat] = useState(false);
  const [tenNhanVat, setTenNhanVat] = useState("");
  /* Đoạn văn người dùng đã bôi trên trang — lấy một lần lúc mở panel (và
     mỗi lần có `selectionchange` khi panel đang mở). Dùng để bật/tắt nút
     "Dịch đoạn đã chọn" và làm `selected_text` khi gửi. */
  const [doan, setDoan] = useState("");

  const themTin = useCallback((t: Omit<TinNhan, "id">) => {
    demId.current += 1;
    setTin((cu) => [...cu, { ...t, id: demId.current }]);
  }, []);

  const dong = useCallback(() => {
    setMo(false);
    setDangNhapNhanVat(false);
    setTenNhanVat("");
    setLoi(null);
  }, []);

  /* -- chrome: focus trap + Escape + trả focus cho nút mở (như ConfirmDialog) -- */

  useEffect(() => {
    if (!mo) return;
    nguoiMo.current = document.activeElement;

    // `setDoan` doi vao khung ve sau (cung mot cho voi focus ben duoi) —
    // goi setState dong bo ngay trong than effect gay render day chuyen
    // (react-hooks/set-state-in-effect, bat o CI qua ESLint).
    const frame = requestAnimationFrame(() => {
      const doanTruoc = layLuaChon();
      if (doanTruoc) setDoan(doanTruoc);
      panel.current
        ?.querySelector<HTMLElement>("[data-autofocus]")
        ?.focus();
    });

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        dong();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const muc = panel.current.querySelectorAll<HTMLElement>(
        "button:not(:disabled), [href], input, textarea, select",
      );
      if (muc.length === 0) return;
      const dau = muc[0];
      const cuoi = muc[muc.length - 1];
      if (event.shiftKey && document.activeElement === dau) {
        event.preventDefault();
        cuoi.focus();
      } else if (!event.shiftKey && document.activeElement === cuoi) {
        event.preventDefault();
        dau.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKey);
      (nguoiMo.current as HTMLElement | null)?.focus?.();
    };
  }, [mo, dong]);

  /* -- bám lấy đoạn đang bôi lúc panel mở (cho nút "Dịch đoạn đã chọn") -- */

  useEffect(() => {
    if (!mo) return;
    const capNhat = () => {
      const s = layLuaChon();
      setDoan((cu) => s || cu);
    };
    document.addEventListener("selectionchange", capNhat);
    return () => document.removeEventListener("selectionchange", capNhat);
  }, [mo]);

  /* -- cuộn xuống tin mới nhất khi danh sách thay đổi / đang gửi -- */

  useEffect(() => {
    const el = danhSach.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [tin, dangGui, loi]);

  /* ------------------------------------------------------- gửi câu hỏi */

  const guiCauHoi = useCallback(
    async (
      question: string,
      scope: ChatScope,
      selectedText: string | null = null,
    ) => {
      const q = question.trim();
      if (!q || dangGui) return;
      setDangGui(true);
      setLoi(null);
      setCauHoi("");
      setDangNhapNhanVat(false);
      setTenNhanVat("");
      themTin({
        vaiTro: "hoi",
        noiDung: q,
        trichDan: [],
        evidenceInsufficient: false,
      });
      try {
        const tra = await goiChat({
          novel_id: novelId,
          chapter_id: chapterId,
          question: q,
          scope,
          selected_text: selectedText,
          current_chapter_index: chapterIndex,
          spoiler_protection_enabled: baoVeSpoiler,
        });
        themTin({
          vaiTro: "tra",
          noiDung: tra.answer,
          trichDan: tra.citations ?? [],
          evidenceInsufficient: tra.evidence_insufficient,
        });
      } catch (e) {
        const thongBao =
          e instanceof Error ? e.message : "Không trả lời được lúc này.";
        setLoi(thongBao);
      } finally {
        setDangGui(false);
      }
    },
    [dangGui, novelId, chapterId, chapterIndex, baoVeSpoiler, themTin],
  );

  const guiTuDo = (event: React.FormEvent) => {
    event.preventDefault();
    void guiCauHoi(cauHoi, null);
  };

  const guiNhanVat = (event: React.FormEvent) => {
    event.preventDefault();
    const ten = tenNhanVat.trim();
    if (!ten) return;
    void guiCauHoi(
      `Nhân vật ${ten}: hãy giải thích ${ten} là ai và vai trò của họ trong câu chuyện.`,
      "character",
    );
  };

  const chayNhanh = (n: (typeof NHANH)[number]) => {
    if (n.hoiTen) {
      setDangNhapNhanVat(true);
      setLoi(null);
      return;
    }
    let doanGui: string | null = null;
    if (n.canDoan) {
      const tam = layLuaChon() || doan.trim();
      doanGui = tam || (chapterContent ?? "").slice(0, 600) || null;
    }
    setDangNhapNhanVat(false);
    void guiCauHoi(n.cau, n.scope, doanGui);
  };

  const onNen = (event: React.MouseEvent) => {
    if (event.target === event.currentTarget) dong();
  };

  /* -------------------------------------------------------------- render */

  return (
    <>
      <button
        type="button"
        className="btn btn-sm"
        aria-expanded={mo}
        onClick={() => setMo(true)}
      >
        <IconSparkles size={15} />
        <span>Hỏi AI</span>
      </button>

      {mo
        ? createPortal(
            <>
              <style>{CSS_PANEL}</style>
              <div className="ask-ai-backdrop" onMouseDown={onNen}>
                <div
                  className="ask-ai-panel"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby={`${idGoc}-tieu-de`}
                  ref={panel}
                >
                  <header className="ask-ai-dau">
                    <div className="stack-2 ask-ai-dau-chu">
                      <h2 className="ask-ai-tieu-de" id={`${idGoc}-tieu-de`}>
                        Hỏi AI
                      </h2>
                      <span className="hint ask-ai-spoiler">
                        Chống spoiler:{" "}
                        <strong>{baoVeSpoiler ? "BẬT" : "TẮT"}</strong>
                        {baoVeSpoiler ? (
                          <span>· chặn đến chương {chapterIndex}</span>
                        ) : null}
                        <button
                          type="button"
                          className="ask-ai-nut-nho"
                          aria-pressed={baoVeSpoiler}
                          onClick={() => setBaoVeSpoiler((v) => !v)}
                        >
                          {baoVeSpoiler ? "Tắt" : "Bật"}
                        </button>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      onClick={dong}
                    >
                      Đóng
                    </button>
                  </header>

                  <div className="ask-ai-tin" ref={danhSach}>
                    {tin.map((t) => (
                      <div
                        key={t.id}
                        className={`ask-ai-bong ask-ai-${t.vaiTro}`}
                      >
                        <div>{t.noiDung}</div>
                        {t.evidenceInsufficient ? (
                          <p className="hint ask-ai-gianh">
                            Nguồn tư liệu còn hạn chế — câu trả lời có thể
                            chưa đầy đủ.
                          </p>
                        ) : null}
                        {t.trichDan.length ? (
                          <div
                            className="ask-ai-trichdan"
                            aria-label="Trích dẫn nguồn"
                          >
                            {t.trichDan.map((c) => (
                              <Link
                                key={`${c.chapter_id}-${c.chunk_order}`}
                                className="ask-ai-chip"
                                href={`/chapters/${c.chapter_id}`}
                              >
                                Chương {c.chapter_index}
                              </Link>
                            ))}
                          </div>
                        ) : null}
                      </div>
                    ))}
                    {dangGui ? (
                      <div className="ask-ai-bong ask-ai-tra">
                        <span className="row muted">
                          <span className="spinner" aria-hidden="true" />
                          <span>Đang suy nghĩ…</span>
                        </span>
                      </div>
                    ) : null}
                  </div>

                  {loi ? (
                    <p className="hint ask-ai-loi" role="alert">
                      {loi}
                    </p>
                  ) : null}

                  <div className="ask-ai-nhanh" aria-label="Câu hỏi nhanh">
                    {NHANH.map((n) => {
                      const tat = !!n.canDoan && !chapterContent && !doan.trim();
                      return (
                        <button
                          key={n.nhan}
                          type="button"
                          className="btn btn-sm btn-ghost"
                          disabled={tat || dangGui}
                          onClick={() => chayNhanh(n)}
                        >
                          {n.nhan}
                        </button>
                      );
                    })}
                  </div>

                  {dangNhapNhanVat ? (
                    <form
                      className="ask-ai-nhanvat"
                      onSubmit={guiNhanVat}
                    >
                      <input
                        className="ask-ai-o"
                        value={tenNhanVat}
                        onChange={(e) => setTenNhanVat(e.target.value)}
                        placeholder="Tên nhân vật…"
                        aria-label="Tên nhân vật"
                      />
                      <button
                        type="submit"
                        className="btn btn-sm"
                        disabled={dangGui || !tenNhanVat.trim()}
                      >
                        {dangGui ? (
                          <span className="spinner" aria-hidden="true" />
                        ) : (
                          "Hỏi"
                        )}
                      </button>
                    </form>
                  ) : null}

                  <form className="ask-ai-nhap" onSubmit={guiTuDo}>
                    <input
                      className="ask-ai-o"
                      data-autofocus
                      type="text"
                      value={cauHoi}
                      onChange={(e) => setCauHoi(e.target.value)}
                      placeholder="Hỏi tự do về truyện…"
                      aria-label="Câu hỏi tự do"
                      disabled={dangGui}
                    />
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm"
                      disabled={dangGui || !cauHoi.trim()}
                    >
                      {dangGui ? (
                        <span className="spinner" aria-hidden="true" />
                      ) : (
                        "Gửi"
                      )}
                    </button>
                  </form>
                </div>
              </div>
            </>,
            document.body,
          )
        : null}
    </>
  );
}