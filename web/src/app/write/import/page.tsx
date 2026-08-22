"use client";

/**
 * Nhập chương HÀNG LOẠT (TXT/JSON) vào một truyện.
 *
 * Trang này KHÔNG phải một luồng tạo chương thứ hai. Nó gọi đúng những thứ đã
 * có: `POST /api/novels/{id}/chapter-imports` (mở lô), `GET .../{batch_id}`
 * (tiến độ) và `POST /api/novels/{id}/publish` (xuất bản, vốn là cấp TRUYỆN —
 * nên không có, và sẽ không có, nút "xuất bản hàng loạt"). Việc tạo chương và
 * xếp job thật do worker làm ở tiến trình nền, xem
 * `server/bulk_import_service.py`.
 *
 * BA điều giao diện phải nói thẳng, vì đoán sai ở quy mô 500 chương là đắt:
 *
 *  1. XEM TRƯỚC trước khi ghi. Quy ước tách chương phải kiểm được, không phải
 *     tin được — nên nút "Bắt đầu nhập" chỉ mở sau khi đã xem trước.
 *  2. GỬI LẠI CÙNG TỆP là TIẾP TỤC, không phải nhập lần hai.
 *  3. HUỶ chỉ dừng việc MỚI. Audio đang tổng hợp vẫn chạy đến cùng và vẫn được
 *     ghi nhận — đừng vẽ "đã dừng hẳn".
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  type ChapterImportBatch,
  type ChapterImportDetail,
  type Novel,
  type Voice,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { loginHref } from "@/lib/nav";
import { fanficOnly } from "@/lib/workspace";
import {
  MAX_CHAPTER_CHARS,
  MAX_IMPORT_ITEMS,
  MAX_IMPORT_TOTAL_CHARS,
} from "@/lib/limits";
import {
  ALL_VOICES_LABEL,
  RECOMMENDED_LABEL,
  defaultVoiceId,
  usableVoices,
  voiceOptionLabel,
  voiceSections,
} from "@/lib/voices";
import {
  Alert,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  ProgressBar,
  formatNumber,
} from "@/components/ui";

/** Mẫu một tệp TXT hợp lệ — hiện thẳng trên trang, không bắt đi đọc tài liệu. */
const MAU_TXT = `=== Chương 1: Khởi đầu ===
Nội dung chương một…

=== Chương 2: Ra khơi ===
Nội dung chương hai…`;

const NHAN_LO: Record<string, string> = {
  preparing: "Đang ghi danh sách chương",
  running: "Đang chạy",
  cancelling: "Đang huỷ — chờ audio đang làm",
  cancelled: "Đã huỷ",
  completed: "Hoàn tất",
  partial: "Xong, có chương lỗi",
  failed: "Lỗi",
};

const NHAN_MUC: Record<string, string> = {
  pending: "Chờ tạo chương",
  chapter_created: "Đã tạo chương",
  job_queued: "Đang tạo audio",
  completed: "Xong",
  failed: "Lỗi",
};

const HANG_MUC: Record<string, string> = {
  completed: "badge badge-ok",
  failed: "badge badge-danger",
  job_queued: "badge badge-brand",
  chapter_created: "badge badge-info",
  pending: "badge",
};

/** Lô còn được worker xử lý -> giao diện phải tự làm mới. */
function dangChay(batch: ChapterImportBatch | null | undefined): boolean {
  if (!batch) return false;
  return batch.status === "preparing"
    || batch.status === "running"
    || batch.status === "cancelling";
}

function doanDinhDang(filename: string, text: string): "txt" | "json" {
  if (filename.toLowerCase().endsWith(".json")) return "json";
  const dau = text.trimStart()[0];
  return dau === "[" || dau === "{" ? "json" : "txt";
}

export default function ChapterImportPage() {
  const router = useRouter();
  const { profile, loading: sessionLoading } = useSession();
  const toast = useToast();

  const [novels, setNovels] = useState<Novel[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [novelId, setNovelId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [text, setText] = useState("");
  const [format, setFormat] = useState<"txt" | "json">("txt");
  const [sourceName, setSourceName] = useState("");
  const [voiceId, setVoiceId] = useState("");
  /** Bỏ chọn = lô CHỈ tạo chương. Trạng thái hợp lệ và hữu dụng. */
  const [taoAudio, setTaoAudio] = useState(true);

  const [preview, setPreview] = useState<
    Awaited<ReturnType<typeof api.previewChapterImport>> | null
  >(null);
  const [dangXemTruoc, setDangXemTruoc] = useState(false);
  const [dangBatDau, setDangBatDau] = useState(false);

  const [batchId, setBatchId] = useState("");
  const [detail, setDetail] = useState<ChapterImportDetail | null>(null);
  const [loSan, setLoSan] = useState<ChapterImportBatch[]>([]);
  const [locTrangThai, setLocTrangThai] = useState("");
  const [dangHuy, setDangHuy] = useState(false);
  const [dangThuLai, setDangThuLai] = useState("");
  const [dangXuatBan, setDangXuatBan] = useState(false);

  const nhomGiong = useMemo(
    () => voiceSections(usableVoices(voices)),
    [voices],
  );
  const truyen = useMemo(
    () => novels.find((n) => n.novel_id === novelId) ?? null,
    [novels, novelId],
  );

  /* ---------------------------------------------------------------- nạp */

  const load = useCallback(() => {
    Promise.all([api.listNovels(true), api.voices()])
      .then(([danhSach, giong]) => {
        const cuaToi = fanficOnly(danhSach.novels);
        setNovels(cuaToi);
        setVoices(giong.voices);
        setVoiceId((cur) => cur || defaultVoiceId(giong.voices));
        setNovelId((cur) => cur || cuaToi[0]?.novel_id || "");
      })
      .catch((cause) => setError(errorMessage(cause)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (sessionLoading || !profile) return;
    load();
  }, [sessionLoading, profile, load]);

  /*
    Chưa đăng nhập -> sang trang đăng nhập, KÈM nơi cần quay lại. `replace` chứ
    không `push`: nút Back phải đưa về trang trước, không phải về một trang sẽ
    lại đẩy sang đăng nhập. Cùng cách làm với `/write`.
  */
  useEffect(() => {
    if (sessionLoading || profile) return;
    router.replace(loginHref("/write/import"));
  }, [sessionLoading, profile, router]);

  /*
    Đổi truyện thì mọi thứ của truyện cũ phải biến mất, kể cả lô đang xem.

    Việc DỌN nằm ở handler `doiTruyen` (một sự kiện người dùng), không nằm trong
    effect: gọi `setState` đồng bộ trong thân effect gây một loạt render lồng
    nhau — và `eslint-plugin-react-hooks` khoá lại đúng chỗ đó. Effect ở đây chỉ
    ĐỌC danh sách lô, tức là đúng việc của một effect.
  */
  const doiTruyen = useCallback((id: string) => {
    setNovelId(id);
    setPreview(null);
    setBatchId("");
    setDetail(null);
    setLoSan([]);
  }, []);

  useEffect(() => {
    if (!novelId) return;
    let con_dung = true;
    api
      .listChapterImports(novelId)
      .then((d) => {
        if (!con_dung) return;
        setLoSan(d.batches);
        // Tự mở lô đang chạy: đóng tab rồi mở lại phải thấy ngay việc đang dở.
        const dang = d.batches.find((b) => dangChay(b));
        if (dang) setBatchId(dang.batch_id);
      })
      .catch(() => {
        if (con_dung) setLoSan([]);
      });
    return () => {
      con_dung = false;
    };
  }, [novelId]);

  /* ------------------------------------------------------- theo dõi lô */

  const napLo = useCallback(
    (bid: string, loc: string) => {
      if (!novelId || !bid) return;
      api
        .getChapterImport(novelId, bid, { limit: 200, status: loc || undefined })
        .then(setDetail)
        .catch((cause) => toast.error(errorMessage(cause)));
    },
    [novelId, toast],
  );

  useEffect(() => {
    if (!batchId) return;
    napLo(batchId, locTrangThai);
  }, [batchId, locTrangThai, napLo]);

  /*
    Tự làm mới KHI VÀ CHỈ KHI lô còn chạy.

    Dừng ngay khi lô kết: một tab mở suốt ngày không được tiếp tục gõ vào backend
    cho một lô đã xong — đó là cách dễ nhất để đốt hạn mức đọc. 3 giây khớp chu
    kỳ quét của worker (`FAS_WORKER_POLL_SECONDS`); nhanh hơn thì chỉ thấy lại
    đúng con số cũ.

    `locRef` để bộ hẹn không phải dựng lại mỗi lần người dùng đổi bộ lọc.
  */
  const locRef = useRef(locTrangThai);
  // Ghi ref trong EFFECT, không trong thân render: đọc/ghi `.current` lúc render
  // làm component có thể không cập nhật như mong đợi, và lint khoá lại chỗ đó.
  useEffect(() => {
    locRef.current = locTrangThai;
  }, [locTrangThai]);
  const conChay = dangChay(detail?.batch);
  useEffect(() => {
    if (!batchId || !conChay) return;
    const t = window.setInterval(() => napLo(batchId, locRef.current), 3000);
    return () => window.clearInterval(t);
  }, [batchId, conChay, napLo]);

  /* ---------------------------------------------------------- thao tác */

  const chonTep = useCallback(async (file: File | null) => {
    if (!file) return;
    // `file.text()`, KHÔNG base64: đầu vào là văn bản thuần, và base64 chỉ làm
    // thân request phồng thêm một phần ba mà không được gì.
    const noiDung = await file.text();
    setText(noiDung);
    setFormat(doanDinhDang(file.name, noiDung));
    setSourceName(file.name);
    setPreview(null);
  }, []);

  const xemTruoc = useCallback(() => {
    if (!novelId || !text.trim()) return;
    setDangXemTruoc(true);
    api
      .previewChapterImport(novelId, { text, format })
      .then((d) => {
        setPreview(d);
        if (d.already_imported) {
          toast.ok("Đầu vào này đã có lô — gửi lại sẽ TIẾP TỤC lô đó.");
        }
      })
      .catch((cause) => {
        setPreview(null);
        toast.error(errorMessage(cause));
      })
      .finally(() => setDangXemTruoc(false));
  }, [novelId, text, format, toast]);

  const batDau = useCallback(() => {
    if (!novelId || !preview) return;
    setDangBatDau(true);
    api
      .createChapterImport(novelId, {
        text,
        format,
        voice_id: taoAudio ? voiceId : "",
        source_name: sourceName,
      })
      .then((d) => {
        setBatchId(d.batch.batch_id);
        setDetail({ batch: d.batch, progress: d.progress, items: [], count: 0 });
        if (d.voice_ignored) {
          toast.ok(
            "Lô này đã có từ trước và giữ giọng của lần gửi đầu. Muốn giọng "
              + "khác thì đổi ở từng chương.",
          );
        } else if (d.resumed) {
          toast.ok("Tiếp tục lô cũ từ chỗ đang dở.");
        } else if (!d.created) {
          toast.ok("Đầu vào này đã nhập xong trước đó — không còn gì để làm.");
        } else {
          toast.ok("Đã mở lô nhập. Chương sẽ hiện dần.");
        }
        api
          .listChapterImports(novelId)
          .then((l) => setLoSan(l.batches))
          .catch(() => undefined);
      })
      .catch((cause) => toast.error(errorMessage(cause)))
      .finally(() => setDangBatDau(false));
  }, [novelId, preview, text, format, taoAudio, voiceId, sourceName, toast]);

  const huy = useCallback(() => {
    if (!novelId || !batchId) return;
    setDangHuy(true);
    api
      .cancelChapterImport(novelId, batchId)
      .then((d) => {
        setDetail((cur) =>
          cur ? { ...cur, batch: d.batch, progress: d.progress } : cur,
        );
        if (!d.cancelled) {
          toast.ok("Lô đã kết thúc từ trước.");
        } else if (d.jobs_in_flight) {
          toast.ok(
            `Đã dừng xếp việc mới. ${d.jobs_in_flight} audio đang làm vẫn chạy `
              + "đến cùng và vẫn được ghi nhận.",
          );
        } else {
          toast.ok("Đã huỷ lô.");
        }
      })
      .catch((cause) => toast.error(errorMessage(cause)))
      .finally(() => setDangHuy(false));
  }, [novelId, batchId, toast]);

  const thuLai = useCallback(
    (itemId: string) => {
      if (!novelId || !batchId) return;
      setDangThuLai(itemId || "tat-ca");
      const goi = itemId
        ? api.retryChapterImportItem(novelId, batchId, itemId)
        : api.retryChapterImport(novelId, batchId);
      goi
        .then((d) => {
          toast.ok(
            d.retried
              ? `Đã đưa ${d.retried} chương về hàng chờ.`
              : "Không có chương nào cần thử lại.",
          );
          napLo(batchId, locTrangThai);
        })
        .catch((cause) => toast.error(errorMessage(cause)))
        .finally(() => setDangThuLai(""));
    },
    [novelId, batchId, locTrangThai, napLo, toast],
  );

  const xuatBan = useCallback(() => {
    if (!novelId) return;
    setDangXuatBan(true);
    api
      .publishNovel(novelId)
      .then((d) => {
        setNovels((cur) =>
          cur.map((n) => (n.novel_id === novelId ? d.novel : n)),
        );
        toast.ok("Đã xuất bản truyện.");
      })
      .catch((cause) => toast.error(errorMessage(cause)))
      .finally(() => setDangXuatBan(false));
  }, [novelId, toast]);

  /* ------------------------------------------------------------- render */

  if (sessionLoading || loading) return <Loading />;
  if (error && novels.length === 0) {
    return (
      <main className="page">
        <ErrorState
          message={error}
          onRetry={() => {
            setError("");
            setLoading(true);
            load();
          }}
        />
      </main>
    );
  }

  const batch = detail?.batch ?? null;
  const progress = detail?.progress ?? null;
  const quaDai = text.length > MAX_IMPORT_TOTAL_CHARS;

  return (
    <main className="page stack-5">
      <PageHeader
        eyebrow="Tác giả"
        title="Nhập chương hàng loạt"
        lead="Đưa nhiều chương từ một tệp TXT/JSON vào một truyện, rồi tạo audio dần."
        action={
          <Link href="/write" className="btn btn-ghost">
            Về trang Viết truyện
          </Link>
        }
      />

      {novels.length === 0 ? (
        <EmptyState
          icon="📚"
          title="Chưa có truyện nào"
          hint="Tạo truyện trước, rồi quay lại đây để nhập chương."
          action={
            <Link href="/write" className="btn btn-primary">
              Sang trang Viết truyện
            </Link>
          }
        />
      ) : (
        <>
          {/* ------------------------------------------------ chọn truyện */}
          <section className="card stack">
            <h2 className="section-title">Truyện</h2>
            <div className="field">
              <label className="label" htmlFor="import-novel">
                Nhập vào truyện
              </label>
              <select
                id="import-novel"
                className="select"
                value={novelId}
                onChange={(e) => doiTruyen(e.target.value)}
              >
                {novels.map((n) => (
                  <option key={n.novel_id} value={n.novel_id}>
                    {n.title}
                    {n.state === "published" ? " — đã xuất bản" : " — bản nháp"}
                  </option>
                ))}
              </select>
            </div>
            {truyen?.state === "published" ? (
              <Alert kind="info">
                Truyện này đã xuất bản, nên chương nhập vào công khai ngay khi
                được tạo. Chương chưa có audio hiện “chưa có audio” — đó là
                trạng thái bình thường, không phải lỗi.
              </Alert>
            ) : null}
          </section>

          {/* --------------------------------------------------- đầu vào */}
          <section className="card stack">
            <h2 className="section-title">1. Nội dung</h2>
            <p className="hint">
              Mỗi chương bắt đầu bằng một dòng <code>=== Tên chương ===</code>.
              Mọi thứ sau dòng đó, đến dòng tiêu đề kế tiếp, là nội dung chương.
              Một dòng <code>====</code> trơn KHÔNG phải ranh giới chương, nên
              dấu ngắt cảnh trong truyện vẫn an toàn. Văn bản nằm trước dòng
              tiêu đề đầu tiên bị từ chối — để không ai mất chương một mà không
              biết.
            </p>
            <pre className="mono">{MAU_TXT}</pre>

            <div className="row row-tight">
              <div className="field grow">
                <label className="label" htmlFor="import-file">
                  Chọn tệp (.txt hoặc .json)
                </label>
                <input
                  id="import-file"
                  className="input"
                  type="file"
                  accept=".txt,.json,text/plain,application/json"
                  onChange={(e) => void chonTep(e.target.files?.[0] ?? null)}
                />
              </div>
              <div className="field">
                <label className="label" htmlFor="import-format">
                  Định dạng
                </label>
                <select
                  id="import-format"
                  className="select select-inline"
                  value={format}
                  onChange={(e) => {
                    setFormat(e.target.value as "txt" | "json");
                    setPreview(null);
                  }}
                >
                  <option value="txt">TXT — === Tên chương ===</option>
                  <option value="json">JSON — [{"{"}title, content{"}"}]</option>
                </select>
              </div>
            </div>

            <div className="field">
              <div className="label-row">
                <label className="label" htmlFor="import-text">
                  …hoặc dán trực tiếp
                </label>
                <span
                  className={`counter${quaDai ? " counter-over" : ""}`}
                >
                  {formatNumber(text.length)} /{" "}
                  {formatNumber(MAX_IMPORT_TOTAL_CHARS)}
                </span>
              </div>
              <textarea
                id="import-text"
                className="textarea textarea-tall mono"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  setPreview(null);
                }}
              />
              <p className="hint">
                Tối đa {MAX_IMPORT_ITEMS} chương mỗi lô, mỗi chương tối đa{" "}
                {formatNumber(MAX_CHAPTER_CHARS)} ký tự. Truyện dài hơn thì chia
                nhiều lô — các lô nối tiếp nhau đúng thứ tự.
              </p>
            </div>

            <div className="row">
              <button
                type="button"
                className="btn"
                disabled={!text.trim() || quaDai || dangXemTruoc}
                onClick={xemTruoc}
              >
                {dangXemTruoc ? "Đang đọc…" : "Xem trước"}
              </button>
            </div>
          </section>

          {/* -------------------------------------------------- xem trước */}
          {preview ? (
            <section className="card stack">
              <h2 className="section-title">
                2. Xem trước — {preview.count} chương
              </h2>
              {preview.already_imported && preview.existing_batch ? (
                <Alert kind="info">
                  Đầu vào này đã có một lô (
                  {NHAN_LO[preview.existing_batch.status]
                    ?? preview.existing_batch.status}
                  ). Bấm “Bắt đầu nhập” sẽ TIẾP TỤC lô đó, không tạo chương
                  trùng và không tổng hợp lại audio đã có.
                </Alert>
              ) : null}
              <p className="hint">
                Chương mới nối tiếp sau chương thứ {preview.order_base} đang có,
                đúng thứ tự trong tệp. Tổng {formatNumber(preview.total_chars)}{" "}
                ký tự.
              </p>

              <ol className="list">
                {preview.chapters.map((c, i) => (
                  <li className="list-item" key={`${i}-${c.title}`}>
                    <span className="list-index">
                      {preview.order_base + i + 1}
                    </span>
                    <span className="truncate list-title">{c.title}</span>
                    <span className="hint">
                      {formatNumber(c.char_count)} ký tự
                    </span>
                  </li>
                ))}
              </ol>

              <div className="field">
                <label className="label">
                  <input
                    type="checkbox"
                    checked={taoAudio}
                    onChange={(e) => setTaoAudio(e.target.checked)}
                  />{" "}
                  Tạo audio ngay sau khi tạo chương
                </label>
                {taoAudio ? (
                  <select
                    className="select"
                    aria-label="Giọng đọc"
                    value={voiceId}
                    onChange={(e) => setVoiceId(e.target.value)}
                  >
                    {/* Hai mục, MỘT `<select>` — cùng cách làm với `/write`,
                        xem `voiceSections`. */}
                    <optgroup label={RECOMMENDED_LABEL}>
                      {nhomGiong.recommended.map((voice) => (
                        <option
                          key={`goi-y-${voice.voice_id}`}
                          value={voice.voice_id}
                        >
                          {voiceOptionLabel(voice)}
                        </option>
                      ))}
                    </optgroup>
                    <optgroup label={ALL_VOICES_LABEL}>
                      {nhomGiong.all.map((voice) => (
                        <option key={voice.voice_id} value={voice.voice_id}>
                          {voiceOptionLabel(voice)}
                        </option>
                      ))}
                    </optgroup>
                  </select>
                ) : null}
                <p className="hint">
                  Bỏ chọn thì lô chỉ tạo chương — chọn giọng sau, ở từng chương.
                  Lô nhập KHÔNG BAO GIỜ tổng hợp lại audio đã có: muốn giọng
                  khác cho một chương thì đổi ở trang Viết truyện.
                </p>
              </div>

              <div className="row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={dangBatDau}
                  onClick={batDau}
                >
                  {dangBatDau ? "Đang mở lô…" : "Bắt đầu nhập"}
                </button>
              </div>
            </section>
          ) : null}

          {/* --------------------------------------------------- tiến độ */}
          {batch && progress ? (
            <section className="card stack">
              <div className="row-between">
                <h2 className="section-title">
                  3. Tiến độ — {NHAN_LO[batch.status] ?? batch.status}
                </h2>
                <span className="hint mono">{batch.batch_id}</span>
              </div>

              <ProgressBar
                percent={progress.percent}
                label="Tiến độ nhập chương"
              />

              <div className="stat-grid">
                <div className="stat">
                  <span className="stat-label">Tổng</span>
                  <span className="stat-value">{progress.total}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Đã tạo chương</span>
                  <span className="stat-value">{progress.chapters_created}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Đã xếp audio</span>
                  <span className="stat-value">{progress.jobs_queued}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Hoàn tất</span>
                  <span className="stat-value">{progress.completed}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Lỗi</span>
                  <span className="stat-value">{progress.failed}</span>
                </div>
                <div className="stat">
                  <span className="stat-label">Còn chờ</span>
                  <span className="stat-value">{progress.pending}</span>
                </div>
              </div>

              {batch.last_error ? (
                <Alert kind="error">{batch.last_error}</Alert>
              ) : null}
              {batch.status === "cancelling" ? (
                <Alert kind="info">
                  Đã dừng xếp việc mới. Audio đang tổng hợp vẫn chạy đến cùng và
                  vẫn được ghi nhận — bỏ chúng đi là nén đi đúng phần việc đắt
                  nhất.
                </Alert>
              ) : null}
              {batch.status === "failed" ? (
                <Alert kind="error">
                  Lô lỗi ở cấp lô. Gửi lại đúng tệp cũ để tiếp tục từ chỗ đang
                  dở — phần đã nhập không mất.
                </Alert>
              ) : null}
              {batch.status === "partial" ? (
                <Alert kind="warn">
                  Đã chạy hết nhưng còn {progress.failed} chương lỗi. Thử lại
                  từng chương, hoặc thử lại tất cả — chương đã xong không bị
                  chạy lại.
                </Alert>
              ) : null}

              <div className="row row-tight">
                {dangChay(batch) ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={dangHuy}
                    onClick={huy}
                  >
                    {dangHuy ? "Đang huỷ…" : "Huỷ lô"}
                  </button>
                ) : null}
                {progress.failed > 0 ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={dangThuLai === "tat-ca"}
                    onClick={() => thuLai("")}
                  >
                    Thử lại {progress.failed} chương lỗi
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => napLo(batchId, locTrangThai)}
                >
                  Làm mới
                </button>
                <Link
                  href={`/novels/${novelId}`}
                  className="btn btn-sm btn-ghost"
                >
                  Nghe thử trước khi xuất bản
                </Link>
                {truyen?.state !== "published" ? (
                  <button
                    type="button"
                    className="btn btn-sm btn-primary"
                    disabled={dangXuatBan || dangChay(batch)}
                    title={
                      dangChay(batch)
                        ? "Đợi lô kết thúc rồi hãy xuất bản"
                        : undefined
                    }
                    onClick={xuatBan}
                  >
                    {dangXuatBan ? "Đang xuất bản…" : "Xuất bản truyện"}
                  </button>
                ) : null}
              </div>

              {/* ------------------------------------------ danh sách mục */}
              <div className="row row-tight">
                <div className="field">
                  <label className="label" htmlFor="import-filter">
                    Lọc theo trạng thái
                  </label>
                  <select
                    id="import-filter"
                    className="select select-inline"
                    value={locTrangThai}
                    onChange={(e) => setLocTrangThai(e.target.value)}
                  >
                    <option value="">Tất cả</option>
                    {Object.entries(NHAN_MUC).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>
                <span className="hint">{detail?.count ?? 0} mục</span>
              </div>

              <div className="admin-bang-boc">
                <table className="admin-bang">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Chương</th>
                      <th scope="col">Trạng thái</th>
                      <th scope="col">
                        <span className="sr-only">Thao tác</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(detail?.items ?? []).map((m) => (
                      <tr key={m.item_id}>
                        <td>{batch.order_base + m.item_index}</td>
                        <td>
                          {m.chapter_id ? (
                            <Link href={`/chapters/${m.chapter_id}`}>
                              {m.title}
                            </Link>
                          ) : (
                            m.title
                          )}
                          <div className="hint">
                            {formatNumber(m.char_count)} ký tự
                            {m.attempts > 0 ? ` · đã thử ${m.attempts} lần` : ""}
                          </div>
                        </td>
                        <td>
                          <span className={HANG_MUC[m.status] ?? "badge"}>
                            {NHAN_MUC[m.status] ?? m.status}
                          </span>
                          {m.error_message ? (
                            <div className="hint">{m.error_message}</div>
                          ) : null}
                        </td>
                        <td>
                          {m.status === "failed" ? (
                            <button
                              type="button"
                              className="btn btn-sm btn-ghost"
                              disabled={dangThuLai === m.item_id}
                              onClick={() => thuLai(m.item_id)}
                            >
                              Thử lại
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {/* ---------------------------------------------------- lô cũ */}
          {loSan.length > 0 ? (
            <section className="card stack">
              <h2 className="section-title">Các lô của truyện này</h2>
              <ul className="list">
                {loSan.map((b) => (
                  <li className="list-item" key={b.batch_id}>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost truncate"
                      onClick={() => setBatchId(b.batch_id)}
                    >
                      {b.source_name || b.batch_id}
                    </button>
                    <span className="hint">
                      {b.total_items} chương · {NHAN_LO[b.status] ?? b.status}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </main>
  );
}
