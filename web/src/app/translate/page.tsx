"use client";

/**
 * Novel Translation Studio (V5) — /translate.
 *
 * MOT trang, HAI trang thai: chua chon du an (danh sach + form tao moi) va
 * dang xem MOT du an (tien do job + danh sach chuong + Novel Bible +
 * nhap-vao-truyen). Khong tach thanh nhieu route con o vong dau — du an
 * dich chua co nhieu de can dieu huong rieng, va mot trang duy nhat thi
 * trang thai (du an dang chon) song tu nhien trong React state.
 *
 * KHONG tao mot AudioEngine/MiniPlayer thu hai: sau khi nhap vao truyen
 * nhap, tao audio la viec cua /write (pipeline TTS hien co), khong lam o day.
 */

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import {
  GENRE_OPTIONS,
  NAMING_OPTIONS,
  QUALITY_OPTIONS,
  translate,
  type GenrePreset,
  type GlossaryEntry,
  type NamingMode,
  type QualityMode,
  type TranslationJob,
  type TranslationProject,
} from "@/lib/api";
import { errorMessage, useSession } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { useAsyncData } from "@/lib/useAsyncData";
import {
  Alert,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
} from "@/components/ui";
import { loginHref } from "@/lib/nav";
import { IconFeather } from "@/components/Icons";

const TRANG_THAI_NHAN: Record<string, string> = {
  queued: "Đang xếp hàng…",
  analyzing: "Đang phân tích…",
  glossary: "Đang xây dựng từ điển…",
  translating: "Đang dịch…",
  reviewing: "Đang biên tập…",
  qa: "Đang kiểm tra chất lượng…",
  completed: "Đã hoàn tất",
  failed: "Thất bại",
  cancelled: "Đã huỷ",
};

/** Doc mot tep thanh chuoi base64 (KHONG qua canvas — day la van ban/zip,
    khong phai anh). Tach rieng khoi `lib/image.ts::xuLyAnh`: hai bai toan
    khac nhau du cung xuat ra base64. */
function docTepThanhBase64(tep: File): Promise<string> {
  return new Promise((giai, tuChoi) => {
    const doc = new FileReader();
    doc.onload = () => {
      const ket = String(doc.result || "");
      giai(ket.slice(ket.indexOf(",") + 1));
    };
    doc.onerror = () => tuChoi(new Error("Không đọc được tệp."));
    doc.readAsDataURL(tep);
  });
}

export default function TranslatePage() {
  const { profile, loading: dangTaiPhien } = useSession();
  const [duAnDangChon, setDuAnDangChon] = useState<TranslationProject | null>(null);

  if (dangTaiPhien) {
    return (
      <div className="page">
        <Loading label="Đang tải…" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="page">
        <PageHeader
          eyebrow="Công cụ"
          icon={<IconFeather />}
          title="Dịch tiểu thuyết"
          lead="Dịch tiểu thuyết Trung văn sang tiếng Việt, có từ điển thuật ngữ
               riêng cho từng bộ truyện, rồi đưa thẳng vào bản nháp Fanfic World."
        />
        <EmptyState
          icon="🈺"
          title="Đăng nhập để bắt đầu dịch"
          action={
            <Link className="btn btn-primary" href={loginHref("/translate")}>
              Đăng nhập
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow="Công cụ"
        icon={<IconFeather />}
        title="Dịch tiểu thuyết"
        lead="Dán văn bản hoặc tải tệp .txt/.epub/.docx, chọn thể loại và cách
             gọi tên nhân vật, rồi để hệ thống dịch từng chương."
      />
      {duAnDangChon ? (
        <ProjectDetail
          projectId={duAnDangChon.project_id}
          onQuayLai={() => setDuAnDangChon(null)}
        />
      ) : (
        <ProjectPicker onChon={setDuAnDangChon} />
      )}
    </div>
  );
}

/* ============================================================ chon/tao du an */

function ProjectPicker({
  onChon,
}: {
  onChon: (p: TranslationProject) => void;
}) {
  const { data, loading, error, reload } = useAsyncData(
    useCallback(() => translate.listProjects(), []),
  );

  return (
    <div className="stack-5">
      <NewProjectForm onTaoXong={onChon} />

      <section className="stack-2">
        <h2 className="section-title">Dự án của bạn</h2>
        {loading ? (
          <Loading label="Đang tải danh sách…" />
        ) : error ? (
          <ErrorState message={error} onRetry={reload} />
        ) : !data?.projects.length ? (
          <p className="hint">Chưa có dự án dịch nào.</p>
        ) : (
          <ul className="stack-2" style={{ listStyle: "none", padding: 0 }}>
            {data.projects.map((p) => (
              <li key={p.project_id}>
                <button
                  type="button"
                  className="card card-tight"
                  style={{ width: "100%", textAlign: "left", cursor: "pointer" }}
                  onClick={() => onChon(p)}
                >
                  <strong>{p.title}</strong>{" "}
                  <span className="hint">
                    · {p.genre_label} · {p.translated_chapter_count}/
                    {p.chapter_count} chương đã dịch
                    {p.imported_to_novel_id ? " · đã nhập vào truyện" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function NewProjectForm({
  onTaoXong,
}: {
  onTaoXong: (p: TranslationProject) => void;
}) {
  const toast = useToast();
  const [tieuDe, setTieuDe] = useState("");
  const [vanBan, setVanBan] = useState("");
  const [genre, setGenre] = useState<GenrePreset>("auto");
  const [naming, setNaming] = useState<NamingMode>("auto");
  const [quality, setQuality] = useState<QualityMode>("can_bang");
  const [dangTao, setDangTao] = useState(false);
  const [uocLuong, setUocLuong] = useState<{
    characters: number; chapters: number;
  } | null>(null);
  const oTep = useRef<HTMLInputElement | null>(null);

  const capNhatUocLuong = useCallback(async (vb: string) => {
    setVanBan(vb);
    if (!vb.trim()) {
      setUocLuong(null);
      return;
    }
    try {
      const u = await translate.estimate(vb);
      setUocLuong(u);
    } catch {
      // Uoc luong chi la goi y — im lang neu that bai, khong chan nguoi dung.
    }
  }, []);

  const taoBangDan = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!vanBan.trim()) return;
      setDangTao(true);
      try {
        const { project } = await translate.createProject({
          title: tieuDe, sourceText: vanBan, genre,
          namingMode: naming, qualityMode: quality,
        });
        toast.ok(`Đã tạo dự án — ${project.chapter_count} chương.`);
        onTaoXong(project);
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setDangTao(false);
      }
    },
    [tieuDe, vanBan, genre, naming, quality, toast, onTaoXong],
  );

  const chonTep = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const tep = event.target.files?.[0];
      event.target.value = "";
      if (!tep) return;
      setDangTao(true);
      try {
        const b64 = await docTepThanhBase64(tep);
        const { project } = await translate.uploadProject({
          filename: tep.name, base64: b64, title: tieuDe,
          genre, namingMode: naming, qualityMode: quality,
        });
        toast.ok(`Đã tải "${tep.name}" — ${project.chapter_count} chương.`);
        onTaoXong(project);
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setDangTao(false);
      }
    },
    [tieuDe, genre, naming, quality, toast, onTaoXong],
  );

  return (
    <form className="card stack" onSubmit={taoBangDan}>
      <h2 className="section-title">Bắt đầu dịch mới</h2>
      <div className="field">
        <label className="label" htmlFor="trans-title">
          Tên dự án (tuỳ chọn)
        </label>
        <input
          id="trans-title"
          className="input"
          value={tieuDe}
          onChange={(e) => setTieuDe(e.target.value)}
          maxLength={200}
          placeholder="Ví dụ: Đấu Phá Thương Khung"
        />
      </div>
      <div className="field">
        <label className="label" htmlFor="trans-text">
          Dán văn bản gốc
        </label>
        <textarea
          id="trans-text"
          className="textarea"
          rows={8}
          value={vanBan}
          onChange={(e) => void capNhatUocLuong(e.target.value)}
          placeholder="Dán nội dung tiểu thuyết Trung văn vào đây…"
        />
        {uocLuong ? (
          <span className="hint">
            {uocLuong.characters.toLocaleString("vi-VN")} ký tự · ước tính{" "}
            {uocLuong.chapters} chương
          </span>
        ) : null}
      </div>

      <div className="row row-tight">
        <div className="field">
          <label className="label" htmlFor="trans-genre">
            Thể loại
          </label>
          <select
            id="trans-genre"
            className="input"
            value={genre}
            onChange={(e) => setGenre(e.target.value as GenrePreset)}
          >
            {GENRE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="trans-naming">
            Cách gọi tên
          </label>
          <select
            id="trans-naming"
            className="input"
            value={naming}
            onChange={(e) => setNaming(e.target.value as NamingMode)}
          >
            {NAMING_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset className="stack-2">
        <legend className="label">Chế độ chất lượng</legend>
        <div className="row row-tight">
          {QUALITY_OPTIONS.map((o) => (
            <label key={o.value} className="chip" style={{ cursor: "pointer" }}>
              <input
                type="radio"
                name="quality"
                value={o.value}
                checked={quality === o.value}
                onChange={() => setQuality(o.value)}
                style={{ marginRight: 6 }}
              />
              {o.label}
            </label>
          ))}
        </div>
        <span className="hint">
          {QUALITY_OPTIONS.find((o) => o.value === quality)?.hint}
        </span>
      </fieldset>

      <div className="row row-tight">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={dangTao || !vanBan.trim()}
        >
          {dangTao ? <span className="spinner" aria-hidden="true" /> : null}
          Dịch văn bản đã dán
        </button>
        <label className="btn btn-outline" style={{ cursor: "pointer" }}>
          Hoặc tải tệp .txt/.epub/.docx
          <input
            ref={oTep}
            type="file"
            accept=".txt,.epub,.docx"
            hidden
            disabled={dangTao}
            onChange={chonTep}
          />
        </label>
      </div>
    </form>
  );
}

/* ============================================================ chi tiet du an */

function ProjectDetail({
  projectId,
  onQuayLai,
}: {
  projectId: string;
  onQuayLai: () => void;
}) {
  const toast = useToast();
  const { data, loading, error, reload } = useAsyncData(
    useCallback(() => translate.getProject(projectId), [projectId]),
  );
  const [dangTaoJob, setDangTaoJob] = useState(false);
  const [dangNhap, setDangNhap] = useState(false);
  const jobDinhKy = useRef<number | null>(null);

  const batDauDich = useCallback(async () => {
    setDangTaoJob(true);
    try {
      await translate.createJob(projectId);
      toast.ok("Đã bắt đầu dịch.");
      // Doi tuong mock hoan tat gan nhu ngay — tai lai NGAY, roi van dat
      // mot vong hoi dinh ky ngan de xu ly truong hop provider that (co do
      // tre) ma khong lam nguoi dung cho vo han: dung khi da completed/failed.
      reload();
      let lan = 0;
      const hoi = () => {
        lan += 1;
        translate.getProject(projectId).then((d) => {
          const job = d.jobs[0];
          if (!job || job.status === "completed" || job.status === "failed"
              || job.status === "cancelled" || lan > 30) {
            reload();
            return;
          }
          jobDinhKy.current = window.setTimeout(hoi, 2000);
        });
      };
      jobDinhKy.current = window.setTimeout(hoi, 2000);
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangTaoJob(false);
    }
  }, [projectId, toast, reload]);

  const nhapVaoTruyen = useCallback(async () => {
    setDangNhap(true);
    try {
      const ra = await translate.importToDraft(projectId);
      toast.ok(
        ra.already_imported
          ? "Dự án này đã được nhập vào truyện trước đó."
          : `Đã tạo truyện với ${ra.chapters_created} chương.`,
      );
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangNhap(false);
    }
  }, [projectId, toast, reload]);

  if (loading) return <Loading label="Đang tải dự án…" />;
  if (error) return <ErrorState message={error} onRetry={reload} />;
  if (!data) return null;

  const { project, chapters, jobs } = data;
  const jobMoiNhat: TranslationJob | undefined = jobs[0];
  const coBanDich = project.translated_chapter_count > 0;

  return (
    <div className="stack-5">
      <button type="button" className="btn btn-ghost btn-sm" onClick={onQuayLai}>
        ← Danh sách dự án
      </button>

      <section className="card stack">
        <div className="row-between">
          <div className="stack-2">
            <h2 className="section-title">{project.title}</h2>
            <span className="hint">
              {project.genre_label} · {project.naming_mode_label} ·{" "}
              {project.chapter_count} chương
              {project.source_filename ? ` · ${project.source_filename}` : ""}
            </span>
          </div>
          {project.imported_to_novel_id ? (
            <Link className="btn btn-sm" href={`/novels/${project.imported_to_novel_id}`}>
              Xem truyện đã nhập
            </Link>
          ) : null}
        </div>

        {jobMoiNhat ? (
          <div className="stack-2">
            <span className="hint">
              Chương {jobMoiNhat.current_chapter}/{jobMoiNhat.total_chapters} ·{" "}
              {TRANG_THAI_NHAN[jobMoiNhat.status] ?? jobMoiNhat.status}
            </span>
            <div
              className="progress"
              role="progressbar"
              aria-valuenow={jobMoiNhat.progress}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="progress-bar" style={{ width: `${jobMoiNhat.progress}%` }} />
            </div>
            {jobMoiNhat.status === "failed" && jobMoiNhat.error ? (
              <Alert kind="error">{jobMoiNhat.error}</Alert>
            ) : null}
          </div>
        ) : null}

        <div className="row row-tight">
          {!jobMoiNhat || jobMoiNhat.status === "failed"
           || jobMoiNhat.status === "cancelled" ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={dangTaoJob}
              onClick={batDauDich}
            >
              {dangTaoJob ? <span className="spinner" aria-hidden="true" /> : null}
              Bắt đầu dịch
            </button>
          ) : null}
          {coBanDich && !project.imported_to_novel_id ? (
            <button
              type="button"
              className="btn btn-outline"
              disabled={dangNhap}
              onClick={nhapVaoTruyen}
            >
              {dangNhap ? <span className="spinner" aria-hidden="true" /> : null}
              Đưa vào truyện nháp
            </button>
          ) : null}
        </div>
      </section>

      <GlossaryPanel projectId={projectId} />

      {coBanDich ? (
        <section className="stack-2">
          <h2 className="section-title">Bản dịch</h2>
          {chapters.filter((c) => c.translated).map((c) => (
            <details key={c.index} className="card card-tight">
              <summary style={{ cursor: "pointer" }}>Chương {c.index + 1}</summary>
              <p className="prose" style={{ marginTop: 8 }}>{c.text}</p>
            </details>
          ))}
        </section>
      ) : null}
    </div>
  );
}

/* ============================================================ Novel Bible */

function GlossaryPanel({ projectId }: { projectId: string }) {
  const toast = useToast();
  const { data, loading, reload } = useAsyncData(
    useCallback(() => translate.listGlossary(projectId), [projectId]),
  );
  const [goc, setGoc] = useState("");
  const [dich, setDich] = useState("");
  const [dangThem, setDangThem] = useState(false);

  const them = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!goc.trim() || !dich.trim()) return;
      setDangThem(true);
      try {
        await translate.addGlossaryEntry(projectId, {
          category: "character", original: goc.trim(), translated: dich.trim(),
        });
        setGoc("");
        setDich("");
        reload();
      } catch (cause) {
        toast.error(errorMessage(cause));
      } finally {
        setDangThem(false);
      }
    },
    [projectId, goc, dich, toast, reload],
  );

  const doiKhoa = useCallback(
    async (entry: GlossaryEntry) => {
      try {
        await translate.updateGlossaryEntry(projectId, entry.term_id, {
          locked: !entry.locked,
        });
        reload();
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [projectId, toast, reload],
  );

  return (
    <section className="card stack-2">
      <h2 className="section-title">Từ điển thuật ngữ (Novel Bible)</h2>
      <p className="hint">
        Khoá một thuật ngữ để giữ nguyên bản dịch của bạn ở mọi chương sau này.
      </p>
      {loading ? (
        <Loading label="Đang tải từ điển…" />
      ) : !data?.entries.length ? (
        <p className="hint">Chưa có thuật ngữ nào.</p>
      ) : (
        <ul className="stack-2" style={{ listStyle: "none", padding: 0 }}>
          {data.entries.map((entry) => (
            <li key={entry.term_id} className="row-between">
              <span>
                <strong>{entry.original}</strong> → {entry.translated}
              </span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void doiKhoa(entry)}
              >
                {entry.locked ? "🔒 Đã khoá" : "🔓 Khoá"}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="row row-tight" onSubmit={them}>
        <input
          className="input"
          placeholder="Từ gốc (萧炎)"
          value={goc}
          onChange={(e) => setGoc(e.target.value)}
          maxLength={80}
        />
        <input
          className="input"
          placeholder="Bản dịch (Tiêu Viêm)"
          value={dich}
          onChange={(e) => setDich(e.target.value)}
          maxLength={80}
        />
        <button type="submit" className="btn btn-sm" disabled={dangThem}>
          Thêm
        </button>
      </form>
    </section>
  );
}
