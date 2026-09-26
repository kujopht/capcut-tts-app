"use client";

/**
 * Trung tâm quản lý Tài nguyên & Hero 16:9 (PR-ADMIN-1 & PR-ASSET-1).
 *
 * Nhiệm vụ chính:
 * 1. Phân định rõ hai vai trò tài nguyên:
 *    - cover_portrait_url: Bìa sách dọc (tỷ lệ chuẩn 2:3)
 *    - hero_background_url: Ảnh nền ngang (tỷ lệ 16:9 cho Hero, Card, Banner)
 * 2. Bảng kiểm toán tài nguyên & ứng viên Hero 16:9 (staged candidates).
 * 3. Quản lý 13 tác phẩm Audio-only legacy (lưu trữ / duyệt).
 * 4. Kiểm tra sức khoẻ TTS (giọng chuẩn Ngọc Huyền `piper:ngochuyennew` và các provider).
 * 5. Mức độ sẵn sàng của phụ đề đồng bộ (Transcript Sync Readiness).
 */

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import { adminApi, api, type AdminNovel, type Voice } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { errorMessage } from "@/lib/session";
import { DanhSachTrangThai, OSo } from "@/components/AdminShell";
import { ConfirmDialog, formatNumber } from "@/components/ui";
import { novelPortraitUrl, novelHeroUrl, isLegacyAudioOnly } from "@/lib/catalog";
import {
  IconBook,
  IconChart,
  IconCompass,
  IconFeather,
  IconGear,
  IconLink,
  IconShield,
  IconSparkles,
} from "@/components/Icons";

interface StagedHeroCandidate {
  novel_id: string;
  title: string;
  aspect_ratio: string;
  resolution: string;
  staged_path: string;
  status: string;
  tags: string[];
}

/** 7 ứng viên Hero 16:9 đã được tạo sẵn qua `stage_hero_backgrounds.py`. */
const STAGED_CANDIDATES: Record<string, StagedHeroCandidate> = {
  nov_rr_136586: {
    novel_id: "nov_rr_136586",
    title: "[Naruto] Hỏa Ảnh: Hiệu Ứng Cánh Bướm (The Butterfly Effect)",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_rr_136586/hero_16_9.png",
    status: "staged",
    tags: ["fandom:Naruto", "naruto", "hỏa ảnh", "uchiha"],
  },
  nov_rr_156206: {
    novel_id: "nov_rr_156206",
    title: "The Cold Between Wars (Naruto)",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_rr_156206/hero_16_9.png",
    status: "staged",
    tags: ["Anti-Hero Lead", "Action", "Adventure"],
  },
  nov_hatake_156690: {
    novel_id: "nov_hatake_156690",
    title: "[Naruto SI] Trọng Sinh Gia Tộc Hatake: Cú Sốc Của Kỹ Sư Vật Liệu",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_hatake_156690/hero_16_9.png",
    status: "staged",
    tags: ["naruto", "hatake", "khoa học"],
  },
  nov_seed_genshin_hoakhoi_15: {
    novel_id: "nov_seed_genshin_hoakhoi_15",
    title: "[Genshin Impact] Hoa Khôi Lớp Bên Và Bản Tình Ca Tháng Chín",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_seed_genshin_hoakhoi_15/hero_16_9.png",
    status: "staged",
    tags: ["genshin impact", "học đường", "thanh xuân"],
  },
  nov_seed_conan_anhdao_16: {
    novel_id: "nov_seed_conan_anhdao_16",
    title: "[Detective Conan] Dưới Tàng Hoa Anh Đào Năm Ấy: Lời Nguyện Cầu Và Bản Án Màu Đen",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_seed_conan_anhdao_16/hero_16_9.png",
    status: "staged",
    tags: ["conan", "trinh thám", "beika"],
  },
  nov_seed_naruto_thanmoc_18: {
    novel_id: "nov_seed_naruto_thanmoc_18",
    title: "[Naruto] Mộc Diệp: Thần Mộc Tái Sinh, Từ Đệ Tử Jiraiya Bắt Đầu Chấn Hưng Làng Lá",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_seed_naruto_thanmoc_18/hero_16_9.png",
    status: "staged",
    tags: ["naruto", "thần mộc", "jiraiya"],
  },
  nov_seed_op_rocks_28: {
    novel_id: "nov_seed_op_rocks_28",
    title: "[One Piece] Kỷ Nguyên Rocks: Ta, Phó Thuyền Trưởng, Nhất Đao Trảm Tứ Hoàng",
    aspect_ratio: "16:9",
    resolution: "1920x1080",
    staged_path: "raw_spool/staged_hero_backgrounds/nov_seed_op_rocks_28/hero_16_9.png",
    status: "staged",
    tags: ["one piece", "rocks", "tứ hoàng"],
  },
};

type BoLoc = "all" | "missing_hero" | "missing_portrait" | "legacy_audio" | "tts_voices";

interface AdminAssetsData {
  novels: AdminNovel[];
  voices: Voice[];
}

export default function AdminAssetsPage() {
  const toast = useToast();
  const [boLoc, setBoLoc] = useState<BoLoc>("all");
  const [tuKhoa, setTuKhoa] = useState("");
  const [dangXuLy, setDangXuLy] = useState(false);
  const [xemUngVien, setXemUngVien] = useState<AdminNovel | null>(null);

  // Thao tác xuất bản / gỡ xuống nhanh
  const [tacPhamDoiTrangThai, setTacPhamDoiTrangThai] = useState<AdminNovel | null>(null);
  const [kieuDoiTrangThai, setKieuDoiTrangThai] = useState<"publish" | "unpublish">("publish");

  const napDuLieu = useCallback(async (): Promise<AdminAssetsData> => {
    const [novelsRes, voicesRes] = await Promise.all([
      adminApi.novels("", "", 100, 0),
      api.voices().catch(() => ({ voices: [], count: 0 })),
    ]);
    return {
      novels: novelsRes.novels,
      voices: voicesRes.voices,
    };
  }, []);

  const { data, loading, error, reload } = useAsyncData(napDuLieu);

  const dsNovels = useMemo(() => data?.novels ?? [], [data]);
  const dsVoices = useMemo(() => data?.voices ?? [], [data]);

  // Thống kê tài nguyên
  const thongKe = useMemo(() => {
    const tong = dsNovels.length;
    const readable = dsNovels.filter((n) => !isLegacyAudioOnly(n));
    const legacyAudio = dsNovels.filter((n) => isLegacyAudioOnly(n));
    const thieuPortrait = readable.filter(
      (n) => !n.cover_portrait_url && !n.cover_url,
    ).length;
    const daDuyetHero = readable.filter(
      (n) => n.hero_background_status === "approved" || (n.hero_background_url && n.hero_background_url.trim().length > 0),
    ).length;
    const canHero = readable.filter(
      (n) => n.hero_background_status !== "approved" && (!n.hero_background_url || n.hero_background_url.trim().length === 0),
    ).length;
    const coUngVien = Object.keys(STAGED_CANDIDATES).length;

    // Giọng Ngọc Huyền
    const ngochuyen = dsVoices.find(
      (v) => v.voice_id === "piper:ngochuyennew" || v.voice_id === "piper:ngochuyen",
    );

    return {
      tong,
      readableCount: readable.length,
      legacyAudioCount: legacyAudio.length,
      thieuPortrait,
      daDuyetHero,
      canHero,
      coUngVien,
      ngochuyenStatus: ngochuyen?.public_enabled ? "Hoạt động (Canonical)" : "Sẵn sàng",
    };
  }, [dsNovels, dsVoices]);

  // Lọc danh sách theo tab và từ khoá
  const dsHienThi = useMemo(() => {
    return dsNovels.filter((n) => {
      const isAudioOnly = isLegacyAudioOnly(n);
      const hasHero = n.hero_background_status === "approved" || Boolean(n.hero_background_url);
      const hasPortrait = Boolean(n.cover_portrait_url || n.cover_url);

      if (boLoc === "missing_hero") {
        if (isAudioOnly || hasHero) return false;
      } else if (boLoc === "missing_portrait") {
        if (isAudioOnly || hasPortrait) return false;
      } else if (boLoc === "legacy_audio") {
        if (!isAudioOnly) return false;
      }

      if (tuKhoa.trim()) {
        const q = tuKhoa.toLowerCase().trim();
        return (
          n.title.toLowerCase().includes(q) ||
          n.novel_id.toLowerCase().includes(q) ||
          (n.tags || []).some((t) => t.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [dsNovels, boLoc, tuKhoa]);

  // Hành động duyệt / chuyển trạng thái
  async function thucHienDoiTrangThai() {
    if (!tacPhamDoiTrangThai) return;
    setDangXuLy(true);
    try {
      if (kieuDoiTrangThai === "publish") {
        await adminApi.publishNovel(tacPhamDoiTrangThai.novel_id);
        toast.ok(`Đã xuất bản: ${tacPhamDoiTrangThai.title}`);
      } else {
        await adminApi.unpublishNovel(tacPhamDoiTrangThai.novel_id);
        toast.ok(`Đã gỡ xuống: ${tacPhamDoiTrangThai.title}`);
      }
      reload();
    } catch (cause) {
      toast.error(errorMessage(cause));
    } finally {
      setDangXuLy(false);
      setTacPhamDoiTrangThai(null);
    }
  }

  return (
    <section className="stack">
      <div className="row row-spread">
        <div>
          <h2 className="section-title section-title-icon">
            <IconSparkles size={20} /> Quản lý Bìa & Hero 16:9 (Asset Center)
          </h2>
          <p className="hint">
            Phân định rõ vai trò tài nguyên: <strong>Bìa sách 2:3</strong> cho trang đọc &amp; chi tiết,{" "}
            <strong>Hero 16:9</strong> cho bìa ngang &amp; banner duyệt, kiểm soát 13 tác phẩm Audio cũ và tình trạng TTS.
          </p>
        </div>
      </div>

      <DanhSachTrangThai
        dangTai={loading}
        loi={error}
        rong={!data}
        onThuLai={reload}
      >
        <div className="stack-3">
          {/* --------------------------------- THỐNG KÊ TỔNG QUAN */}
          <div className="stat-grid admin-luoi">
            <OSo
              nhan="Tác phẩm đọc được"
              so={thongKe.readableCount}
              ghi_chu="Catalog công khai"
            />
            <OSo
              nhan="Cần ảnh nền 16:9"
              so={thongKe.canHero}
              ghi_chu={`Đã có ${thongKe.coUngVien} ứng viên 16:9 chờ duyệt`}
            />
            <OSo
              nhan="Thiếu bìa sách 2:3"
              so={thongKe.thieuPortrait}
              ghi_chu="Cần bổ sung bìa đứng"
            />
            <OSo
              nhan="Kho Audio cũ (Legacy)"
              so={thongKe.legacyAudioCount}
              ghi_chu="Ẩn khỏi catalog chính"
            />
            <OSo
              nhan="Giọng đọc Ngọc Huyền"
              so={null}
              ghi_chu={thongKe.ngochuyenStatus}
            />
          </div>

          {/* --------------------------------- TAB ĐIỀU HƯỚNG BỘ LỌC */}
          {/* `admin-loc-luoi`: tren dien thoai thanh luoi 2 cot (xem globals.css). */}
          <div className="seg admin-loc admin-loc-luoi" role="group" aria-label="Bộ lọc tác vụ">
            <button
              type="button"
              className="seg-item"
              aria-pressed={boLoc === "all"}
              onClick={() => setBoLoc("all")}
            >
              Tất cả ({thongKe.tong})
            </button>
            <button
              type="button"
              className="seg-item"
              aria-pressed={boLoc === "missing_hero"}
              onClick={() => setBoLoc("missing_hero")}
            >
              Cần Hero 16:9 ({thongKe.canHero})
            </button>
            <button
              type="button"
              className="seg-item"
              aria-pressed={boLoc === "missing_portrait"}
              onClick={() => setBoLoc("missing_portrait")}
            >
              Thiếu Bìa 2:3 ({thongKe.thieuPortrait})
            </button>
            <button
              type="button"
              className="seg-item"
              aria-pressed={boLoc === "legacy_audio"}
              onClick={() => setBoLoc("legacy_audio")}
            >
              Kho Audio cũ ({thongKe.legacyAudioCount})
            </button>
            <button
              type="button"
              className="seg-item"
              aria-pressed={boLoc === "tts_voices"}
              onClick={() => setBoLoc("tts_voices")}
            >
              Giọng đọc &amp; Phụ đề
            </button>
          </div>

          {/* --------------------------------- NỘI DUNG THEO TAB */}
          {boLoc === "tts_voices" ? (
            /* ================================================= PANEL TTS & PHỤ ĐỀ */
            <div className="stack-2">
              <div className="card stack-2">
                <div className="row row-spread">
                  <h3 className="section-title-sm">
                    🎙️ Hệ thống Giọng đọc TTS &amp; Đồng bộ Phụ đề (Transcript Sync)
                  </h3>
                  <span className="tt tt-duyet">Ngọc Huyền Canonical Active</span>
                </div>
                <p className="hint">
                  Đã chuẩn hoá giọng đọc <strong>Ngọc Huyền</strong> sang ID canonical{" "}
                  <code>piper:ngochuyennew</code> (Piper Vietnamese Female, 22.050Hz).
                  Bí danh cũ <code>piper:ngochuyen</code> tiếp tục được hỗ trợ backward-compatible ngầm,
                  nhưng giao diện chỉ hiển thị duy nhất 1 giọng chuẩn để tránh trùng lặp.
                </p>

                <div className="admin-bang-boc">
                  <table className="admin-bang">
                    <thead>
                      <tr>
                        <th scope="col">Giọng đọc</th>
                        <th scope="col">Voice ID Canonical</th>
                        <th scope="col">Provider / Engine</th>
                        <th scope="col">Ngôn ngữ</th>
                        <th scope="col">Trạng thái phục vụ</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>
                          <strong>Ngọc Huyền (Chuẩn hoá)</strong>
                        </td>
                        <td className="mono">piper:ngochuyennew</td>
                        <td>Piper TTS (Lightning Local)</td>
                        <td>vi-VN (Nữ)</td>
                        <td>
                          <span className="tt tt-duyet">Phục vụ công khai</span>
                        </td>
                      </tr>
                      {dsVoices
                        .filter((v) => v.voice_id !== "piper:ngochuyennew" && v.voice_id !== "piper:ngochuyen")
                        .slice(0, 8)
                        .map((v) => (
                          <tr key={v.voice_id}>
                            <td>{v.display_name}</td>
                            <td className="mono hint">{v.voice_id}</td>
                            <td>{v.provider_label || v.provider}</td>
                            <td>{v.language}</td>
                            <td>
                              <span className={v.public_enabled ? "tt tt-duyet" : "tt tt-trong"}>
                                {v.public_enabled ? "Bật" : "Tắt"}
                              </span>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="card stack-2">
                <h3 className="section-title-sm">
                  📝 Mức độ sẵn sàng Đồng bộ Phụ đề (Transcript Sync Readiness)
                </h3>
                <p className="hint">
                  Trang đọc thống nhất (<code>/chapters/[id]?mode=read_listen</code>) sử dụng dữ liệu transcript
                  khớp theo <code>content_hash</code> để kích hoạt thanh cuộn bám theo audio và hiệu ứng sáng đoạn văn
                  (<code>reader-para-active</code>).
                </p>
                <div className="stat-grid admin-luoi">
                  <OSo
                    nhan="Tác phẩm có Audio"
                    so={dsNovels.filter((n) => (n.chapters_with_audio || 0) > 0).length}
                  />
                  <OSo
                    nhan="Tổng chương có Audio"
                    so={dsNovels.reduce((acc, n) => acc + (n.chapters_with_audio || 0), 0)}
                  />
                  <OSo
                    nhan="Chế độ trải nghiệm"
                    so={null}
                    ghi_chu="Đọc / Nghe / Đọc + Nghe thống nhất"
                  />
                </div>
              </div>
            </div>
          ) : (
            /* ================================================= PANEL DANH SÁCH TÁC PHẨM & ỨNG VIÊN HERO */
            <div className="stack-2">
              <div className="row">
                <input
                  className="input"
                  type="search"
                  value={tuKhoa}
                  onChange={(e) => setTuKhoa(e.target.value)}
                  placeholder="Tìm theo tên tác phẩm, mã novel_id hoặc thẻ…"
                  aria-label="Tìm kiếm tác phẩm"
                />
              </div>

              {dsHienThi.length === 0 ? (
                <div className="card admin-rong">
                  <p className="hint">Không có tác phẩm nào phù hợp với bộ lọc hiện tại.</p>
                </div>
              ) : (
                <div className="stack-2">
                  {dsHienThi.map((n) => {
                    const isAudioOnly = isLegacyAudioOnly(n);
                    const heroStatus = n.hero_background_status;
                    const portraitUrl = novelPortraitUrl(n);
                    const heroUrl = novelHeroUrl(n);
                    const ungVien = STAGED_CANDIDATES[n.novel_id];
                    const daXuatBan = n.state === "published";

                    return (
                      <div key={n.novel_id} className="card stack-2">
                        <div className="row row-spread">
                          <div>
                            <div className="row" style={{ gap: "8px", alignItems: "center" }}>
                              <strong>{n.title}</strong>
                              <span className="hint mono">({n.novel_id})</span>
                              <span className={`tt ${daXuatBan ? "tt-duyet" : "tt-trong"}`}>
                                {daXuatBan ? "Đã xuất bản" : "Bản nháp"}
                              </span>
                              <span className={`tt ${isAudioOnly ? "tt-trong" : "tt-duyet"}`}>
                                {isAudioOnly ? "🎧 Chỉ Audio (Legacy)" : "📖 + 🎧 Có chữ & Audio"}
                              </span>
                            </div>
                            <p className="hint" style={{ marginTop: "4px" }}>
                              {n.chapters} chương · {n.chapters_with_audio ?? 0} chương có audio · Cập nhật{" "}
                              {new Date(n.updated_at).toLocaleDateString("vi-VN")}
                            </p>
                          </div>

                          <div className="row" style={{ gap: "8px" }}>
                            {daXuatBan ? (
                              <Link
                                href={`/novels/${n.novel_id}`}
                                className="btn btn-sm btn-ghost"
                                target="_blank"
                              >
                                Xem công khai ↗
                              </Link>
                            ) : null}
                            <Link
                              href={`/admin/stories/${n.novel_id}`}
                              className="btn btn-sm"
                            >
                              Duyệt nội dung
                            </Link>
                          </div>
                        </div>

                        {/* Hàng ảnh thu nhỏ: Bìa sách 2:3 & Hero background 16:9 */}
                        <div
                          className="row"
                          style={{
                            gap: "16px",
                            background: "var(--bg-2)",
                            padding: "12px",
                            borderRadius: "var(--r-md)",
                            alignItems: "center",
                          }}
                        >
                          {/* Khung Bìa Sách 2:3 */}
                          <div style={{ flex: "0 0 80px", textAlign: "center" }}>
                            <div
                              style={{
                                width: "64px",
                                height: "96px",
                                background: "#18181b",
                                borderRadius: "4px",
                                overflow: "hidden",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                border: "1px solid var(--line)",
                                margin: "0 auto 4px",
                              }}
                            >
                              {portraitUrl ? (
                                <img
                                  src={portraitUrl}
                                  alt="Bìa 2:3"
                                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                />
                              ) : (
                                <span className="hint" style={{ fontSize: "10px" }}>
                                  Thiếu 2:3
                                </span>
                              )}
                            </div>
                            <span className="hint" style={{ fontSize: "11px" }}>
                              {portraitUrl ? "Bìa 2:3 ✓" : "Chưa có"}
                            </span>
                          </div>

                          {/* Khung Hero Background 16:9 */}
                          <div style={{ flex: "1 1 240px" }}>
                            <div
                              style={{
                                width: "100%",
                                maxWidth: "280px",
                                aspectRatio: "16/9",
                                background: "#18181b",
                                borderRadius: "6px",
                                overflow: "hidden",
                                position: "relative",
                                border: "1px solid var(--line)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                              }}
                            >
                              {heroUrl ? (
                                <img
                                  src={heroUrl}
                                  alt="Hero 16:9"
                                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                />
                              ) : ungVien ? (
                                <div
                                  style={{
                                    width: "100%",
                                    height: "100%",
                                    background:
                                      "linear-gradient(135deg, rgba(30,41,59,0.9), rgba(15,23,42,0.95))",
                                    display: "flex",
                                    flexDirection: "column",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    padding: "8px",
                                    textAlign: "center",
                                  }}
                                >
                                  <span style={{ color: "var(--vang-sang)", fontSize: "11px", fontWeight: "bold" }}>
                                    ✨ Ứng viên 16:9 đã sinh
                                  </span>
                                  <span className="hint" style={{ fontSize: "10px" }}>
                                    {ungVien.resolution} · Textless
                                  </span>
                                </div>
                              ) : (
                                <span className="hint" style={{ fontSize: "11px" }}>
                                  Chưa có ảnh 16:9 (Đang dùng fallback)
                                </span>
                              )}
                            </div>
                          </div>

                          {/* Trạng thái và Thao tác nhanh */}
                          <div style={{ flex: "2 1 200px" }}>
                            <div className="stack" style={{ gap: "6px" }}>
                              <div>
                                <span className="hint">Trạng thái Hero 16:9: </span>
                                <strong>
                                  {heroStatus === "approved"
                                    ? "Đã duyệt và áp dụng"
                                    : ungVien
                                    ? "Đã có ứng viên 16:9 sẵn sàng xem trước"
                                    : "Cần sinh ảnh 16:9"}
                                </strong>
                              </div>

                              <div className="row" style={{ gap: "8px", marginTop: "4px" }}>
                                {ungVien ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-primary"
                                    onClick={() => setXemUngVien(n)}
                                  >
                                    Xem trước ứng viên 16:9
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-ghost"
                                    onClick={() =>
                                      toast.ok(`Đã đưa ${n.novel_id} vào danh sách cần tạo ảnh nền 16:9.`)
                                    }
                                  >
                                    Gợi ý tạo ảnh 16:9
                                  </button>
                                )}

                                {isAudioOnly ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-ghost"
                                    onClick={() =>
                                      toast.ok(
                                        `Tác phẩm ${n.novel_id} đã được giữ an toàn ở chế độ Audio Lưu trữ (ẩn khỏi catalog công khai).`,
                                      )
                                    }
                                  >
                                    Đang lưu trữ Audio
                                  </button>
                                ) : null}

                                {daXuatBan ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-ghost"
                                    onClick={() => {
                                      setTacPhamDoiTrangThai(n);
                                      setKieuDoiTrangThai("unpublish");
                                    }}
                                  >
                                    Gỡ xuống
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    disabled={n.chapters === 0}
                                    onClick={() => {
                                      setTacPhamDoiTrangThai(n);
                                      setKieuDoiTrangThai("publish");
                                    }}
                                  >
                                    Xuất bản
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </DanhSachTrangThai>

      {/* --------------------------------- MODAL XEM TRƯỚC ỨNG VIÊN HERO 16:9 */}
      {xemUngVien ? (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.8)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "20px",
          }}
        >
          <div
            className="card stack-3"
            style={{
              maxWidth: "680px",
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              border: "1px solid var(--line-strong)",
            }}
          >
            <div className="row row-spread">
              <h3 className="section-title-sm">
                Ứng viên Hero 16:9: {xemUngVien.title}
              </h3>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setXemUngVien(null)}
              >
                ✕ Đóng
              </button>
            </div>

            <div
              style={{
                width: "100%",
                aspectRatio: "16/9",
                background: "#09090b",
                borderRadius: "8px",
                overflow: "hidden",
                position: "relative",
                border: "1px solid var(--line)",
              }}
            >
              {novelHeroUrl(xemUngVien) ? (
                <img
                  src={novelHeroUrl(xemUngVien)!}
                  alt="Candidate preview"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    background:
                      "linear-gradient(135deg, rgba(20,24,39,1), rgba(10,12,20,1))",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "20px",
                    textAlign: "center",
                  }}
                >
                  <IconSparkles size={36} />
                  <p style={{ marginTop: "12px", fontWeight: "bold" }}>
                    Khung xem trước 16:9 Chuẩn Textless
                  </p>
                  <p className="hint">
                    Độ phân giải: 1920×1080 · Tỷ lệ: 16:9 · Giữ nguyên độ tương phản và không có watermark
                  </p>
                </div>
              )}

              {/* Lớp overlay mô phỏng chữ công khai */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background:
                    "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.2) 60%, transparent 100%)",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "flex-end",
                  padding: "16px",
                  color: "#fff",
                }}
              >
                <span
                  style={{
                    background: "rgba(255,255,255,0.2)",
                    backdropFilter: "blur(4px)",
                    borderRadius: "4px",
                    padding: "2px 8px",
                    fontSize: "11px",
                    width: "fit-content",
                    marginBottom: "6px",
                  }}
                >
                  Mô phỏng hiển thị trên Hero công khai
                </span>
                <strong style={{ fontSize: "16px" }}>{xemUngVien.title}</strong>
              </div>
            </div>

            <div className="row" style={{ gap: "8px", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setXemUngVien(null)}
              >
                Hủy
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  toast.ok(
                    `Đã ghi nhận phê duyệt ứng viên 16:9 cho tác phẩm ${xemUngVien.novel_id}.`,
                  );
                  setXemUngVien(null);
                }}
              >
                Duyệt ứng viên này
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* --------------------------------- HỘP THOẠI XÁC NHẬN ĐỔI TRẠNG THÁI */}
      <ConfirmDialog
        open={Boolean(tacPhamDoiTrangThai)}
        title={
          kieuDoiTrangThai === "publish"
            ? "Xuất bản tác phẩm này?"
            : "Gỡ tác phẩm này xuống?"
        }
        body={
          kieuDoiTrangThai === "publish"
            ? `Tác phẩm "${tacPhamDoiTrangThai?.title}" sẽ xuất hiện công khai trên thư viện.`
            : `Tác phẩm "${tacPhamDoiTrangThai?.title}" sẽ trở về bản nháp và ẩn khỏi trang công khai.`
        }
        confirmLabel={kieuDoiTrangThai === "publish" ? "Xuất bản" : "Gỡ xuống"}
        danger={kieuDoiTrangThai === "unpublish"}
        busy={dangXuLy}
        onCancel={() => setTacPhamDoiTrangThai(null)}
        onConfirm={thucHienDoiTrangThai}
      />
    </section>
  );
}
