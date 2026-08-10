"use client";

/**
 * Bo component dung chung cua design system.
 *
 * Moi trang deu dung lai o day, khong tu ve lai button/card/badge rieng.
 */

import { useCallback, useEffect, useRef } from "react";
import type { JobStatus } from "@/lib/api";

/* ------------------------------------------------------------- dau trang */

/**
 * Dau trang: nhan nho, tieu de, mo ta, va cho dat hanh dong ben phai.
 *
 * Truoc day moi trang tu ghep `<header className="row-between">` kem
 * `style={{ maxWidth: 620 }}` inline. Bay cho lam cung mot viec la bay lan de
 * lech, va style inline thi media query khong voi toi — o dien thoai doan mo
 * ta van bi ep o 620px.
 */
export function PageHeader({
  eyebrow,
  icon,
  title,
  lead,
  action,
  id,
}: {
  eyebrow?: string;
  /** Bieu tuong dat truoc nhan nho. Tuy chon — khong phai dau trang nao cung can. */
  icon?: React.ReactNode;
  title: string;
  lead?: React.ReactNode;
  action?: React.ReactNode;
  /** Dat khi trang can `aria-labelledby` tro toi tieu de nay. */
  id?: string;
}) {
  return (
    <header className="page-head">
      <div className="stack-2 page-head-body">
        {eyebrow ? (
          <span className="eyebrow eyebrow-icon">
            {icon}
            {eyebrow}
          </span>
        ) : null}
        <h1 className="page-title" id={id}>
          {title}
        </h1>
        {lead ? <p className="lead lead-narrow">{lead}</p> : null}
      </div>
      {action ? <div className="row page-head-actions">{action}</div> : null}
    </header>
  );
}

/* ------------------------------------------------------------ trang thai */

export function Loading({ label = "Đang tải…" }: { label?: string }) {
  return (
    <div className="row muted" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function SkeletonCards({ count = 6 }: { count?: number }) {
  return (
    <div className="grid" role="status" aria-label="Đang tải nội dung">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card stack-2" aria-hidden="true">
          <div className="sk sk-title" />
          <div className="sk sk-text" />
          <div className="sk sk-text" style={{ width: "70%" }} />
        </div>
      ))}
    </div>
  );
}

export function SkeletonList({ count = 4 }: { count?: number }) {
  return (
    <div className="list" role="status" aria-label="Đang tải danh sách">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="sk" style={{ height: 54 }} aria-hidden="true" />
      ))}
    </div>
  );
}

export function EmptyState({
  icon = "✨",
  title,
  hint,
  action,
}: {
  icon?: string;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty" role="status">
      <span className="empty-icon" aria-hidden="true">
        {icon}
      </span>
      <strong>{title}</strong>
      {hint ? <p className="hint">{hint}</p> : null}
      {action}
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
    <div className="empty" role="alert">
      <span className="empty-icon" aria-hidden="true">
        ⚠️
      </span>
      <strong>Không tải được dữ liệu</strong>
      <p className="hint">{message}</p>
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          Thử lại
        </button>
      ) : null}
    </div>
  );
}

export function Alert({
  kind = "info",
  children,
}: {
  kind?: "info" | "ok" | "warn" | "error";
  children: React.ReactNode;
}) {
  const icon = { info: "ℹ️", ok: "✅", warn: "⚠️", error: "⛔" }[kind];
  return (
    <div
      className={`alert alert-${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      <span aria-hidden="true">{icon}</span>
      <span>{children}</span>
    </div>
  );
}

/* ------------------------------------------------------------ job */

const JOB_LOOK: Record<
  JobStatus,
  { label: string; cls: string; pulse: boolean }
> = {
  pending: { label: "Đang xếp hàng", cls: "badge-info", pulse: true },
  running: { label: "Đang xử lý", cls: "badge-brand", pulse: true },
  completed: { label: "Hoàn tất", cls: "badge-ok", pulse: false },
  failed: { label: "Thất bại", cls: "badge-danger", pulse: false },
};

/** Trang thai job: LUON co chu, khong chi dua vao mau. */
export function JobBadge({ status }: { status: JobStatus }) {
  const look = JOB_LOOK[status] ?? JOB_LOOK.pending;
  return (
    <span className={`badge ${look.cls}`}>
      <span
        className={`dot${look.pulse ? " dot-pulse" : ""}`}
        aria-hidden="true"
      />
      {look.label}
    </span>
  );
}

export function ProgressBar({
  percent,
  indeterminate = false,
  label,
}: {
  percent: number;
  indeterminate?: boolean;
  label?: string;
}) {
  const value = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div
      className={`progress${indeterminate ? " progress-indeterminate" : ""}`}
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : value}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? "Tiến trình"}
    >
      <div className="progress-bar" style={{ width: `${value}%` }} />
    </div>
  );
}

/* ------------------------------------------------------------ modal */

/**
 * Hop thoai xac nhan cho thao tac quan trong.
 *
 * Bay focus trong hop thoai, dong bang Escape, tra focus ve cho cu khi dong.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Đồng ý",
  cancelLabel = "Huỷ",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const frame = requestAnimationFrame(() => {
      panel.current?.querySelector<HTMLButtonElement>("[data-autofocus]")?.focus();
    });

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const items = panel.current.querySelectorAll<HTMLElement>(
        "button:not(:disabled), [href], input, select, textarea",
      );
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKey);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [open, onCancel]);

  const onBackdrop = useCallback(
    (event: React.MouseEvent) => {
      if (event.target === event.currentTarget) onCancel();
    },
    [onCancel],
  );

  if (!open) return null;

  return (
    <div className="modal-backdrop" onMouseDown={onBackdrop}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        ref={panel}
      >
        <h2 id="confirm-title">{title}</h2>
        <div className="muted modal-body">
          {body}
        </div>
        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            data-autofocus
            className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ tien ich */

export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(value: number): string {
  return value.toLocaleString("vi-VN");
}
