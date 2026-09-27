import type { Metadata } from "next";

// Hoi thoai ho tro la rieng tu cua tung nguoi: khong de may tim kiem danh chi muc.
export const metadata: Metadata = {
  title: "Trợ giúp",
  robots: { index: false, follow: false },
};

export default function SupportLayout({ children }: { children: React.ReactNode }) {
  return children;
}
