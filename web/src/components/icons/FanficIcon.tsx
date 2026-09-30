/**
 * Bo bieu tuong dung chung, dua tren Icons8 Line Awesome (kieu "solid").
 *
 * VI SAO MOT COMPONENT MOI, khong ghep vao `Icons.tsx`: bo cu la net-stroke tu
 * ve tay (24 viewBox, stroke 1.75) — dung tot cho vai chuc hinh da co. Bo nay
 * la DU LIEU PATH vendor tu mot goi icon that (32 viewBox, fill), phuc vu quy
 * mo lon hon va nhieu mat noi dung hon (chi tiet xem
 * `web/src/components/icons/lineAwesome.generated.ts`). Hai bo cung ton tai —
 * khong doi nguoc `Icons.tsx`, chi tranh dung CA HAI cho CUNG mot cho.
 *
 * `size` mac dinh 20 (mat do day: menu, hang cong dong). Dung 24 cho dieu
 * huong chinh / nut mo Chat (xem quy uoc trong CLAUDE.md frontend).
 */
import { LINE_AWESOME_ICONS, type IconName } from "./lineAwesome.generated";

export type { IconName };

interface Props {
  name: IconName;
  /** 20 cho UI mat do day, 24 cho dieu huong chinh/nut lon. */
  size?: number;
  /** Co gia tri -> icon TU minh hoa (role="img" + aria-label). Khong co ->
   *  thuan tuy trang tri, an voi trinh doc man hinh. */
  label?: string;
  className?: string;
}

export function FanficIcon({ name, size = 20, label, className }: Props) {
  const du = LINE_AWESOME_ICONS[name];
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox={du.viewBox}
      fill="currentColor"
      {...(label
        ? { role: "img", "aria-label": label }
        : { "aria-hidden": "true", focusable: "false" })}
    >
      <path d={du.path} />
    </svg>
  );
}
