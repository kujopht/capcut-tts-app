/** Trang thai trong — noi THAT dieu gi dang xay ra va nguoi dung lam gi duoc. */
export function ChatEmptyState({
  icon = "💬",
  title,
  hint,
  children,
}: {
  icon?: string;
  title: string;
  hint?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="chat-empty" role="status">
      <span className="chat-empty-icon" aria-hidden="true">{icon}</span>
      <strong>{title}</strong>
      {hint ? <p className="hint">{hint}</p> : null}
      {children}
    </div>
  );
}
