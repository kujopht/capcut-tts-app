"use client";

/**
 * Trang quan tri Universal Story Scraper (Quet truyen tu dong & Hang doi duyet).
 *
 * Cho phep operator:
 * 1. Dan URL truyen, xem truoc (discover), va bat dau/tiep tuc quet.
 * 2. Theo doi tien do, drive tung chu ky (hoac tu dong chay), huy hoac thu lai ca lo.
 * 3. Duyet tung chuong trong hang doi: xem trang thai, bo qua, thu lai chuong loi.
 * 4. Chon va xem lai cac tac vu quet cu tu lich su.
 *
 * LUU Y: Day la HANG DOI DUYET (Review Queue), khong tu dong xuat ban —
 * cac chuong sau khi quet can cho kiem duyet truoc khi xuat ban.
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  adminApi,
  type DiscoveryProposal,
  type ScrapeItemStatus,
  type ScrapeRun,
  type ScrapeRunItem,
  type ScrapeRunStatus,
} from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useToast } from "@/lib/toast";
import { DanhSachTrangThai, loiApi } from "@/components/AdminShell";
import { ConfirmDialog, ProgressBar } from "@/components/ui";
import { IconBook, IconHistory, IconLink } from "@/components/Icons";

const NHAN_TRANG_THAI_RUN: Record<ScrapeRunStatus, { chu: string; lop: string }> = {
  planning: { chu: "Đang lập kế hoạch", lop: "tt-cho" },
  running: { chu: "Đang quét", lop: "tt-duyet" },
  cancel_requested: { chu: "Đang yêu cầu huỷ", lop: "tt-treo" },
  cancelled: { chu: "Đã huỷ", lop: "tt-trong" },
  completed: { chu: "Hoàn tất", lop: "tt-duyet" },
  partial: { chu: "Một phần", lop: "tt-cho" },
  failed: { chu: "Thất bại", lop: "tt-tuchoi" },
};

const NHAN_TRANG_THAI_MUC: Record<ScrapeItemStatus, { chu: string; lop: string }> = {
  pending: { chu: "Đang chờ", lop: "tt-cho" },
  review_ready: { chu: "Sẵn sàng duyệt", lop: "tt-duyet" },
  failed: { chu: "Lỗi", lop: "tt-tuchoi" },
  skipped: { chu: "Đã bỏ qua", lop: "tt-trong" },
};

const BO_LOC_MUC: ReadonlyArray<{ khoa: "" | ScrapeItemStatus; nhan: string }> = [
  { khoa: "", nhan: "Tất cả" },
  { khoa: "review_ready", nhan: "Sẵn sàng duyệt" },
  { khoa: "pending", nhan: "Đang chờ" },
  { khoa: "failed", nhan: "Lỗi" },
  { khoa: "skipped", nhan: "Đã bỏ qua" },
];

const SO_MUC_MOI_TRANG = 25;

export default function AdminScraperPage() {
  return (
    <Suspense fallback={<DanhSachTrangThai dangTai loi="" rong={false}>{null}</DanhSachTrangThai>}>
      <ScraperPageContent />
    </Suspense>
  );
}

function ScraperPageContent() {
  const searchParams = useSearchParams();
  const runIdParam = searchParams.get("run_id") ?? "";
  const toast = useToast();

  // -- Danh sach run va ten mien ho tro --
  const napDanhSachRuns = useCallback(() => adminApi.listScrapeRuns(), []);
  const {
    data: dataRuns,
    loading: dangTaiRuns,
    error: loiTaiRuns,
    reload: taiLaiDanhSachRuns,
  } = useAsyncData(napDanhSachRuns);

  const danhSachRuns = dataRuns?.runs ?? [];
  const supportedDomains = dataRuns?.supported_domains ?? [];

  // -- Form URL & Xem truoc --
  const [inputUrl, setInputUrl] = useState("");
  const [chapterLimit, setChapterLimit] = useState("");
  const [dangXemTruoc, setDangXemTruoc] = useState(false);
  const [ketQuaXemTruoc, setKetQuaXemTruoc] = useState<{
    run: ScrapeRun;
    supported: boolean;
  } | null>(null);
  const [loiXemTruoc, setLoiXemTruoc] = useState("");
  const [dangBatDau, setDangBatDau] = useState(false);

  // -- Story Harvester V3 Phase 2/4: nguon MOI chua duoc cau hinh --
  // `discoverScrape` tra ve de xuat (khong loi) khi domain chua co
  // SiteConfig/SiteProfile — operator xem bang chung roi tu quyet dinh
  // co xac nhan hay khong (xem `handleXacNhanNguonMoi`).
  const [deXuatNguonMoi, setDeXuatNguonMoi] = useState<DiscoveryProposal | null>(null);
  const [dangXacNhanNguon, setDangXacNhanNguon] = useState(false);

  // -- Run dang duoc chon / xem chi tiet --
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const activeRunId = selectedRunId ?? runIdParam;

  // -- Loc & phan trang danh sach chuong --
  const [locTrangThaiMuc, setLocTrangThaiMuc] = useState<"" | ScrapeItemStatus>("");
  const [trangMuc, setTrangMuc] = useState(0);

  // Tai chi tiet run dang chon
  const napChiTiet = useCallback(() => {
    if (!activeRunId) {
      return Promise.resolve({
        run: null as unknown as ScrapeRun,
        items: [] as ScrapeRunItem[],
        progress: {
          estimated_total: 0,
          already_done_count: 0,
          total_discovered: 0,
          pending: 0,
          review_ready: 0,
          failed: 0,
          skipped: 0,
          done: 0,
          percent: 0,
        },
      });
    }
    return adminApi.getScrapeRun(activeRunId, {
      limit: SO_MUC_MOI_TRANG,
      offset: trangMuc * SO_MUC_MOI_TRANG,
      status: locTrangThaiMuc || undefined,
    });
  }, [activeRunId, trangMuc, locTrangThaiMuc]);

  const {
    data: dataChiTiet,
    loading: dangTaiChiTiet,
    error: loiChiTiet,
    reload: taiLaiChiTiet,
    setData: setChiTietData,
  } = useAsyncData(napChiTiet, { enabled: Boolean(activeRunId) });

  const activeRun = dataChiTiet?.run ?? null;
  const activeProgress = dataChiTiet?.progress ?? null;
  const activeItems = dataChiTiet?.items ?? [];

  // -- Thao tac dang xu ly --
  const [dangDrive, setDangDrive] = useState(false);
  const [tuDongChay, setTuDongChay] = useState(false);
  const [dangRetryRun, setDangRetryRun] = useState(false);
  const [dangHuyRun, setDangHuyRun] = useState(false);
  const [hoiHuyRun, setHoiHuyRun] = useState(false);

  // -- Thao tac tren tung dong --
  const [dangXuLyItemId, setDangXuLyItemId] = useState<string | null>(null);
  const [hoiBoQuaItem, setHoiBoQuaItem] = useState<ScrapeRunItem | null>(null);
  const [lyDoBoQua, setLyDoBoQua] = useState("");

  // Polling tien do khi run dang 'running' hoac 'cancel_requested'
  const isRunning = activeRun?.status === "running" || activeRun?.status === "cancel_requested";
  useEffect(() => {
    if (!activeRunId || !isRunning) return;

    const timer = window.setInterval(() => {
      adminApi
        .getScrapeRun(activeRunId, {
          limit: SO_MUC_MOI_TRANG,
          offset: trangMuc * SO_MUC_MOI_TRANG,
          status: locTrangThaiMuc || undefined,
        })
        .then((res) => {
          setChiTietData(() => res);
        })
        .catch(() => {});
    }, 3000);

    return () => {
      window.clearInterval(timer);
    };
  }, [activeRunId, isRunning, trangMuc, locTrangThaiMuc, setChiTietData]);

  // Auto-drive loop: neu tuDongChay = true va run van running -> tu goi driveScrapeRun
  useEffect(() => {
    if (!tuDongChay || activeRun?.status !== "running" || !activeRunId) return;

    let timeoutId: number;
    let cancelled = false;

    function chayVongTiepTheo() {
      if (cancelled) return;
      setDangDrive(true);
      adminApi
        .driveScrapeRun(activeRunId)
        .then((res) => {
          if (cancelled) return;
          setChiTietData((prev) =>
            prev ? { ...prev, run: res.run, progress: res.progress } : prev,
          );
          taiLaiChiTiet();
          if (res.run.status !== "running") {
            setTuDongChay(false);
            taiLaiDanhSachRuns();
          } else {
            timeoutId = window.setTimeout(chayVongTiepTheo, 2000);
          }
        })
        .catch((cause) => {
          if (cancelled) return;
          toast.error(loiApi(cause, "Lỗi khi tự động tiếp tục quét."));
          setTuDongChay(false);
        })
        .finally(() => {
          if (!cancelled) setDangDrive(false);
        });
    }

    timeoutId = window.setTimeout(chayVongTiepTheo, 500);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [tuDongChay, activeRun?.status, activeRunId, taiLaiChiTiet, taiLaiDanhSachRuns, setChiTietData, toast]);

  // -- Handlers --

  async function handleXemTruoc(e: React.FormEvent) {
    e.preventDefault();
    const url = inputUrl.trim();
    if (!url) {
      toast.error("Vui lòng nhập URL truyện.");
      return;
    }

    setDangXemTruoc(true);
    setKetQuaXemTruoc(null);
    setDeXuatNguonMoi(null);
    setLoiXemTruoc("");
    try {
      const res = await adminApi.discoverScrape(url);
      if (res.supported) {
        setKetQuaXemTruoc(res);
        toast.ok(`Đã phát hiện: "${res.run.series_title || "Truyện"}"`);
      } else {
        setDeXuatNguonMoi(res.proposal);
        toast.ok("Phát hiện nguồn mới — xem đề xuất bên dưới trước khi xác nhận.");
      }
    } catch (cause) {
      const msg = loiApi(cause, "Không thể xem trước URL này.");
      setLoiXemTruoc(msg);
      toast.error(msg);
    } finally {
      setDangXemTruoc(false);
    }
  }

  async function handleXacNhanNguonMoi() {
    const url = deXuatNguonMoi?.source_url?.trim();
    if (!url) return;

    setDangXacNhanNguon(true);
    try {
      await adminApi.confirmScrapeSource(url);
      toast.ok("Đã xác nhận nguồn mới — đang xem trước lại để bắt đầu quét.");
      setDeXuatNguonMoi(null);
      // Xem truoc LAI sau khi xac nhan — gio domain da co SiteProfile
      // usable, `discoverScrape` se di duong `supported: true` binh
      // thuong, dua thang vao luong "Bat dau quet" san co, khong can
      // duong rieng.
      const res = await adminApi.discoverScrape(url);
      if (res.supported) {
        setKetQuaXemTruoc(res);
      }
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể xác nhận nguồn này."));
    } finally {
      setDangXacNhanNguon(false);
    }
  }

  async function handleBatDauQuet() {
    // Dung URL cua CHINH lan xem-truoc thanh cong, KHONG dung `inputUrl`
    // truc tiep — operator co the sua o input SAU khi xem truoc truyen A
    // ma KHONG bam xem truoc lai, va vo tinh bat dau quet truyen B duoi
    // danh nghia da xac nhan cua A. Phat hien qua review Codex.
    const url = ketQuaXemTruoc?.run.source_url?.trim();
    if (!url) return;

    setDangBatDau(true);
    try {
      const limit = chapterLimit.trim() ? Number(chapterLimit) : undefined;
      const res = await adminApi.startScrapeRun(url, { chapterLimit: limit });
      toast.ok("Đã khởi tạo tác vụ quét.");
      setSelectedRunId(res.run.run_id);
      setChiTietData(() => ({
        run: res.run,
        progress: res.progress,
        items: [],
      }));
      setKetQuaXemTruoc(null);
      taiLaiDanhSachRuns();
      taiLaiChiTiet();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể bắt đầu tác vụ quét."));
    } finally {
      setDangBatDau(false);
    }
  }

  async function handleDriveMotChuKy() {
    if (!activeRunId) return;
    setDangDrive(true);
    try {
      const res = await adminApi.driveScrapeRun(activeRunId);
      setChiTietData((prev) =>
        prev ? { ...prev, run: res.run, progress: res.progress } : prev,
      );
      toast.ok("Đã thực hiện 1 chu kỳ quét.");
      taiLaiChiTiet();
      taiLaiDanhSachRuns();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể tiếp tục quét."));
    } finally {
      setDangDrive(false);
    }
  }

  async function handleHuyRun() {
    if (!activeRunId) return;
    setDangHuyRun(true);
    try {
      await adminApi.cancelScrapeRun(activeRunId);
      setTuDongChay(false);
      setHoiHuyRun(false);
      // `cancel` CHI bat co `cancel_requested` — no chi thanh `cancelled`
      // THAT SU khi mot lan `drive` sau do quan sat thay co nay (xem
      // docstring backend `bulk.py::request_cancel`). Neu operator dang
      // KHONG tu dong chay va khong bam "Tiếp tục" nua, dot se ket ket o
      // `cancel_requested` mai mai — chu dong drive MOT lan ngay o day de
      // hoan tat huy thay vi cho operator tinh co bam nut khac. Phat hien
      // qua review Codex.
      const finalRes = await adminApi.driveScrapeRun(activeRunId);
      setChiTietData((prev) =>
        prev ? { ...prev, run: finalRes.run, progress: finalRes.progress } : prev,
      );
      toast.ok("Đã huỷ tác vụ.");
      taiLaiChiTiet();
      taiLaiDanhSachRuns();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể huỷ tác vụ."));
    } finally {
      setDangHuyRun(false);
    }
  }

  async function handleRetryToanBo() {
    if (!activeRunId) return;
    setDangRetryRun(true);
    try {
      const res = await adminApi.retryScrapeRun(activeRunId);
      setChiTietData((prev) =>
        prev ? { ...prev, run: res.run, progress: res.progress } : prev,
      );
      toast.ok(`Đã xếp lại ${res.retried} mục lỗi để thử lại.`);
      taiLaiChiTiet();
      taiLaiDanhSachRuns();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể thử lại toàn bộ mục lỗi."));
    } finally {
      setDangRetryRun(false);
    }
  }

  async function handleRetryItem(item: ScrapeRunItem) {
    if (!activeRunId) return;
    setDangXuLyItemId(item.item_id);
    try {
      const res = await adminApi.retryScrapeRun(activeRunId, { itemId: item.item_id });
      setChiTietData((prev) =>
        prev ? { ...prev, run: res.run, progress: res.progress } : prev,
      );
      toast.ok(`Đã xếp lại chương "${item.chapter_title}" để thử lại.`);
      taiLaiChiTiet();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể thử lại chương này."));
    } finally {
      setDangXuLyItemId(null);
    }
  }

  async function handleBoQuaItem() {
    if (!activeRunId || !hoiBoQuaItem) return;
    setDangXuLyItemId(hoiBoQuaItem.item_id);
    try {
      const res = await adminApi.skipScrapeItem(
        activeRunId,
        hoiBoQuaItem.item_id,
        lyDoBoQua.trim(),
      );
      setChiTietData((prev) =>
        prev ? { ...prev, run: res.run, progress: res.progress } : prev,
      );
      toast.ok(`Đã bỏ qua chương "${hoiBoQuaItem.chapter_title}".`);
      setHoiBoQuaItem(null);
      setLyDoBoQua("");
      taiLaiChiTiet();
    } catch (cause) {
      toast.error(loiApi(cause, "Không thể bỏ qua chương này."));
    } finally {
      setDangXuLyItemId(null);
    }
  }

  return (
    <section className="stack">
      {/* Header & Thong bao Review Queue */}
      <header className="stack-2">
        <h2 className="section-title section-title-icon">
          <IconBook size={19} /> Quét truyện tự động (Universal Scraper)
        </h2>
        <p className="hint">
          Công cụ cào và chuẩn hoá các chương truyện từ nguồn bên ngoài vào hàng đợi kiểm duyệt.
        </p>
      </header>

      {/* Canh bao Review Queue */}
      <div className="card stack-2" style={{ borderLeft: "4px solid var(--accent, #7c5cff)" }}>
        <strong>Hàng đợi kiểm duyệt chương</strong>
        <p className="hint">
          Các chương quét thành công sẽ được xếp vào hàng đợi ở trạng thái <strong>Sẵn sàng duyệt</strong>.
          Đây là bước thu thập và chuẩn hoá nội dung, không tự động xuất bản truyện ra ngoài website.
        </p>
      </div>

      {/* Khoi 1: Nhap URL & Xem truoc / Bat dau quet */}
      <div className="card stack-2">
        <h3 className="section-title">1. Thêm tác vụ quét mới</h3>
        <form onSubmit={handleXemTruoc} className="stack-2">
          <div className="row row-tight" style={{ flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 280 }}
              type="url"
              placeholder="Dán URL trang truyện (vd: https://truyenfull.vn/...)"
              value={inputUrl}
              onChange={(e) => {
                setInputUrl(e.target.value);
                // Sua URL sau khi xem truoc -> huy xac nhan cu, buoc xem
                // truoc lai truoc khi duoc bat dau (xem `handleBatDauQuet`).
                setKetQuaXemTruoc(null);
                setDeXuatNguonMoi(null);
              }}
              disabled={dangXemTruoc || dangBatDau}
            />
            <input
              className="input"
              style={{ width: 140 }}
              type="number"
              min={1}
              placeholder="Giới hạn số chương"
              value={chapterLimit}
              onChange={(e) => setChapterLimit(e.target.value)}
              disabled={dangXemTruoc || dangBatDau}
              title="Để trống để quét toàn bộ chương"
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={dangXemTruoc || !inputUrl.trim()}
            >
              {dangXemTruoc ? "Đang kiểm tra…" : "Xem trước"}
            </button>
          </div>

          {supportedDomains.length > 0 ? (
            <p className="hint">
              Các nguồn hỗ trợ: <strong>{supportedDomains.join(", ")}</strong>
            </p>
          ) : null}
        </form>

        {loiXemTruoc ? (
          <div className="card stack-2" role="alert" style={{ background: "rgba(239, 68, 68, 0.08)" }}>
            <strong>Không thể quét URL này</strong>
            <p className="hint">{loiXemTruoc}</p>
          </div>
        ) : null}

        {ketQuaXemTruoc ? (
          <div className="card stack-2" style={{ background: "rgba(124, 92, 255, 0.05)", borderColor: "var(--accent, #7c5cff)" }}>
            <div className="row row-spread">
              <h4 className="section-title">Kết quả xem trước</h4>
              <span className="tt tt-duyet">Nguồn hợp lệ</span>
            </div>
            <div className="stat-grid admin-luoi">
              <div className="stat">
                <span className="stat-value">{ketQuaXemTruoc.run.series_title || "—"}</span>
                <span className="stat-label">Tên truyện</span>
              </div>
              <div className="stat">
                <span className="stat-value">{ketQuaXemTruoc.run.source_domain || "—"}</span>
                <span className="stat-label">Tên miền</span>
              </div>
              <div className="stat">
                <span className="stat-value">
                  {ketQuaXemTruoc.run.total_discovered || ketQuaXemTruoc.run.estimated_total || 0}
                </span>
                <span className="stat-label">Số chương phát hiện</span>
              </div>
              <div className="stat">
                <span className="stat-value">{ketQuaXemTruoc.run.already_done_count || 0}</span>
                <span className="stat-label">Đã có từ trước</span>
              </div>
            </div>

            <div className="row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={dangBatDau}
                onClick={handleBatDauQuet}
              >
                {dangBatDau ? "Đang khởi tạo…" : "Bắt đầu quét"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={dangBatDau}
                onClick={() => setKetQuaXemTruoc(null)}
              >
                Huỷ
              </button>
            </div>
          </div>
        ) : null}

        {deXuatNguonMoi ? (
          <div className="card stack-2" style={{ background: "rgba(234, 179, 8, 0.06)", borderColor: "#eab308" }}>
            <div className="row row-spread">
              <h4 className="section-title">Phát hiện nguồn mới</h4>
              <span className="tt" style={{ background: "#eab308", color: "#1a1a1a" }}>
                Độ tin cậy:{" "}
                {deXuatNguonMoi.confidence === "high" ? "Cao"
                  : deXuatNguonMoi.confidence === "medium" ? "Trung bình" : "Thấp"}
              </span>
            </div>
            <p className="hint">
              Đây là trang chưa từng được cấu hình sẵn. Hệ thống đã tự phân tích
              cấu trúc trang — hãy xem kỹ bằng chứng bên dưới trước khi xác nhận
              (chưa quét gì, chưa ghi gì).
            </p>
            <div className="stat-grid admin-luoi">
              <div className="stat">
                <span className="stat-value">{deXuatNguonMoi.work_title || "—"}</span>
                <span className="stat-label">Tên truyện (đoán)</span>
              </div>
              <div className="stat">
                <span className="stat-value">{deXuatNguonMoi.author || "—"}</span>
                <span className="stat-label">Tác giả (đoán)</span>
              </div>
              <div className="stat">
                <span className="stat-value">{deXuatNguonMoi.chapter_count_estimate}</span>
                <span className="stat-label">Số chương ước lượng</span>
              </div>
              <div className="stat">
                <span className="stat-value">
                  {deXuatNguonMoi.content_container_candidate || "Chưa xác định"}
                </span>
                <span className="stat-label">Vùng nội dung phát hiện</span>
              </div>
            </div>

            <div className="stack-1">
              <strong className="hint">Bằng chứng:</strong>
              <ul className="hint" style={{ margin: 0, paddingLeft: 20 }}>
                {deXuatNguonMoi.evidence.map((ly_do, idx) => (
                  <li key={idx}>{ly_do}</li>
                ))}
              </ul>
            </div>

            <div className="row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={dangXacNhanNguon || deXuatNguonMoi.confidence === "low"}
                onClick={handleXacNhanNguonMoi}
                title={deXuatNguonMoi.confidence === "low"
                  ? "Độ tin cậy quá thấp — cần một kỹ sư cấu hình thủ công."
                  : undefined}
              >
                {dangXacNhanNguon ? "Đang xác nhận…" : "Xác nhận nguồn này"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={dangXacNhanNguon}
                onClick={() => setDeXuatNguonMoi(null)}
              >
                Huỷ
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {/* Khoi 2: Tien do & Dieu khien tac vu dang chon */}
      {activeRunId && (
        <div className="card stack-2">
          {dangTaiChiTiet && !activeRun ? (
            <DanhSachTrangThai dangTai={true} loi="" rong={false}>{null}</DanhSachTrangThai>
          ) : activeRun ? (
            <>
              <div className="row row-spread" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <div className="stack-2">
                  <h3 className="section-title section-title-icon">
                    <IconLink size={17} /> {activeRun.series_title || activeRun.source_url}
                  </h3>
                  <span className="hint">
                    Nguồn:{" "}
                    <a href={activeRun.source_url} target="_blank" rel="noreferrer">
                      {activeRun.source_domain} ({activeRun.source_url})
                    </a>
                    {" · ID: "}
                    <span className="mono">{activeRun.run_id}</span>
                  </span>
                </div>
                <span className={`tt ${NHAN_TRANG_THAI_RUN[activeRun.status]?.lop ?? "tt-trong"}`}>
                  {NHAN_TRANG_THAI_RUN[activeRun.status]?.chu ?? activeRun.status}
                </span>
              </div>

              {/* Thanh tien do */}
              <div className="stack-2">
                <div className="row row-spread">
                  <span className="hint">Tiến độ cào chương</span>
                  <strong className="mono">{activeProgress?.percent ?? 0}%</strong>
                </div>
                <ProgressBar
                  percent={activeProgress?.percent ?? 0}
                  label={`Tiến độ quét: ${activeProgress?.percent ?? 0}%`}
                />
              </div>

              {/* Thong so dem */}
              <div className="stat-grid admin-luoi">
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.total_discovered ?? activeRun.total_discovered ?? activeRun.estimated_total}
                  </span>
                  <span className="stat-label">Tổng phát hiện</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.done ?? (activeRun.count_review_ready + activeRun.count_skipped)}
                  </span>
                  <span className="stat-label">Đã hoàn thành</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.review_ready ?? activeRun.count_review_ready}
                  </span>
                  <span className="stat-label">Sẵn sàng duyệt</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.pending ?? activeRun.count_pending}
                  </span>
                  <span className="stat-label">Đang chờ quét</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.failed ?? activeRun.count_failed}
                  </span>
                  <span className="stat-label">Lỗi</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {activeProgress?.skipped ?? activeRun.count_skipped}
                  </span>
                  <span className="stat-label">Đã bỏ qua</span>
                </div>
              </div>

              {/* Thong bao loi gan nhat neu co */}
              {activeRun.last_error ? (
                <div className="card stack-2" role="alert" style={{ background: "rgba(239, 68, 68, 0.08)" }}>
                  <strong>Lỗi gần nhất:</strong>
                  <p className="hint">{activeRun.last_error}</p>
                </div>
              ) : null}

              {/* Thanh nut dieu khien */}
              <div className="row row-spread" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <div className="row row-tight" style={{ flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={dangDrive || activeRun.status === "completed" || activeRun.status === "cancelled"}
                    onClick={handleDriveMotChuKy}
                    title="Quét tiếp 1 chu kỳ các chương trong hàng đợi"
                  >
                    {dangDrive ? "Đang quét…" : "Tiếp tục quét (1 chu kỳ)"}
                  </button>

                  {activeRun.status === "running" ? (
                    <button
                      type="button"
                      className={`btn btn-sm ${tuDongChay ? "btn-danger" : ""}`}
                      onClick={() => setTuDongChay((v) => !v)}
                    >
                      {tuDongChay ? "Dừng tự động" : "Tự động chạy liên tục"}
                    </button>
                  ) : null}

                  {(activeRun.count_failed > 0 || activeRun.status === "failed" || activeRun.status === "partial") ? (
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={dangRetryRun}
                      onClick={handleRetryToanBo}
                    >
                      {dangRetryRun ? "Đang xếp lại…" : "Thử lại tất cả lỗi"}
                    </button>
                  ) : null}

                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    disabled={dangTaiChiTiet}
                    onClick={taiLaiChiTiet}
                  >
                    Làm mới
                  </button>
                </div>

                {(activeRun.status === "running" || activeRun.status === "planning") ? (
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    disabled={dangHuyRun}
                    onClick={() => setHoiHuyRun(true)}
                  >
                    Huỷ tác vụ
                  </button>
                ) : null}
              </div>

              {/* Khoi 3: Bang danh sach chuong duyet */}
              <div className="stack-2" style={{ marginTop: "1rem" }}>
                <div className="row row-spread" style={{ flexWrap: "wrap" }}>
                  <h4 className="section-title">Danh sách chương ({activeItems.length})</h4>
                  <div className="seg" role="group" aria-label="Lọc trạng thái chương" style={{ flexWrap: "wrap" }}>
                    {BO_LOC_MUC.map((b) => (
                      <button
                        key={b.khoa || "all"}
                        type="button"
                        className="seg-item"
                        aria-pressed={locTrangThaiMuc === b.khoa}
                        onClick={() => {
                          setLocTrangThaiMuc(b.khoa);
                          setTrangMuc(0);
                        }}
                      >
                        {b.nhan}
                      </button>
                    ))}
                  </div>
                </div>

                <DanhSachTrangThai
                  dangTai={dangTaiChiTiet}
                  loi={loiChiTiet}
                  // CHI thuc su "rong" o trang dau — mot trang SAU rong (vi
                  // du bo-qua/thu-lai lam tong so muc giam vua het trang
                  // cuoi) van phai giu nut phan trang de operator lui lai
                  // duoc, khong bi ket. Phat hien qua review Codex.
                  rong={activeItems.length === 0 && trangMuc === 0}
                  onThuLai={taiLaiChiTiet}
                >
                  <div className="admin-bang-boc">
                    <table className="admin-bang">
                      <thead>
                        <tr>
                          <th scope="col">Chương</th>
                          <th scope="col">Trạng thái</th>
                          <th scope="col">Chi tiết / Lỗi</th>
                          <th scope="col">Số lần thử</th>
                          <th scope="col"><span className="sr-only">Thao tác</span></th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeItems.map((item) => (
                          <tr key={item.item_id}>
                            <td>
                              {item.chapter_url ? (
                                <a href={item.chapter_url} target="_blank" rel="noreferrer">
                                  {item.chapter_number != null ? `Chương ${item.chapter_number}: ` : ""}
                                  {item.chapter_title || "(Không có tiêu đề)"}
                                </a>
                              ) : (
                                <span>
                                  {item.chapter_number != null ? `Chương ${item.chapter_number}: ` : ""}
                                  {item.chapter_title || "(Không có tiêu đề)"}
                                </span>
                              )}
                            </td>
                            <td>
                              <span className={`tt ${NHAN_TRANG_THAI_MUC[item.status]?.lop ?? "tt-trong"}`}>
                                {NHAN_TRANG_THAI_MUC[item.status]?.chu ?? item.status}
                              </span>
                            </td>
                            <td className="hint" style={{ maxWidth: 280 }}>
                              {item.error_message ? (
                                <span style={{ color: "var(--danger, #ef4444)" }}>{item.error_message}</span>
                              ) : item.skipped_reason ? (
                                <span>Bỏ qua: {item.skipped_reason}</span>
                              ) : item.decision ? (
                                <span>{item.decision}</span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="mono">{item.attempts ?? 0}</td>
                            <td>
                              <div className="row row-tight">
                                {item.status === "failed" ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm"
                                    disabled={dangXuLyItemId === item.item_id}
                                    onClick={() => handleRetryItem(item)}
                                  >
                                    {dangXuLyItemId === item.item_id ? "Đang gửi…" : "Thử lại"}
                                  </button>
                                ) : null}
                                {item.status === "pending" || item.status === "failed" ? (
                                  <button
                                    type="button"
                                    className="btn btn-sm btn-ghost"
                                    disabled={dangXuLyItemId === item.item_id}
                                    onClick={() => {
                                      setHoiBoQuaItem(item);
                                      setLyDoBoQua("");
                                    }}
                                  >
                                    Bỏ qua
                                  </button>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Phan trang chuong */}
                  <div className="row row-spread">
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={trangMuc === 0}
                      onClick={() => setTrangMuc((v) => Math.max(0, v - 1))}
                    >
                      ← Trang trước
                    </button>
                    <span className="hint">Trang {trangMuc + 1}</span>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={activeItems.length < SO_MUC_MOI_TRANG}
                      onClick={() => setTrangMuc((v) => v + 1)}
                    >
                      Trang sau →
                    </button>
                  </div>
                </DanhSachTrangThai>
              </div>
            </>
          ) : (
            <DanhSachTrangThai dangTai={false} loi={loiChiTiet || "Không tìm thấy tác vụ."} rong={false} onThuLai={taiLaiChiTiet}>
              {null}
            </DanhSachTrangThai>
          )}
        </div>
      )}

      {/* Khoi 4: Danh sach cac tac vu quet trong he thong */}
      <div className="card stack-2">
        <div className="row row-spread">
          <h3 className="section-title section-title-icon">
            <IconHistory size={17} /> Danh sách tác vụ quét ({danhSachRuns.length})
          </h3>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            disabled={dangTaiRuns}
            onClick={taiLaiDanhSachRuns}
          >
            Làm mới
          </button>
        </div>

        <DanhSachTrangThai
          dangTai={dangTaiRuns}
          loi={loiTaiRuns}
          rong={danhSachRuns.length === 0}
          onThuLai={taiLaiDanhSachRuns}
        >
          <div className="admin-bang-boc">
            <table className="admin-bang">
              <thead>
                <tr>
                  <th scope="col">Truyện</th>
                  <th scope="col">Nguồn</th>
                  <th scope="col">Trạng thái</th>
                  <th scope="col">Tiến độ</th>
                  <th scope="col">Thời gian tạo</th>
                  <th scope="col"><span className="sr-only">Thao tác</span></th>
                </tr>
              </thead>
              <tbody>
                {danhSachRuns.map((r) => {
                  const dangXem = r.run_id === activeRunId;
                  return (
                    <tr
                      key={r.run_id}
                      style={dangXem ? { background: "rgba(124, 92, 255, 0.08)" } : undefined}
                    >
                      <td>
                        <strong>{r.series_title || "(Chưa có tiêu đề)"}</strong>
                        <div className="hint mono" style={{ fontSize: "0.8rem" }}>
                          {r.run_id}
                        </div>
                      </td>
                      <td>
                        <a href={r.source_url} target="_blank" rel="noreferrer" className="hint">
                          {r.source_domain}
                        </a>
                      </td>
                      <td>
                        <span className={`tt ${NHAN_TRANG_THAI_RUN[r.status]?.lop ?? "tt-trong"}`}>
                          {NHAN_TRANG_THAI_RUN[r.status]?.chu ?? r.status}
                        </span>
                      </td>
                      <td className="mono">
                        {r.count_review_ready}/{r.total_discovered || r.estimated_total || 0}
                        {r.count_failed > 0 ? (
                          <span style={{ color: "var(--danger, #ef4444)", marginLeft: 4 }}>
                            ({r.count_failed} lỗi)
                          </span>
                        ) : null}
                      </td>
                      <td className="hint">
                        {r.created_at ? new Date(r.created_at).toLocaleString("vi-VN") : "—"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className={`btn btn-sm ${dangXem ? "btn-primary" : ""}`}
                          onClick={() => {
                            setSelectedRunId(r.run_id);
                            setTrangMuc(0);
                          }}
                        >
                          {dangXem ? "Đang xem" : "Xem"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </DanhSachTrangThai>
      </div>

      {/* Hop thoai xac nhan bo qua chuong */}
      <ConfirmDialog
        open={Boolean(hoiBoQuaItem)}
        title={`Bỏ qua "${hoiBoQuaItem?.chapter_title}"?`}
        body={
          <div className="stack-2">
            <p className="hint">
              Chương này sẽ được đánh dấu trạng thái <strong>Đã bỏ qua</strong> và không đưa vào hàng đợi duyệt nữa.
            </p>
            <textarea
              className="textarea textarea-sm"
              placeholder="Lý do bỏ qua (không bắt buộc)"
              value={lyDoBoQua}
              onChange={(e) => setLyDoBoQua(e.target.value)}
              maxLength={500}
              rows={2}
            />
          </div>
        }
        confirmLabel="Bỏ qua chương"
        danger
        busy={dangXuLyItemId === hoiBoQuaItem?.item_id}
        onConfirm={handleBoQuaItem}
        onCancel={() => {
          setHoiBoQuaItem(null);
          setLyDoBoQua("");
        }}
      />

      {/* Hop thoai xac nhan huy run */}
      <ConfirmDialog
        open={hoiHuyRun}
        title={`Huỷ tác vụ quét "${activeRun?.series_title || activeRun?.run_id}"?`}
        body="Tác vụ sẽ dừng quét các chương tiếp theo. Các chương đã quét thành công vẫn sẽ được giữ lại."
        confirmLabel="Huỷ tác vụ"
        danger
        busy={dangHuyRun}
        onConfirm={handleHuyRun}
        onCancel={() => setHoiHuyRun(false)}
      />
    </section>
  );
}
