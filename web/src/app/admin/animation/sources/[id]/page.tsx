"use client";

/**
 * Chi tiet MOT Trusted Video Source (Phase 5, Admin Control Center V2).
 *
 * Bon khoi: cai dat nguon (bat/tat, cac co tu dong, nguong tin cay), anh xa
 * series (them/sua/xoa `SeriesMapping`), "Quet video co san" (goi
 * `TrustedSourceService.scan_source`, hien ket qua dem duoc — KHONG tu
 * dong xuat ban toan bo kenh), va danh sach nhap gan day (chi xem, day du
 * o `/admin/animation/import-queue?source=...`).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useState } from "react";
import {
  adminApi,
  type AdminSeriesMappingRow,
  type AdminAnimationSeriesRow,
  type SubscriptionStatus,
  type TrustedSourceScanResult,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { ChuaCauHinh, DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { ConfirmDialog } from "@/components/ui";
import { IconLink } from "@/components/Icons";

const TEN_LOAI: Record<string, string> = {
  youtube_channel: "Kênh YouTube",
  youtube_playlist: "Playlist YouTube",
  youtube_video: "Video đơn lẻ",
};

const NHAN_DANG_KY: Record<SubscriptionStatus, { chu: string; lop: string }> = {
  none: { chu: "Chưa đăng ký", lop: "tt-trong" },
  pending: { chu: "Đang chờ xác minh", lop: "tt-cho" },
  active: { chu: "Đang hoạt động", lop: "tt-duyet" },
  expired: { chu: "Đã hết hạn", lop: "tt-treo" },
  failed: { chu: "Lỗi", lop: "tt-tuchoi" },
};

export default function AdminTrustedSourceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: sourceId } = use(params);
  const toast = useToast();
  const router = useRouter();

  const nap = useCallback(() => adminApi.trustedSourceDetail(sourceId), [sourceId]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const s = data?.source;

  const [tenHienThi, setTenHienThi] = useState("");
  const [autoDiscover, setAutoDiscover] = useState(false);
  const [autoImport, setAutoImport] = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);
  const [nguong, setNguong] = useState(90);
  const [dangLuu, setDangLuu] = useState(false);

  // Dieu chinh form theo `s` MOI NAP — dung mau "dieu chinh trang thai luc
  // render" cua React (khong phai `useEffect`, tranh canh bao
  // react-hooks/set-state-in-effect va khong render thua mot nhip).
  const [sourceIdDaNap, setSourceIdDaNap] = useState<string | null>(null);
  if (s && s.source_id !== sourceIdDaNap) {
    setSourceIdDaNap(s.source_id);
    setTenHienThi(s.display_name);
    setAutoDiscover(s.auto_discover);
    setAutoImport(s.auto_import);
    setAutoPublish(s.auto_publish);
    setNguong(Math.round(s.minimum_confidence * 100));
  }

  const [dangQuet, setDangQuet] = useState(false);
  const [ketQuaQuet, setKetQuaQuet] = useState<TrustedSourceScanResult | null>(null);
  const [hoiXoaNguon, setHoiXoaNguon] = useState(false);
  const [dangXoa, setDangXoa] = useState(false);

  const [dangDangKy, setDangDangKy] = useState(false);
  const [dangDoiChieu, setDangDoiChieu] = useState(false);
  const [ketQuaDoiChieu, setKetQuaDoiChieu] = useState<
    { sources_checked: number; sources_failed: number; videos_detected: number } | null
  >(null);

  const [danhSachSeries, setDanhSachSeries] = useState<AdminAnimationSeriesRow[]>([]);
  useEffect(() => {
    adminApi.animationSeries({ limit: 100 }).then(
      (r) => setDanhSachSeries(r.series),
      () => setDanhSachSeries([]),
    );
  }, []);

  async function luuCaiDat() {
    setDangLuu(true);
    try {
      await adminApi.updateTrustedSource(sourceId, {
        display_name: tenHienThi.trim(), auto_discover: autoDiscover,
        auto_import: autoImport, auto_publish: autoPublish,
        minimum_confidence: nguong / 100,
      });
      toast.ok("Đã lưu cài đặt.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không lưu được cài đặt."));
    } finally {
      setDangLuu(false);
    }
  }

  async function datBatTat(enabled: boolean) {
    try {
      await adminApi.setTrustedSourceEnabled(sourceId, enabled);
      toast.ok(enabled ? "Đã bật nguồn." : "Đã tắt nguồn.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không đổi được trạng thái."));
    }
  }

  async function xoaNguon() {
    setDangXoa(true);
    try {
      await adminApi.removeTrustedSource(sourceId);
      toast.ok("Đã bỏ tin cậy nguồn này.");
      router.push("/admin/animation/sources");
    } catch (cause) {
      toast.error(loiApi(cause, "Không xoá được."));
      setDangXoa(false);
    }
  }

  async function quet() {
    setDangQuet(true);
    setKetQuaQuet(null);
    try {
      const ket_qua = await adminApi.scanTrustedSource(sourceId, { maxPages: 2 });
      setKetQuaQuet(ket_qua);
      toast.ok(`Đã quét: ${ket_qua.detected} video phát hiện.`);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Quét thất bại."));
    } finally {
      setDangQuet(false);
    }
  }

  async function dangKy() {
    setDangDangKy(true);
    try {
      await adminApi.subscribeTrustedSource(sourceId);
      toast.ok("Đã gửi yêu cầu đăng ký WebSub — chờ YouTube xác minh.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không đăng ký được."));
    } finally {
      setDangDangKy(false);
    }
  }

  async function chayDoiChieu() {
    setDangDoiChieu(true);
    setKetQuaDoiChieu(null);
    try {
      const ket_qua = await adminApi.runReconciliation(sourceId);
      setKetQuaDoiChieu(ket_qua);
      toast.ok(`Đã đối chiếu: ${ket_qua.videos_detected} video phát hiện.`);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Đối chiếu thất bại."));
    } finally {
      setDangDoiChieu(false);
    }
  }

  return (
    <section className="stack">
      <p className="hint">
        <Link href="/admin/animation/sources">← Trusted Video Sources</Link>
      </p>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!s} onThuLai={reload}>
        {data && s ? (
          <div className="stack">
            <header className="row row-spread">
              <span className="stack-2">
                <h2 className="section-title section-title-icon">
                  <IconLink size={19} /> {s.display_name || "(chưa đặt tên)"}
                </h2>
                <span className="hint">
                  {TEN_LOAI[s.source_type] ?? s.source_type}
                  {s.youtube_channel_id ? ` · ${s.youtube_channel_id}` : ""}
                  {s.youtube_playlist_id ? ` · ${s.youtube_playlist_id}` : ""}
                  {s.youtube_video_id ? ` · ${s.youtube_video_id}` : ""}
                </span>
              </span>
              <span className={`tt ${s.enabled ? "tt-duyet" : "tt-trong"}`}>
                {s.enabled ? "Đang bật" : "Đã tạm dừng"}
              </span>
            </header>

            {s.last_error_message && s.last_error_at > s.last_success_at ? (
              <div className="card stack-2" role="alert">
                <strong>Lần quét gần nhất lỗi.</strong>
                <p className="hint">{s.last_error_message}</p>
              </div>
            ) : null}

            <div className="card stack-2">
              <h3 className="section-title">Cài đặt</h3>
              <label className="stack-2">
                <span>Tên hiển thị</span>
                <input className="input" type="text" value={tenHienThi}
                       onChange={(e) => setTenHienThi(e.target.value)} maxLength={200} />
              </label>
              <div className="stack-2">
                <label className="row row-tight">
                  <input type="checkbox" checked={autoDiscover}
                         onChange={(e) => setAutoDiscover(e.target.checked)} />
                  <span>Auto Discover (Phase 6/WebSub)</span>
                </label>
                <label className="row row-tight">
                  <input type="checkbox" checked={autoImport}
                         onChange={(e) => setAutoImport(e.target.checked)} />
                  <span>Auto Import</span>
                </label>
                <label className="row row-tight">
                  <input type="checkbox" checked={autoPublish}
                         onChange={(e) => setAutoPublish(e.target.checked)} />
                  <span>Auto Publish</span>
                </label>
              </div>
              <label className="stack-2">
                <span>Ngưỡng độ tin cậy tối thiểu: {nguong}%</span>
                <input type="range" min={0} max={100} step={5} value={nguong}
                       onChange={(e) => setNguong(Number(e.target.value))}
                       aria-label="Ngưỡng độ tin cậy" />
              </label>
              <div className="row row-spread">
                <div className="row">
                  <button type="button" className="btn btn-primary" disabled={dangLuu}
                          onClick={luuCaiDat}>
                    {dangLuu ? "Đang lưu…" : "Lưu cài đặt"}
                  </button>
                  <button type="button" className="btn btn-sm"
                          onClick={() => datBatTat(!s.enabled)}>
                    {s.enabled ? "Tạm dừng nguồn" : "Tiếp tục nguồn"}
                  </button>
                </div>
                <button type="button" className="btn btn-sm btn-danger"
                        onClick={() => setHoiXoaNguon(true)}>
                  Bỏ tin cậy
                </button>
              </div>
            </div>

            <div className="card stack-2">
              <h3 className="section-title">Đồng bộ tự động (WebSub)</h3>
              {!data.websub_configured ? (
                <ChuaCauHinh
                  tieuDe="Chưa cấu hình"
                  ghiChu="Cần một backend công khai qua HTTPS (YOUTUBE_WEBSUB_CALLBACK_BASE_URL) để YouTube gọi callback được — chưa khả dụng trên môi trường phát triển cục bộ."
                />
              ) : (
                <>
                  <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                    <span className={`tt ${NHAN_DANG_KY[s.subscription_status].lop}`}>
                      {NHAN_DANG_KY[s.subscription_status].chu}
                    </span>
                  </div>
                  <div className="stat-grid admin-luoi">
                    <div className="stat">
                      <span className="stat-value">
                        {s.last_notification_at
                          ? new Date(s.last_notification_at).toLocaleString("vi-VN")
                          : "—"}
                      </span>
                      <span className="stat-label">Thông báo gần nhất</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">
                        {s.last_successful_sync_at
                          ? new Date(s.last_successful_sync_at).toLocaleString("vi-VN")
                          : "—"}
                      </span>
                      <span className="stat-label">Đối chiếu thành công gần nhất</span>
                    </div>
                    <div className="stat">
                      <span className="stat-value">
                        {s.subscription_expires_at
                          ? new Date(s.subscription_expires_at).toLocaleString("vi-VN")
                          : "—"}
                      </span>
                      <span className="stat-label">Hạn đăng ký</span>
                    </div>
                  </div>
                  {s.last_websub_error ? (
                    <p className="hint" role="alert">Lỗi gần nhất: {s.last_websub_error}</p>
                  ) : null}
                  <div className="row">
                    <button type="button" className="btn btn-sm" disabled={dangDangKy}
                            onClick={dangKy}>
                      {dangDangKy ? "Đang đăng ký…"
                        : s.subscription_status === "none" ? "Đăng ký"
                        : "Đăng ký lại"}
                    </button>
                    <button type="button" className="btn btn-sm" disabled={dangDoiChieu}
                            onClick={chayDoiChieu}>
                      {dangDoiChieu ? "Đang đối chiếu…" : "Chạy đối chiếu ngay"}
                    </button>
                  </div>
                  {ketQuaDoiChieu ? (
                    <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                      <span className="tt tt-trong">
                        Nguồn đã kiểm: {ketQuaDoiChieu.sources_checked}
                      </span>
                      <span className="tt tt-trong">
                        Video phát hiện: {ketQuaDoiChieu.videos_detected}
                      </span>
                      {ketQuaDoiChieu.sources_failed > 0 ? (
                        <span className="tt tt-tuchoi">
                          Lỗi: {ketQuaDoiChieu.sources_failed}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div className="card stack-2">
              <h3 className="section-title">Quét video có sẵn</h3>
              <p className="hint">
                Ưu tiên playlist đã chọn/ánh xạ, nếu không thì playlist tải
                lên của kênh. Kết quả KHÔNG tự xuất bản toàn bộ kênh — chỉ
                video đủ điều kiện Auto Import/Publish mới được tạo tập
                ngay, phần còn lại vào hàng đợi để duyệt tay.
              </p>
              <div className="row">
                <button type="button" className="btn btn-primary" disabled={dangQuet}
                        onClick={quet}>
                  {dangQuet ? "Đang quét…" : "Quét video có sẵn"}
                </button>
              </div>
              {ketQuaQuet ? (
                <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                  <span className="tt tt-trong">Phát hiện: {ketQuaQuet.detected}</span>
                  <span className="tt tt-trong">Khớp series: {ketQuaQuet.matched}</span>
                  <span className="tt tt-cho">Chờ duyệt: {ketQuaQuet.pending}</span>
                  <span className="tt tt-duyet">Tự nhập: {ketQuaQuet.auto_imported}</span>
                  <span className="tt tt-duyet">Tự xuất bản: {ketQuaQuet.auto_published}</span>
                  <span className="tt tt-trong">Loại trừ: {ketQuaQuet.excluded}</span>
                  <span className="tt tt-treo">Trùng: {ketQuaQuet.duplicates}</span>
                  <span className="tt tt-treo">Xung đột: {ketQuaQuet.conflicts}</span>
                  <span className="tt tt-trong">Đã theo dõi: {ketQuaQuet.already_tracked}</span>
                </div>
              ) : null}
              <p className="hint">
                <Link href={`/admin/animation/import-queue?source=${sourceId}`}>
                  Xem hàng đợi nhập của nguồn này →
                </Link>
              </p>
            </div>

            <MangAnhXa sourceId={sourceId} mappings={data.mappings}
                       danhSachSeries={danhSachSeries} onDoi={reload} />

            {data.recent_imports.length > 0 ? (
              <div className="stack-2">
                <h3 className="section-title">Video phát hiện gần đây</h3>
                <div className="admin-bang-boc">
                  <table className="admin-bang">
                    <thead>
                      <tr>
                        <th scope="col">Tiêu đề</th>
                        <th scope="col">Tập</th>
                        <th scope="col">Độ tin cậy</th>
                        <th scope="col">Trạng thái</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_imports.map((im) => (
                        <tr key={im.import_id}>
                          <td>
                            <a href={`https://www.youtube.com/watch?v=${im.youtube_video_id}`}
                               target="_blank" rel="noreferrer">
                              {im.title}
                            </a>
                          </td>
                          <td className="mono">{im.detected_episode_number ?? "—"}</td>
                          <td className="mono">{Math.round(im.confidence * 100)}%</td>
                          <td>{im.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </DanhSachTrangThai>

      <ConfirmDialog
        open={hoiXoaNguon}
        title={`Bỏ tin cậy "${s?.display_name}"?`}
        body="Ánh xạ series của nguồn này sẽ bị xoá theo. Các tập ĐÃ NHẬP trước đó không bị xoá."
        confirmLabel="Bỏ tin cậy"
        danger
        busy={dangXoa}
        onConfirm={xoaNguon}
        onCancel={() => setHoiXoaNguon(false)}
      />
    </section>
  );
}

/** Khoi anh xa series — them/sua/xoa, tach rieng de gon than component chinh. */
function MangAnhXa({
  sourceId,
  mappings,
  danhSachSeries,
  onDoi,
}: {
  sourceId: string;
  mappings: AdminSeriesMappingRow[];
  danhSachSeries: AdminAnimationSeriesRow[];
  onDoi: () => void;
}) {
  const toast = useToast();
  const [dangMo, setDangMo] = useState(false);
  const [seriesId, setSeriesId] = useState("");
  const [aliases, setAliases] = useState("");
  const [tuKhoaBaoGom, setTuKhoaBaoGom] = useState("");
  const [tuKhoaLoaiTru, setTuKhoaLoaiTru] = useState("");
  const [dangGui, setDangGui] = useState(false);
  const [hoiXoa, setHoiXoa] = useState<AdminSeriesMappingRow | null>(null);

  function tachDay(v: string): string[] {
    return v.split(",").map((x) => x.trim()).filter(Boolean);
  }

  async function them() {
    if (!seriesId) return;
    setDangGui(true);
    try {
      await adminApi.createSeriesMapping(sourceId, {
        animation_series_id: seriesId, aliases: tachDay(aliases),
        include_keywords: tachDay(tuKhoaBaoGom), exclude_keywords: tachDay(tuKhoaLoaiTru),
      });
      toast.ok("Đã thêm ánh xạ series.");
      setDangMo(false);
      setSeriesId(""); setAliases(""); setTuKhoaBaoGom(""); setTuKhoaLoaiTru("");
      onDoi();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thêm được ánh xạ."));
    } finally {
      setDangGui(false);
    }
  }

  async function xoa() {
    if (!hoiXoa) return;
    setDangGui(true);
    try {
      await adminApi.removeSeriesMapping(hoiXoa.mapping_id);
      toast.ok("Đã xoá ánh xạ.");
      setHoiXoa(null);
      onDoi();
    } catch (cause) {
      toast.error(loiApi(cause, "Không xoá được."));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <div className="card stack-2">
      <div className="row row-spread">
        <h3 className="section-title">Ánh xạ series ({mappings.length})</h3>
        <button type="button" className="btn btn-sm" onClick={() => setDangMo((v) => !v)}>
          {dangMo ? "Đóng" : "+ Thêm ánh xạ"}
        </button>
      </div>

      {dangMo ? (
        <div className="stack-2">
          <label className="stack-2">
            <span>Series animation</span>
            <select className="input" value={seriesId}
                    onChange={(e) => setSeriesId(e.target.value)}>
              <option value="">— Chọn series —</option>
              {danhSachSeries.map((sr) => (
                <option key={sr.series_id} value={sr.series_id}>{sr.title}</option>
              ))}
            </select>
          </label>
          <label className="stack-2">
            <span>Tên khác (aliases, cách nhau bằng dấu phẩy)</span>
            <input className="input" type="text" value={aliases}
                   onChange={(e) => setAliases(e.target.value)}
                   placeholder="tiên nghịch, renegade immortal" />
          </label>
          <label className="stack-2">
            <span>Từ khoá mong đợi</span>
            <input className="input" type="text" value={tuKhoaBaoGom}
                   onChange={(e) => setTuKhoaBaoGom(e.target.value)} />
          </label>
          <label className="stack-2">
            <span>Từ khoá loại trừ riêng (ngoài trailer/teaser/OST mặc định)</span>
            <input className="input" type="text" value={tuKhoaLoaiTru}
                   onChange={(e) => setTuKhoaLoaiTru(e.target.value)} />
          </label>
          <div className="row">
            <button type="button" className="btn btn-primary" disabled={dangGui || !seriesId}
                    onClick={them}>
              Thêm ánh xạ
            </button>
          </div>
        </div>
      ) : null}

      {mappings.length > 0 ? (
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Series</th>
                <th scope="col">Alias</th>
                <th scope="col">Tự động</th>
                <th scope="col"><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((m) => (
                <tr key={m.mapping_id}>
                  <td>{m.series_title || m.animation_series_id}</td>
                  <td className="hint">{m.aliases.join(", ") || "—"}</td>
                  <td className="hint mono">
                    {m.auto_import === null ? "kế thừa" : m.auto_import ? "import" : "—"}
                    {" / "}
                    {m.auto_publish === null ? "kế thừa" : m.auto_publish ? "publish" : "—"}
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm btn-danger"
                            onClick={() => setHoiXoa(m)}>
                      Xoá
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">Nguồn này chưa ánh xạ tới series nào.</p>
      )}

      <ConfirmDialog
        open={Boolean(hoiXoa)}
        title={`Xoá ánh xạ tới "${hoiXoa?.series_title}"?`}
        body="Video đã nhập trước đó không bị ảnh hưởng — chỉ dừng phân loại tự động cho series này."
        confirmLabel="Xoá ánh xạ"
        danger
        busy={dangGui}
        onConfirm={xoa}
        onCancel={() => setHoiXoa(null)}
      />
    </div>
  );
}
