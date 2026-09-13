"use client";

/**
 * Thanh tuy chon DOC + vach TIEN DO doc.
 *
 * Hai thu nho nhung dung cho mot phien doc dai:
 *   - co chu / be ngang cot chu, nho qua dieu huong (xem `readerPrefs`);
 *   - mot vach mong bao da doc toi dau, dat o dinh man hinh.
 *
 * Vach tien do doc `scrollY` qua `requestAnimationFrame` chu khong xu ly
 * thang trong `scroll`: `scroll` ban ra rat day va moi lan dat `style` la mot
 * lan trinh duyet tinh lai bo cuc. Gop ve mot khung hinh la du muot va khong
 * lam giat chinh viec cuon ma no dang do.
 */

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import {
  doiCoChu,
  ghi,
  kho,
  type BeNgang,
  type TuyChonDoc,
} from "@/lib/readerPrefs";

const NHAN_NGANG: Record<BeNgang, string> = {
  hep: "Hẹp",
  vua: "Vừa",
  rong: "Rộng",
};

export function ReaderPrefs({
  onDoi,
}: {
  onDoi: (d: TuyChonDoc) => void;
}) {
  /*
    `useSyncExternalStore` chu khong `useState` + `useEffect`: xem ghi chu o
    `lib/readerPrefs.ts`. Anh chup phia may chu la MAC DINH, nen HTML dung o
    may chu khop voi lan ve dau o trinh duyet, va khong co lan ve thu hai chi
    de doc mot gia tri da nam san trong `localStorage`.
  */
  const d = useSyncExternalStore(kho.dangKy, kho.anhChup, kho.anhChupMayChu);

  /*
    Bao len tren MOI khi gia tri doi — ke ca lan dau, khi kho vua doc xong tu
    `localStorage`. Trang cha giu hai thuoc tinh `data-*` o the ngoai cung,
    nen no phai biet gia tri that ngay tu luc nap chu khong doi toi luc nguoi
    dung bam mot cai nut.
  */
  useEffect(() => {
    onDoi(d);
  }, [d, onDoi]);

  const capNhat = useCallback((moi: TuyChonDoc) => {
    // Chi ghi vao kho; kho tu bao lai cho moi nguoi dang nghe, ke ca chinh
    // thanh nay. Mot duong di, khong hai nguon su that.
    ghi(moi);
  }, []);

  return (
    <div className="doc-tuychon" role="group" aria-label="Tuỳ chọn đọc">
      <div className="doc-tuychon-nhom">
        <span className="doc-tuychon-nhan" id="doc-cochu">
          Cỡ chữ
        </span>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          aria-describedby="doc-cochu"
          aria-label="Giảm cỡ chữ"
          disabled={d.coChu === "nho"}
          onClick={() => capNhat({ ...d, coChu: doiCoChu(d.coChu, -1) })}
        >
          A−
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          aria-describedby="doc-cochu"
          aria-label="Tăng cỡ chữ"
          disabled={d.coChu === "rat-lon"}
          onClick={() => capNhat({ ...d, coChu: doiCoChu(d.coChu, 1) })}
        >
          A+
        </button>
      </div>

      <div className="doc-tuychon-nhom">
        <span className="doc-tuychon-nhan" id="doc-ngang">
          Bề ngang
        </span>
        {(Object.keys(NHAN_NGANG) as BeNgang[]).map((x) => (
          <button
            key={x}
            type="button"
            className={`btn btn-sm ${d.beNgang === x ? "btn-primary" : "btn-ghost"}`}
            aria-describedby="doc-ngang"
            aria-pressed={d.beNgang === x}
            onClick={() => capNhat({ ...d, beNgang: x })}
          >
            {NHAN_NGANG[x]}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Vach mong o dinh man hinh: da doc bao nhieu phan cua trang. */
export function ReaderProgress() {
  const vach = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let khung = 0;
    const tinh = () => {
      khung = 0;
      const el = vach.current;
      if (!el) return;
      const cao = document.documentElement.scrollHeight - window.innerHeight;
      // Trang ngan hon man hinh thi khong co gi de bao — giu vach o 0.
      const p = cao > 0 ? Math.min(1, Math.max(0, window.scrollY / cao)) : 0;
      el.style.transform = `scaleX(${p})`;
      el.parentElement?.setAttribute("aria-valuenow", String(Math.round(p * 100)));
    };
    const nhip = () => {
      if (!khung) khung = window.requestAnimationFrame(tinh);
    };
    tinh();
    window.addEventListener("scroll", nhip, { passive: true });
    window.addEventListener("resize", nhip);
    return () => {
      window.removeEventListener("scroll", nhip);
      window.removeEventListener("resize", nhip);
      if (khung) window.cancelAnimationFrame(khung);
    };
  }, []);

  return (
    <div
      className="doc-tiendo"
      role="progressbar"
      aria-label="Tiến độ đọc"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={0}
    >
      <div className="doc-tiendo-vach" ref={vach} />
    </div>
  );
}
