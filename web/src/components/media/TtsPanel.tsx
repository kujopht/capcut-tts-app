"use client";

/**
 * TAO LOI DOC — ngay trong trinh soan, khong phai o mot trang khac.
 *
 * §7: quy trinh chuan khong duoc bat nguoi dung roi khoi Media Studio. Do la
 * diem chinh cua ca dot nay — truoc day muon co loi doc thi phai sang
 * `/studio/audio`, tao, tai xuong, roi quay lai tai len.
 *
 * GIONG lay tu SO DANG KY THAT (`/api/voices` -> `defaultVoiceId`), khong go
 * cung mot chuoi id nao. §7 noi "prefer Ngọc Huyền ... but use the actual
 * voice registry rather than hardcoding a guessed identifier" — va `voices.ts`
 * da co dung phep chon do, kem thu tu de xuat do MAY CHU cap.
 */

import { useCallback, useMemo, useState } from "react";
import { type TtsJob, type Voice } from "@/lib/api";
import {
  ALL_VOICES_LABEL,
  RECOMMENDED_LABEL,
  voiceOptionLabel,
  voiceSections,
} from "@/lib/voices";
import { JobProgress } from "@/components/JobProgress";

export interface YeuCauTts {
  tieuDe: string;
  vanBan: string;
  giong: string;
  tocDo: string;
}

/** Toc do doc — cung thang voi Audio Studio cu, de nguoi quen khong phai hoc lai. */
const TOC_DO = ["0.75", "0.9", "1.0", "1.1", "1.25", "1.5"];

/**
 * Tran ky tu cho MOT lan tao — bao toan tu Audio Studio cu.
 *
 * Khong co tran nay, dan ca mot chuong (hoac ca mot truyen) vao roi bam Tao
 * se sinh MOT job khong lo ma nguoi dung khong duoc canh bao truoc, va cang
 * dai thi cang de cham tran cua nha cung cap TTS o phia may chu.
 */
const MAX_CHARS = 20_000;
/** Bat dau canh bao truoc khi cham tran, khong doi den luc da vuot. */
const CANH_BAO_TAI = 0.85;

export function TtsPanel({
  voices, giong, onGiong, dangTao, loi, onTao, job,
}: {
  voices: Voice[];
  giong: string;
  onGiong: (v: string) => void;
  dangTao: boolean;
  loi: string;
  onTao: (y: YeuCauTts) => void;
  /**
   * Job dang chay, neu co — ve bang `<JobProgress>` dung chung, khong phai
   * mot thanh tien do rieng cua Media Studio. Hai thanh tien do trong mot
   * san pham la hai cho ke chuyen khac nhau.
   */
  job: TtsJob | null;
}) {
  const [tieuDe, datTieuDe] = useState("");
  const [vanBan, datVanBan] = useState("");
  const [tocDo, datTocDo] = useState("1.0");

  /*
    Hai nhom, va nhom "de xuat" dung TRUOC — thu tu trong do do MAY CHU cap
    (`recommended_order`, lay tu `desktop_app/providers/recommended.py`).
    Frontend khong tu sap xep lai: §7 noi "use the actual voice registry
    rather than hardcoding a guessed identifier", va thu tu cung la mot phan
    cua so dang ky do.
  */
  const muc = useMemo(() => {
    const { recommended, all } = voiceSections(voices);
    const ra: { label: string; voices: Voice[] }[] = [];
    if (recommended.length > 0) {
      ra.push({ label: RECOMMENDED_LABEL, voices: recommended });
    }
    if (all.length > 0) ra.push({ label: ALL_VOICES_LABEL, voices: all });
    return ra;
  }, [voices]);
  const soKyTu = vanBan.trim().length;
  const vuotTran = soKyTu > MAX_CHARS;
  const guiDuoc = soKyTu > 0 && !vuotTran && Boolean(giong) && !dangTao;

  const gui = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!guiDuoc) return;
      onTao({ tieuDe: tieuDe.trim(), vanBan, giong, tocDo });
    },
    [guiDuoc, giong, onTao, tieuDe, tocDo, vanBan],
  );

  return (
    <form className="tts" onSubmit={gui}>
      <h3 className="tts-ten">Tạo lời đọc</h3>

      <label className="field">
        <span className="field-nhan">Tiêu đề</span>
        <input
          className="input"
          value={tieuDe}
          onChange={(e) => datTieuDe(e.target.value)}
          placeholder="Chương 1 — Gió đêm…"
          maxLength={120}
        />
      </label>

      <label className="field">
        <span className="field-nhan">Văn bản</span>
        <textarea
          className="input tts-van-ban"
          value={vanBan}
          onChange={(e) => datVanBan(e.target.value)}
          placeholder="Dán đoạn văn cần đọc…"
          rows={7}
        />
        <span className={vuotTran ? "trang-thai-loi" : "hint"}>
          {soKyTu.toLocaleString("vi-VN")} / {MAX_CHARS.toLocaleString("vi-VN")} ký tự
          {vuotTran
            ? ` — vượt quá ${MAX_CHARS.toLocaleString("vi-VN")} ký tự. Hãy cắt bớt hoặc chia thành nhiều phần.`
            : soKyTu > MAX_CHARS * CANH_BAO_TAI
              ? " — sắp chạm giới hạn"
              : ""}
        </span>
      </label>

      <div className="tts-hang">
        <label className="field">
          <span className="field-nhan">Giọng</span>
          <select
            className="input"
            value={giong}
            onChange={(e) => onGiong(e.target.value)}
          >
            {muc.map((m) => (
              <optgroup key={m.label} label={m.label}>
                {m.voices.map((v) => (
                  <option key={v.voice_id} value={v.voice_id}>
                    {voiceOptionLabel(v)}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        <label className="field tts-toc">
          <span className="field-nhan">Tốc độ</span>
          <select
            className="input"
            value={tocDo}
            onChange={(e) => datTocDo(e.target.value)}
          >
            {TOC_DO.map((t) => (
              <option key={t} value={t}>{t}×</option>
            ))}
          </select>
        </label>
      </div>

      {loi ? <p className="trang-thai-loi">{loi}</p> : null}
      {job ? (
        <JobProgress job={job} tieuDe="Tiến trình tạo lời đọc" ghiChu={<GhiChuJob job={job} />} />
      ) : null}

      {/*
        MOT nut duy nhat lam ca hai viec, khong them mot nut "Thử lại" rieng:
        van ban/giong VAN CON nguyen sau khi job that bai (khong tu xoa),
        nen nham nhac lai chinh nut nay la du — no chi doi CHU de noi ro dang
        lam gi, dung nhu Audio Studio cu.
      */}
      <button type="submit" className="btn btn-primary" disabled={!guiDuoc}>
        {dangTao
          ? "Đang tạo…"
          : job?.status === "failed" ? "Thử lại" : "Tạo lời đọc"}
      </button>
    </form>
  );
}

/**
 * Ghi chu di kem theo trang thai job — bao toan tu Audio Studio cu.
 *
 * `pending` + giong `piper:` la giong chay tren MAY CHU rieng (khong phai
 * may nguoi dung — xem `docs/GCE-WORKER-CAPACITY.md`), va may do xu ly TUNG
 * job mot. Cho la binh thuong, khong phai hong; mot thanh tien do quay mai
 * ma khong giai thich thi nguoi dung chi biet la hong.
 *
 * `failed` phai noi ro LUAT CUNG cua he thong (CLAUDE.md): tong hop that bai
 * KHONG duoc am tham doi giong. Thieu cau nay thi nguoi dung co the tuong
 * audio nhan duoc la dung giong ho da chon.
 */
function GhiChuJob({ job }: { job: TtsJob }) {
  if (job.status === "pending") {
    return (
      <p className="hint">
        {job.voice_id.startsWith("piper:")
          ? "Đã nhận yêu cầu và đang xếp hàng chờ máy chủ tạo giọng. Máy chủ xử lý lần lượt từng bản nên có thể phải chờ; bản của bạn vẫn được giữ nguyên và không bị đổi sang giọng khác. Bạn có thể đóng trang này."
          : "Đã nhận yêu cầu, đang chờ tới lượt xử lý."}
      </p>
    );
  }
  if (job.status === "failed") {
    return (
      <p className="hint">
        Hệ thống không tự đổi sang giọng khác. Bạn có thể thử lại với cùng
        giọng, hoặc chọn giọng khác rồi tạo lại.
      </p>
    );
  }
  return null;
}
