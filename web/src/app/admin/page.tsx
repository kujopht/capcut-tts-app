"use client";

/**
 * Bang tong quan.
 *
 * CHI nhung con so may chu dem duoc RE. Khong bia them chi so nao: mot con so
 * sai tren bang quan tri con te han khong co con so nao, vi no duoc dung de ra
 * quyet dinh.
 */

import Link from "next/link";
import { useCallback } from "react";
import { adminApi, type AdminOverview } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { IconFeather, IconSparkles } from "@/components/Icons";

export default function AdminDashboard() {
  const nap = useCallback(() => adminApi.overview(), []);
  const { data, loading, error, reload } = useAsyncData<AdminOverview>(nap);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconSparkles size={19} /> Tổng quan
      </h2>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={!data}
        onThuLai={reload}
      >
        {data ? (
          <>
            {data.pending_applications > 0 ? (
              <Link className="card admin-nhac" href="/admin/authors/applications?status=pending">
                <IconFeather size={19} />
                <span>
                  <strong>{data.pending_applications}</strong> đơn tác giả đang
                  chờ duyệt
                </span>
                <span className="hint">Xem hàng đợi →</span>
              </Link>
            ) : null}

            <div className="stat-grid admin-luoi">
              <OSo nhan="Đơn chờ duyệt" so={data.pending_applications} />
              <OSo nhan="Tác giả đã duyệt" so={data.approved_authors} />
              <OSo nhan="Đang tạm dừng" so={data.suspended_authors} />
              <OSo nhan="Đơn bị từ chối" so={data.rejected_applications} />
              <OSo nhan="Truyện đã xuất bản" so={data.published_novels} />
              <OSo
                nhan="Người dùng có tên công khai"
                so={data.users_with_username}
                ghi_chu="Người chưa chọn tên công khai không nằm trong số này."
              />
              <OSo nhan="Lượt nghe hợp lệ" so={data.qualified_listens} />
            </div>

            <p className="hint">
              Các con số trên đếm từ dữ liệu thật của backend đang chạy. Những chỉ
              số chưa đếm được rẻ — lượt xem, thời gian nghe theo ngày — không
              được hiển thị ở đây thay vì hiển thị một giá trị đoán.
            </p>
          </>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
