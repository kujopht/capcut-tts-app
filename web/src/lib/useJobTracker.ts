"use client";

/**
 * Vong theo doi job TTS — MOT ban duy nhat cho ca `/write` va `/studio`.
 *
 * VI SAO CO TEP NAY: hai trang tung tu viet vong poll rieng. Cac ban va cua
 * PR #11/#12/#13 (khoi phuc sau reload, nhip dem lam vong poll thuc su lap,
 * bao tong so phan ngay tu dau) chi duoc ap vao ban cua `/write`. `/studio` o
 * lai phia sau: van `percent={activeJob.progress || 8}` — mot con so 8% khong
 * den tu dau ca — va chi theo doi DUNG MOT job.
 *
 * Gio khong con hai ban de lech nhau nua.
 *
 * KHO MOI LA NGUON SU THAT. Khong doc `job_id` tu localStorage: trinh duyet co
 * the bi xoa du lieu, mo o may khac, hoac giu mot `job_id` da bi worker khac
 * thay the sau khi lease chet. `khoiPhuc()` nhan thang ket qua `listJobs()`.
 *
 * Phan quyet dinh nam o `lib/jobs.ts` duoi dang ham thuan (`khoaTheoDoi`,
 * `gopNhipPoll`) de bo test chay duoc that su nhieu nhip lien tiep. Cho nay
 * chi con la cai vo dat `setTimeout`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type TtsJob } from "./api";
import { dangChayJob, gopNhipPoll, khoaTheoDoi, moiNhatTheoChuong } from "./jobs";

export const POLL_MS = 1500;

export interface JobTracker {
  /** Job dang ke nhat cua moi chuong, khoa la `chapter_id`. */
  jobs: Record<string, TtsJob>;
  dangChay: TtsJob[];
  /** Nap lai tu kho sau khi tai trang — day la duong khoi phuc sau F5. */
  khoiPhuc: (danh_sach: TtsJob[]) => void;
  /** Dua mot job vua tao vao vong theo doi. */
  theoDoi: (job: TtsJob) => void;
  quenChuong: (chapterId: string) => void;
  quenHet: () => void;
}

export function useJobTracker({
  onCompleted,
  onFailed,
  pollMs = POLL_MS,
}: {
  onCompleted?: (job: TtsJob) => void;
  onFailed?: (job: TtsJob) => void;
  pollMs?: number;
} = {}): JobTracker {
  const [jobs, setJobs] = useState<Record<string, TtsJob>>({});

  /*
    NHIP DEM, va no la thu lam vong poll THUC SU LAP.

    Ban dau tien chi phu thuoc `[dangChayKey]`. Sau moi lan poll, `setJobs()`
    tao object moi nen danh sach dang chay duoc tinh lai — nhung khoa van la
    CUNG MOT CHUOI (van dung mot `job_id` do). Dependency khong doi thi effect
    khong chay lai, nen khong co `setTimeout` nao duoc dat tiep: vong poll chet
    sau DUNG MOT nhip.

    Hau qua tren production: poll bat duoc `pending -> running` (luc do
    `total_parts` con 0), roi dung han. Job xong sau 7 giay nhung giao dien
    dung mai o "Đang xử lý".
  */
  const [tick, setTick] = useState(0);

  /*
    Callback qua ref chu khong qua dependency cua effect.

    Trang truyen ham inline (`(j) => toast.ok(...)`), moi lan render la mot ham
    moi. De no trong dependency thi effect huy va dat lai `setTimeout` o moi
    lan render — vong poll bi lui vo han va khong bao gio chay.
  */
  const goiLai = useRef({ onCompleted, onFailed });
  useEffect(() => {
    goiLai.current = { onCompleted, onFailed };
  });

  /** Ban chup `jobs` de so trang thai TRUOC/SAU mot nhip, ngoai `setState`. */
  const banChup = useRef<Record<string, TtsJob>>({});
  useEffect(() => {
    banChup.current = jobs;
  }, [jobs]);

  const dangChay = useMemo(() => Object.values(jobs).filter(dangChayJob), [jobs]);
  const dangChayKey = useMemo(() => khoaTheoDoi(jobs), [jobs]);

  useEffect(() => {
    if (!dangChayKey) return;
    const ids = dangChayKey.split(",");
    const id = window.setTimeout(() => {
      Promise.all(ids.map((jid) => api.getJob(jid).catch(() => null))).then(
        (ket_qua) => {
          const moi = ket_qua.map((r) => r?.job ?? null);
          /*
            Ban do di qua ham cap nhat cua `setState` — neu nguoi dung vua tao
            mot job trong luc request con bay, ghi de bang mot ban chup cu se
            lam mat job vua tao. `gopNhipPoll` la ham THUAN nen goi trong do
            an toan, ke ca khi React 19 goi hai lan o che do nghiem ngat.
          */
          setJobs((current) => gopNhipPoll(current, moi).jobs);
          // Su kien thi tinh tu ban chup, BEN NGOAI ham cap nhat: goi toast
          // trong do se bi React 19 chan va ca khoi nay dung giua chung.
          const nhip = gopNhipPoll(banChup.current, moi);
          nhip.xong.forEach((j) => goiLai.current.onCompleted?.(j));
          nhip.hong.forEach((j) => goiLai.current.onFailed?.(j));
          // Dat NGOAI vong lap va khong dieu kien: mot lan mang chap (moi
          // request deu `catch` thanh null) cung phai dat duoc nhip ke tiep,
          // neu khong mot loi mang thoang qua se giet vong poll y het loi cu.
          setTick((t) => t + 1);
        },
      );
    }, pollMs);
    return () => window.clearTimeout(id);
  }, [dangChayKey, tick, pollMs]);

  const khoiPhuc = useCallback((danh_sach: TtsJob[]) => {
    setJobs(moiNhatTheoChuong(danh_sach));
  }, []);

  const theoDoi = useCallback((job: TtsJob) => {
    setJobs((current) => ({ ...current, [job.chapter_id]: job }));
  }, []);

  const quenChuong = useCallback((chapterId: string) => {
    setJobs((current) => {
      const next = { ...current };
      delete next[chapterId];
      return next;
    });
  }, []);

  const quenHet = useCallback(() => setJobs({}), []);

  return { jobs, dangChay, khoiPhuc, theoDoi, quenChuong, quenHet };
}
