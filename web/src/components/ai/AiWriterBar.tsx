"use client";

/**
 * Thanh Studio viết — CHỈ hiện ở mode `writer` (§6): chọn/tạo/đổi tên/xoá dự
 * án đã lưu (`ai_projects`), và các chip tiểu-ý-định (brainstorm/premise/
 * outline/characters/worldbuilding/draft_chapter) chèn một câu mở đầu vào ô
 * soạn — người dùng VẪN phải tự bấm Gửi, không có gì tự động gửi thay.
 *
 * Xoá dự án dùng xác nhận HAI BƯỚC TRONG TRANG (không `window.confirm`),
 * cùng khuôn với "Xoá toàn bộ ký ức AI" ở `AiControls.tsx`.
 */
import { useEffect, useState } from "react";
import { useAi } from "./AiProvider";
import { FanficIcon } from "@/components/icons/FanficIcon";

const CHIPS: { label: string; goi: string }[] = [
  { label: "Brainstorm", goi: "Hãy giúp tôi brainstorm ý tưởng cho: " },
  { label: "Premise", goi: "Hãy giúp tôi viết ý tưởng cốt truyện (premise) cho: " },
  { label: "Dàn ý", goi: "Hãy giúp tôi xây dàn ý (outline) chi tiết cho: " },
  { label: "Nhân vật", goi: "Hãy giúp tôi xây dựng nhân vật sau: " },
  { label: "Thế giới", goi: "Hãy giúp tôi xây dựng bối cảnh/thế giới cho: " },
  { label: "Viết nháp chương", goi: "Hãy viết nháp một chương dựa trên: " },
];

export function AiWriterBar() {
  const {
    mode,
    projects,
    activeProjectId,
    activeProject,
    loadProjects,
    createProject,
    selectProject,
    renameProject,
    deleteProjectById,
    draft,
    setDraft,
  } = useAi();
  const [taoMoi, setTaoMoi] = useState(false);
  const [tieuDeMoi, setTieuDeMoi] = useState("");
  const [dangSua, setDangSua] = useState(false);
  const [tieuDeSua, setTieuDeSua] = useState("");
  const [xoaXacNhan, setXoaXacNhan] = useState(false);

  useEffect(() => {
    if (mode === "writer") void loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    setDangSua(false);
    setXoaXacNhan(false);
  }, [activeProjectId]);

  if (mode !== "writer") return null;

  return (
    <div className="ai-writerbar">
      <div className="ai-writerbar-hang">
        <select
          className="ai-mode ai-writerbar-chon"
          aria-label="Chọn dự án viết"
          value={activeProjectId ?? ""}
          onChange={(e) => void selectProject(e.target.value || null)}
        >
          <option value="">— Không chọn dự án —</option>
          {projects.map((p) => (
            <option key={p.project_id} value={p.project_id}>
              {p.title || "(chưa đặt tên)"}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="ai-nut ai-nut-nho"
          aria-label="Tạo dự án mới"
          aria-expanded={taoMoi}
          title="Dự án mới"
          onClick={() => setTaoMoi((v) => !v)}
        >
          <FanficIcon name="plus" size={14} />
        </button>
        {activeProjectId ? (
          <>
            <button
              type="button"
              className="ai-nut ai-nut-nho"
              aria-label="Đổi tên dự án"
              aria-expanded={dangSua}
              title="Đổi tên"
              onClick={() => {
                setTieuDeSua(activeProject?.title ?? "");
                setDangSua((v) => !v);
              }}
            >
              <FanficIcon name="edit" size={14} />
            </button>
            <button
              type="button"
              className="ai-nut ai-nut-nho"
              aria-label="Xoá dự án"
              title="Xoá dự án"
              onClick={() => setXoaXacNhan(true)}
            >
              <FanficIcon name="trash" size={14} />
            </button>
          </>
        ) : null}
      </div>

      {taoMoi ? (
        <form
          className="ai-writerbar-form"
          onSubmit={(e) => {
            e.preventDefault();
            const t = tieuDeMoi.trim();
            if (!t) return;
            void createProject(t);
            setTieuDeMoi("");
            setTaoMoi(false);
          }}
        >
          <input
            className="ai-o ai-writerbar-input"
            value={tieuDeMoi}
            onChange={(e) => setTieuDeMoi(e.target.value)}
            placeholder="Tên dự án mới"
            maxLength={120}
            aria-label="Tên dự án mới"
            autoFocus
          />
          <button type="submit" className="btn btn-sm" disabled={!tieuDeMoi.trim()}>
            Tạo
          </button>
        </form>
      ) : null}

      {dangSua && activeProjectId ? (
        <form
          className="ai-writerbar-form"
          onSubmit={(e) => {
            e.preventDefault();
            const t = tieuDeSua.trim();
            if (!t) return;
            void renameProject(activeProjectId, t);
            setDangSua(false);
          }}
        >
          <input
            className="ai-o ai-writerbar-input"
            value={tieuDeSua}
            onChange={(e) => setTieuDeSua(e.target.value)}
            placeholder="Tên dự án"
            maxLength={120}
            aria-label="Đổi tên dự án"
            autoFocus
          />
          <button type="submit" className="btn btn-sm" disabled={!tieuDeSua.trim()}>
            Lưu
          </button>
        </form>
      ) : null}

      {xoaXacNhan && activeProjectId ? (
        <div className="ai-writerbar-xacnhan">
          <p className="hint">Xoá dự án &quot;{activeProject?.title || "(chưa đặt tên)"}&quot;? Không thể hoàn tác.</p>
          <div className="row">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setXoaXacNhan(false)}>
              Huỷ
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                void deleteProjectById(activeProjectId);
                setXoaXacNhan(false);
              }}
            >
              Xác nhận xoá
            </button>
          </div>
        </div>
      ) : null}

      <div className="ai-writerbar-chip" role="group" aria-label="Gợi ý bắt đầu">
        {CHIPS.map((c) => (
          <button
            key={c.label}
            type="button"
            className="ai-chip"
            onClick={() => setDraft(draft ? `${draft}\n${c.goi}` : c.goi)}
          >
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}
