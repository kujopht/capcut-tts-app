"use client";

/**
 * Cac trang thai dung chung: loading / empty / error.
 *
 * Tach rieng de moi trang deu co day du bon trang thai ma khong lap code.
 */

export function Loading({ label = "Đang tải..." }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <p style={{ marginTop: 12 }}>{label}</p>
    </div>
  );
}

export function EmptyState({
  icon = "📚",
  title,
  body,
  action,
}: {
  icon?: string;
  title: string;
  body?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state">
      <div style={{ fontSize: 40, marginBottom: 8 }} aria-hidden="true">
        {icon}
      </div>
      <p className="state-title">{title}</p>
      {body ? <p style={{ marginTop: 0 }}>{body}</p> : null}
      {action ? <div style={{ marginTop: 16 }}>{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state" role="alert">
      <div style={{ fontSize: 40, marginBottom: 8 }} aria-hidden="true">
        ⚠️
      </div>
      <p className="state-title">Không tải được dữ liệu</p>
      <p style={{ marginTop: 0 }}>{message}</p>
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          Thử lại
        </button>
      ) : null}
    </div>
  );
}

export function Alert({
  kind = "error",
  children,
}: {
  kind?: "error" | "ok" | "warn";
  children: React.ReactNode;
}) {
  return (
    <div
      className={`alert alert-${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

/** Nhan trang thai job, kem mau va chu - khong chi dua vao mau sac. */
export function JobBadge({ status }: { status: string }) {
  const map: Record<string, { cls: string; text: string }> = {
    pending: { cls: "badge", text: "Đang chờ" },
    running: { cls: "badge badge-run", text: "Đang tạo" },
    completed: { cls: "badge badge-ok", text: "Hoàn thành" },
    failed: { cls: "badge badge-err", text: "Thất bại" },
  };
  const item = map[status] ?? { cls: "badge", text: status };
  return <span className={item.cls}>{item.text}</span>;
}
