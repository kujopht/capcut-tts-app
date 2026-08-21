"use client";

/**
 * Phu de dong bo — V4, Phan 2F-2K (overnight Phase 2).
 *
 * Doc `api.getChapterTranscript()` mot lan, roi bam theo
 * `AudioEngine.trangThai.thoiDiem` de biet doan nao dang doc — KHONG polling,
 * chi tinh lai moi lan `thoiDiem` doi (engine da phat `timeupdate` san).
 *
 * TIM DOAN DANG DOC bang TIM NHI PHAN tren mang da sap xep theo `start_ms`
 * (segments luon sap theo thoi gian — dam bao boi `build_transcript` o
 * backend) — O(log n) thay vi quet tuyen tinh moi lan `timeupdate` ban, quan
 * trong voi chuong dai hang tram doan.
 *
 * TU CUON THEO (auto-follow): doan dang doc duoc cuon vao vung thay duoc.
 * Nguoi dung tu cuon tay thi TAT auto-follow ngay (khong danh nhau voi thao
 * tac cua ho) va hien nut "↓ Theo lời đọc" de bat lai khi ho muon.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, type ChapterTranscript, type TranscriptSegment } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { useAudioEngineOptional } from "@/components/AudioEngine";
import { Loading } from "@/components/ui";

/** Tim CHI SO doan co `start_ms <= msHienTai < end_ms`, hoac doan GAN NHAT
    truoc do neu dang o khoang trong giua hai doan (do uoc luong khong khop
    tuyet doi 100%). Tim nhi phan tren mang da sap theo `start_ms`. */
function timChiSoDoanDangDoc(segments: TranscriptSegment[], msHienTai: number): number {
  if (segments.length === 0) return -1;
  let lo = 0;
  let hi = segments.length - 1;
  let ung_vien = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segments[mid].start_ms <= msHienTai) {
      ung_vien = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ung_vien;
}

export function SyncedTranscript({ chapterId }: { chapterId: string }) {
  const fetchTranscript = useCallback(
    () => api.getChapterTranscript(chapterId),
    [chapterId],
  );
  const { data, loading, error } = useAsyncData<ChapterTranscript>(fetchTranscript);
  const engine = useAudioEngineOptional();

  const [dangTuCuon, setDangTuCuon] = useState(true);
  const khungRef = useRef<HTMLDivElement | null>(null);
  const doanDangHoatDongRef = useRef<HTMLButtonElement | null>(null);
  /** Bo qua MOT lan cuon sinh ra boi CHINH auto-follow — tranh no tu kich
      hoat trinh xu ly `onScroll` roi tu tat chinh minh. */
  const boQuaCuonKeTiep = useRef(false);

  const segments = useMemo(
    () => (data && data.available ? data.segments : []),
    [data],
  );

  const laBaiCuaMinh = engine?.trangThai.chapterId === chapterId;
  const msHienTai = laBaiCuaMinh ? Math.round((engine?.trangThai.thoiDiem ?? 0) * 1000) : 0;
  const chiSoDangDoc = useMemo(
    () => (laBaiCuaMinh ? timChiSoDoanDangDoc(segments, msHienTai) : -1),
    [segments, msHienTai, laBaiCuaMinh],
  );

  /* Cuon doan dang doc vao vung thay duoc — chi khi auto-follow dang bat. */
  useEffect(() => {
    if (!dangTuCuon || chiSoDangDoc < 0) return;
    const el = doanDangHoatDongRef.current;
    if (!el) return;
    const giamChuyenDong =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    boQuaCuonKeTiep.current = true;
    el.scrollIntoView({
      block: "center",
      behavior: giamChuyenDong ? "auto" : "smooth",
    });
    // Nhip cuon smooth co the mat vai tram ms — giu co ngan chan du lau de
    // khong hieu nham chinh no la "nguoi dung vua cuon tay".
    const hen = window.setTimeout(() => {
      boQuaCuonKeTiep.current = false;
    }, 500);
    return () => window.clearTimeout(hen);
  }, [chiSoDangDoc, dangTuCuon]);

  const nguoiDungTuCuon = useCallback(() => {
    if (boQuaCuonKeTiep.current) return;
    setDangTuCuon(false);
  }, []);

  const seek = useCallback(
    (segment: TranscriptSegment) => {
      if (!laBaiCuaMinh || !engine) return;
      engine.dieuKhien.tua(segment.start_ms / 1000);
    },
    [engine, laBaiCuaMinh],
  );

  if (loading) {
    return (
      <div className="synced-transcript synced-transcript-trong">
        <Loading label="Đang tải phụ đề…" />
      </div>
    );
  }

  if (error || !data || !data.available) {
    return (
      <p className="hint synced-transcript-trong" role="status">
        Transcript đồng bộ chưa có cho bản audio này.
      </p>
    );
  }

  if (segments.length === 0) {
    return (
      <p className="hint synced-transcript-trong" role="status">
        Chương này chưa có nội dung để hiển thị phụ đề.
      </p>
    );
  }

  return (
    <div className="synced-transcript-wrap">
      <div
        className="synced-transcript"
        ref={khungRef}
        onWheel={nguoiDungTuCuon}
        onTouchMove={nguoiDungTuCuon}
        role="list"
        aria-label="Phụ đề đồng bộ"
      >
        {segments.map((doan, i) => {
          const dangDoc = i === chiSoDangDoc;
          return (
            <button
              key={`${doan.start_ms}-${i}`}
              ref={dangDoc ? doanDangHoatDongRef : undefined}
              type="button"
              role="listitem"
              className={`synced-seg${dangDoc ? " synced-seg-active" : ""}`}
              aria-current={dangDoc ? "true" : undefined}
              disabled={!laBaiCuaMinh}
              onClick={() => seek(doan)}
            >
              {doan.text}
            </button>
          );
        })}
      </div>

      {!dangTuCuon ? (
        <button
          type="button"
          className="btn btn-sm synced-transcript-resume"
          onClick={() => setDangTuCuon(true)}
        >
          <span aria-hidden="true">↓</span> Theo lời đọc
        </button>
      ) : null}

      <p className="hint synced-transcript-do-chinh-xac">
        Thời lượng từng phần chính xác (đo thật); thời điểm từng câu bên
        trong là ước lượng theo tỷ lệ số ký tự.
      </p>
    </div>
  );
}
