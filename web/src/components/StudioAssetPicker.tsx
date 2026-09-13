"use client";

/**
 * BỘ CHỌN TÀI SẢN dùng chung cho cả Studio.
 *
 * Trước đó mỗi công cụ tự dựng danh sách riêng: Video Composer có `<select>`
 * của nó, Thư viện có danh sách của nó, và mỗi nơi tự quyết định hiển thị gì.
 * Ba bản sao của một khái niệm là ba chỗ có thể lệch — và chỗ lệch nguy hiểm
 * nhất là phép lọc "tài sản của ai".
 *
 * Ở đây chỉ có MỘT nguồn: `GET /api/studio/assets/{stage}`, và backend luôn
 * chỉ trả tài sản của chính người gọi. Giao diện không bao giờ tự lọc theo
 * chủ sở hữu — một phép lọc ở trình duyệt là một phép lọc bỏ qua được.
 */

import { useCallback, useState } from "react";
import {
  studio,
  type StudioAsset,
  type StudioStage,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { EmptyState, ErrorState, SkeletonList } from "@/components/ui";

export function StudioAssetPicker({
  stage,
  projectId,
  onPick,
  onClose,
  emptyHint,
}: {
  stage: StudioStage;
  projectId: string;
  onPick: (assetId: string) => void | Promise<void>;
  onClose: () => void;
  emptyHint?: string;
}) {
  const [dangGan, datDangGan] = useState("");

  const nap = useCallback(
    () => studio.assets(stage, projectId),
    [stage, projectId],
  );
  const { data, loading, error, reload } = useAsyncData(nap);

  const chon = useCallback(
    async (a: StudioAsset) => {
      if (a.in_project) return;
      datDangGan(a.id);
      try {
        await onPick(a.id);
      } finally {
        datDangGan("");
      }
    },
    [onPick],
  );

  const ds = data?.assets ?? [];

  return (
    <div className="sp-chon" role="dialog" aria-modal="true"
         aria-label="Chọn tài sản">
      <div className="sp-chon-dau">
        <h3 className="sp-chon-ten">Chọn từ thư viện của bạn</h3>
        <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
          Đóng
        </button>
      </div>

      {loading ? (
        <SkeletonList count={4} />
      ) : error ? (
        <ErrorState message={error} onRetry={reload} />
      ) : ds.length === 0 ? (
        <EmptyState
          icon="📁"
          title="Chưa có gì ở đây"
          hint={emptyHint || "Tạo ở công cụ tương ứng rồi quay lại."}
        />
      ) : (
        <ul className="sp-chon-ds">
          {ds.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className={`sp-chon-muc${a.in_project ? " sp-chon-da" : ""}`}
                onClick={() => void chon(a)}
                disabled={a.in_project || dangGan === a.id}
                aria-label={a.in_project ? `${a.label} — đã thêm` : a.label}
              >
                <span className="truncate sp-chon-nhan">{a.label}</span>
                <span className="hint sp-chon-phu">
                  {a.in_project ? "đã thêm" : a.detail}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
