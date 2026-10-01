/** Thay `next/link` trong harness QA bằng thẻ <a> thường. */
import type { AnchorHTMLAttributes, ReactNode } from "react";

interface Props extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  prefetch?: boolean;
  children?: ReactNode;
}

export default function Link({ href, prefetch: _prefetch, children, ...rest }: Props) {
  return (
    <a href={`#${href}`} {...rest}>
      {children}
    </a>
  );
}
