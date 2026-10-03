import type { RoomId } from "../core/types";

/**
 * Bảng màu gốc của game: nền lưu trữ xanh navy/than, giấy cũ nhạt màu, Ink Scout xanh lơ/tím, ký ức vàng nhạt/trắng, tha hoá & Redactor đỏ thẫm/đen.
 * Mọi hình vẽ lấy màu từ đây để toàn game nhất quán.
 */
export const C = {
  void: "#05060c",
  navy0: "#0a0e1f",
  navy1: "#10172f",
  navy2: "#18214a",
  slate0: "#1d2543",
  slate1: "#2a3358",
  slate2: "#3a4672",
  slate3: "#53628f",
  wood0: "#1a1426",
  wood1: "#2b2038",
  parch0: "#7e775f",
  parch1: "#a39a80",
  parch2: "#cdc3a6",
  cyan: "#22d3ee",
  cyanDark: "#127a99",
  cyanLight: "#9af0ff",
  violet: "#8b6cff",
  violetDark: "#52419f",
  violetLight: "#c3b3ff",
  gold: "#f3e3a2",
  goldDark: "#b9a458",
  white: "#f6f8ff",
  crimson: "#d9304c",
  crimsonDark: "#74142a",
  crimsonLight: "#ff7a8e",
  ink: "#0a0b14",
  ink2: "#161a2e",
  skin: "#f1cba9",
  skinShade: "#d4a584",
  hair: "#1c2352",
  hairLight: "#2d3980",
  eye: "#35a7ff",
  jacket: "#13152a",
} as const;

export interface RoomStyle {
  /** Màu nền trên/dưới. */
  sky0: string;
  sky1: string;
  /** Màu nhấn của ánh sáng/hạt bụi. */
  accent: string;
  /** Độ đậm của lớp phủ tối quanh viền (0–1). */
  vignette: number;
  /** Vẽ sương mù/tha hoá đỏ. */
  corruption: number;
}

export const ROOM_STYLE: Readonly<Record<RoomId, RoomStyle>> = {
  entrance: { sky0: "#0b1330", sky1: "#101c40", accent: "#9af0ff", vignette: 0.45, corruption: 0 },
  hall: { sky0: "#0c1233", sky1: "#1a2350", accent: "#f3e3a2", vignette: 0.4, corruption: 0 },
  echo: { sky0: "#07202a", sky1: "#0e3342", accent: "#7fe7ff", vignette: 0.5, corruption: 0 },
  stacks: { sky0: "#0a0c1c", sky1: "#141a38", accent: "#8b6cff", vignette: 0.55, corruption: 0.08 },
  shrine: { sky0: "#150f2e", sky1: "#251a4f", accent: "#c3b3ff", vignette: 0.45, corruption: 0 },
  sealed: { sky0: "#0a1022", sky1: "#17203f", accent: "#9af0ff", vignette: 0.55, corruption: 0.12 },
  secret: { sky0: "#17130a", sky1: "#2a2210", accent: "#f3e3a2", vignette: 0.5, corruption: 0 },
  redacted: { sky0: "#12070d", sky1: "#26101c", accent: "#ff7a8e", vignette: 0.6, corruption: 0.35 },
  bookmark: { sky0: "#171024", sky1: "#2a1c3c", accent: "#f3e3a2", vignette: 0.4, corruption: 0.05 },
  arena: { sky0: "#12060b", sky1: "#2a0e18", accent: "#ff7a8e", vignette: 0.65, corruption: 0.55 },
  ending: { sky0: "#0d1330", sky1: "#26305f", accent: "#ffffff", vignette: 0.3, corruption: 0 },
};
