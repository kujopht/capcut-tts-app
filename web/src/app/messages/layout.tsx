import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Tin nhắn",
  // Hop thu rieng tu — khong co gi de lap chi muc.
  robots: { index: false, follow: false },
};

export default function MessagesLayout({ children }: { children: React.ReactNode }) {
  return children;
}
