"use client";

/**
 * Chi tiet MOT series Animation cho khu quan tri (Phase 4, Admin Control
 * Center V2).
 *
 * HAI truc TACH BACH duoc ve o hai cho:
 *   - Xuat ban (`state`) — CUA CHU SO HUU, chi hien thi o day, KHONG sua
 *     duoc tu trang nay (quan tri khong "xuat ban ho" tac gia).
 *   - Kiem duyet (`moderation_state`) — CUA QUAN TRI, go/phuc hoi o day.
 *     Chu so huu KHONG hoan tac duoc lenh go bang cach xuat ban lai — xem
 *     `server/animation_domain.py::AnimationSeries.moderation_state`.
 *
 * Tap CO THE go RIENG TUNG CAI ma khong dong toi ca series — moi tap co nut
 * rieng.
 */

import Link from "next/link";
import { use, useCallback, useState } from "react";
import {
  adminApi,
  type AdminAnimationSeriesDetail,
  type AnimationEpisode,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { ConfirmDialog } from "@/components/ui";
import { IconFilm, IconHistory } from "@/components/Icons";

export default function AdminAnimationSeriesDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: seriesId } = use(params);
  const toast = useToast();

  const nap = useCallback(() => adminApi.animationSeriesDetail(seriesId), [seriesId]);
  const { data, loading, error, reload } = useAsyncData(nap);
  const s = data?.series;

  const [hoiGoSeries, setHoiGoSeries] = useState(false);
  const [hoiGoTap, setHoiGoTap] = useState<AnimationEpisode | null>(null);
  const [ghiChu, setGhiChu] = useState("");
  const [dangGui, setDangGui] = useState(false);

  async function goSeries() {
    if (!ghiChu.trim()) return;
    setDangGui(true);
    try {
      await adminApi.unpublishAnimationSeries(seriesId, ghiChu.trim());
      toast.ok("Đã gỡ series — không ai xem được nữa, kể cả chủ sở hữu.");
      setHoiGoSeries(false);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không gỡ được series."));
    } finally {
      setDangGui(false);
    }
  }

  async function phucHoiSeries() {
    setDangGui(true);
    try {
      await adminApi.restoreAnimationSeries(seriesId);
      toast.ok("Đã phục hồi series.");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không phục hồi được."));
    } finally {
      setDangGui(false);
    }
  }

  async function goTap() {
    if (!hoiGoTap || !ghiChu.trim()) return;
    setDangGui(true);
    try {
      await adminApi.unpublishAnimationEpisode(hoiGoTap.episode_id, ghiChu.trim());
      toast.ok(`Đã gỡ tập "${hoiGoTap.title}".`);
      setHoiGoTap(null);
      setGhiChu("");
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không gỡ được tập này."));
    } finally {
      setDangGui(false);
    }
  }

  async function phucHoiTap(tap: AnimationEpisode) {
    setDangGui(true);
    try {
      await adminApi.restoreAnimationEpisode(tap.episode_id);
      toast.ok(`Đã phục hồi tập "${tap.title}".`);
      reload();
    } catch (cause) {
      toast.error(loiApi(cause, "Không phục hồi được."));
    } finally {
      setDangGui(false);
    }
  }

  return (
    <section className="stack">
      <p className="hint">
        <Link href="/admin/animation/series">← Về danh sách series</Link>
      </p>

      <DanhSachTrangThai dangTai={loading} loi={error} rong={!s} onThuLai={reload}>
        {data && s ? (
          <div className="stack">
            <header className="row row-spread">
              <span className="stack-2">
                <h2 className="section-title section-title-icon">
                  <IconFilm size={19} /> {s.title}
                </h2>
                <span className="hint">
                  {data.owner?.username ? (
                    <Link href={`/u/${data.owner.username}`}>
                      @{data.owner.username}
                    </Link>
                  ) : data.owner ? (
                    `${data.owner.display_name} (chưa chọn tên công khai)`
                  ) : "(không rõ chủ sở hữu)"}
                  {data.related_novel ? (
                    <>
                      {" · dựa trên "}
                      <Link href={`/novels/${data.related_novel.novel_id}`}>
                        {data.related_novel.title}
                      </Link>
                    </>
                  ) : null}
                </span>
              </span>
              <span className="stack-2" style={{ alignItems: "flex-end" }}>
                <span className={`tt ${s.state === "published" ? "tt-duyet" : "tt-trong"}`}>
                  {s.state === "published" ? "Đã xuất bản (chủ sở hữu)" : "Bản nháp (chủ sở hữu)"}
                </span>
                <span className={`tt ${s.moderation_state === "removed" ? "tt-treo" : "tt-duyet"}`}>
                  {s.moderation_state === "removed" ? "Đã bị gỡ (kiểm duyệt)" : "Bình thường (kiểm duyệt)"}
                </span>
              </span>
            </header>

            {s.description ? <p className="lead">{s.description}</p> : null}

            {s.moderation_state === "removed" ? (
              <div className="card stack-2" role="status">
                <strong>Series này đã bị gỡ.</strong>
                <p className="hint">Lý do: {s.removed_reason || "(không ghi)"}</p>
                <div className="row">
                  <button type="button" className="btn btn-sm" disabled={dangGui}
                          onClick={phucHoiSeries}>
                    Phục hồi series
                  </button>
                </div>
              </div>
            ) : (
              <div className="row">
                <button type="button" className="btn btn-sm btn-danger" disabled={dangGui}
                        onClick={() => { setHoiGoSeries(true); setGhiChu(""); }}>
                  Gỡ series
                </button>
              </div>
            )}

            <div className="stack-2">
              <h3 className="section-title">Tập ({data.episodes.length})</h3>
              {data.episodes.length > 0 ? (
                <div className="admin-bang-boc">
                  <table className="admin-bang">
                    <thead>
                      <tr>
                        <th scope="col">#</th>
                        <th scope="col">Tập</th>
                        <th scope="col">Nguồn</th>
                        <th scope="col">Kiểm duyệt</th>
                        <th scope="col"><span className="sr-only">Thao tác</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.episodes.map((e) => (
                        <tr key={e.episode_id}>
                          <td className="mono">{e.order_index}</td>
                          <td>{e.title}</td>
                          <td>
                            {e.source === "youtube" ? (
                              <a href={`https://www.youtube.com/watch?v=${e.external_id}`}
                                 target="_blank" rel="noreferrer" className="hint mono">
                                youtube:{e.external_id}
                              </a>
                            ) : (
                              <span className="hint mono">{e.source}:{e.external_id}</span>
                            )}
                          </td>
                          <td>
                            <span className={`tt ${e.moderation_state === "removed" ? "tt-treo" : "tt-duyet"}`}>
                              {e.moderation_state === "removed" ? "Đã gỡ" : "Bình thường"}
                            </span>
                            {e.moderation_state === "removed" && e.removed_reason ? (
                              <span className="hint"> — {e.removed_reason}</span>
                            ) : null}
                          </td>
                          <td>
                            {e.moderation_state === "removed" ? (
                              <button type="button" className="btn btn-sm" disabled={dangGui}
                                      onClick={() => phucHoiTap(e)}>
                                Phục hồi
                              </button>
                            ) : (
                              <button type="button" className="btn btn-sm btn-danger" disabled={dangGui}
                                      onClick={() => { setHoiGoTap(e); setGhiChu(""); }}>
                                Gỡ tập
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="hint">Series này chưa có tập nào.</p>
              )}
            </div>

            {data.events.length > 0 ? (
              <div className="stack-2">
                <h3 className="section-title section-title-icon">
                  <IconHistory size={17} /> Lịch sử kiểm duyệt series này
                </h3>
                <ul className="admin-nhat-ky">
                  {data.events.map((ev) => (
                    <li key={ev.event_id} className="admin-su-kien">
                      <span className="mono">{ev.action}</span>
                      {ev.note ? <span className="hint">{ev.note}</span> : null}
                      <span className="hint admin-luc">
                        {new Date(ev.created_at).toLocaleString("vi-VN")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </DanhSachTrangThai>

      {hoiGoSeries ? (
        <ConfirmDialog
          open
          title={`Gỡ series "${s?.title}"?`}
          body={
            <span className="stack-2">
              <span>
                Series và MỌI tập bên trong sẽ không ai xem được nữa, kể cả
                chính chủ sở hữu — họ không thể tự xuất bản lại để hoàn tác
                lệnh gỡ này.
              </span>
              <textarea
                className="textarea textarea-sm"
                placeholder="Lý do gỡ (bắt buộc, ghi vào nhật ký kiểm duyệt)"
                value={ghiChu}
                onChange={(e) => setGhiChu(e.target.value)}
                maxLength={1000}
                rows={2}
              />
            </span>
          }
          confirmLabel="Gỡ series"
          danger
          busy={dangGui}
          onConfirm={goSeries}
          onCancel={() => setHoiGoSeries(false)}
        />
      ) : null}

      {hoiGoTap ? (
        <ConfirmDialog
          open
          title={`Gỡ tập "${hoiGoTap.title}"?`}
          body={
            <span className="stack-2">
              <span>Chỉ tập này bị gỡ — series và các tập khác không đổi.</span>
              <textarea
                className="textarea textarea-sm"
                placeholder="Lý do gỡ (bắt buộc, ghi vào nhật ký kiểm duyệt)"
                value={ghiChu}
                onChange={(e) => setGhiChu(e.target.value)}
                maxLength={1000}
                rows={2}
              />
            </span>
          }
          confirmLabel="Gỡ tập"
          danger
          busy={dangGui}
          onConfirm={goTap}
          onCancel={() => setHoiGoTap(null)}
        />
      ) : null}
    </section>
  );
}
