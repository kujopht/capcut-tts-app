"use client";

/**
 * Mo ta truyen, THU GON o 4 dong kem "Xem thêm" (Product UX Sprint 2).
 *
 * Mo ta dai day nut hanh dong va muc luc xuong duoi nep gap. Nut chi hien khi
 * chu THAT SU bi cat (do bang ResizeObserver), khong hien cho mo ta ngan.
 * HTML may chu van chua TOAN BO mo ta (SEO, trinh doc man hinh) — chi CSS cat.
 */

import { useEffect, useRef, useState } from "react";

export function NovelDescription({ text }: { text: string }) {
  const el = useRef<HTMLParagraphElement>(null);
  const moRef = useRef(false);
  const [mo, setMo] = useState(false);
  const [biCat, setBiCat] = useState(false);

  useEffect(() => {
    const p = el.current;
    if (!p || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      // Chi do khi DANG thu gon: mo ra thi khong con gi bi cat de do.
      if (!moRef.current) setBiCat(p.scrollHeight > p.clientHeight + 2);
    });
    ro.observe(p);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="novel-desc">
      <p ref={el} className={`lead lead-narrow novel-desc-text${mo ? " is-open" : ""}`}>
        {text}
      </p>
      {biCat ? (
        <button
          type="button"
          className="novel-desc-toggle"
          aria-expanded={mo}
          onClick={() => {
            moRef.current = !mo;
            setMo(!mo);
          }}
        >
          {mo ? "Thu gọn" : "Xem thêm"}
        </button>
      ) : null}
    </div>
  );
}
