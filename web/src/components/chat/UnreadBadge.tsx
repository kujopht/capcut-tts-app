/** Cham so tin chua doc — cung hinh voi `.bell-dot` cua chuong thong bao. */
export function UnreadBadge({ count, className = "" }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <span className={`chat-badge ${className}`.trim()} aria-hidden="true">
      {count > 99 ? "99+" : count}
    </span>
  );
}
