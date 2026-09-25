"use client";

/**
 * Cot chu cua chuong — cac `<p>` that, ve o MAY CHU (component client van
 * duoc Next ve san thanh HTML), nen SEO/`Ctrl+F`/trinh doc man hinh thay
 * dung van ban nhu truoc.
 *
 * MOI doan la mot component `memo`: khi giong doc sang doan moi chi HAI doan
 * ve lai (doan cu tat sang, doan moi bat sang), khong phai ca 300 doan cua
 * chuong dai — `timeupdate` ban ~4 lan/giay.
 *
 * Bam mot doan KHONG tua ngay. Ban WIP truoc tua ngay khi cham — tren dien
 * thoai, cham de dung cuon hay de bo chon chu la audio nhay di cho khac.
 * O day cham chi CHON doan, va hien mot nut ro rang "Nghe từ đoạn này".
 */

import { memo, useCallback } from "react";
import { IconPlay } from "@/components/Icons";

export interface ReaderTextProps {
  paragraphs: readonly string[];
  /** Doan dang duoc doc, -1 khi khong co. */
  activeIdx: number;
  /** Doan nguoi dung vua cham (de hien nut "Nghe từ đoạn này"), -1 khi khong. */
  selectedIdx: number;
  /** Co the nghe tu mot doan khong (chuong co audio, che do co nghe). */
  canSeek: boolean;
  onSelect: (i: number) => void;
  onListenFrom: (i: number) => void;
}

const Doan = memo(function Doan({
  i,
  text,
  active,
  selected,
  canSeek,
  onSelect,
  onListenFrom,
}: {
  i: number;
  text: string;
  active: boolean;
  selected: boolean;
  canSeek: boolean;
  onSelect: (i: number) => void;
  onListenFrom: (i: number) => void;
}) {
  const cls = `reader-para${active ? " is-speaking" : ""}${selected ? " is-selected" : ""}`;
  return (
    <p
      className={cls}
      data-doan={i}
      aria-current={active ? "true" : undefined}
      onClick={canSeek ? () => onSelect(i) : undefined}
    >
      {text}
      {selected && canSeek ? (
        <button
          type="button"
          className="reader-para-listen"
          onClick={(e) => {
            e.stopPropagation();
            onListenFrom(i);
          }}
        >
          <IconPlay size={12} /> Nghe từ đoạn này
        </button>
      ) : null}
    </p>
  );
});

export const ReaderText = memo(function ReaderText({
  paragraphs,
  activeIdx,
  selectedIdx,
  canSeek,
  onSelect,
  onListenFrom,
}: ReaderTextProps) {
  /*
    Cham de BOI DEN chu thi khong phai "chon doan": nguoi ta dang chep mot
    cau. Kiem vung chon TRUOC khi coi cu cham la mot lan chon doan.
  */
  const chon = useCallback(
    (i: number) => {
      const sel = typeof window !== "undefined" ? window.getSelection?.() : null;
      if (sel && sel.toString().trim().length > 0) return;
      onSelect(i);
    },
    [onSelect],
  );

  return (
    <div className="prose">
      {paragraphs.map((p, i) => (
        <Doan
          key={i}
          i={i}
          text={p}
          active={i === activeIdx}
          selected={i === selectedIdx}
          canSeek={canSeek}
          onSelect={chon}
          onListenFrom={onListenFrom}
        />
      ))}
    </div>
  );
});
