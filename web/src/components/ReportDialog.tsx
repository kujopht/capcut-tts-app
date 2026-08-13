"use client";

/**
 * Hộp thoại báo cáo một bài hoặc một bình luận.
 *
 * NÓI RÕ VỚI NGƯỜI DÙNG rằng báo cáo KHÔNG gỡ nội dung ngay. Đó không phải một
 * câu trấn an: nếu người ta tưởng bấm xong là nội dung biến mất, họ sẽ bấm lại
 * nhiều lần rồi kết luận nút này hỏng. Một dòng giải thích ở đây rẻ hơn nhiều so
 * với việc đó.
 *
 * Quản lý TIÊU ĐIỂM: hộp thoại nhận tiêu điểm khi mở, Escape đóng, và tiêu điểm
 * trả về nút đã mở nó. Không có ba thứ này thì người dùng bàn phím mở được hộp
 * thoại nhưng không ra được.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, social, type ReportReason } from "@/lib/api";

/** Lý do, kèm câu mô tả người thường đọc được. Khớp `domain.ReportReason`. */
const LY_DO: ReadonlyArray<{ key: ReportReason; label: string }> = [
  { key: "spam", label: "Spam hoặc quảng cáo" },
  { key: "harassment", label: "Quấy rối, xúc phạm" },
  { key: "inappropriate", label: "Nội dung không phù hợp" },
  { key: "copyright", label: "Vi phạm bản quyền" },
  { key: "other", label: "Lý do khác" },
];

export function ReportDialog({
  targetKind,
  targetId,
  onClose,
}: {
  targetKind: "post" | "comment";
  targetId: string;
  onClose: () => void;
}) {
  const [lyDo, setLyDo] = useState<ReportReason>("spam");
  const [chiTiet, setChiTiet] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [xong, setXong] = useState(false);
  const [loi, setLoi] = useState("");
  const hop = useRef<HTMLDivElement | null>(null);

  /* Tiêu điểm vào hộp thoại khi mở, và Escape đóng. Không có hai thứ này thì
     người dùng bàn phím vào được mà không ra được. */
  useEffect(() => {
    hop.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const gui = useCallback(async () => {
    setDangGui(true);
    setLoi("");
    try {
      await social.report({
        target_kind: targetKind,
        target_id: targetId,
        reason: lyDo,
        detail: chiTiet,
      });
      setXong(true);
    } catch (e) {
      setLoi(e instanceof ApiError ? e.message : "Không gửi được báo cáo.");
    } finally {
      setDangGui(false);
    }
  }, [targetKind, targetId, lyDo, chiTiet]);

  return (
    <div className="lop-phu" role="presentation">
      <div
        className="hop-thoai"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bao-cao-tieu-de"
        tabIndex={-1}
        ref={hop}
      >
        <h2 id="bao-cao-tieu-de" className="h3">
          Báo cáo {targetKind === "post" ? "bài đăng" : "bình luận"}
        </h2>

        {xong ? (
          <>
            <p className="hint">
              Đã gửi. Báo cáo của bạn vào hàng đợi kiểm duyệt và sẽ có người xem.
            </p>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>
                Đóng
              </button>
            </div>
          </>
        ) : (
          <>
            {/*
              Câu này KHÔNG phải để trấn an. Nếu người ta tưởng bấm xong là nội
              dung biến mất, họ sẽ bấm lại nhiều lần rồi kết luận nút này hỏng.
            */}
            <p className="hint">
              Báo cáo <strong>không tự gỡ</strong> nội dung. Nó đưa nội dung vào
              hàng đợi để người kiểm duyệt xem.
            </p>

            <fieldset className="bao-cao-ly-do">
              <legend className="hint">Lý do</legend>
              {LY_DO.map((m) => (
                <label key={m.key} className="radio-hang">
                  <input
                    type="radio"
                    name="ly-do"
                    value={m.key}
                    checked={lyDo === m.key}
                    onChange={() => setLyDo(m.key)}
                  />
                  <span>{m.label}</span>
                </label>
              ))}
            </fieldset>

            <label className="hint" htmlFor="bao-cao-chi-tiet">
              Mô tả thêm (không bắt buộc)
            </label>
            <textarea
              id="bao-cao-chi-tiet"
              className="input"
              rows={3}
              maxLength={500}
              value={chiTiet}
              onChange={(e) => setChiTiet(e.target.value)}
              placeholder="Điều gì khiến bạn báo cáo nội dung này?"
            />

            {loi ? (
              <p className="hint loi" role="alert">
                {loi}
              </p>
            ) : null}

            <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
                Huỷ
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={dangGui}
                onClick={gui}
              >
                {dangGui ? "Đang gửi…" : "Gửi báo cáo"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
