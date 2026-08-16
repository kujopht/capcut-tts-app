"use client";

/**
 * Analytics — Admin Control Center V2, Phase 2 (A6).
 *
 * Dung LAI du lieu tu `/api/admin/overview` (mot lan goi, khong them truy
 * van moi) — tach hai loai theo dung tinh than A6:
 * - TRAFFIC: nha cung cap ngoai (Cloudflare) — hien "chưa cấu hình" ro rang
 *   khi chua co credential, KHONG chan ca trang Analytics.
 * - PRODUCT: tong hop tu chinh du lieu Fanfic World (dang ky/noi dung/dich/
 *   TTS/anh/credit) — cac phep dem BI CHAN da co san o Dashboard.
 */

import { useCallback } from "react";
import { adminApi, type AdminOverview } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChuaCauHinh, DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { IconChart } from "@/components/Icons";

export default function AdminAnalytics() {
  const nap = useCallback(() => adminApi.overview(), []);
  const { data, loading, error, reload } = useAsyncData<AdminOverview>(nap);

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconChart size={19} /> Analytics
      </h2>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!data} onThuLai={reload}>
        {data ? (
          <div className="stack-3">
            <div>
              <h3 className="section-title-sm">Lưu lượng truy cập</h3>
              {data.traffic.configured ? (
                <div className="stat-grid admin-luoi">
                  <OSo nhan="Lượt truy cập (7 ngày)" so={data.traffic.visits_7d} />
                  <OSo nhan="Lượt xem trang (7 ngày)" so={data.traffic.pageviews_7d} />
                  <OSo nhan="Lượt truy cập (30 ngày)" so={data.traffic.visits_30d} />
                  <OSo nhan="Lượt xem trang (30 ngày)" so={data.traffic.pageviews_30d} />
                </div>
              ) : (
                <ChuaCauHinh
                  tieuDe="Traffic analytics not configured"
                  ghiChu={data.traffic.message || "Chưa có credential Cloudflare Analytics."}
                />
              )}
            </div>

            <div>
              <h3 className="section-title-sm">Sản phẩm (Fanfic World)</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Đăng ký (hôm nay)" so={data.users.new_today} />
                <OSo nhan="Đăng ký (7 ngày)" so={data.users.new_7d} />
                <OSo nhan="Đăng ký (30 ngày)" so={data.users.new_30d} />
                <OSo nhan="Lượt nghe hợp lệ" so={data.qualified_listens} />
                <OSo nhan="Dự án dịch" so={data.product.translation_projects_total} />
                <OSo nhan="Job TTS" so={data.product.tts_jobs_total} />
                <OSo nhan="Tập Animation" so={data.content.animation_episodes_total} />
                <OSo
                  nhan="Chi tiêu Image Studio (USD)"
                  so={Math.round(data.product.image_studio_spend_usd * 100) / 100}
                />
              </div>
              <p className="hint">
                Chưa có bản tổng hợp DAU/WAU/MAU theo ngày (cần một job tổng
                hợp riêng để tránh quét toàn bộ sự kiện thô) — các số trên là
                tổng lũy kế/theo khoảng thời gian, không phải người dùng hoạt
                động độc lập theo ngày.
              </p>
            </div>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
