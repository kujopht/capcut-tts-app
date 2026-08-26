import Link from "next/link";
import { EmptyState } from "@/components/ui";

/**
 * 404 toan cuc — bat moi URL khong khop route nao (tu Next 13.3.0, root
 * `app/not-found.tsx` lam viec nay ma khong can co `global-not-found`/flag
 * thu nghiem, vi site chi co MOT root layout — xem
 * `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/not-found.md`).
 *
 * TRUOC DAY: khong co file nay, nen Next tra ve trang 404 mac dinh bang
 * tieng Anh ("This page could not be found.") — lac long voi phan con lai
 * cua site, noi moi trang khac (kem ca cac empty-state "Khong tim thay...")
 * deu dung tieng Viet va cung mot component `EmptyState`.
 *
 * File nay duoc render BEN TRONG root layout (header/footer/nav van con),
 * nen chi can noi dung trang, khong can `<html>`/`<body>` nhu
 * `global-not-found.js`.
 */
export default function NotFound() {
  return (
    <div className="page">
      <EmptyState
        icon="🧭"
        title="Không tìm thấy trang này"
        hint="Đường dẫn có thể đã đổi hoặc chưa từng tồn tại."
        action={
          <Link className="btn btn-primary" href="/" prefetch={false}>
            Về trang chủ
          </Link>
        }
      />
    </div>
  );
}
