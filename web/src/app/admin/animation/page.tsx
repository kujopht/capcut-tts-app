"use client";

/**
 * Muc Animation trong khu quan tri — trang LANDING (Phase 4, Admin Control
 * Center V2). Danh sach/kiem duyet THAT nam o `/admin/animation/series`,
 * `/admin/animation/sources`, va `/admin/animation/import-queue`; day chi la
 * loi vao ngan dan sang ba trang do.
 */

import Link from "next/link";
import { IconFilm, IconInbox, IconLink } from "@/components/Icons";

export default function AdminAnimation() {
  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconFilm size={19} /> Animation
      </h2>
      <p className="hint">
        Kiểm duyệt series/tập Animation trên toàn nền tảng — mọi chủ sở hữu,
        không chỉ series của riêng bạn.
      </p>

      <div className="bento-grid">
        <Link href="/admin/animation/series" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconFilm size={17} /> Series
          </h3>
          <p className="hint">
            Danh sách series, tìm kiếm, lọc theo trạng thái, xem chi tiết
            từng series kèm danh sách tập — gỡ xuống/phục hồi khi cần.
          </p>
        </Link>

        <Link href="/admin/animation/sources" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconLink size={17} /> Trusted Sources
          </h3>
          <p className="hint">Quản lý nguồn tin cậy, WebSub, quét/khám phá.</p>
        </Link>

        <Link href="/admin/animation/import-queue" className="card stack-2">
          <h3 className="section-title section-title-icon">
            <IconInbox size={17} /> Import Queue
          </h3>
          <p className="hint">Xem hàng đợi nhập, duyệt/từ chối từng mục.</p>
        </Link>
      </div>
    </section>
  );
}
