"use client";

/**
 * Bang tong quan — Admin Control Center V2, Phase 2 (A1).
 *
 * CHI nhung con so may chu dem duoc RE, qua truy van BI CHAN (limit(1) + doc
 * `total` cua Appwrite, hoac snapshot trong bo nho) — khong quet toan bang,
 * khong N+1 (xem `server/main.py::_admin_dashboard_them`). Chi so nao CHUA
 * theo doi duoc (vd tai khoan verified/suspended, luu luong truy cap khi
 * Cloudflare chua cau hinh) hien RO la "chua co du lieu", KHONG bia so 0.
 */

import Link from "next/link";
import { useCallback } from "react";
import { adminApi, type AdminOverview } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChuaCauHinh, DanhSachTrangThai, OSo } from "@/components/AdminShell";
import {
  IconChart,
  IconFeather,
  IconGear,
  IconLink,
  IconSparkles,
} from "@/components/Icons";

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
          <div className="stack-3">
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

            {/* ---------------------------------------------------- USERS */}
            <div>
              <h3 className="section-title-sm">Người dùng</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Tổng số" so={data.users.total} />
                <OSo nhan="Mới hôm nay" so={data.users.new_today} />
                <OSo nhan="Mới 7 ngày" so={data.users.new_7d} />
                <OSo nhan="Mới 30 ngày" so={data.users.new_30d} />
                <OSo nhan="Đã xác minh" so={data.users.verified} />
                <OSo nhan="Chưa xác minh" so={data.users.unverified} />
                <OSo nhan="Đang tạm dừng" so={data.users.suspended} />
                <OSo
                  nhan="Có tên công khai"
                  so={data.users_with_username}
                  ghi_chu="Người chưa chọn tên công khai không nằm trong số này."
                />
              </div>
            </div>

            {/* -------------------------------------------------- CONTENT */}
            <div>
              <h3 className="section-title-sm">Nội dung</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Truyện (mọi trạng thái)" so={data.content.novels_total} />
                <OSo nhan="Truyện đã xuất bản" so={data.published_novels} />
                <OSo nhan="Chương" so={data.content.chapters_total} />
                <OSo nhan="Bình luận" so={data.content.comments_total} />
                <OSo nhan="Series Animation" so={data.content.animation_series_total} />
                <OSo
                  nhan="Series đã xuất bản"
                  so={data.content.animation_series_published}
                />
                <OSo nhan="Tập Animation" so={data.content.animation_episodes_total} />
                <OSo nhan="Báo cáo đang chờ" so={data.content.pending_reports} />
              </div>
            </div>

            {/* -------------------------------------------------- PRODUCT */}
            <div>
              <h3 className="section-title-sm">Sản phẩm</h3>
              <div className="stat-grid admin-luoi">
                <OSo
                  nhan="Dự án dịch"
                  so={data.product.translation_projects_total}
                />
                <OSo nhan="Job TTS" so={data.product.tts_jobs_total} />
                <OSo nhan="Lượt nghe hợp lệ" so={data.qualified_listens} />
                <OSo
                  nhan="Chi tiêu Image Studio (USD)"
                  so={Math.round(data.product.image_studio_spend_usd * 100) / 100}
                  ghi_chu={`Ngân sách tháng: $${data.product.image_studio_budget_usd}`}
                />
                <OSo nhan="Lượt sinh ảnh" so={data.product.image_generations_total} />
              </div>
            </div>

            {/* ----------------------------------------- ANIMATION (Phần B) */}
            <div>
              <h3 className="section-title-sm">
                <IconLink size={16} /> Trusted Video Sources
              </h3>
              {data.trusted_sources.configured ? (
                <div className="stat-grid admin-luoi">
                  <OSo nhan="Kênh tin cậy" so={data.trusted_sources.total ?? null} />
                  <OSo nhan="Đang theo dõi" so={data.trusted_sources.enabled_total ?? null} />
                  <OSo nhan="Video phát hiện hôm nay" so={data.trusted_sources.detected_today ?? null} />
                  <OSo nhan="Tự động nhập" so={data.trusted_sources.auto_imported_total ?? null} />
                  <OSo nhan="Chờ duyệt" so={data.trusted_sources.pending_total ?? null} />
                  <OSo nhan="Lỗi/xung đột" so={data.trusted_sources.error_total ?? null} />
                </div>
              ) : (
                <ChuaCauHinh
                  tieuDe="Chưa xây dựng"
                  ghiChu="Trusted Video Sources sẽ có ở giai đoạn tiếp theo (Phần B) — xem /admin/animation/sources."
                />
              )}
            </div>

            {/* ------------------------------------------------- TRAFFIC */}
            <div>
              <h3 className="section-title-sm">
                <IconChart size={16} /> Lưu lượng truy cập
              </h3>
              {data.traffic.configured ? (
                <div className="stat-grid admin-luoi">
                  <OSo nhan="Lượt truy cập (7 ngày)" so={data.traffic.visits_7d} />
                  <OSo nhan="Lượt xem trang (7 ngày)" so={data.traffic.pageviews_7d} />
                  <OSo nhan="Lượt truy cập (30 ngày)" so={data.traffic.visits_30d} />
                </div>
              ) : (
                <ChuaCauHinh
                  tieuDe="Traffic analytics not configured"
                  ghiChu="Chưa có credential Cloudflare Analytics — xem server/traffic_analytics.py."
                />
              )}
            </div>

            {/* -------------------------------------------------- SYSTEM */}
            <div>
              <h3 className="section-title-sm">
                <IconGear size={16} /> Hệ thống
              </h3>
              <div className="stat-grid admin-luoi">
                <OSo
                  nhan="Kho dữ liệu"
                  so={null}
                  ghi_chu={data.system.data_backend}
                />
                <OSo
                  nhan="Appwrite"
                  so={null}
                  ghi_chu={
                    !data.system.appwrite_configured
                      ? "Chưa cấu hình (mock)"
                      : data.system.appwrite_healthy
                        ? "Khoẻ"
                        : "Không phản hồi"
                  }
                />
                <OSo
                  nhan="Worker TTS"
                  so={null}
                  ghi_chu={data.system.inline_worker ? "Chạy trong tiến trình web" : "Tiến trình riêng"}
                />
                <OSo
                  nhan="Provider dịch"
                  so={null}
                  ghi_chu={data.system.translation_provider_configured ? "Đã cấu hình" : "Chưa cấu hình"}
                />
              </div>
            </div>

            <p className="hint">
              Các con số trên đếm từ dữ liệu thật của backend đang chạy, qua
              truy vấn bị chặn (không quét toàn bảng). Chỉ số hiện &ldquo;—&rdquo;
              nghĩa là chưa có dữ liệu/chưa cấu hình, không phải bằng 0.
            </p>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
