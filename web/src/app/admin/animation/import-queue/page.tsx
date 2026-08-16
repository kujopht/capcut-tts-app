"use client";

/**
 * Hang doi nhap video (Phase 5, Admin Control Center V2 / Trusted Video Sources).
 *
 * Moi video YouTube phat hien duoc (tu quet thu cong o trang chi tiet nguon)
 * dung o day cho toi khi thanh mot `AnimationEpisode` that (Nhap/Nhap+Xuat
 * ban), bi tu choi, hoac bi bo qua. KHONG bao gio ghi de am tham mot tap da
 * co — server tu kiem lai trung lap/xung dot ngay luc bam nut, xem
 * `TrustedSourceService.import_video`.
 */

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  adminApi,
  type AdminAnimationSeriesRow,
  type AdminVideoImportRow,
  type VideoImportStatus,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { ConfirmDialog } from "@/components/ui";
import { IconInbox } from "@/components/Icons";

const TRANG_THAI: ReadonlyArray<{ khoa: "" | VideoImportStatus; nhan: string }> = [
  { khoa: "", nhan: "Tất cả" },
  { khoa: "new", nhan: "Mới" },
  { khoa: "pending", nhan: "Chờ duyệt" },
  { khoa: "conflict", nhan: "Xung đột" },
  { khoa: "duplicate", nhan: "Trùng" },
  { khoa: "auto_imported", nhan: "Tự nhập" },
  { khoa: "auto_published", nhan: "Tự xuất bản" },
  { khoa: "imported", nhan: "Đã nhập" },
  { khoa: "rejected", nhan: "Đã từ chối" },
  { khoa: "ignored", nhan: "Đã bỏ qua" },
];

const LOP_TRANG_THAI: Record<string, string> = {
  new: "tt-trong", pending: "tt-cho", auto_imported: "tt-duyet",
  auto_published: "tt-duyet", imported: "tt-duyet", rejected: "tt-tuchoi",
  ignored: "tt-trong", duplicate: "tt-treo", conflict: "tt-treo",
  unavailable: "tt-tuchoi", failed: "tt-tuchoi",
};

const TRANG = 25;

export default function AdminImportQueuePage() {
  return (
    <Suspense fallback={<DanhSachTrangThai dangTai loi="" rong={false}>{null}</DanhSachTrangThai>}>
      <ImportQueue />
    </Suspense>
  );
}

function ImportQueue() {
  const params = useSearchParams();
  const nguonLoc = params.get("source") ?? "";
  const toast = useToast();

  const [tt, setTt] = useState<"" | VideoImportStatus>("");
  const [trangThai, setTrangThai] = useState(0);

  const nap = useCallback(
    () => adminApi.videoImports({
      status: tt, trustedSourceId: nguonLoc, limit: TRANG, offset: trangThai * TRANG,
    }),
    [tt, nguonLoc, trangThai],
  );
  const { data, loading, error, reload } = useAsyncData(nap);
  const ds = data?.imports ?? [];
  const tong = data?.total ?? 0;

  const [danhSachSeries, setDanhSachSeries] = useState<AdminAnimationSeriesRow[]>([]);
  useEffect(() => {
    adminApi.animationSeries({ limit: 100 }).then(
      (r) => setDanhSachSeries(r.series), () => setDanhSachSeries([]));
  }, []);

  const [dangGan, setDangGan] = useState<string | null>(null);
  const [ganSeriesId, setGanSeriesId] = useState("");
  const [ganTap, setGanTap] = useState("");
  const [dangXuLy, setDangXuLy] = useState<string | null>(null);
  const [hoiTuChoi, setHoiTuChoi] = useState<AdminVideoImportRow | null>(null);
  const [lyDo, setLyDo] = useState("");

  function moGan(im: AdminVideoImportRow) {
    setDangGan(im.import_id);
    setGanSeriesId(im.detected_series_id);
    setGanTap(im.detected_episode_number !== null ? String(im.detected_episode_number) : "");
  }

  async function luuGan(im: AdminVideoImportRow) {
    setDangXuLy(im.import_id);
    try {
      await adminApi.setImportSeries(
        im.import_id, ganSeriesId, ganTap.trim() ? Number(ganTap) : null);
      toast.ok("Đã gán series/tập.");
      setDangGan(null);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không gán được."));
    } finally {
      setDangXuLy(null);
    }
  }

  async function nhap(im: AdminVideoImportRow, publish: boolean) {
    setDangXuLy(im.import_id);
    try {
      const { import: updated } = await adminApi.importVideo(im.import_id, publish);
      if (updated.status === "duplicate" || updated.status === "conflict") {
        toast.error(updated.reason || "Không nhập được — trùng lặp hoặc xung đột.");
      } else {
        toast.ok(publish ? "Đã nhập và xuất bản." : "Đã nhập (bản nháp).");
      }
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không nhập được video này."));
    } finally {
      setDangXuLy(null);
    }
  }

  async function tuChoi() {
    if (!hoiTuChoi) return;
    setDangXuLy(hoiTuChoi.import_id);
    try {
      await adminApi.rejectVideoImport(hoiTuChoi.import_id, lyDo.trim());
      toast.ok("Đã từ chối.");
      setHoiTuChoi(null);
      setLyDo("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không từ chối được."));
    } finally {
      setDangXuLy(null);
    }
  }

  async function boQua(im: AdminVideoImportRow) {
    setDangXuLy(im.import_id);
    try {
      await adminApi.ignoreVideoImport(im.import_id);
      toast.ok("Đã bỏ qua.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không bỏ qua được."));
    } finally {
      setDangXuLy(null);
    }
  }

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconInbox size={19} /> Hàng đợi nhập video
      </h2>
      <p className="hint">
        <Link href="/admin/animation">← Animation</Link>
        {nguonLoc ? (
          <>
            {" · lọc theo nguồn "}
            <Link href={`/admin/animation/sources/${nguonLoc}`}>{nguonLoc}</Link>
            {" · "}
            <Link href="/admin/animation/import-queue">Bỏ lọc</Link>
          </>
        ) : null}
      </p>

      <div className="seg" role="group" aria-label="Lọc theo trạng thái" style={{ flexWrap: "wrap" }}>
        {TRANG_THAI.map((t) => (
          <button key={t.khoa || "all"} type="button" className="seg-item"
                  aria-pressed={tt === t.khoa}
                  onClick={() => { setTt(t.khoa); setTrangThai(0); }}>
            {t.nhan}
          </button>
        ))}
      </div>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={ds.length === 0} onThuLai={reload}>
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">Video</th>
                <th scope="col">Series / Tập phát hiện</th>
                <th scope="col">Độ tin cậy</th>
                <th scope="col">Xuất bản trên YouTube</th>
                <th scope="col">Trạng thái</th>
                <th scope="col"><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {ds.map((im: AdminVideoImportRow) => (
                <tr key={im.import_id}>
                  <td>
                    <a href={`https://www.youtube.com/watch?v=${im.youtube_video_id}`}
                       target="_blank" rel="noreferrer">
                      {im.title}
                    </a>
                    <div className="hint">
                      {im.channel_title}
                      {im.source_display_name ? ` · ${im.source_display_name}` : ""}
                    </div>
                  </td>
                  <td>
                    {dangGan === im.import_id ? (
                      <div className="stack-2">
                        <select className="input" value={ganSeriesId}
                                onChange={(e) => setGanSeriesId(e.target.value)}>
                          <option value="">— Chọn series —</option>
                          {danhSachSeries.map((sr) => (
                            <option key={sr.series_id} value={sr.series_id}>{sr.title}</option>
                          ))}
                        </select>
                        <input className="input" type="number" min={1} value={ganTap}
                               onChange={(e) => setGanTap(e.target.value)}
                               placeholder="Số tập" style={{ maxWidth: 100 }} />
                        <div className="row">
                          <button type="button" className="btn btn-sm btn-primary"
                                  disabled={dangXuLy === im.import_id}
                                  onClick={() => luuGan(im)}>
                            Lưu
                          </button>
                          <button type="button" className="btn btn-sm btn-ghost"
                                  onClick={() => setDangGan(null)}>
                            Huỷ
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button type="button" className="btn btn-sm btn-ghost"
                              onClick={() => moGan(im)}>
                        {im.series_title || "(chưa gán series)"}
                        {" · Tập "}{im.detected_episode_number ?? "?"}
                      </button>
                    )}
                    {im.signals.length > 0 ? (
                      <div className="hint">{im.signals.join("; ")}</div>
                    ) : null}
                  </td>
                  <td className="mono">{Math.round(im.confidence * 100)}%</td>
                  <td className="hint">
                    {im.published_at ? new Date(im.published_at).toLocaleDateString("vi-VN") : "—"}
                  </td>
                  <td>
                    <span className={`tt ${LOP_TRANG_THAI[im.status] ?? "tt-trong"}`}>
                      {im.status}
                    </span>
                    {im.reason ? <div className="hint">{im.reason}</div> : null}
                  </td>
                  <td>
                    <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                      <button type="button" className="btn btn-sm"
                              disabled={dangXuLy === im.import_id}
                              onClick={() => nhap(im, false)}>
                        Nhập
                      </button>
                      <button type="button" className="btn btn-sm btn-primary"
                              disabled={dangXuLy === im.import_id}
                              onClick={() => nhap(im, true)}>
                        Nhập + Xuất bản
                      </button>
                      <button type="button" className="btn btn-sm btn-danger"
                              disabled={dangXuLy === im.import_id}
                              onClick={() => { setHoiTuChoi(im); setLyDo(""); }}>
                        Từ chối
                      </button>
                      <button type="button" className="btn btn-sm btn-ghost"
                              disabled={dangXuLy === im.import_id}
                              onClick={() => boQua(im)}>
                        Bỏ qua
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="row row-spread">
          <button type="button" className="btn btn-sm" disabled={trangThai === 0}
                  onClick={() => setTrangThai((v) => Math.max(0, v - 1))}>
            ← Trang trước
          </button>
          <span className="hint">Trang {trangThai + 1} · {tong} video</span>
          <button type="button" className="btn btn-sm"
                  disabled={(trangThai + 1) * TRANG >= tong}
                  onClick={() => setTrangThai((v) => v + 1)}>
            Trang sau →
          </button>
        </div>
      </DanhSachTrangThai>

      <ConfirmDialog
        open={Boolean(hoiTuChoi)}
        title={`Từ chối "${hoiTuChoi?.title}"?`}
        body={
          <textarea
            className="textarea textarea-sm"
            placeholder="Lý do từ chối (không bắt buộc, ghi vào nhật ký kiểm duyệt)"
            value={lyDo}
            onChange={(e) => setLyDo(e.target.value)}
            maxLength={1000}
            rows={2}
          />
        }
        confirmLabel="Từ chối"
        danger
        busy={dangXuLy === hoiTuChoi?.import_id}
        onConfirm={tuChoi}
        onCancel={() => setHoiTuChoi(null)}
      />
    </section>
  );
}
