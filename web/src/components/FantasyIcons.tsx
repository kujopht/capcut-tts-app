"use client";

import React from "react";

interface FantasyIconProps {
  size?: number;
  className?: string;
}

/**
 * Ngọn lửa Ma Pháp Tinh Thể (Arcane Astral Flame)
 * Thay thế cho emoji lửa 🔥 Facebook thông thường.
 * Phong cách Modern Fantasy: Gradient Hoàng Kim - Thạch Anh - Lam Tinh Vân kèm hào quang ma thuật.
 */
export function IconFantasyFlame({ size = 18, className = "" }: FantasyIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`fantasy-icon fantasy-icon-flame ${className}`}
      aria-hidden="true"
      style={{ filter: "drop-shadow(0 0 3px rgba(251, 191, 36, 0.45))" }}
    >
      <defs>
        <linearGradient id="fantasy-flame-outer" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#f59e0b" />
          <stop offset="45%" stopColor="#ec4899" />
          <stop offset="90%" stopColor="#38bdf8" />
        </linearGradient>
        <linearGradient id="fantasy-flame-core" x1="0%" y1="100%" x2="0%" y2="0%">
          <stop offset="0%" stopColor="#fbbf24" />
          <stop offset="60%" stopColor="#fef08a" />
          <stop offset="100%" stopColor="#ffffff" />
        </linearGradient>
      </defs>
      {/* Vầng lửa ma pháp chính */}
      <path
        d="M12 2C12 5.5 8.5 7.5 8.5 12C8.5 15.5 11 18 13.5 18C16.5 18 19 15.5 19 11.5C19 6.5 14.5 4.5 12 2Z"
        fill="url(#fantasy-flame-outer)"
      />
      {/* Cánh xoáy ma thuật bên trái */}
      <path
        d="M6 13.5C6 17.5 9 21 13 21C16.5 21 19.5 18.5 19.8 15C18.2 16.8 15.8 18 13.2 18C9.5 18 8 15.2 8.5 12C7 12.5 6 12.8 6 13.5Z"
        fill="url(#fantasy-flame-outer)"
        opacity="0.9"
      />
      {/* Lõi sáng pha lê tinh khiết */}
      <path
        d="M12.5 9.5C12.5 11.8 10.5 13.2 10.5 15C10.5 16.5 11.8 17.5 13 17.5C14.5 17.5 15.8 16.2 15.8 14.2C15.8 11.8 13.8 10.5 12.5 9.5Z"
        fill="url(#fantasy-flame-core)"
      />
      {/* Hạt bụi ma pháp lơ lửng */}
      <circle cx="16.5" cy="5.5" r="1.2" fill="#38bdf8" />
      <circle cx="7" cy="9.5" r="0.9" fill="#fbbf24" />
    </svg>
  );
}

/**
 * Tinh Linh Loa Báo Ma Thuật (Arcane Astral Herald / Mystic Horn)
 * Thay thế cho emoji loa 📢 Facebook thông thường.
 * Phong cách Modern Fantasy: Gradient Tím Thạch Anh - Lam Ngọc kèm sóng mana phát quang.
 */
export function IconFantasyHerald({ size = 18, className = "" }: FantasyIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`fantasy-icon fantasy-icon-herald ${className}`}
      aria-hidden="true"
      style={{ filter: "drop-shadow(0 0 3px rgba(192, 132, 252, 0.45))" }}
    >
      <defs>
        <linearGradient id="fantasy-herald-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#c084fc" />
          <stop offset="50%" stopColor="#a855f7" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
      </defs>
      {/* Thân kèn / loa ma pháp tinh xảo */}
      <path
        d="M4 11.5V14.5C4 15.6 4.9 16.5 6 16.5H7.5L10.8 20.5C11.6 21.4 13 20.8 13 19.5V6.5C13 5.2 11.6 4.6 10.8 5.5L7.5 9.5H6C4.9 9.5 4 10.4 4 11.5Z"
        fill="url(#fantasy-herald-grad)"
      />
      {/* Lõi vành kèn ngọc bích */}
      <ellipse cx="13" cy="13" rx="1.5" ry="5.5" fill="#f1f5f9" opacity="0.85" />
      {/* Sóng âm mana ma thuật lan tỏa */}
      <path
        d="M16.5 9C18 10.5 18 14.5 16.5 16"
        stroke="#38bdf8"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M19.5 6.5C22 9.5 22 15.5 19.5 18.5"
        stroke="#c084fc"
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray="2 2"
      />
      {/* Ngôi sao ma thuật báo hiệu */}
      <path
        d="M20 3.5L20.6 4.9L22 5.5L20.6 6.1L20 7.5L19.4 6.1L18 5.5L19.4 4.9Z"
        fill="#fbbf24"
      />
    </svg>
  );
}

/**
 * Cuốn Sách Cổ Ma Pháp (Arcane Grimoire)
 * Thay thế cho emoji 📖
 */
export function IconFantasyTome({ size = 18, className = "" }: FantasyIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`fantasy-icon fantasy-icon-tome ${className}`}
      aria-hidden="true"
      style={{ filter: "drop-shadow(0 0 3px rgba(56, 189, 248, 0.4))" }}
    >
      <defs>
        <linearGradient id="fantasy-tome-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#818cf8" />
        </linearGradient>
      </defs>
      <path
        d="M12 6.5C10 4.8 7 4.3 3.5 4.8V18C7 17.5 10 18 12 19.5C14 18 17 17.5 20.5 18V4.8C17 4.3 14 4.8 12 6.5Z"
        fill="url(#fantasy-tome-grad)"
        fillOpacity="0.3"
        stroke="url(#fantasy-tome-grad)"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M12 6.5V19.5" stroke="#ffffff" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7 8.5H5.5M7 12H5.5M18.5 8.5H17M18.5 12H17" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Quả Cầu Pha Lê Animation (Arcane Orb / Cinema Crystal)
 * Thay thế cho emoji 🎬
 */
export function IconFantasyCrystal({ size = 18, className = "" }: FantasyIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`fantasy-icon fantasy-icon-crystal ${className}`}
      aria-hidden="true"
      style={{ filter: "drop-shadow(0 0 3px rgba(192, 132, 252, 0.45))" }}
    >
      <defs>
        <linearGradient id="fantasy-crystal-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#c084fc" />
          <stop offset="100%" stopColor="#38bdf8" />
        </linearGradient>
      </defs>
      <polygon
        points="12,2 20,7 20,17 12,22 4,17 4,7"
        fill="url(#fantasy-crystal-grad)"
        fillOpacity="0.25"
        stroke="url(#fantasy-crystal-grad)"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <polygon points="12,6 17,9.5 17,14.5 12,18 7,14.5 7,9.5" stroke="#ffffff" strokeWidth="1.2" strokeOpacity="0.8" />
      <polygon points="10,9 15,12 10,15" fill="#ffffff" />
    </svg>
  );
}

/**
 * Chuông Thông Báo Ma Thuật (Astral Crystal Bell)
 * Thay thế cho emoji chuông 🔔 Facebook thông thường.
 */
export function IconFantasyBell({ size = 18, className = "" }: FantasyIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`fantasy-icon fantasy-icon-bell ${className}`}
      aria-hidden="true"
      style={{ filter: "drop-shadow(0 0 3px rgba(251, 191, 36, 0.45))" }}
    >
      <defs>
        <linearGradient id="fantasy-bell-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#fbbf24" />
          <stop offset="60%" stopColor="#f59e0b" />
          <stop offset="100%" stopColor="#d97706" />
        </linearGradient>
      </defs>
      <path
        d="M12 2.5C9.5 2.5 7.5 4.5 7.5 7V11C7.5 12.5 6.5 14 5 15C4.5 15.3 4.2 15.8 4.5 16.3C4.7 16.7 5.2 17 5.8 17H18.2C18.8 17 19.3 16.7 19.5 16.3C19.8 15.8 19.5 15.3 19 15C17.5 14 16.5 12.5 16.5 11V7C16.5 4.5 14.5 2.5 12 2.5Z"
        fill="url(#fantasy-bell-grad)"
      />
      <path
        d="M10 18C10.2 19.5 11 20.5 12 20.5C13 20.5 13.8 19.5 14 18H10Z"
        fill="#fef08a"
      />
      <circle cx="12" cy="7" r="1" fill="#ffffff" />
    </svg>
  );
}
