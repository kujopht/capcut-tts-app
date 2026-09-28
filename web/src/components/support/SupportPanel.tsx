"use client";

/**
 * Hội thoại Fanfic AI Support: HỎI ĐÁP và BÁO LỖI KỸ THUẬT.
 *
 * Mỗi câu trả lời kèm danh sách phép kiểm tra THẬT máy chủ đã chạy (✓/⚠/✕) —
 * người dùng thấy trợ lý dựa vào đâu, không phải một câu trả lời hộp đen. Chưa
 * rõ nguyên nhân thì nút "Gửi cho quản trị viên" nổi lên, tạo báo cáo SUP-xxxx.
 *
 * Trợ lý CHỈ ĐỌC: không có nút nào ở đây làm thay đổi dữ liệu. Không tự bật,
 * không thăm dò: chỉ gọi máy chủ khi người dùng bấm gửi.
 */
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { supportApi, type SupportAskResponse, type SupportCheck } from "@/lib/support/api";
import { useSession } from "@/lib/session";
import { layBoiCanh, phienHoTro, type SupportContext } from "@/lib/support/context";
import { maLoiCuoi } from "@/lib/support/collector";
import "./support.css";

type Tin =
  | { id: number; vai: "nguoi"; text: string }
  | { id: number; vai: "tro_ly"; res: SupportAskResponse; hoi: string; cheDo: "qa" | "report" }
  | { id: number; vai: "he_thong"; text: string; ma?: string };

type Loi = { loai: "tat" | "gioi_han" | "mang" | "khac"; text: string } | null;

const TEN_KIEM_TRA: Record<string, string> = {
  check_api_health: "Máy chủ Fanfic World",
  check_current_build: "Phiên bản máy chủ",
  check_route: "Trang bạn đang mở",
  check_chapter: "Chương",
  check_audio_track: "Audio của chương",
  check_audio_range: "Tua audio",
  check_novel: "Truyện",
  check_feature_status: "Tính năng",
  get_recent_public_incidents: "Sự cố đã biết",
  get_sanitized_client_errors: "Lỗi trình duyệt đã ghi nhận",
  get_public_system_health: "Tình trạng hệ thống",
  get_recent_sentry_issues: "Hệ thống giám sát lỗi",
};

const DAU: Record<SupportCheck["status"], { k: string; nhan: string }> = {
  ok: { k: "✓", nhan: "Bình thường" },
  warn: { k: "!", nhan: "Cần chú ý" },
  fail: { k: "✕", nhan: "Có lỗi" },
  unknown: { k: "?", nhan: "Chưa rõ" },
  denied: { k: "⛔", nhan: "Bị từ chối" },
};

const GOI_Y: Record<"qa" | "report", string[]> = {
  qa: ["Audio chương này không chạy", "Sao tôi không vào được Studio?", "Trang này bị lỗi", "Tôi bị đăng xuất liên tục"],
  report: ["Bấm nghe thì báo lỗi, không phát được", "Trang trắng sau khi đăng nhập", "Không lưu được chương trong Studio"],
};

function loiTu(e: unknown): Loi {
  if (e instanceof ApiError) {
    if (e.status === 503 && e.code === "support_disabled") return { loai: "tat", text: "Trợ giúp AI chưa được bật trên máy chủ." };
    if (e.status === 429) return { loai: "gioi_han", text: "Bạn gửi hơi nhiều trong ít phút — thử lại sau một lúc nhé." };
    if (e.status === 0) return { loai: "mang", text: "Không kết nối được máy chủ. Kiểm tra mạng rồi gửi lại." };
    return { loai: "khac", text: e.message };
  }
  return { loai: "khac", text: "Có lỗi không mong đợi. Thử lại sau giây lát." };
}

function KiemTra({ ds }: { ds: SupportCheck[] }) {
  return (
    <details className="ho-tro-kiem" open={ds.some((c) => c.status === "fail")}>
      <summary>Đã kiểm tra {ds.length} mục</summary>
      <ul>
        {ds.map((c, i) => (
          <li key={`${c.tool}-${i}`} className={`ho-tro-kiem-${c.status}`}>
            <span className="ho-tro-kiem-dau" aria-label={DAU[c.status].nhan} title={DAU[c.status].nhan}>{DAU[c.status].k}</span>
            <span className="ho-tro-kiem-chu">
              <strong>{TEN_KIEM_TRA[c.tool] ?? c.tool}</strong>
              <span className="hint">{c.summary}</span>
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export function SupportPanel({ boiCanhDau, cheDoDau = "qa" }: { boiCanhDau: Partial<SupportContext>; cheDoDau?: "qa" | "report" }) {
  const { profile } = useSession();
  const [cheDo, setCheDo] = useState<"qa" | "report">(cheDoDau);
  const [tin, setTin] = useState<Tin[]>([]);
  const [nhap, setNhap] = useState("");
  const [ban, setBan] = useState(false);
  const [loi, setLoi] = useState<Loi>(null);
  const [aiBat, setAiBat] = useState<boolean | null>(null);
  const [daGui, setDaGui] = useState<string | null>(null);
  const [boiCanh, setBoiCanh] = useState(boiCanhDau);
  const o = useRef<HTMLTextAreaElement | null>(null);
  const cuoi = useRef<HTMLDivElement | null>(null);
  const soId = useRef(0);

  // MOT lan khi mo trang /support — khong o trang nao khac, khong lap lai.
  useEffect(() => {
    let huy = false;
    supportApi.status().then(
      (s) => { if (!huy) { setAiBat(s.enabled && s.ai_available); if (!s.enabled) setLoi({ loai: "tat", text: "Trợ giúp AI chưa được bật trên máy chủ." }); } },
      () => { if (!huy) setAiBat(false); },
    );
    return () => { huy = true; };
  }, []);

  useEffect(() => {
    cuoi.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [tin.length]);

  const gui = useCallback(async (cau: string) => {
    const t = cau.trim();
    if (!t || ban) return;
    setLoi(null);
    setBan(true);
    setNhap("");
    setTin((ds) => [...ds, { id: ++soId.current, vai: "nguoi", text: t }]);
    try {
      const ctx = layBoiCanh({ ...boiCanh, last_error_code: boiCanh.last_error_code || maLoiCuoi() });
      const res = await supportApi.ask({ mode: cheDo, message: t, session_id: phienHoTro(), context: ctx });
      setAiBat(res.ai_available);
      setTin((ds) => [...ds, { id: ++soId.current, vai: "tro_ly", res, hoi: t, cheDo }]);
    } catch (e) {
      setLoi(loiTu(e));
    } finally {
      setBan(false);
      requestAnimationFrame(() => o.current?.focus());
    }
  }, [ban, boiCanh, cheDo]);

  const baoCao = useCallback(async (hoi: string, res?: SupportAskResponse) => {
    if (ban) return;
    setBan(true);
    setLoi(null);
    try {
      const ctx = layBoiCanh({ ...boiCanh, last_error_code: boiCanh.last_error_code || maLoiCuoi() });
      const r = await supportApi.report({ summary: hoi, session_id: phienHoTro(), context: ctx, diagnostic_id: res?.diagnostic_id });
      setDaGui(r.report_id);
      setTin((ds) => [...ds, { id: ++soId.current, vai: "he_thong", text: r.message, ma: r.report_id }]);
    } catch (e) {
      setLoi(loiTu(e));
    } finally {
      setBan(false);
    }
  }, [ban, boiCanh]);

  const tat = loi?.loai === "tat";
  return (
    <section className="ho-tro" aria-label="Trợ giúp Fanfic World">
      <div className="ho-tro-dau">
        <div className="seg ho-tro-che-do" role="group" aria-label="Chế độ trợ giúp">
          {(["qa", "report"] as const).map((m) => (
            <button key={m} type="button" aria-pressed={cheDo === m} className="seg-item" onClick={() => setCheDo(m)}>
              {m === "qa" ? "💬 Hỏi đáp" : "🛠 Báo lỗi kỹ thuật"}
            </button>
          ))}
        </div>
        <span className={`ho-tro-ai${aiBat ? " ho-tro-ai-bat" : ""}`}>
          {aiBat === null ? "…" : aiBat ? "AI đang trả lời" : "Kiểm tra tự động · AI chưa bật"}
        </span>
      </div>

      {boiCanh.route && boiCanh.route !== "/" ? (
        <div className="ho-tro-ngu-canh">
          <span className="hint">
            Đang hỗ trợ cho trang <code>{boiCanh.route}</code>
            {boiCanh.last_error_code ? <> · lỗi <code>{boiCanh.last_error_code}</code></> : null}
          </span>
          <button type="button" className="ho-tro-nut-x" aria-label="Bỏ ngữ cảnh trang"
            onClick={() => setBoiCanh({})}>✕</button>
        </div>
      ) : null}

      <div className="ho-tro-tin" role="log" aria-live="polite" aria-label="Hội thoại hỗ trợ">
        {!tin.length ? (
          <div className="ho-tro-chao">
            <strong>{cheDo === "qa" ? "Mình có thể giúp gì?" : "Tả lỗi bạn gặp"}</strong>
            <p className="hint">
              {cheDo === "qa"
                ? "Trợ lý kiểm tra máy chủ, trang và chương bạn đang dùng (chỉ đọc) rồi giải thích. Chưa rõ nguyên nhân thì gửi cho quản trị viên."
                : "Kể bạn đang làm gì và thấy gì. Trợ lý kiểm tra trước, rồi bạn chọn gửi báo cáo cho quản trị viên."}
            </p>
            <div className="ho-tro-goi-y-ds">
              {GOI_Y[cheDo].map((g) => (
                <button key={g} type="button" className="chip" disabled={ban || tat} onClick={() => void gui(g)}>{g}</button>
              ))}
            </div>
          </div>
        ) : null}
        {tin.map((m) =>
          m.vai === "nguoi" ? (
            <div key={m.id} className="ho-tro-nguoi"><div className="ho-tro-bong">{m.text}</div></div>
          ) : m.vai === "he_thong" ? (
            <div key={m.id} className="ho-tro-he-thong" role="status">
              <span aria-hidden="true">✅</span>
              <span>{m.text}</span>
              {m.ma ? (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => {
                  navigator.clipboard?.writeText(m.ma ?? "").catch(() => undefined);
                }}>Sao chép mã</button>
              ) : null}
            </div>
          ) : (
            <article key={m.id} className="ho-tro-tra-loi" aria-label="Trả lời của trợ lý">
              <div className="ho-tro-tra-loi-dau">
                <span aria-hidden="true">🛟</span>
                <span className="hint">{m.res.ai_mode === "ai" ? "Trợ lý AI" : "Kiểm tra tự động"}</span>
                {m.res.denied.length ? <span className="badge ho-tro-tu-choi">Một phần yêu cầu bị từ chối vì an toàn</span> : null}
              </div>
              <p className="ho-tro-van">{m.res.answer}</p>
              <KiemTra ds={m.res.checks} />
              {daGui ? null : (
                <div className="row ho-tro-hanh-dong">
                  <button type="button" disabled={ban}
                    className={`btn btn-sm ${m.cheDo === "report" || m.res.suggest_escalate ? "btn-primary" : "btn-ghost"}`}
                    onClick={() => void baoCao(m.hoi, m.res)}>
                    Gửi cho quản trị viên
                  </button>
                  {m.cheDo === "qa" && !m.res.suggest_escalate ? (
                    <span className="hint">Đã ổn? Không cần gửi.</span>
                  ) : null}
                </div>
              )}
            </article>
          ),
        )}
        {ban ? (
          <div className="ho-tro-dang" role="status"><span className="spinner" aria-hidden="true" /> Đang kiểm tra…</div>
        ) : null}
        {/* scroll-margin: o soan dinh day (sticky) khong duoc che phan cuoi cau
            tra loi vua cuon toi — do that o 390px. */}
        <div ref={cuoi} style={{ scrollMarginBottom: 150 }} />
      </div>

      {loi ? (
        <div className={`alert ${loi.loai === "tat" ? "alert-info" : "alert-error"} ho-tro-loi`} role="alert">
          <span>{loi.text}</span>
        </div>
      ) : null}

      <form className="ho-tro-soan" onSubmit={(e) => { e.preventDefault(); void gui(nhap); }}>
        <textarea
          ref={o}
          className="ho-tro-o"
          rows={2}
          value={nhap}
          maxLength={1000}
          disabled={tat}
          placeholder={cheDo === "qa" ? "Hỏi trợ lý…" : "Mô tả lỗi: bạn làm gì, thấy gì…"}
          aria-label={cheDo === "qa" ? "Câu hỏi cho trợ lý" : "Mô tả lỗi"}
          onChange={(e) => setNhap(e.target.value)}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || e.shiftKey) return;
            if (e.nativeEvent.isComposing || e.keyCode === 229) return; // bo go tieng Viet dang soan
            e.preventDefault();
            void gui(nhap);
          }}
        />
        <button type="submit" className="btn btn-primary" disabled={ban || tat || !nhap.trim()}>
          {cheDo === "qa" ? "Gửi" : "Kiểm tra"}
        </button>
      </form>
      <p className="hint ho-tro-rieng-tu">
        Chỉ gửi đường dẫn trang, phiên bản, trình duyệt và mã lỗi — không gửi mật khẩu, cookie hay tin nhắn của bạn.
        {profile ? null : <> <Link href="/login?next=/support" prefetch={false}>Đăng nhập</Link> để trợ lý kiểm tra cả truyện nháp của bạn.</>}
      </p>
    </section>
  );
}
