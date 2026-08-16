"use client";

/**
 * Analytics — Admin Control Center V2, Phase 7.
 *
 * Doc `/api/admin/analytics/detail?range=...` — TACH khoi `/api/admin/overview`
 * (dashboard chinh phai nhe, khong them truy van bi chan o do). Doi khoang
 * thoi gian (Hom nay/7 ngay/30 ngay) goi lai route nay MOT LAN, khong polling.
 *
 * Nguyen tac: KHONG bia chi so khong the tinh dung (DAU/WAU/MAU, luot doc
 * truyen/hoan thanh chuong/luot xem Animation) — hien ro "Chưa đo lường
 * được" kem ly do, thay vi mot con so gia.
 */

import { useCallback, useState } from "react";
import {
  adminApi,
  type AdminAnalyticsDetail,
  type PhamViPhanTich,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChuaCauHinh, DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { IconChart } from "@/components/Icons";

const PHAM_VI: Array<{ khoa: PhamViPhanTich; nhan: string }> = [
  { khoa: "today", nhan: "Hôm nay" },
  { khoa: "7d", nhan: "7 ngày" },
  { khoa: "30d", nhan: "30 ngày" },
];

export default function AdminAnalytics() {
  const [pham_vi, setPhamVi] = useState<PhamViPhanTich>("7d");
  const nap = useCallback(() => adminApi.analyticsDetail(pham_vi), [pham_vi]);
  const { data, loading, error, reload } = useAsyncData<AdminAnalyticsDetail>(nap);

  return (
    <section className="stack">
      <header className="row row-spread">
        <h2 className="section-title section-title-icon">
          <IconChart size={19} /> Analytics
        </h2>
        <div className="seg" role="group" aria-label="Khoảng thời gian">
          {PHAM_VI.map((p) => (
            <button
              key={p.khoa}
              type="button"
              className="seg-item"
              aria-pressed={pham_vi === p.khoa}
              onClick={() => setPhamVi(p.khoa)}
            >
              {p.nhan}
            </button>
          ))}
        </div>
      </header>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!data} onThuLai={reload}>
        {data ? (
          <div className="stack-3">
            <div className="card stack-2">
              <h3 className="section-title-sm">Người dùng</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Đăng ký mới trong kỳ" so={data.users.registrations} />
                <OSo nhan="Hoạt động/ngày (DAU)" so={data.users.active_daily} />
                <OSo nhan="Hoạt động/tuần (WAU)" so={data.users.active_weekly} />
                <OSo nhan="Hoạt động/tháng (MAU)" so={data.users.active_monthly} />
              </div>
              <p className="hint">{data.users.active_note}</p>
            </div>

            <div className="card stack-2">
              <h3 className="section-title-sm">Nội dung</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Bình luận mới trong kỳ" so={data.content.comments} />
                <OSo nhan="Lượt đọc truyện" so={data.content.novel_reads} />
                <OSo nhan="Chương hoàn thành" so={data.content.chapter_completions} />
                <OSo nhan="Lượt xem Animation" so={data.content.animation_views} />
              </div>
              <p className="hint">{data.content.content_activity_note}</p>
            </div>

            <div className="card stack-2">
              <h3 className="section-title-sm">AI / Sản phẩm</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Dịch — hoàn thành" so={data.ai_product.translation_jobs.completed} />
                <OSo nhan="Dịch — thất bại" so={data.ai_product.translation_jobs.failed} />
                <OSo nhan="Dịch — đang xử lý" so={data.ai_product.translation_jobs.in_progress} />
                <OSo nhan="TTS — hoàn thành" so={data.ai_product.tts_jobs.completed} />
                <OSo nhan="TTS — thất bại" so={data.ai_product.tts_jobs.failed} />
                <OSo nhan="TTS — đang chạy" so={data.ai_product.tts_jobs.running} />
                <OSo nhan="Lượt sinh ảnh Image Studio" so={data.ai_product.image_studio_generations} />
              </div>
              <p className="hint">{data.ai_product.image_studio_note}</p>
            </div>

            <div className="card stack-2">
              <h3 className="section-title-sm">Trusted Video Sources</h3>
              <div className="stat-grid admin-luoi">
                <OSo nhan="Video phát hiện trong kỳ" so={data.trusted_video.detected} />
                <OSo nhan="Tự động nhập trong kỳ" so={data.trusted_video.auto_imported} />
                <OSo nhan="Chờ duyệt" so={data.trusted_video.pending} />
                <OSo nhan="Xung đột/lỗi" so={data.trusted_video.errors} />
                <OSo nhan="Lượt đối chiếu trong kỳ" so={data.trusted_video.reconciliation_runs} />
              </div>
              <p className="hint">
                Trạng thái đăng ký WebSub (snapshot hiện tại, không theo kỳ):{" "}
                {Object.entries(data.trusted_video.websub_status_breakdown)
                  .map(([trang, so]) => `${trang}: ${so}`)
                  .join(" · ")}
              </p>
            </div>

            <div className="card stack-2">
              <h3 className="section-title-sm">Lưu lượng truy cập</h3>
              {data.traffic.configured ? (
                <>
                  <div className="stat-grid admin-luoi">
                    <OSo nhan="Lượt truy cập (7 ngày)" so={data.traffic.visits_7d} />
                    <OSo nhan="Lượt xem trang (7 ngày)" so={data.traffic.pageviews_7d} />
                    <OSo nhan="Lượt truy cập (30 ngày)" so={data.traffic.visits_30d} />
                    <OSo nhan="Lượt xem trang (30 ngày)" so={data.traffic.pageviews_30d} />
                  </div>
                  {data.traffic.message ? (
                    <p className="hint">{data.traffic.message}</p>
                  ) : null}
                  {data.traffic.top_paths && data.traffic.top_paths.length > 0 ? (
                    <div className="admin-bang-boc">
                      <table className="admin-bang">
                        <thead>
                          <tr><th scope="col">Đường dẫn</th><th scope="col">Lượt xem</th></tr>
                        </thead>
                        <tbody>
                          {data.traffic.top_paths.map((p) => (
                            <tr key={p.path}>
                              <td>{p.path}</td>
                              <td>{p.count.toLocaleString("vi-VN")}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : null}
                </>
              ) : (
                <ChuaCauHinh
                  tieuDe="Traffic analytics not configured"
                  ghiChu={data.traffic.message || "Chưa có credential Cloudflare Analytics."}
                />
              )}
            </div>
          </div>
        ) : null}
      </DanhSachTrangThai>
    </section>
  );
}
