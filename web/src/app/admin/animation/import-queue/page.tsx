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

/** Auto-Ingestion Phase 4 — nhan de hieu cho `discovered_via` (xem cung ten
    o trang chi tiet nguon). */
const NHAN_TRIGGER: Record<string, string> = {
  manual_scan: "quét thủ công",
  reconcile: "đối chiếu định kỳ",
  websub: "WebSub (tự động)",
  auto_discovery: "khám phá series",
  "": "không rõ (trước Phase 4)",
};

/** Auto-Ingestion Phase 4 (Stage E, "explainability") — trang thai
    AUTO_IMPORTED/AUTO_PUBLISHED la HE THONG tu quyet dinh, `reviewed_by`
    rong; moi trang thai khac neu co `reviewed_by` la QUAN TRI da bam nut. */
function nguonQuyetDinh(im: AdminVideoImportRow): string {
  if (im.status === "auto_imported" || im.status === "auto_published") return "Tự động";
  if (im.reviewed_by) return "Quản trị";
  return "—";
}

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

  /*
   * Nhap hang loat (bulk import) — chon nhieu dong, xem truoc, roi nhap
   * cung luc. CHI cho chon video DA co du series+tap (dac ta: "distinguish
   * videos that cannot yet be imported because a series mapping is
   * missing") — video thieu du lieu se bi loai khoi tap chon TU DONG (xem
   * `theoDoiChon`), khong chi disable nut ma con don sach lua chon khi
   * trang tai lai (vd sau khi gan series cho mot video khac).
   */
  const [daChon, setDaChon] = useState<ReadonlySet<string>>(new Set());
  const [hoiNhapHangLoat, setHoiNhapHangLoat] = useState<boolean | null>(null); // null=dong, true/false = gia tri `publish` dinh dung
  const [dangNhapHangLoat, setDangNhapHangLoat] = useState(false);

  const coTheChon = useCallback(
    (im: AdminVideoImportRow) => Boolean(im.detected_series_id) && im.detected_episode_number !== null,
    [],
  );

  /*
   * Don sach lua chon khi doi trang/loc — ID cu co the khong con trong
   * trang moi, giu lai se hien "da chon N" sai voi thu that thay. Dieu
   * chinh state NGAY TRONG THAN component (khong dung `useEffect`) — cung
   * mau voi `sources/[id]/page.tsx` da sua truoc do cho dung loi lint
   * `react-hooks/set-state-in-effect` (goi setState dong bo trong effect
   * gay render dom domino khong can thiet).
   */
  const khoaLoc = `${tt}|${nguonLoc}|${trangThai}`;
  const [khoaLocDaThay, setKhoaLocDaThay] = useState(khoaLoc);
  if (khoaLoc !== khoaLocDaThay) {
    setKhoaLocDaThay(khoaLoc);
    setDaChon(new Set());
  }

  function chuyenChon(importId: string) {
    setDaChon((truoc) => {
      const moi = new Set(truoc);
      if (moi.has(importId)) moi.delete(importId); else moi.add(importId);
      return moi;
    });
  }

  const dsCoTheChonTrongTrang = ds.filter(coTheChon);
  const daChonHet = dsCoTheChonTrongTrang.length > 0
    && dsCoTheChonTrongTrang.every((im) => daChon.has(im.import_id));

  function chonTatCaTrongTrang() {
    setDaChon((truoc) => {
      if (daChonHet) return new Set();
      const moi = new Set(truoc);
      for (const im of dsCoTheChonTrongTrang) moi.add(im.import_id);
      return moi;
    });
  }

  const dsDaChon = ds.filter((im) => daChon.has(im.import_id));

  async function nhapHangLoat(publish: boolean) {
    if (dsDaChon.length === 0) return;
    setDangNhapHangLoat(true);
    try {
      const { results } = await adminApi.bulkImportVideos(
        dsDaChon.map((im) => ({ importId: im.import_id, publish })));
      const thanhCong = results.filter((r) => r.ok).length;
      const thatBai = results.length - thanhCong;
      if (thatBai === 0) {
        toast.ok(`Đã nhập ${thanhCong} video.`);
      } else {
        toast.error(`Nhập ${thanhCong}/${results.length} video — ${thatBai} video lỗi (xem trạng thái từng dòng).`);
      }
      setDaChon(new Set());
      setHoiNhapHangLoat(null);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không nhập được lô video này."));
    } finally {
      setDangNhapHangLoat(false);
    }
  }

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

      {daChon.size > 0 ? (
        <div className="row row-spread admin-bulk-bar">
          <span className="hint">Đã chọn {daChon.size} video</span>
          <div className="row row-tight">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setDaChon(new Set())}>
              Bỏ chọn
            </button>
            <button type="button" className="btn btn-sm"
                    onClick={() => setHoiNhapHangLoat(false)}>
              Nhập đã chọn
            </button>
            <button type="button" className="btn btn-sm btn-primary"
                    onClick={() => setHoiNhapHangLoat(true)}>
              Nhập + Xuất bản đã chọn
            </button>
          </div>
        </div>
      ) : null}

      <DanhSachTrangThai dangTai={loading} loi={error} rong={ds.length === 0} onThuLai={reload}>
        <div className="admin-bang-boc">
          <table className="admin-bang">
            <thead>
              <tr>
                <th scope="col">
                  <input
                    type="checkbox"
                    aria-label="Chọn tất cả video có thể nhập trong trang này"
                    checked={daChonHet}
                    disabled={dsCoTheChonTrongTrang.length === 0}
                    onChange={chonTatCaTrongTrang}
                  />
                </th>
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
                    <input
                      type="checkbox"
                      aria-label={`Chọn "${im.title}" để nhập hàng loạt`}
                      checked={daChon.has(im.import_id)}
                      disabled={!coTheChon(im)}
                      title={coTheChon(im) ? "" : "Chưa gán series/tập — không thể nhập hàng loạt"}
                      onChange={() => chuyenChon(im.import_id)}
                    />
                  </td>
                  <td>
                    <a href={`https://www.youtube.com/watch?v=${im.youtube_video_id}`}
                       target="_blank" rel="noreferrer">
                      {im.title}
                    </a>
                    <div className="hint">
                      {im.channel_title}
                      {im.source_display_name ? ` · ${im.source_display_name}` : ""}
                      {" · "}{NHAN_TRIGGER[im.discovered_via] ?? im.discovered_via}
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
                    <div className="hint">Quyết định: {nguonQuyetDinh(im)}</div>
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

      {/*
        Xem truoc TRUOC KHI nhap hang loat — dac ta cam ro "bulk import
        should NOT be a mysterious one-click action with no preview". Liet
        ke DUNG nhung video se bi tac dong, kem series/tap da gan cho tung
        video, de quan tri xac nhan dung y truoc khi ghi thay doi thuc.
      */}
      <ConfirmDialog
        open={hoiNhapHangLoat !== null}
        title={hoiNhapHangLoat
          ? `Nhập + xuất bản ${dsDaChon.length} video?`
          : `Nhập ${dsDaChon.length} video (bản nháp)?`}
        body={
          <div className="stack-2">
            <p className="hint">
              {hoiNhapHangLoat
                ? "Các tập sẽ hiện công khai ngay sau khi nhập."
                : "Các tập sẽ ở dạng bản nháp, chưa hiện công khai."}
              {" "}Video đã tồn tại hoặc trùng số tập sẽ tự báo lỗi riêng, không ảnh hưởng video khác trong lô.
            </p>
            <ul className="admin-bulk-xem-truoc">
              {dsDaChon.map((im) => (
                <li key={im.import_id}>
                  <strong>{im.title}</strong>
                  <span className="hint"> — {im.series_title || "?"} · Tập {im.detected_episode_number}</span>
                </li>
              ))}
            </ul>
          </div>
        }
        confirmLabel={hoiNhapHangLoat ? "Nhập + Xuất bản" : "Nhập"}
        busy={dangNhapHangLoat}
        onConfirm={() => nhapHangLoat(Boolean(hoiNhapHangLoat))}
        onCancel={() => setHoiNhapHangLoat(null)}
      />
    </section>
  );
}
