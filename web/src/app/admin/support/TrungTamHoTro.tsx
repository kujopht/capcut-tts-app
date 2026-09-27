"use client";

/**
 * Trung tâm hỗ trợ (Fanfic AI Support V1) — màn hình làm việc của quản trị.
 *
 * BA điều quyết định thiết kế:
 *
 * 1. MỘT SỰ CỐ, KHÔNG PHẢI 50 DÒNG. Máy chủ đã gom theo dấu vân tay (trang + lỗi
 *    chuẩn + phân hệ); ở đây mỗi dòng là một sự cố kèm số lần, số người, số
 *    báo cáo, bản build — đủ để biết nên xử lý cái nào trước.
 * 2. KHÔNG TỰ LÀM GÌ. Không tự làm mới (không thăm dò), không tự tạo issue, không
 *    tự sửa: "Chuẩn bị issue GitHub" chỉ ra bản nháp để quản trị tự sao chép.
 * 3. DI ĐỘNG DÙNG ĐƯỢC. Ở 390px danh sách và chi tiết là hai màn; chọn một sự cố
 *    đẩy `?i=` lên URL nên cử chỉ Back quay về danh sách.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { supportApi } from "@/lib/support/api";
import {
  adminSupportApi,
  type SupportIncident,
  type SupportIncidentDetail,
  type SupportIncidentStatus,
  type SupportReportRow,
  type SupportSummary,
} from "@/lib/support/adminApi";
import { khiNao } from "@/lib/time";
import { DanhSachTrangThai } from "@/components/AdminShell";
import "./admin-support.css";

const TAB: ReadonlyArray<{ key: string; nhan: string; loc: { status?: string; unresolved?: boolean } }> = [
  { key: "open", nhan: "Đang mở", loc: { unresolved: true } },
  { key: "new", nhan: "Mới", loc: { status: "new" } },
  { key: "ai", nhan: "AI đã chẩn đoán", loc: { status: "ai_diagnosed" } },
  { key: "owner", nhan: "Cần chủ dự án", loc: { status: "needs_owner" } },
  { key: "resolved", nhan: "Đã xử lý", loc: { status: "resolved" } },
  { key: "all", nhan: "Tất cả", loc: {} },
];

const PHAN_HE: Record<string, string> = {
  audio: "Audio", reader: "Đọc truyện", studio: "Studio", api: "API", storage: "Kho lưu trữ",
  auth: "Đăng nhập", chat: "Tin nhắn", support: "Trợ giúp", web: "Giao diện web", unknown: "Chưa rõ",
};
const MUC_DO: Record<string, string> = { critical: "Nghiêm trọng", high: "Cao", medium: "Vừa", low: "Thấp" };
const TRANG_THAI: Record<SupportIncidentStatus, string> = {
  new: "Mới", open: "Đang mở", ai_diagnosed: "AI đã chẩn đoán", needs_owner: "Cần chủ dự án", resolved: "Đã xử lý",
};
const KIEM: Record<string, string> = { ok: "✓", warn: "!", fail: "✕", unknown: "?", denied: "⛔" };

const luc = (s: number) => khiNao(new Date(s * 1000).toISOString());
const loiCua = (e: unknown, macDinh: string) => (e instanceof ApiError ? e.message : macDinh);

export function TrungTamHoTro() {
  const router = useRouter();
  const params = useSearchParams();
  const chon = params.get("i");
  const [tab, setTab] = useState("open");
  const [phanHe, setPhanHe] = useState("");
  const [mucDo, setMucDo] = useState("");
  const [build, setBuild] = useState("");
  const [route, setRoute] = useState("");
  const [tim, setTim] = useState("");
  const [tong, setTong] = useState<SupportSummary | null>(null);
  const [ds, setDs] = useState<SupportIncident[] | null>(null);
  const [soDs, setSoDs] = useState(0);
  const [baoCao, setBaoCao] = useState<SupportReportRow[]>([]);
  const [loi, setLoi] = useState("");
  const [batMayChu, setBatMayChu] = useState<boolean | null>(null);
  const [ct, setCt] = useState<SupportIncidentDetail | null>(null);
  const [loiCt, setLoiCt] = useState("");
  const [ghiChu, setGhiChu] = useState("");
  const [dangLam, setDangLam] = useState("");
  const [nhap, setNhap] = useState<{ title: string; body: string; labels: string[]; new_issue_url?: string } | null>(null);

  const tai = useCallback(() => {
    setLoi("");
    setDs(null);
    const loc = TAB.find((t) => t.key === tab)?.loc ?? {};
    Promise.all([
      adminSupportApi.summary(),
      adminSupportApi.incidents({ ...loc, subsystem: phanHe, severity: mucDo, build: build.trim(), route: route.trim(), q: tim.trim() }),
      adminSupportApi.reports(),
    ]).then(
      ([s, r, b]) => { setTong(s); setDs(r.items); setSoDs(r.total); setBaoCao(b.items.filter((x) => x.status === "new").slice(0, 6)); },
      (e) => { setDs([]); setLoi(loiCua(e, "Không tải được trung tâm hỗ trợ.")); },
    );
  }, [tab, phanHe, mucDo, build, route, tim]);

  useEffect(() => {
    queueMicrotask(tai);
  }, [tai]);

  // MOT lan: may chu co bat Support khong (bat web ma tat may chu -> noi thang).
  useEffect(() => {
    supportApi.status().then((s) => setBatMayChu(s.enabled), () => setBatMayChu(null));
  }, []);

  const taiCt = useCallback((id: string) => {
    setLoiCt("");
    setCt(null);
    setNhap(null);
    adminSupportApi.incident(id).then(setCt, (e) => setLoiCt(loiCua(e, "Không tải được sự cố.")));
  }, []);

  useEffect(() => {
    if (chon) queueMicrotask(() => taiCt(chon));
    else queueMicrotask(() => { setCt(null); setNhap(null); });
  }, [chon, taiCt]);

  const moSuCo = (id: string) => router.push(`/admin/support?i=${encodeURIComponent(id)}`, { scroll: false });
  const dong = () => (window.history.length > 1 ? router.back() : router.replace("/admin/support"));

  const doiTrangThai = async (st: SupportIncidentStatus) => {
    if (!ct) return;
    setDangLam(st);
    try {
      await adminSupportApi.setStatus(ct.incident_id, st, ghiChu.trim());
      setGhiChu("");
      taiCt(ct.incident_id);
      tai();
    } catch (e) {
      setLoiCt(loiCua(e, "Không đổi được trạng thái."));
    } finally {
      setDangLam("");
    }
  };

  const chuanBiIssue = async () => {
    if (!ct) return;
    setDangLam("issue");
    try {
      setNhap(await adminSupportApi.issueDraft(ct.incident_id));
    } catch (e) {
      setLoiCt(loiCua(e, "Không tạo được bản nháp."));
    } finally {
      setDangLam("");
    }
  };

  const oTong: ReadonlyArray<[string, number | undefined, string]> = [
    ["Sự cố đang mở", tong?.open_incidents, ""],
    ["Báo cáo mới", tong?.new_reports, ""],
    ["Cần chủ dự án", tong?.needs_owner, "ht-o-can"],
    ["AI đã chẩn đoán", tong?.ai_diagnosed, ""],
    ["Đã xử lý", tong?.resolved, ""],
    ["Người bị ảnh hưởng", tong?.affected_users, ""],
  ];

  return (
    <div className={`stack ht${chon ? " ht-co-chon" : ""}`}>
      <header className="stack-2">
        <h1 className="page-title">Trung tâm hỗ trợ</h1>
        <p className="hint">
          Lỗi người dùng gặp, đã gom theo trang + lỗi + phân hệ. Không tự làm mới — bấm <em>Làm mới</em> khi cần.
        </p>
      </header>

      {batMayChu === false ? (
        <div className="alert alert-warn" role="status">
          <span>Máy chủ chưa bật Support (<code>FAS_SUPPORT_V1</code>) — sẽ không có sự cố mới nào được ghi nhận.</span>
        </div>
      ) : null}

      <section className="ht-tong" aria-label="Số liệu tổng">
        {oTong.map(([nhan, so, lop]) => (
          <div key={nhan} className={`card ht-o ${lop}`}>
            <span className="ht-o-so">{so ?? "—"}</span>
            <span className="hint">{nhan}</span>
          </div>
        ))}
      </section>
      {tong ? (
        <p className="hint ht-ghi-chu">
          Lưu trong bộ nhớ máy chủ (mất khi khởi động lại) · AI: {tong.ai_available ? "đang bật" : "chưa bật — chế độ kiểm tra tự động"}
        </p>
      ) : null}

      <div className="ht-luoi">
        <section className="stack ht-cot-ds" aria-label="Danh sách sự cố">
          <div className="row ht-tab" role="group" aria-label="Lọc theo trạng thái">
            {TAB.map((t) => (
              <button key={t.key} type="button" aria-pressed={tab === t.key}
                className={tab === t.key ? "btn btn-sm" : "btn btn-ghost btn-sm"} onClick={() => setTab(t.key)}>
                {t.nhan}
              </button>
            ))}
            <button type="button" className="btn btn-ghost btn-sm ht-lam-moi" onClick={tai}>↻ Làm mới</button>
          </div>
          <div className="ht-loc">
            <select className="input" value={phanHe} onChange={(e) => setPhanHe(e.target.value)} aria-label="Phân hệ">
              <option value="">Mọi phân hệ</option>
              {Object.entries(PHAN_HE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select className="input" value={mucDo} onChange={(e) => setMucDo(e.target.value)} aria-label="Mức độ">
              <option value="">Mọi mức độ</option>
              {Object.entries(MUC_DO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="input" value={build} onChange={(e) => setBuild(e.target.value)} placeholder="Build" aria-label="Lọc theo build" maxLength={40} />
            <input className="input" value={route} onChange={(e) => setRoute(e.target.value)} placeholder="Trang, vd /chapters/[id]" aria-label="Lọc theo trang" maxLength={120} />
            <input className="input" value={tim} onChange={(e) => setTim(e.target.value)} placeholder="Tìm lỗi / mã INC" aria-label="Tìm" maxLength={80} />
          </div>
          <p className="hint">{soDs} sự cố</p>
          <DanhSachTrangThai dangTai={ds === null && !loi} loi={loi} rong={!!ds && ds.length === 0} onThuLai={tai}>
            <ul className="ht-ds">
              {(ds ?? []).map((i) => (
                <li key={i.incident_id}>
                  <button type="button" className={`ht-muc${chon === i.incident_id ? " ht-muc-dang" : ""}`}
                    aria-current={chon === i.incident_id ? "true" : undefined} onClick={() => moSuCo(i.incident_id)}>
                    <span className="row ht-muc-dau">
                      <span className={`badge ht-md-${i.severity}`}>{MUC_DO[i.severity]}</span>
                      <span className="badge">{TRANG_THAI[i.status]}</span>
                      {i.owner_needed ? <span className="badge badge-warn">Cần chủ dự án</span> : null}
                      <span className="hint ht-muc-luc">{luc(i.last_seen)}</span>
                    </span>
                    <strong className="ht-muc-tieu-de">{i.title}</strong>
                    <span className="hint ht-muc-meta">
                      {PHAN_HE[i.subsystem] ?? i.subsystem} · <code>{i.route}</code> · {i.event_count} lần · {i.affected_count} người
                      {i.report_count ? ` · ${i.report_count} báo cáo` : ""}
                      {i.builds.length ? ` · build ${i.builds.slice(0, 2).join(", ")}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </DanhSachTrangThai>
          {baoCao.length ? (
            <section className="stack-2 ht-bc-moi" aria-label="Báo cáo mới">
              <h2 className="section-title-sm">Báo cáo mới</h2>
              {baoCao.map((b) => (
                <button key={b.report_id} type="button" className="ht-bc" disabled={!b.incident_id}
                  onClick={() => b.incident_id && moSuCo(b.incident_id)}>
                  <span className="row ht-muc-dau">
                    <code>{b.report_id}</code>
                    <span className="badge">{PHAN_HE[b.subsystem] ?? b.subsystem}</span>
                    <span className="hint ht-muc-luc">{luc(b.created_at)}</span>
                  </span>
                  <span className="ht-bc-chu">“{b.summary}”</span>
                  <span className="hint">{b.reporter === "user" ? "Người dùng" : "Khách"} · {b.browser}/{b.device} · <code>{b.route}</code></span>
                </button>
              ))}
            </section>
          ) : null}
        </section>

        <aside className="ht-cot-ct" aria-label="Chi tiết sự cố">
          {!chon ? (
            <div className="card ht-trong"><p className="hint">Chọn một sự cố để xem dòng thời gian, bằng chứng và cách tái hiện.</p></div>
          ) : loiCt && !ct ? (
            <div className="card stack-2" role="alert"><strong>Không tải được.</strong><p className="hint">{loiCt}</p></div>
          ) : !ct ? (
            <div className="card ht-trong"><span className="spinner" aria-hidden="true" /> Đang tải…</div>
          ) : (
            <article className="card stack ht-ct">
              <button type="button" className="btn btn-ghost btn-sm ht-lui" onClick={dong}>← Danh sách</button>
              <header className="stack-2">
                <span className="row ht-muc-dau">
                  <code>{ct.incident_id}</code>
                  <span className={`badge ht-md-${ct.severity}`}>{MUC_DO[ct.severity]}</span>
                  <span className="badge">{TRANG_THAI[ct.status]}</span>
                  <span className="badge">{PHAN_HE[ct.subsystem] ?? ct.subsystem}</span>
                </span>
                <h2 className="ht-ct-tieu-de">{ct.title}</h2>
                <p className="hint">Trang <code>{ct.route}</code> · lần đầu {luc(ct.first_seen)} · lần cuối {luc(ct.last_seen)}</p>
              </header>
              <dl className="ht-so">
                <div><dt>Số lần</dt><dd>{ct.event_count}</dd></div>
                <div><dt>Người</dt><dd>{ct.affected_count}</dd></div>
                <div><dt>Báo cáo</dt><dd>{ct.report_count}</dd></div>
              </dl>
              <p className="hint ht-build">
                Build: {Object.entries(ct.builds_all).map(([k, v]) => `${k} (${v})`).join(" · ") || "—"}
              </p>

              <section className="stack-2">
                <h3 className="section-title-sm">Xử lý</h3>
                <input className="input" value={ghiChu} onChange={(e) => setGhiChu(e.target.value)} maxLength={300}
                  placeholder="Ghi chú (tuỳ chọn), vd: đã sửa ở PR #…" aria-label="Ghi chú xử lý" />
                <div className="row ht-hanh-dong">
                  {(["open", "needs_owner", "resolved"] as const).map((st) => (
                    <button key={st} type="button" className={st === "resolved" ? "btn btn-sm btn-primary" : "btn btn-sm"}
                      disabled={!!dangLam || ct.status === st} onClick={() => void doiTrangThai(st)}>
                      {dangLam === st ? "…" : st === "open" ? "Đang xử lý" : st === "needs_owner" ? "Cần chủ dự án" : "Đã xử lý"}
                    </button>
                  ))}
                  <button type="button" className="btn btn-sm btn-ghost" disabled={!!dangLam} onClick={() => void chuanBiIssue()}>
                    {dangLam === "issue" ? "…" : "Chuẩn bị issue GitHub"}
                  </button>
                </div>
                {loiCt ? <p className="hint ht-loi" role="alert">{loiCt}</p> : null}
                {nhap ? (
                  <div className="stack-2 ht-nhap">
                    <p className="hint">Bản nháp — chưa tạo gì trên GitHub. Kiểm tra rồi tự đăng.</p>
                    <input className="input" readOnly value={nhap.title} aria-label="Tiêu đề issue" />
                    <textarea className="input ht-nhap-than" readOnly value={nhap.body} rows={10} aria-label="Nội dung issue" />
                    <div className="row">
                      <button type="button" className="btn btn-sm" onClick={() => {
                        navigator.clipboard?.writeText(`${nhap.title}\n\n${nhap.body}`).catch(() => undefined);
                      }}>Sao chép</button>
                      {nhap.new_issue_url ? (
                        <a className="btn btn-sm btn-ghost" href={nhap.new_issue_url} target="_blank" rel="noopener noreferrer">
                          Mở trang tạo issue (bạn tự bấm tạo)
                        </a>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </section>

              <section className="stack-2">
                <h3 className="section-title-sm">Kiểm tra đã chạy</h3>
                {ct.checks.length ? (
                  <ul className="ht-kiem">
                    {ct.checks.map((k, n) => (
                      <li key={n} className={`ht-kiem-${k.status}`}><span className="ht-kiem-dau">{KIEM[k.status] ?? "?"}</span>
                        <span><strong>{k.tool}</strong> <span className="hint">{k.summary}</span></span></li>
                    ))}
                  </ul>
                ) : <p className="hint">Chưa có (sự cố chỉ từ lỗi client, chưa ai gửi báo cáo).</p>}
              </section>
              {ct.findings.length ? (
                <section className="stack-2">
                  <h3 className="section-title-sm">Phát hiện</h3>
                  <ul className="ht-dong">{ct.findings.map((f, n) => <li key={n}>{f.text} <span className="hint">→ {f.next}</span></li>)}</ul>
                </section>
              ) : null}
              {ct.reproduction.length ? (
                <section className="stack-2">
                  <h3 className="section-title-sm">Tái hiện</h3>
                  <ul className="ht-dong">{ct.reproduction.map((r, n) => <li key={n}>{r}</li>)}</ul>
                </section>
              ) : null}
              <section className="stack-2">
                <h3 className="section-title-sm">Phạm vi</h3>
                <p className="hint">Trang: {Object.entries(ct.routes).map(([k, v]) => `${k} (${v})`).join(", ") || "—"}</p>
                <p className="hint">Trình duyệt: {Object.entries(ct.browsers).map(([k, v]) => `${k} (${v})`).join(", ") || "—"}</p>
                <p className="hint">Thiết bị: {Object.entries(ct.devices).map(([k, v]) => `${k} (${v})`).join(", ") || "—"}</p>
              </section>
              {ct.evidence.length ? (
                <section className="stack-2">
                  <h3 className="section-title-sm">Bằng chứng (đã làm sạch)</h3>
                  <ul className="ht-dong ht-mono">{ct.evidence.slice(-10).map((e, n) => <li key={n}>{e}</li>)}</ul>
                </section>
              ) : null}
              {ct.reports.length ? (
                <section className="stack-2">
                  <h3 className="section-title-sm">Báo cáo ({ct.reports.length})</h3>
                  <ul className="ht-dong">
                    {ct.reports.map((b) => (
                      <li key={b.report_id}><code>{b.report_id}</code> “{b.summary}”{" "}
                        <span className="hint">— {b.reporter === "user" ? `người dùng ${b.reporter_user_id?.slice(0, 10) ?? ""}` : "khách"} · {b.browser}/{b.device} · {luc(b.created_at)}</span></li>
                    ))}
                  </ul>
                </section>
              ) : null}
              <section className="stack-2">
                <h3 className="section-title-sm">Dòng thời gian</h3>
                <ol className="ht-tg">
                  {[...ct.timeline].reverse().map((t, n) => (
                    <li key={n}><span className="hint">{luc(t.at)}</span> {t.text}</li>
                  ))}
                </ol>
              </section>
            </article>
          )}
        </aside>
      </div>
    </div>
  );
}
