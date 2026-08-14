"use client";

/**
 * Luoi thanh tuu cua CHINH MINH (V4 visual completion, Phan G-J).
 *
 * Goi `GET /api/account/achievements` — TINH TAI CHO tu du lieu da co, khong
 * phai ban ghi rieng (xem `server/gamification.py`). Chi dung cho trang cua
 * CHINH CHU (`/account`); chua co duong an toan de hien thanh tuu CUA NGUOI
 * KHAC (`tts_characters_used` khong nam trong danh sach cong khai cua
 * `creator.public_profile()`), nen `/u/[username]` CHUA hien module nay.
 *
 * An hoan toan khi loi/rong — day la mot module PHU, mot lan mat mang o day
 * khong duoc bien thanh mot thong bao loi choan trang ho so.
 */

import { useCallback } from "react";
import { api, type Achievement } from "@/lib/api";
import { useAsyncData } from "@/lib/useAsyncData";
import { IconShield } from "@/components/Icons";

function TheThanhTuu({ a }: { a: Achievement }) {
  return (
    <div
      className={`achievement-card do-hiem-${a.rarity}${
        a.unlocked ? "" : " achievement-card-locked"
      }`}
    >
      <span className="achievement-card-icon" aria-hidden="true">
        {a.icon}
      </span>
      <span className="progress-card-body">
        <strong>{a.name}</strong>
        <span className="hint">{a.description}</span>
        {a.progress ? (
          <span className="achievement-card-progress">
            {a.progress[0]} / {a.progress[1]}
          </span>
        ) : null}
      </span>
    </div>
  );
}

export function AchievementGrid() {
  const fetcher = useCallback(() => api.getAchievements(), []);
  const { data } = useAsyncData(fetcher);
  const items = data?.achievements ?? [];

  if (items.length === 0) return null;

  return (
    <section className="stack-2" aria-labelledby="acc-thanh-tuu">
      <h2 className="section-title section-title-icon" id="acc-thanh-tuu">
        <IconShield size={19} /> Thành tựu
      </h2>
      <div className="bento-grid">
        {items.map((a) => (
          <TheThanhTuu key={a.key} a={a} />
        ))}
      </div>
    </section>
  );
}
