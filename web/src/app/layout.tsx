import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { NavAuth, NavLinks } from "@/components/NavAuth";
import { Logo } from "@/components/Logo";

const DESCRIPTION =
  "Tạo audio từ văn bản bất kỳ và nghe fanfic bằng giọng đọc tiếng Việt.";

export const metadata: Metadata = {
  // `template` de moi trang tu dat tieu de rieng ma van giu ten san pham
  title: { default: "Fanfic Audio Studio", template: "%s · Fanfic Audio Studio" },
  description: DESCRIPTION,
  applicationName: "Fanfic Audio Studio",
  // `icon.svg`, `apple-icon.tsx` va `opengraph-image.tsx` trong cung thu muc
  // duoc Next tu gan vao <head> — khong khai bao tay o day.
  openGraph: {
    type: "website",
    siteName: "Fanfic Audio Studio",
    title: "Fanfic Audio Studio",
    description: DESCRIPTION,
    locale: "vi_VN",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b0d12",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>
        <SessionProvider>
          <ToastProvider>
            <a className="skip-link" href="#main">
              Bỏ qua điều hướng
            </a>

            <header className="site-header">
              <div className="wrap">
                <Link href="/" className="brand" aria-label="Fanfic Audio Studio — trang chủ">
                  <Logo size={30} />
                </Link>
                <NavLinks />
                <span className="spacer" />
                <NavAuth />
              </div>
            </header>

            <main id="main">
              <div className="wrap">{children}</div>
            </main>

            <footer className="site-footer">
              <div className="wrap row-between">
                <span>
                  Fanfic Audio Studio — bản MVP riêng tư, chưa thương mại.
                </span>
                {/*
                  Câu này đã đổi hai lần, mỗi lần vì một sự thật đã thay đổi:

                  1. "Giọng đọc chạy cục bộ chưa xác minh giấy phép thương
                     mại." — chủ dự án đã cho phép công bố các giọng NghiTTS
                     và chịu trách nhiệm về quyền sử dụng.
                  2. Câu thay thế nói một số giọng xử lý trên máy cá nhân nên
                     có thể phải chờ — đúng khi worker còn chạy trên laptop
                     chủ dự án. Production chạy worker 24/7 trên Google Compute
                     Engine, nên cách nói đó vừa sai vừa gợi ý rằng người dùng
                     phải có máy của riêng họ.

                  Câu hiện tại chỉ nói điều còn đúng: xếp hàng là có thật, và
                  đóng trang không làm mất job.
                */}
                <span className="hint">
                  Giọng NghiTTS xử lý trên máy chủ và có thể phải xếp hàng.
                </span>
              </div>
            </footer>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
