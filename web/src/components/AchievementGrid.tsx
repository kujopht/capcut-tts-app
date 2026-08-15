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

  // Rong = KHONG tai duoc (loi mang/auth) — module PHU nen an hoan toan thay
  // vi choan trang bang mot thong bao loi. Danh sach thanh tuu THAT (tu
  // `ACHIEVEMENTS` o may chu) khong bao gio rong: nguoi moi tinh van thay
  // du bon the, chi la tat ca dang khoa — xem `daChuaMoKhoaNao` ben duoi.
  if (items.length === 0) return null;

  const daChuaMoKhoaNao = items.every((a) => !a.unlocked);

  return (
    <section className="stack-2" aria-labelledby="acc-thanh-tuu">
      <h2 className="section-title section-title-icon" id="acc-thanh-tuu">
        <IconShield size={19} /> Thành tựu
      </h2>
      {daChuaMoKhoaNao ? (
        <div className="profile-showcase-card">
          <strong>Bạn chưa mở khoá thành tựu nào</strong>
          <p className="hint">
            Thành tựu là những cột mốc đọc, nghe và sáng tác trên Fanfic
            World — mỗi thẻ dưới đây đã ghi rõ điều kiện để mở khoá. Đọc một
            chương, tổng hợp một bản audio hay xuất bản một tiểu thuyết là
            những bước đầu tiên; tiến độ được máy chủ ghi nhận tự động,
            không cần tự báo.
          </p>
        </div>
      ) : null}
      <div className="bento-grid">
        {items.map((a) => (
          <TheThanhTuu key={a.key} a={a} />
        ))}
      </div>
    </section>
  );
}
