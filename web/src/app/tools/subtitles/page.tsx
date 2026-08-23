"use client";

/**
 * Subtitle Studio — cong cu phu de/dich video CUC BO (overnight Phase 4, V6).
 *
 * THAM KHAO san pham/kien truc tu subvid.app (github.com/midudev/subvid.app,
 * giay phep PolyForm Noncommercial 1.0.0) — KHONG sao chep/vendor/dich BAT
 * KY dong code nao tu do. Toan bo trien khai duoi day la CUA FANFIC, viet
 * doc lap tu mo ta hanh vi trong dac ta, khong doc source cua du an tham
 * khao.
 *
 * LOCAL-FIRST THAT SU: video KHONG BAO GIO roi khoi may nguoi dung —
 * `URL.createObjectURL(file)` tao mot URL cuc bo cho `<video>`, khong co
 * `fetch`/upload nao dong toi file do o BAT KY dau trong file nay. Chi
 * VAN BAN (dong phu de) moi roi may khi dung che do "Dịch AI" (Phan 4E).
 *
 * DA LAM (Phan 4A/4B/4D/4G/4H): tai video/audio cuc bo, nhap phu de co san
 * (SRT/VTT — xem ghi chu o `NhapPhuDe`), soan phu de (sua gio/chu, tach/gop/
 * xoa/them), xuat SRT/VTT, luu/mo du an cuc bo (IndexedDB).
 *
 * CHUA LAM, ghi trung thuc thay vi gia vo (Phan 4C/4G/4I):
 *   - Nhan dien giong noi cuc bo (Whisper-trong-trinh-duyet) — CHUA co. Nguon
 *     phu de duy nhat hien nay la NHAP file co san hoac go tay.
 *   - "Dịch cục bộ" (NLLB trong trinh duyet) — CHUA co, nut bi khoa va ghi
 *     ro ly do. Chi co "Dịch AI" (gui van ban qua Fanfic Translation).
 *   - Ghi phu de VAO video (burned-in export) — CHUA co, chi co SRT/VTT.
 *   - Google Drive — CHUA co, xem bao cao overnight ve scope OAuth can xin.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  gopVoiPhanDoanSau,
  idPhanDoanMoi,
  nhapSrtHoacVtt,
  sapXep,
  suaThoiGian,
  suaVanBan,
  tachPhanDoan,
  taoPhanDoan,
  xoaPhanDoan,
  xuatSrt,
  xuatVtt,
  type SubtitleSegment,
} from "@/lib/subtitles/model";
import { dichDongPhuDe, SubtitleTranslateError } from "@/lib/subtitles/translate";
import {
  danhSachDuAn,
  docDuAn,
  luuDuAn,
  xoaDuAn,
  type SubtitleProject,
} from "@/lib/subtitles/projectStore";
import { SegmentRow } from "@/components/subtitles/SegmentRow";
import { useToast } from "@/lib/toast";
import { IconFilm } from "@/components/Icons";

/** Tran lich su undo/redo — du de nguoi dung lam-lai sai vai buoc, khong
    giu vo han (moi snapshot la ban sao mang phan doan). */
const TRAN_LICH_SU = 100;

function taiTepThanhVanBan(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function formatBytesGon(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const don_vi = ["KB", "MB", "GB"];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < don_vi.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(1)} ${don_vi[i]}`;
}

export default function SubtitleStudioPage() {
  const toast = useToast();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  const [tenFile, setTenFile] = useState("");
  const [kichThuoc, setKichThuoc] = useState(0);
  const [loaiFile, setLoaiFile] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [thoiLuong, setThoiLuong] = useState(0);
  const [viTriHienTai, setViTriHienTai] = useState(0);
  const [dangPhat, setDangPhat] = useState(false);

  const [segments, setSegmentsRaw] = useState<SubtitleSegment[]>([]);
  const lichSu = useRef<SubtitleSegment[][]>([]);
  const lichSuSau = useRef<SubtitleSegment[][]>([]);
  // Ref KHONG kich re-render — hai co nay la ban sao PHAN ANH do dai hai ref
  // tren, chi de `disabled` doc duoc trong luc render (khong doc thang
  // `.current` cua ref trong JSX — vi pham quy tac react-hooks/refs).
  const [coTheHoanTac, setCoTheHoanTac] = useState(false);
  const [coTheLamLaiTiep, setCoTheLamLaiTiep] = useState(false);

  const [tenDuAn, setTenDuAn] = useState("");
  const [danhSachLuu, setDanhSachLuu] = useState<SubtitleProject[]>([]);
  const [dangDich, setDangDich] = useState(false);
  const [tienDoDich, setTienDoDich] = useState<{ xong: number; tong: number } | null>(null);

  /* -------------------------------------------------------- doi phan doan */

  const doiSegments = useCallback(
    (fn: (hienTai: SubtitleSegment[]) => SubtitleSegment[], ghiLichSu = true) => {
      setSegmentsRaw((hienTai) => {
        const moi = sapXep(fn(hienTai));
        if (ghiLichSu) {
          lichSu.current = [...lichSu.current, hienTai].slice(-TRAN_LICH_SU);
          lichSuSau.current = [];
          setCoTheHoanTac(true);
          setCoTheLamLaiTiep(false);
        }
        return moi;
      });
    },
    [],
  );

  const lamLai = useCallback(() => {
    if (lichSu.current.length === 0) return;
    setSegmentsRaw((hienTai) => {
      const truoc = lichSu.current[lichSu.current.length - 1];
      lichSu.current = lichSu.current.slice(0, -1);
      lichSuSau.current = [...lichSuSau.current, hienTai];
      setCoTheHoanTac(lichSu.current.length > 0);
      setCoTheLamLaiTiep(true);
      return truoc;
    });
  }, []);

  const lamLaiTiep = useCallback(() => {
    if (lichSuSau.current.length === 0) return;
    setSegmentsRaw((hienTai) => {
      const sau = lichSuSau.current[lichSuSau.current.length - 1];
      lichSuSau.current = lichSuSau.current.slice(0, -1);
      lichSu.current = [...lichSu.current, hienTai];
      setCoTheHoanTac(true);
      setCoTheLamLaiTiep(lichSuSau.current.length > 0);
      return sau;
    });
  }, []);

  /* -------------------------------------------------------------- video */

  const chonFile = useCallback((file: File | null) => {
    if (!file) return;
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    const url = URL.createObjectURL(file);
    objectUrlRef.current = url;
    setVideoUrl(url);
    setTenFile(file.name);
    setKichThuoc(file.size);
    setLoaiFile(file.type || "không rõ");
    setViTriHienTai(0);
    setThoiLuong(0);
  }, []);

  useEffect(() => {
    // Thu hoi Object URL khi roi trang — KHONG giu tham chieu toi file cuc
    // bo lau hon can thiet (Phan 4J: "Revoke object URLs").
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const tua = useCallback((giay: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = giay;
    setViTriHienTai(giay);
  }, []);

  /* --------------------------------------------------------- nhap phu de */

  const nhapPhuDe = useCallback(
    async (file: File | null) => {
      if (!file) return;
      const text = await taiTepThanhVanBan(file);
      const ra = nhapSrtHoacVtt(text);
      if (ra.length === 0) {
        toast.error("Không đọc được phụ đề từ tệp này — kiểm tra định dạng SRT/VTT.");
        return;
      }
      doiSegments(() => ra);
      toast.ok(`Đã nhập ${ra.length} đoạn phụ đề.`);
    },
    [doiSegments, toast],
  );

  const themDoanTaiViTriHienTai = useCallback(() => {
    const batDau = viTriHienTai;
    const ketThuc = Math.min(thoiLuong || batDau + 2, batDau + 2);
    doiSegments((hienTai) => [...hienTai, taoPhanDoan(batDau, Math.max(ketThuc, batDau + 0.5))]);
  }, [viTriHienTai, thoiLuong, doiSegments]);

  /* ---------------------------------------------------------------- xuat */

  const taiXuong = useCallback((noiDung: string, ten: string, mime: string) => {
    const blob = new Blob([noiDung], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = ten;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  /* --------------------------------------------------------------- du an */

  const taiDanhSachDuAn = useCallback(() => {
    danhSachDuAn().then(setDanhSachLuu).catch(() => {});
  }, []);

  useEffect(() => {
    taiDanhSachDuAn();
  }, [taiDanhSachDuAn]);

  const luu = useCallback(async () => {
    const ten = tenDuAn.trim();
    if (!ten) {
      toast.error("Đặt tên dự án trước khi lưu.");
      return;
    }
    const duAn: SubtitleProject = {
      id: ten,
      name: ten,
      updatedAt: new Date().toISOString(),
      segments,
      videoFingerprint: tenFile
        ? { fileName: tenFile, sizeBytes: kichThuoc, durationSeconds: thoiLuong }
        : null,
      targetLanguage: "vi",
    };
    await luuDuAn(duAn);
    taiDanhSachDuAn();
    toast.ok(`Đã lưu dự án “${ten}” trên máy này.`);
  }, [tenDuAn, segments, tenFile, kichThuoc, thoiLuong, toast, taiDanhSachDuAn]);

  const mo = useCallback(
    async (id: string) => {
      const duAn = await docDuAn(id);
      if (!duAn) return;
      setTenDuAn(duAn.name);
      doiSegments(() => duAn.segments, false);
      lichSu.current = [];
      lichSuSau.current = [];
      setCoTheHoanTac(false);
      setCoTheLamLaiTiep(false);
      toast.ok(`Đã mở dự án “${duAn.name}”. Nhớ chọn lại video/audio gốc.`);
    },
    [doiSegments, toast],
  );

  const xoa = useCallback(
    async (id: string) => {
      await xoaDuAn(id);
      taiDanhSachDuAn();
    },
    [taiDanhSachDuAn],
  );

  /* ------------------------------------------------------------- dich AI */

  const dichAI = useCallback(async () => {
    if (segments.length === 0) return;
    setDangDich(true);
    setTienDoDich({ xong: 0, tong: segments.length });
    try {
      const goc = segments.map((s) => s.text);
      const dich = await dichDongPhuDe(goc, (xong, tong) =>
        setTienDoDich({ xong, tong }));
      doiSegments((hienTai) =>
        hienTai.map((s, i) => ({ ...s, text: dich[i] ?? s.text })));
      toast.ok("Đã dịch xong — bản gốc đã được thay bằng bản dịch.");
    } catch (cause) {
      const msg = cause instanceof SubtitleTranslateError
        ? cause.message
        : "Không dịch được — thử lại sau.";
      toast.error(msg);
    } finally {
      setDangDich(false);
      setTienDoDich(null);
    }
  }, [segments, doiSegments, toast]);

  /* -------------------------------------------------------------- phim tat */

  useEffect(() => {
    const phim = (e: KeyboardEvent) => {
      const dich = document.activeElement;
      const dangGoChu =
        dich instanceof HTMLTextAreaElement || dich instanceof HTMLInputElement;
      if (dangGoChu) return;
      if (e.code === "Space") {
        e.preventDefault();
        const v = videoRef.current;
        if (!v) return;
        if (v.paused) void v.play();
        else v.pause();
      } else if (e.key === "z" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (e.shiftKey) lamLaiTiep();
        else lamLai();
      }
    };
    window.addEventListener("keydown", phim);
    return () => window.removeEventListener("keydown", phim);
  }, [lamLai, lamLaiTiep]);

  const doanDangHoatDong = useMemo(
    () => segments.find((s) => viTriHienTai >= s.start && viTriHienTai < s.end)?.id ?? "",
    [segments, viTriHienTai],
  );

  return (
    <div className="page">
      <header className="stack-2">
        <span className="eyebrow eyebrow-icon">
          <IconFilm size={17} /> Công cụ
        </span>
        <h1 className="page-title">Subtitle Studio</h1>
        <p className="hint lead-narrow">
          Soạn phụ đề cho video của bạn — video luôn ở trên máy bạn, không
          bao giờ được tải lên Fanfic. Nhập phụ đề có sẵn (SRT/VTT) hoặc gõ
          tay, chỉnh thời gian/lời thoại, rồi xuất lại SRT/VTT.
        </p>
      </header>

      <section className="card stack-2">
        <h2 className="section-title">1. Chọn video/audio</h2>
        <label className="btn btn-sm">
          Chọn tệp
          <input
            type="file"
            accept="video/*,audio/*"
            className="sr-only"
            onChange={(e) => chonFile(e.target.files?.[0] ?? null)}
            aria-label="Chọn tệp video hoặc audio"
          />
        </label>
        {tenFile ? (
          <p className="hint">
            {tenFile} · {formatBytesGon(kichThuoc)} · {loaiFile}
            {thoiLuong ? ` · ${thoiLuong.toFixed(1)}s` : ""}
          </p>
        ) : null}
        {videoUrl ? (
          <video
            ref={videoRef}
            src={videoUrl}
            controls
            className="sub-video"
            onLoadedMetadata={(e) => setThoiLuong(e.currentTarget.duration || 0)}
            onTimeUpdate={(e) => setViTriHienTai(e.currentTarget.currentTime)}
            onPlay={() => setDangPhat(true)}
            onPause={() => setDangPhat(false)}
          />
        ) : (
          <p className="hint">Chưa chọn tệp nào.</p>
        )}
      </section>

      <section className="card stack-2">
        <h2 className="section-title">2. Phụ đề nguồn</h2>
        <p className="hint">
          Chưa có nhận diện giọng nói cục bộ trong bản này — nhập một tệp
          SRT/VTT có sẵn, hoặc thêm từng đoạn bằng tay khi phát video.
        </p>
        <div className="row row-tight">
          <label className="btn btn-sm">
            Nhập SRT/VTT
            <input
              type="file"
              accept=".srt,.vtt,text/plain"
              className="sr-only"
              onChange={(e) => void nhapPhuDe(e.target.files?.[0] ?? null)}
            />
          </label>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={themDoanTaiViTriHienTai}
            disabled={!videoUrl}
          >
            + Thêm đoạn tại {viTriHienTai.toFixed(1)}s
          </button>
          <span className="spacer" />
          <button type="button" className="btn btn-sm" onClick={lamLai}
                  disabled={!coTheHoanTac}>
            ↶ Hoàn tác
          </button>
          <button type="button" className="btn btn-sm" onClick={lamLaiTiep}
                  disabled={!coTheLamLaiTiep}>
            ↷ Làm lại
          </button>
        </div>
      </section>

      {segments.length > 0 ? (
        <section className="stack-2">
          <div className="row-between">
            <h2 className="section-title">3. Soạn phụ đề ({segments.length} đoạn)</h2>
            <span className="hint" role="status">
              {dangPhat ? "Đang phát" : "Đã tạm dừng"}
            </span>
          </div>
          <div className="stack sub-list">
            {segments.map((s, i) => (
              <SegmentRow
                key={s.id}
                segment={s}
                dangHoatDong={s.id === doanDangHoatDong}
                onSeek={tua}
                onSuaVanBan={(text) => doiSegments((h) => suaVanBan(h, s.id, text))}
                onSuaThoiGian={(truong, giay) =>
                  doiSegments((h) => suaThoiGian(h, s.id, truong, giay))}
                onTach={() => doiSegments((h) => tachPhanDoan(h, s.id, viTriHienTai))}
                onGop={() => doiSegments((h) => gopVoiPhanDoanSau(h, s.id))}
                onXoa={() => doiSegments((h) => xoaPhanDoan(h, s.id))}
                coTheGop={i < segments.length - 1}
              />
            ))}
          </div>
        </section>
      ) : null}

      <section className="card stack-2">
        <h2 className="section-title">4. Dịch</h2>
        <div className="row row-tight">
          <button
            type="button"
            className="btn btn-primary"
            onClick={dichAI}
            disabled={segments.length === 0 || dangDich}
          >
            {dangDich ? <span className="spinner" aria-hidden="true" /> : null}
            Dịch AI sang tiếng Việt
          </button>
          <button type="button" className="btn" disabled title="Chưa khả dụng — cần mô hình dịch chạy trong trình duyệt, chưa có trong bản này">
            Dịch cục bộ (riêng tư) — chưa khả dụng
          </button>
        </div>
        {tienDoDich ? (
          <p className="hint" role="status">
            Đang dịch {tienDoDich.xong}/{tienDoDich.tong} đoạn…
          </p>
        ) : null}
        <p className="hint">
          <strong>Dịch AI</strong> chỉ gửi VĂN BẢN từng dòng phụ đề sang hệ
          thống dịch của Fanfic — video không rời khỏi máy bạn.{" "}
          <strong>Dịch cục bộ</strong> (khi có) sẽ chạy hoàn toàn trong trình
          duyệt, không gửi gì đi cả — hiện chưa có trong bản này.
        </p>
      </section>

      <section className="card stack-2">
        <h2 className="section-title">5. Xuất & lưu dự án</h2>
        <div className="row row-tight">
          <button
            type="button"
            className="btn"
            disabled={segments.length === 0}
            onClick={() => taiXuong(xuatSrt(segments), `${tenFile || "phu-de"}.srt`,
                                   "application/x-subrip")}
          >
            Tải .srt
          </button>
          <button
            type="button"
            className="btn"
            disabled={segments.length === 0}
            onClick={() => taiXuong(xuatVtt(segments), `${tenFile || "phu-de"}.vtt`,
                                   "text/vtt")}
          >
            Tải .vtt
          </button>
          <span className="hint" title="Cần ghép phụ đề trực tiếp vào khung hình video — chưa có trong bản này, dùng .srt/.vtt với trình phát hỗ trợ phụ đề rời">
            Xuất video có phụ đề sẵn — chưa khả dụng
          </span>
        </div>

        <div className="row row-tight">
          <input
            className="input"
            placeholder="Tên dự án…"
            value={tenDuAn}
            onChange={(e) => setTenDuAn(e.target.value)}
          />
          <button type="button" className="btn btn-primary" onClick={() => void luu()}>
            Lưu dự án trên máy
          </button>
        </div>

        {danhSachLuu.length > 0 ? (
          <div className="stack-2">
            <span className="label">Dự án đã lưu trên máy này</span>
            {danhSachLuu.map((d) => (
              <div key={d.id} className="row-between">
                <span>
                  {d.name} <span className="hint">({d.segments.length} đoạn)</span>
                </span>
                <span className="row row-tight">
                  <button type="button" className="btn btn-sm" onClick={() => void mo(d.id)}>
                    Mở
                  </button>
                  <button type="button" className="btn btn-sm btn-danger"
                          onClick={() => void xoa(d.id)}>
                    Xoá
                  </button>
                </span>
              </div>
            ))}
          </div>
        ) : null}
        <p className="hint">
          Dự án lưu ngay trên trình duyệt này (IndexedDB) — chỉ lưu phụ đề và
          tên tệp video để nhận lại, KHÔNG lưu chính video. Đổi máy/trình
          duyệt sẽ không thấy dự án cũ.
        </p>
      </section>

      <p className="hint">
        <Link href="/studio">← Về Audio Studio</Link>
      </p>
    </div>
  );
}
