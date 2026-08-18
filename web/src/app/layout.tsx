import type { Metadata, Viewport } from "next";
import { Fraunces } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { SessionProvider } from "@/lib/session";
import { ToastProvider } from "@/lib/toast";
import { NavAuth, NavLinks } from "@/components/NavAuth";
import { PageBackground } from "@/components/PageBackground";
import { RouteTransitionVeil } from "@/components/RouteTransitionVeil";
import { ContentAtmosphere } from "@/components/ContentAtmosphere";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteSearch } from "@/components/SiteSearch";
import { Logo } from "@/components/Logo";
import { AudioEngineProvider } from "@/components/AudioEngine";
import { GlobalMiniPlayer } from "@/components/GlobalMiniPlayer";

/**
 * Mat chu HIEN THI (Visual Bible V1, muc 4) — dung RAT TIET CHE, chi cho tieu
 * de lon (Hero, cong the gioi). Tu-host qua `next/font` (tai o BUILD, khong
 * goi mang luc chay) — bien CSS `--font-display` duoc gan vao `<body>`,
 * KHONG thay the `--font` (UI/body) hien co.
 *
 * Subset "vietnamese" la BAT BUOC: thieu subset nay thi cac ky tu co dau se
 * roi ve mat chu du phong xau hon thay vi loi ro rang — da kiem tra truc
 * tiep tren trinh duyet (xem QA Phase 3) truoc khi chot dung font nay.
 */
const fraunces = Fraunces({
  subsets: ["latin", "vietnamese"],
  weight: ["500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

// Mo ta cu noi ve viec tao audio truoc tien. San pham nay la nen tang doc va
// nghe fanfic; Audio Studio la cong cu phu. Mo ta cung phai noi theo thu tu do.
const DESCRIPTION =
  "Đọc và nghe fanfic tiếng Việt. Khám phá truyện do cộng đồng xuất bản, nghe bằng giọng đọc tự nhiên.";

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
  // Bang DUNG `--bg` o `globals.css`. Doi nen trang thi phai doi ca o day —
  // trinh duyet doc gia tri nay truoc khi co CSS nao chay nen khong dung
  // `var()` duoc, va lech nhau thi thanh trinh duyet vien mot mau khac than.
  themeColor: "#08090f",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body className={fraunces.variable}>
        <SessionProvider>
          <ToastProvider>
          {/*
            Dong co phat TOAN CUC — bao NGOAI `{children}`, nen dieu huong
            giua cac trang (chi thay `{children}`) khong lam no unmount. Day
            la ly do audio SONG XUYEN ROUTE: xem `components/AudioEngine.tsx`.
          */}
          <AudioEngineProvider>
            {/* Lop tranh nen — mot phan tu `fixed` nam duoi tat ca. Ve TRUOC
                lien ket bo qua de no khong bao gio chen vao thu tu tieu diem. */}
            <PageBackground />

            {/*
              Hieu ung chuyen canh route "Aether Rift Reveal" (V4) — MOT LAN
              duy nhat, ngang hang voi `PageBackground`. `.aether-rift` dat
              z-index -1 (chi hon `.page-bg` -2 mot bac) — CA HAI la con am,
              nen LUON ve TRUOC vung noi dung chinh (khong dinh vi) nhung SAU
              cac lop dieu huong/modal z-index duong. Ket qua: NEN < HIEU UNG
              < GIAO DIEN — hieu ung KHONG bao gio che PageHero/nut/the (dung
              tu V1-V3, tat ca bi tu choi vi hinh dang, khong phai z-index).
              Xem `components/RouteTransitionVeil.tsx`.
            */}
            <RouteTransitionVeil />

            <a className="skip-link" href="#main">
              Bỏ qua điều hướng
            </a>

            {/*
              Thu tu trong header la thu tu uu tien cua san pham: thuong hieu,
              ba muc doc/nghe, roi moi den tim kiem va cong cu. Audio Studio
              KHONG con o thanh chinh — no nam trong menu ben phai, va
              `/studio` giu nguyen duong dan lan chuc nang.
            */}
            <SiteHeader>
              <div className="wrap">
                <Link href="/" className="brand" aria-label="Fanfic World — trang chủ">
                  <Logo size={30} />
                </Link>
                <NavLinks />
                <span className="spacer" />
                <SiteSearch />
                <NavAuth />
              </div>
            </SiteHeader>

            <main id="main">
              <ContentAtmosphere>{children}</ContentAtmosphere>
            </main>

            {/*
              Footer CHI dan toi cac route CO THAT trong `src/app/`. Cac muc
              quen thuoc cua mot footer — Dieu khoan, Bao mat, Lien he — deu
              bi bo, vi tao lien ket toi trang chua ton tai la mot lien ket
              hong, va tao trang phap ly gia con te hon: no ngu y mot cam ket
              phap ly khong ai viet.
            */}
            <footer className="site-footer">
              <div className="wrap footer-grid">
                <div className="stack-2 footer-brand">
                  <Logo size={26} />
                  <p className="hint">
                    Nền tảng đọc và nghe fanfic tiếng Việt. Bản MVP riêng tư,
                    chưa thương mại.
                  </p>
                </div>

                <nav className="footer-col" aria-label="Đọc truyện">
                  <h2 className="footer-title">Đọc truyện</h2>
                  <Link href="/" className="footer-link">
                    Trang chủ
                  </Link>
                  <Link href="/fanfic" className="footer-link">
                    Khám phá
                  </Link>
                  <Link href="/library" className="footer-link">
                    Thư viện của bạn
                  </Link>
                </nav>

                <nav className="footer-col" aria-label="Sáng tác">
                  <h2 className="footer-title">Sáng tác</h2>
                  <Link href="/write" className="footer-link">
                    Khu vực tác giả
                  </Link>
                  <Link href="/studio" className="footer-link">
                    Audio Studio
                  </Link>
                  <Link href="/account" className="footer-link">
                    Tài khoản
                  </Link>
                </nav>
              </div>

              <div className="wrap footer-note">
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

            {/* Thanh phat nho, song xuyen moi tuyen duong — xem
                `components/GlobalMiniPlayer.tsx`. Tu an khi khong co gi
                dang phat, hoac khi dang o chinh trang doc chuong do (trang
                do da co trinh phat lon + thanh nho theo cuon rieng). */}
            <GlobalMiniPlayer />
          </AudioEngineProvider>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
