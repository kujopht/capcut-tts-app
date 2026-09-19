"use client";

/**
 * Live Floating Lyric Stream (Phuong an A: Chay lyric giua thanh dock).
 *
 * Dong bo tung chu (word-by-word karaoke highlighting) voi do chinh xac sub-second
 * trich xuat tu mo hinh Whisper AI tren dung file nhac reverb thuc te.
 *
 * Tinh gian toi da theo yeu cau nguoi dung:
 * - Khong khung hop vien cong kenh ("ko can 1 cai khung ham ho").
 * - Chu lyric tha noi mem mai ngay giua thanh dock dieu huong.
 * - Chay sang tung chu theo giong ca si (is-past, is-current, is-upcoming).
 * - Khong bao gio bi cat mat chu nao ("dung de chu nao mat ko hien dc").
 */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { musicStore, getActiveLyricLine } from "@/lib/musicStore";
import type { LyricLine, LyricWord } from "@/lib/lyricsData";

/**
 * Phân tách câu hát chỉ khi câu THẬT SỰ quá dài (> 10 từ hoặc > 56 ký tự).
 * Các câu thông thường (dưới 10 từ) được giữ nguyên vẹn trọn câu để tận dụng tối đa
 * khoảng không gian rộng rãi giữa thanh dock, người nghe đọc trọn ý câu hát tự nhiên.
 */
function chunkLyricWords(words: LyricWord[] | undefined): LyricWord[][] {
  if (!words || words.length === 0) return [];

  const totalChars = words.reduce((sum, w) => sum + w.word.length, 0);

  // Câu có độ dài thông thường (≤ 10 từ hoặc ≤ 56 ký tự): Giữ nguyên trọn vẹn 1 câu!
  if (words.length <= 10 && totalChars <= 56) {
    return [words];
  }

  // Với câu thật sự dài (rap, điệp khúc kép > 10 từ): Chia thành các vế tự nhiên (khoảng 6-8 từ mỗi vế)
  const targetChunkCount = Math.ceil(words.length / 8);
  const wordsPerChunk = Math.ceil(words.length / targetChunkCount);

  const chunks: LyricWord[][] = [];
  let current: LyricWord[] = [];

  for (let i = 0; i < words.length; i++) {
    current.push(words[i]);
    const remaining = words.length - (i + 1);
    const endsWithPause = /[,.;?!—]/.test(words[i].word);

    // Ưu tiên ngắt tại dấu ngắt câu nếu cụm đã có ≥ 4 từ và phần còn lại còn ≥ 4 từ
    const pauseBreak = endsWithPause && current.length >= 4 && remaining >= 4;
    const sizeBreak = current.length >= wordsPerChunk && remaining >= 4;

    if (pauseBreak || sizeBreak || remaining === 0) {
      chunks.push(current);
      current = [];
    }
  }

  if (current.length > 0) {
    if (chunks.length > 0 && current.length <= 2) {
      // Nếu cụm cuối chỉ còn 1-2 từ, gộp luôn vào cụm trước để câu không bị vụn vặt
      chunks[chunks.length - 1].push(...current);
    } else {
      chunks.push(current);
    }
  }

  return chunks;
}

export function LiveLyricTicker() {
  const { isPlaying, currentTrack } = useSyncExternalStore(
    musicStore.subscribe,
    musicStore.getSnapshot,
    () => musicStore.getSnapshot(),
  );

  const [currentTime, setCurrentTime] = useState(() => musicStore.getCurrentTime());
  const containerRef = useRef<HTMLSpanElement | null>(null);
  const activeWordRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const unsub = musicStore.subscribeTime((t) => {
      setCurrentTime(t);
    });
    return unsub;
  }, []);

  const activeLine: LyricLine | null = getActiveLyricLine(currentTrack, currentTime);
  const words: LyricWord[] | undefined = activeLine?.words;

  // Chia nhỏ câu dài thành các cụm từ vừa vặn với thanh dock
  const chunks = useMemo(() => chunkLyricWords(words), [words]);

  // Xác định cụm từ đang được hát theo currentTime
  const activeChunkIndex = useMemo(() => {
    if (chunks.length <= 1) return 0;
    for (let i = 0; i < chunks.length - 1; i++) {
      const nextChunkFirstWord = chunks[i + 1][0];
      if (nextChunkFirstWord && currentTime < nextChunkFirstWord.start) {
        return i;
      }
    }
    return chunks.length - 1;
  }, [chunks, currentTime]);

  const activeWords = chunks[activeChunkIndex] || words || [];

  // Reset cuộn container về đầu mỗi khi chuyển sang câu hoặc cụm từ mới
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollLeft = 0;
    }
  }, [activeLine?.text, activeChunkIndex]);

  // Cuộn dự phòng nhẹ nhàng nếu trên màn hình cực nhỏ (mobile < 360px) từ chạm mép
  useEffect(() => {
    if (activeWordRef.current && containerRef.current) {
      const container = containerRef.current;
      const wordEl = activeWordRef.current;
      const cRect = container.getBoundingClientRect();
      const wRect = wordEl.getBoundingClientRect();

      if (wRect.right > cRect.right - 12) {
        const delta = wRect.right - cRect.right + 20;
        container.scrollBy({ left: delta, behavior: "smooth" });
      } else if (wRect.left < cRect.left + 12) {
        const delta = wRect.left - cRect.left - 20;
        container.scrollBy({ left: delta, behavior: "smooth" });
      }
    }
  }, [currentTime]);

  const hasWords = activeWords && activeWords.length > 0;

  return (
    <Link
      href="/entertainment"
      className={`live-lyric-ticker ${isPlaying ? "is-playing" : ""}`}
      aria-label={`Đang phát: ${currentTrack.title}. Nhấn để mở Trình phát & Lời bài hát.`}
      title="Nhấn để mở Trình phát & Lời bài hát"
      prefetch={false}
      tabIndex={isPlaying ? 0 : -1}
      aria-hidden={!isPlaying}
    >
      <span
        ref={containerRef}
        className="live-lyric-stream"
        key={`${activeLine?.text || "intro"}-p${activeChunkIndex}`}
      >
        {hasWords ? (
          activeWords.map((w, idx) => {
            const isCurrent = currentTime >= w.start && currentTime <= w.end;
            const isPast = currentTime > w.end;
            const status = isCurrent ? "is-current" : isPast ? "is-past" : "is-upcoming";

            return (
              <span
                key={`${idx}-${w.word}-${w.start}`}
                ref={isCurrent ? activeWordRef : null}
                className={`lyric-word ${status}`}
              >
                {w.word}
              </span>
            );
          })
        ) : (
          <span className="lyric-word is-current">
            {activeLine?.text || `${currentTrack.icon} ${currentTrack.title}`}
          </span>
        )}
      </span>
    </Link>
  );
}
