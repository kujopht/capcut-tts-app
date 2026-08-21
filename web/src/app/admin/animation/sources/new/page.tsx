"use client";

/**
 * Them Trusted Video Source moi (Phase 5, Admin Control Center V2).
 *
 * HAI buoc BAT BUOC theo dac ta: (1) dan URL, may chu tra ve XEM TRUOC that
 * (ten kenh/playlist/video that qua YouTube Data API) — (2) quan tri XAC
 * NHAN ro rang truoc khi tao. KHONG co duong tao thang tu URL ma khong qua
 * xem truoc — dung nhap nham mot kenh khac lam "tin cay".
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { adminApi, ApiError, type TrustedSourcePreview } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { ChuaCauHinh, DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { IconLink } from "@/components/Icons";

const TEN_LOAI: Record<string, string> = {
  youtube_channel: "Kênh YouTube",
  youtube_playlist: "Playlist YouTube",
  youtube_video: "Video đơn lẻ",
};

export default function AdminNewTrustedSource() {
  const router = useRouter();
  const toast = useToast();

  const [url, setUrl] = useState("");
  const [dangXem, setDangXem] = useState(false);
  const [chuaCauHinh, setChuaCauHinh] = useState(false);
  const [loiXem, setLoiXem] = useState("");
  const [xem, setXem] = useState<TrustedSourcePreview | null>(null);

  const [tenHienThi, setTenHienThi] = useState("");
  const [autoDiscover, setAutoDiscover] = useState(false);
  const [autoImport, setAutoImport] = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);
  const [nguong, setNguong] = useState(90);
  const [dangTao, setDangTao] = useState(false);

  async function xemTruoc() {
    if (!url.trim()) return;
    setDangXem(true);
    setLoiXem("");
    setChuaCauHinh(false);
    setXem(null);
    try {
      const ket_qua = await adminApi.previewTrustedSourceUrl(url.trim());
      setXem(ket_qua);
      setTenHienThi(ket_qua.display_name);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 503) {
        setChuaCauHinh(true);
      } else {
        setLoiXem(loiApi(cause, "Không đọc được URL này."));
      }
    } finally {
      setDangXem(false);
    }
  }

  async function xacNhanThem() {
    if (!xem || !tenHienThi.trim()) return;
    setDangTao(true);
    try {
      const { source } = await adminApi.createTrustedSource({
        source_type: xem.source_type,
        youtube_channel_id: xem.youtube_channel_id,
        youtube_playlist_id: xem.youtube_playlist_id,
        youtube_video_id: xem.youtube_video_id,
        display_name: tenHienThi.trim(),
        thumbnail_url: xem.thumbnail_url,
        auto_discover: autoDiscover, auto_import: autoImport, auto_publish: autoPublish,
        minimum_confidence: nguong / 100,
      });
      toast.ok(`Đã thêm "${source.display_name}" làm nguồn tin cậy.`);
      router.push(`/admin/animation/sources/${source.source_id}`);
    } catch (cause) {
      toast.error(loiApi(cause, "Không thêm được nguồn này."));
    } finally {
      setDangTao(false);
    }
  }

  return (
    <section className="stack">
      <h2 className="section-title section-title-icon">
        <IconLink size={19} /> Thêm nguồn tin cậy
      </h2>
      <p className="hint">
        <Link href="/admin/animation/sources">← Trusted Video Sources</Link>
      </p>

      {chuaCauHinh ? (
        <ChuaCauHinh
          tieuDe="Chưa cấu hình YouTube Data API"
          ghiChu="Cần biến môi trường YOUTUBE_API_KEY ở backend và bật YouTube Data API v3 trên Google Cloud trước khi thêm nguồn tin cậy."
        />
      ) : (
        <>
          <div className="card stack-2">
            <label htmlFor="tsrc-url" className="stack-2">
              <strong>Dán URL video / kênh / playlist YouTube</strong>
              <span className="hint">
                Ví dụ: youtube.com/watch?v=..., youtube.com/channel/UC...,
                youtube.com/@tenkenh, hoặc youtube.com/playlist?list=...
              </span>
            </label>
            <div className="row">
              <input
                id="tsrc-url"
                className="input"
                type="text"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") xemTruoc(); }}
                placeholder="https://www.youtube.com/…"
                autoComplete="off"
              />
              <button type="button" className="btn btn-primary" disabled={dangXem || !url.trim()}
                      onClick={xemTruoc}>
                {dangXem ? "Đang tra cứu…" : "Xem trước"}
              </button>
            </div>
          </div>

          {/* `rong={false}` co y: chua bam "Xem truoc" lan nao KHONG phai
              mot ket qua rong, chi la trang thai ban dau — children tra
              `null` cho toi khi co `xem`. */}
          <DanhSachTrangThai dangTai={dangXem} loi={loiXem} rong={false} onThuLai={xemTruoc}>
            {xem ? (
              <div className="card stack-2">
                <strong>Xem trước — kiểm tra kỹ trước khi xác nhận</strong>
                <div className="row" style={{ alignItems: "center" }}>
                  {xem.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={xem.thumbnail_url} alt="" width={120} height={68}
                         style={{ borderRadius: 8, objectFit: "cover" }} />
                  ) : null}
                  <div className="stack-2">
                    <span>{xem.display_name}</span>
                    <span className="hint">
                      {TEN_LOAI[xem.source_type] ?? xem.source_type}
                      {xem.channel_title ? ` · kênh: ${xem.channel_title}` : ""}
                    </span>
                    {xem.item_count !== undefined ? (
                      <span className="hint">{xem.item_count} video trong playlist</span>
                    ) : null}
                  </div>
                </div>

                <label className="stack-2">
                  <span>Tên hiển thị trong khu quản trị</span>
                  <input className="input" type="text" value={tenHienThi}
                         onChange={(e) => setTenHienThi(e.target.value)} maxLength={200} />
                </label>

                <div className="stack-2">
                  <label className="row row-tight">
                    <input type="checkbox" checked={autoDiscover}
                           onChange={(e) => setAutoDiscover(e.target.checked)} />
                    <span>Tự động phát hiện video mới (Auto Discover — cần Phase 6/WebSub)</span>
                  </label>
                  <label className="row row-tight">
                    <input type="checkbox" checked={autoImport}
                           onChange={(e) => setAutoImport(e.target.checked)} />
                    <span>Tự động nhập khi đủ độ tin cậy (Auto Import)</span>
                  </label>
                  <label className="row row-tight">
                    <input type="checkbox" checked={autoPublish}
                           onChange={(e) => setAutoPublish(e.target.checked)} />
                    <span>Tự động xuất bản tập sau khi nhập (Auto Publish)</span>
                  </label>
                </div>

                <label className="stack-2">
                  <span>Ngưỡng độ tin cậy tối thiểu để tự động: {nguong}%</span>
                  <input type="range" min={0} max={100} step={5} value={nguong}
                         onChange={(e) => setNguong(Number(e.target.value))}
                         aria-label="Ngưỡng độ tin cậy" />
                  <span className="hint">
                    Video dưới ngưỡng luôn vào hàng đợi để quản trị duyệt tay,
                    bất kể các cờ tự động ở trên.
                  </span>
                </label>

                <div className="row">
                  <button type="button" className="btn btn-primary" disabled={dangTao || !tenHienThi.trim()}
                          onClick={xacNhanThem}>
                    {dangTao ? "Đang thêm…" : "Thêm làm nguồn tin cậy"}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setXem(null)}>
                    Huỷ
                  </button>
                </div>
              </div>
            ) : null}
          </DanhSachTrangThai>
        </>
      )}
    </section>
  );
}
