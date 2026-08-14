/**
 * Avatar dung chung: anh that (`avatarUrl` da ky) hoac chu cai dau ten.
 *
 * Truoc V4 moi cho tu ve rieng mot `<span className="avatar">{initials}</span>`
 * — sau khi avatar that xuat hien o SAU noi (NavAuth, /account, PostCard,
 * CommentThread, SearchOverlay x2), chep lai logic anh/chu cai o tung noi la
 * sai. `className` van do NGUOI GOI quyet dinh (kich thuoc khac nhau theo
 * ngu canh: `.avatar`, `.avatar-sm`, `.account-avatar`, `.tim-avatar`), day
 * chi gom phan LOGIC hien anh-hay-chu.
 */

export function Avatar({
  name,
  avatarUrl,
  className,
}: {
  /** Dung de suy chu cai dau khi chua co anh. */
  name: string;
  avatarUrl?: string | null;
  className: string;
}) {
  return (
    <span
      className={className}
      aria-hidden="true"
      style={
        avatarUrl
          ? {
              backgroundImage: `url("${avatarUrl}")`,
              backgroundSize: "cover",
              backgroundPosition: "center",
            }
          : undefined
      }
    >
      {avatarUrl ? null : name.slice(0, 2).toUpperCase()}
    </span>
  );
}
