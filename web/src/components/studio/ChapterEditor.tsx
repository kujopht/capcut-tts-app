"use client";

/**
 * Editor chuong/doan cua Novel Translation Studio (V5) — Part N/O.
 *
 * Bo cuc: [ danh sach chuong ] [ nguon Trung van ] [ ban dich tieng Viet ]
 * — Novel Bible (glossary) da la MOT panel rieng o `page.tsx`
 * (`GlossaryPanel`), khong lap lai o day.
 *
 * NGUYEN TAC "CANH BAO TRUOC KHI GHI DE": moi hanh dong tai sinh (regen
 * doan/chuong, chay lai mot pass) goi API voi `force=false` truoc; neu may
 * chu tra 409 (`ManualEditWouldBeOverwritten`) thi hien `ConfirmDialog` roi
 * goi lai voi `force=true` — KHONG BAO GIO tu dong ghi de sua tay im lang.
 */

import { useCallback, useEffect, useState } from "react";
import {
  translate,
  type ChapterDetail,
  type TranslationVersion,
} from "@/lib/api";
import { errorMessage } from "@/lib/session";
import { useToast } from "@/lib/toast";
import { Alert, ConfirmDialog, Loading } from "@/components/ui";

interface ChapterRow {
  index: number;
  translated: boolean;
  has_warnings: boolean;
}

const NHAN_PASS: Record<string, string> = {
  translator: "Dịch giả",
  editor: "Biên tập văn học",
  qa: "Kiểm tra chất lượng",
  manual: "Chỉnh sửa thủ công",
};

function trangThaiChuong(row: ChapterRow, dangDichChuong: number | null): {
  icon: string; nhan: string;
} {
  if (dangDichChuong !== null && dangDichChuong === row.index) {
    return { icon: "●", nhan: "Đang dịch…" };
  }
  if (!row.translated) return { icon: "○", nhan: "Đang chờ" };
  if (row.has_warnings) return { icon: "!", nhan: "Cần kiểm tra" };
  return { icon: "✓", nhan: "Đã dịch" };
}

/** Hanh dong tai sinh CO THE bi 409 (sua tay se bi ghi de) — dung chung mot
    kieu goi + xu ly ConfirmDialog cho ca ba nut (regen chuong/doan/pass). */
type HanhDongTaiSinh = (force: boolean) => Promise<{ chapter: ChapterDetail }>;

export default function ChapterEditor({
  projectId,
  chapters,
  qualityRoles,
  onChanged,
}: {
  projectId: string;
  chapters: ChapterRow[];
  /** Cac vai tro THAT theo che do chat luong cua du an, vd
      ["translator","editor","qa"] — dung de hien dung nut "chạy lại" nao. */
  qualityRoles: string[];
  /** Goi lai sau khi mot hanh dong thanh cong, de trang cha lam moi
      danh sach chuong (co the doi `has_warnings`/`translated`). */
  onChanged: () => void;
}) {
  const toast = useToast();
  const [chiSoDangMo, setChiSoDangMo] = useState<number>(
    chapters.find((c) => c.translated)?.index ?? 0,
  );
  const [chiTiet, setChiTiet] = useState<ChapterDetail | null>(null);
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState("");
  const [vanBanDang, setVanBanDang] = useState("");
  const [dangLuu, setDangLuu] = useState(false);
  const [dangChayHanhDong, setDangChayHanhDong] = useState(false);
  const [xacNhanGhiDe, setXacNhanGhiDe] = useState<HanhDongTaiSinh | null>(null);
  const [lichSu, setLichSu] = useState<TranslationVersion[] | null>(null);

  const coSuaChuaLuu = chiTiet !== null && vanBanDang !== chiTiet.translated_text;

  // `useEffect` CHI khoi dong promise, moi `setState` nam trong `.then`/
  // `.catch` — cung mau voi `useAsyncData` (xem docstring cua no): goi
  // `setState` DONG BO trong than effect gay render tang bac, ESLint
  // (`react-hooks/set-state-in-effect`) tu choi build neu vi pham. Trang
  // thai "dang tai" cho lan CHUYEN chuong duoc dat truoc, trong `chonChuong`
  // (mot su kien nguoi dung — dat truc tiep o do la an toan); lan tai DAU
  // TIEN dung gia tri mac dinh cua `useState(true)` o tren.
  useEffect(() => {
    let huyBo = false;
    translate.getChapter(projectId, chiSoDangMo).then(
      ({ chapter }) => {
        if (huyBo) return;
        setChiTiet(chapter);
        setVanBanDang(chapter.translated_text);
        setDangTai(false);
      },
      (cause) => {
        if (huyBo) return;
        setLoi(errorMessage(cause));
        setDangTai(false);
      },
    );
    return () => {
      huyBo = true;
    };
  }, [projectId, chiSoDangMo]);

  // Canh bao khi dong tab/tai lai TRANG (khac voi `chonChuong` — chi bao
  // ve luc CHUYEN CHUONG trong noi bo editor). Trinh duyet tu hien hop
  // thoai chuan cua no, `returnValue` chi can khac rong de kich hoat.
  useEffect(() => {
    if (!coSuaChuaLuu) return;
    const canhBao = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", canhBao);
    return () => window.removeEventListener("beforeunload", canhBao);
  }, [coSuaChuaLuu]);

  const chonChuong = useCallback(
    (chiSo: number) => {
      if (coSuaChuaLuu
          && !window.confirm(
            "Bạn có thay đổi chưa lưu ở chương này. Chuyển chương sẽ MẤT thay đổi đó — tiếp tục?",
          )) {
        return;
      }
      setDangTai(true);
      setLoi("");
      setLichSu(null);
      setChiSoDangMo(chiSo);
    },
    [coSuaChuaLuu],
  );

  const luuSuaTay = useCallback(async () => {
    if (!chiTiet) return;
    setDangLuu(true);
    try {
      const { chapter } = await translate.saveChapterEdit(
        projectId, chiTiet.chapter_index, vanBanDang,
      );
      setChiTiet(chapter);
      setVanBanDang(chapter.translated_text);
      toast.ok("Đã lưu chỉnh sửa.");
      onChanged();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangLuu(false);
    }
  }, [projectId, chiTiet, vanBanDang, toast, onChanged]);

  const chayHanhDong = useCallback(
    async (hanhDong: HanhDongTaiSinh) => {
      setDangChayHanhDong(true);
      try {
        const { chapter } = await hanhDong(false);
        setChiTiet(chapter);
        setVanBanDang(chapter.translated_text);
        setLichSu(null);
        toast.ok("Đã cập nhật bản dịch.");
        onChanged();
      } catch (cause) {
        if (errorMessage(cause) && (cause as { status?: number })?.status === 409) {
          setXacNhanGhiDe(() => hanhDong);
        } else {
          toast.error(errorMessage(cause));
        }
      } finally {
        setDangChayHanhDong(false);
      }
    },
    [toast, onChanged],
  );

  const xacNhanVaChay = useCallback(async () => {
    if (!xacNhanGhiDe) return;
    setDangChayHanhDong(true);
    try {
      const { chapter } = await xacNhanGhiDe(true);
      setChiTiet(chapter);
      setVanBanDang(chapter.translated_text);
      setLichSu(null);
      toast.ok("Đã cập nhật bản dịch.");
      onChanged();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangChayHanhDong(false);
      setXacNhanGhiDe(null);
    }
  }, [xacNhanGhiDe, toast, onChanged]);

  const taiLichSu = useCallback(async () => {
    if (!chiTiet) return;
    try {
      const { versions } = await translate.listVersions(projectId, chiTiet.chapter_index);
      setLichSu(versions);
    } catch (cause) {
      toast.error(errorMessage(cause));
    }
  }, [projectId, chiTiet, toast]);

  const khoiPhuc = useCallback(
    async (versionId: string) => {
      try {
        const { chapter } = await translate.revertToVersion(projectId, versionId);
        setChiTiet(chapter);
        setVanBanDang(chapter.translated_text);
        toast.ok("Đã khôi phục phiên bản đã chọn.");
        onChanged();
        void taiLichSu();
      } catch (cause) {
        toast.error(errorMessage(cause));
      }
    },
    [projectId, toast, onChanged, taiLichSu],
  );

  return (
    <div className="editor-layout">
      <ConfirmDialog
        open={xacNhanGhiDe !== null}
        title="Ghi đè nội dung đã sửa tay?"
        body="Chương này đã được chỉnh sửa thủ công sau lần dịch gần nhất. Tạo lại sẽ GHI ĐÈ nội dung đã sửa — bạn vẫn có thể khôi phục lại từ lịch sử phiên bản sau này."
        confirmLabel="Vẫn ghi đè"
        danger
        busy={dangChayHanhDong}
        onConfirm={() => void xacNhanVaChay()}
        onCancel={() => setXacNhanGhiDe(null)}
      />

      <nav className="editor-rail" aria-label="Danh sách chương">
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {chapters.map((c) => {
            const tt = trangThaiChuong(c, null);
            return (
              <li key={c.index}>
                <button
                  type="button"
                  className={`editor-rail-item${c.index === chiSoDangMo ? " is-active" : ""}`}
                  onClick={() => chonChuong(c.index)}
                >
                  <span aria-hidden="true">{tt.icon}</span> Chương {c.index + 1}
                  <span className="hint" style={{ display: "block" }}>{tt.nhan}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="editor-main">
        {dangTai ? (
          <Loading label="Đang tải chương…" />
        ) : loi ? (
          <Alert kind="error">{loi}</Alert>
        ) : !chiTiet ? null : (
          <div className="stack-2">
            {chiTiet.manually_edited ? (
              <Alert kind="info">
                Chương này đang chứa nội dung ĐÃ CHỈNH SỬA THỦ CÔNG.
              </Alert>
            ) : null}
            {chiTiet.warnings.length > 0 ? (
              <Alert kind="warn">
                {chiTiet.warnings.join(" ")}
              </Alert>
            ) : null}

            <div className="editor-panes">
              <div className="stack-2">
                <h3 className="section-title">Nguyên văn (Trung)</h3>
                <div className="prose editor-pane-text">{chiTiet.source_text}</div>
              </div>
              <div className="stack-2">
                <div className="row-between">
                  <h3 className="section-title">Bản dịch (Việt)</h3>
                  {coSuaChuaLuu ? (
                    <span className="badge badge-warn">● Chưa lưu</span>
                  ) : null}
                </div>
                <textarea
                  className="textarea editor-pane-text"
                  rows={16}
                  value={vanBanDang}
                  disabled={!chiTiet.is_translated}
                  onChange={(e) => setVanBanDang(e.target.value)}
                  placeholder={
                    chiTiet.is_translated ? undefined
                      : "Chương này chưa được dịch xong."
                  }
                />
                <div className="row row-tight">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={!coSuaChuaLuu || dangLuu}
                    onClick={() => void luuSuaTay()}
                  >
                    {dangLuu ? <span className="spinner" aria-hidden="true" /> : null}
                    Lưu chỉnh sửa
                  </button>
                  {chiTiet.is_translated ? (
                    <>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={dangChayHanhDong || coSuaChuaLuu}
                        title={coSuaChuaLuu ? "Lưu thay đổi trước khi tạo lại." : undefined}
                        onClick={() => void chayHanhDong(
                          (force) => translate.regenerateChapter(
                            projectId, chiTiet.chapter_index, force),
                        )}
                      >
                        Dịch lại cả chương
                      </button>
                      {qualityRoles.map((vaiTro) => (
                        <button
                          key={vaiTro}
                          type="button"
                          className="btn btn-ghost btn-sm"
                          disabled={dangChayHanhDong || coSuaChuaLuu}
                          onClick={() => void chayHanhDong(
                            (force) => translate.rerunPass(
                              projectId, chiTiet.chapter_index,
                              vaiTro as "translator" | "editor" | "qa", force),
                          )}
                        >
                          Chạy lại: {NHAN_PASS[vaiTro] ?? vaiTro}
                        </button>
                      ))}
                    </>
                  ) : null}
                </div>
              </div>
            </div>

            {chiTiet.is_translated
             && chiTiet.source_paragraphs.length > 0
             && chiTiet.source_paragraphs.length === chiTiet.translated_paragraphs.length ? (
              <details className="card card-tight">
                <summary style={{ cursor: "pointer" }}>
                  Dịch lại từng đoạn ({chiTiet.source_paragraphs.length} đoạn)
                </summary>
                <ul className="stack-2" style={{ listStyle: "none", padding: 0, marginTop: 8 }}>
                  {chiTiet.translated_paragraphs.map((doan, i) => (
                    <li key={i} className="row-between">
                      <span className="hint" style={{ maxWidth: "70%" }}>
                        {doan.slice(0, 120)}{doan.length > 120 ? "…" : ""}
                      </span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={dangChayHanhDong || coSuaChuaLuu}
                        title={coSuaChuaLuu ? "Lưu thay đổi trước khi dịch lại đoạn." : undefined}
                        onClick={() => void chayHanhDong(
                          (force) => translate.regenerateParagraph(
                            projectId, chiTiet.chapter_index, i, force),
                        )}
                      >
                        Dịch lại đoạn này
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}

            <details className="card card-tight" onToggle={(e) => {
              if ((e.target as HTMLDetailsElement).open) void taiLichSu();
            }}>
              <summary style={{ cursor: "pointer" }}>Lịch sử phiên bản</summary>
              {lichSu === null ? (
                <p className="hint">Đang tải…</p>
              ) : lichSu.length === 0 ? (
                <p className="hint">Chưa có lịch sử nào cho chương này.</p>
              ) : (
                <ul className="stack-2" style={{ listStyle: "none", padding: 0, marginTop: 8 }}>
                  {lichSu.map((v) => (
                    <li key={v.version_id} className="row-between">
                      <span className="hint">
                        {new Date(v.created_at).toLocaleString("vi-VN")} ·{" "}
                        {v.operation} · {NHAN_PASS[v.pass_type] ?? v.pass_type}
                        {v.provider_id
                          ? ` · ${v.provider_id}${v.model_id ? `/${v.model_id}` : ""}`
                          : ""}
                      </span>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm"
                        onClick={() => void khoiPhuc(v.version_id)}
                      >
                        Khôi phục
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </details>
          </div>
        )}
      </div>
    </div>
  );
}
