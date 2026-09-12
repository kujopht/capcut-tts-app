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
  IconBook,
  IconChart,
  IconFeather,
  IconGear,
  IconInbox,
  IconLink,
  IconShield,
  IconSparkles,
} from "@/components/Icons";

/**
 * Bang "Cần bạn xử lý".
 *
 * VAN DE no giai quyet: bang tong quan co hon 30 o SO LIEU va truoc day dung
 * MOT o nhac viec (don tac gia). Nhung con so con lai deu doc duoc nhu nhau —
 * "Báo cáo đang chờ: 3" trong nhu "Chương: 1.284" — nen mot viec DANG CHO
 * nguoi that xu ly khong noi hon mot con so chi de biet. Nguoi quan tri phai
 * quet ca trang de tim ra thu can bam vao.
 *
 * KHONG o so lieu nao bi bo di. Bang nay la mot lop DOC THEM dat len tren:
 * cung nhung con so do, nhung chi nhung con so KEO THEO MOT HANH DONG, va moi
 * cai la mot lien ket toi dung hang doi cua no.
 *
 * TRANG THAI RONG duoc ve RO RANG chu khong an di. Mot bang bien mat khi het
 * viec khong phan biet duoc voi mot bang hong — va "khong con viec" la thong
 * tin nguoi truc ca can biet.
 */
function CanBanXuLy({ data }: { data: AdminOverview }) {
  /*
    Truyen CHO XEM LAI — va khong phai cu "tong tru da xuat ban".

    Ban dau the nay lay `novels_total - published_novels`. Do thuc te tren kho
    production: con so do la 43, trong khi chi 2 truyen thuc su cho nguoi xem
    lai. 43 kia gom **10 kho chua cua Audio Studio** (moi nguoi dung mot cai,
    la kho chua chu khong phai truyen, va khong bao gio duoc xuat ban) cung
    **22 ban ghi khong co chuong nao** (lan audio / ban ghi kiem thu).

    Mot the luon khac 0 la mot the bi bo qua. Ca gia tri cua bang nay nam o
    cho no VE RONG khi khong con viec — nen con so phai dem dung thu nguoi
    quan tri se thuc su mo ra doc.

    Loc o day chu khong them mot endpoint moi: `/api/admin/novels?state=draft`
    DA tra ve `tags` va so `chapters` cho tung dong.
  */
  const napNhap = useCallback(() => adminApi.novels("", "draft", 100), []);
  const { data: dsNhap } = useAsyncData(napNhap);
  const nhap = (dsNhap?.novels ?? []).filter(
    (n) => !n.tags.includes("audio-studio") && n.chapters > 0,
  ).length;

  const viec = [
    {
      so: data.pending_applications,
      nhan: "đơn tác giả đang chờ duyệt",
      href: "/admin/authors/applications?status=pending",
      icon: IconFeather,
    },
    {
      so: data.content.pending_reports,
      nhan: "báo cáo kiểm duyệt đang chờ",
      href: "/admin/reports",
      icon: IconShield,
    },
    {
      so: nhap,
      nhan: "truyện có nội dung, đang chờ xem lại",
      href: "/admin/stories?state=draft",
      icon: IconBook,
    },
    {
      so: data.trusted_sources.pending_total ?? 0,
      nhan: "video chờ duyệt nhập",
      href: "/admin/animation/import-queue",
      icon: IconInbox,
    },
    {
      so: data.trusted_sources.error_total ?? 0,
      nhan: "nguồn video đang lỗi/xung đột",
      href: "/admin/animation/sources",
      icon: IconLink,
    },
  ].filter((v) => v.so > 0);

  return (
    <div className="stack-2">
      <h3 className="section-title-sm">Cần bạn xử lý</h3>
      {viec.length === 0 ? (
        <p className="hint admin-khong-viec">
          Không có việc nào đang chờ — hàng đợi duyệt, báo cáo và nhập video
          đều trống.
        </p>
      ) : (
        <div className="stack-2">
          {viec.map(({ so, nhan, href, icon: Icon }) => (
            <Link key={href} className="card admin-nhac" href={href}>
              <Icon size={19} />
              <span>
                <strong>{so.toLocaleString("vi-VN")}</strong> {nhan}
              </span>
              <span className="hint">Xem hàng đợi →</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

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
            <CanBanXuLy data={data} />

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
