"use client";

/**
 * Trình soạn dự án viết (§6) — Ý tưởng/Dàn ý/Nhân vật/Thế giới/Ghi chú, mỗi
 * mục MỘT ô văn bản (backend lưu `outline`/`characters`/`world` dưới dạng
 * JSON tự do; giao diện quy ước một khoá `text`, xem `docVanBanTruongDuAn`
 * ở `client.ts`). Nút Lưu GHI ĐÈ (khác "Lưu vào dự án" trên tin nhắn, vốn
 * NỐI THÊM) — một lượt PUT duy nhất cho cả năm trường.
 *
 * Chỉ mount khi có `activeProject` (xem `AiWriterBar`) — seed lại state cục
 * bộ MỖI KHI đổi dự án (`activeProjectId`), không seed lại mỗi lần
 * `activeProject` refetch sau lưu, để không ghi đè phần người dùng đang gõ.
 */
import { useEffect, useState } from "react";
import { useAi } from "./AiProvider";
import { docVanBanTruongDuAn } from "@/lib/ai/client";
import { AI_PROJECT_FIELD_LABELS, AI_PROJECT_FIELD_MAX, type AiProjectField } from "@/lib/ai/types";

const CAC_TRUONG: AiProjectField[] = ["premise", "outline", "characters", "world", "notes"];

export function AiProjectEditor() {
  const { activeProjectId, activeProject, saveProjectFields } = useAi();
  const [gia, setGia] = useState<Record<AiProjectField, string>>({
    premise: "",
    outline: "",
    characters: "",
    world: "",
    notes: "",
  });
  const [dangLuu, setDangLuu] = useState(false);

  useEffect(() => {
    if (!activeProject) return;
    setGia({
      premise: activeProject.premise ?? "",
      outline: docVanBanTruongDuAn("outline", activeProject.outline),
      characters: docVanBanTruongDuAn("characters", activeProject.characters),
      world: docVanBanTruongDuAn("world", activeProject.world),
      notes: activeProject.notes ?? "",
    });
    // Chỉ seed lại khi ĐỔI dự án — không mỗi lần activeProject refetch sau lưu.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProjectId]);

  if (!activeProjectId) return null;

  const luu = async () => {
    setDangLuu(true);
    try {
      await saveProjectFields(gia);
    } finally {
      setDangLuu(false);
    }
  };

  return (
    <div className="ai-writerbar-editor">
      {CAC_TRUONG.map((f) => (
        <div className="ai-writerbar-editor-truong" key={f}>
          <label htmlFor={`ai-du-an-${f}`}>{AI_PROJECT_FIELD_LABELS[f]}</label>
          <textarea
            id={`ai-du-an-${f}`}
            maxLength={AI_PROJECT_FIELD_MAX[f]}
            value={gia[f]}
            onChange={(e) => setGia((g) => ({ ...g, [f]: e.target.value }))}
            placeholder={`${AI_PROJECT_FIELD_LABELS[f]}…`}
          />
        </div>
      ))}
      <button type="button" className="btn btn-sm ai-writerbar-editor-luu" disabled={dangLuu} onClick={() => void luu()}>
        {dangLuu ? "Đang lưu…" : "Lưu dự án"}
      </button>
    </div>
  );
}
