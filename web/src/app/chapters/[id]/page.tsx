"use client";

/**
 * Doc chuong — CHI CHU, chu-truoc-tien (Phan 2A/2E, overnight Phase 2).
 *
 * TRUOC: trang nay tu la CA trinh doc lan trinh nghe — `ChapterPlayer` +
 * `MiniPlayer` + `ListenReporter` nam TREN dau, chiem het man hinh dau tien
 * truoc khi toi duoc chu. SAU: trai nghiem NGHE chuyen het sang `/listen/[id]`
 * (trang rieng, uu tien tap truoc/sau + chon tap + phu de dong bo); trang nay
 * chi con tieu de + mot lien ket "Nghe chương này" (khi co audio) + noi dung +
 * binh luan — dung nhu ten goi "trang doc".
 */

import Link from "next/link";
import { use, useCallback, useEffect, useMemo } from "react";
import { api, type AudioTrack, type Chapter, type NovelBrief } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useAsyncData } from "@/lib/useAsyncData";
import { ChapterComments } from "@/components/ChapterComments";
import { AskAiPanel } from "@/components/AskAiPanel";
import { EmptyState, ErrorState, SkeletonList, formatNumber } from "@/components/ui";
import { IconBook, IconHeadphones } from "@/components/Icons";

export default function ChapterPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { profile } = useSession();

  /*
    HAI request, khong phu thuoc so chuong: chuong hien tai (`getChapter`, da
    kem san `novel` nen khong phai goi them chi de lay ten truyen) + danh sach
    chuong cua truyen, de biet chuong TRUOC va chuong SAU la gi.

    Danh sach chuong lay theo kieu KHONG DUOC PHEP LAM HONG VIEC DOC: neu
    `getNovel` that bai thi `dsChuong` chi la rong, mat hai cai nut dieu huong,
    va chu van hien ra binh thuong. Bat nguoc lai — de mot loi cua request phu
    lam ca trang doc thanh trang loi — la doi mat noi dung chinh de lay mot
    tien ich.
  */
  const fetchChapter = useCallback(async () => {
    const ket_qua = await api.getChapter(id);
    const novelId = ket_qua.novel?.novel_id ?? ket_qua.chapter?.novel_id;
    if (!novelId) return { ...ket_qua, dsChuong: [] as Chapter[] };
    const dsChuong = await api
      .getNovel(novelId)
      .then((r) => r.chapters)
      .catch(() => [] as Chapter[]);
    return { ...ket_qua, dsChuong };
  }, [id]);

  const { data, loading, error, missing, reload } = useAsyncData(fetchChapter);
  const chapter: Chapter | null = data?.chapter ?? null;
  const audio: AudioTrack | null = data?.audio ?? null;
  const novel: NovelBrief | null = data?.novel ?? null;

  /*
    KHONG tu sap xep lai theo `order_index` — cung ly do da ghi o
    `/listen/[id]`: chuong tao binh thuong deu mang gia tri MAC DINH giong het
    nhau, nen sap theo do se tron hang. `GET /api/novels/{id}` da tra ve DUNG
    thu tu hien thi, va `/novels/[id]` dung thang mang nay.
  */
  const { chuongTruoc, chuongSau, soThuTu, tongSo } = useMemo(() => {
    const ds = data?.dsChuong ?? [];
    const i = ds.findIndex((c) => c.chapter_id === id);
    return {
      chuongTruoc: i > 0 ? ds[i - 1] : null,
      chuongSau: i >= 0 && i < ds.length - 1 ? ds[i + 1] : null,
      // Vi tri trong mang, khong phai `order_index` — xem ghi chu o tren.
      soThuTu: i >= 0 ? i + 1 : 0,
      tongSo: ds.length,
    };
  }, [data, id]);

  /*
    Ghi con tro "Tiếp tục đọc" (Phần B, V4 visual completion) — MỘT LẦN khi mở
    trang, không phải mỗi lần cuộn. Chỉ khi đã đăng nhập: route yêu cầu token,
    và khách vãng lai không có "trang chủ của họ" để quay lại. Lỗi mạng ở đây
    KHÔNG được làm hỏng việc đọc — chỉ là tiện ích, không phải nội dung chính.
  */
  useEffect(() => {
    if (!profile || !chapter) return;
    api.reportReadProgress(chapter.novel_id, chapter.chapter_id).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile?.user_id, chapter?.chapter_id]);

  if (loading) {
    return (
      <div className="page">
        <div className="sk sk-title" style={{ height: 30, width: "45%" }} />
        <SkeletonList count={3} />
      </div>
    );
  }

  if (missing) {
    return (
      <div className="page">
        <EmptyState
          icon="🔍"
          title="Không tìm thấy chương này"
          action={
            <Link className="btn btn-primary" href="/fanfic" prefetch={false}>
              Về trang khám phá
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !chapter) {
    return (
      <div className="page">
        <ErrorState message={error || "Không tải được chương."} onRetry={reload} />
      </div>
    );
  }

  const isOwner = profile?.user_id === chapter.owner_id;

  return (
    <div className="page">
      <nav aria-label="Đường dẫn" className="reader-crumb">
        <Link href={`/novels/${chapter.novel_id}`} className="hint crumb">
          ← {novel?.title ?? "Về truyện"}
        </Link>
      </nav>

      <header className="stack-2 reader-head">
        <h1 className="page-title">{chapter.title}</h1>
        <span className="hint eyebrow-icon">
          <IconBook size={16} />
          {formatNumber(chapter.char_count)} ký tự
          {novel ? ` · ${novel.title}` : ""}
        </span>
        {/*
          MOT lien ket gon toi trai nghiem NGHE rieng (`/listen/[id]`) — KHONG
          con mo trinh phat/MiniPlayer/ListenReporter ngay tai day (Phan 2A).
          Chua co audio thi chi thay huong dan tao (chu so huu) hoac khong
          hien gi ca (nguoi doc thuong — khong ep ho quan tam toi audio).
        */}
        {audio ? (
          <Link
            className="btn btn-sm"
            href={`/listen/${chapter.chapter_id}`}
          >
            <IconHeadphones size={15} /> Nghe chương này
          </Link>
        ) : isOwner ? (
          <Link className="btn btn-sm btn-ghost" href="/write" prefetch={false}>
            <span aria-hidden="true">🎙️</span> Tạo audio cho chương
          </Link>
        ) : null}
      </header>

      {/*
        Cot chu hep hon phan con lai cua trang. Mot dong dai ~68 ky tu la nguong
        mat con lan duoc tu cuoi dong nay sang dau dong sau ma khong lac; ca be
        rong 1180px thi doc mot chuong dai rat met.
      */}
      <section className="reader" aria-label="Nội dung chương">
        {chapter.content ? (
          <div className="prose">{chapter.content}</div>
        ) : audio ? (
          // Cac tac pham nhap tu audio dai tap (13 truyen Fanfic Staging,
          // xem docs/reports/) khong co van ban goc — day la trang thai BINH
          // THUONG cua chung, khong phai loi/thieu du lieu. "Chua co noi
          // dung" doc nhu mot canh bao hong; trang thai rieng nay noi dung
          // dieu do ro rang va dua thang toi trai nghiem nghe.
          <EmptyState
            icon="🎧"
            title="Chương này chỉ có bản audio"
            hint={`Chưa có bản chữ cho chương này${novel ? ` trong ${novel.title}` : ""}. Nghe trọn tập tại trang Nghe.`}
            action={
              <Link className="btn btn-primary" href={`/listen/${chapter.chapter_id}`}>
                <IconHeadphones size={15} /> Nghe tập này
              </Link>
            }
          />
        ) : (
          <p className="hint">Chương này chưa có nội dung.</p>
        )}
      </section>

      {/* Hỏi AI — trợ lý hỏi đáp về truyện/chương (xem AskAiPanel.tsx). */}
      <AskAiPanel
        novelId={chapter.novel_id}
        chapterId={chapter.chapter_id}
        chapterIndex={chapter.order_index}
        chapterContent={chapter.content}
      />

      {/* Binh luan chuong — luon hien du co audio hay khong: day la binh
          luan ve NOI DUNG chuong, khong phai chi rieng ban audio. */}
      <div className="listen-col">
        <ChapterComments chapterId={chapter.chapter_id} />
      </div>

      {/*
        Loi ra o CUOI chuong. Nguoi vua doc xong dang o day, khong phai o dau
        trang — bat ho cuon nguoc len de tim duong sang chuong sau la mot viec
        thua.

        CO nut "chuong truoc / chuong sau" o day. Ban truoc CO Y khong co, voi ly
        do "trang Nghe da co roi, trang doc chi can dan ve trang truyen" — do la
        mot quyet dinh sai voi nguoi DOC: doc xong mot chuong roi phai quay ve
        muc luc, tim lai dong vua doc, rồi bam chuong ke tiep la ba thao tac
        cho mot viec dang le la mot cai bam. Tren mobile con te hon, vi muc luc
        cua truyen 15 chuong phai cuon.

        `prefetch={false}` cho hai nut nay: mot chuong la mot payload lon, va
        Next se nap san CA HAI phia neu de mac dinh.
      */}
      {novel ? (
        <nav className="reader-foot reader-nav" aria-label="Điều hướng chương">
          {chuongTruoc ? (
            <Link
              className="btn reader-nav-prev"
              href={`/chapters/${chuongTruoc.chapter_id}`}
              prefetch={false}
              rel="prev"
            >
              <span aria-hidden="true">←</span>
              <span className="reader-nav-label">
                <span className="reader-nav-cap">Chương trước</span>
                <span className="truncate reader-nav-title">{chuongTruoc.title}</span>
              </span>
            </Link>
          ) : (
            /* Giu o trong de nut "sau" khong nhay sang trai o chuong dau. */
            <span className="reader-nav-prev" aria-hidden="true" />
          )}

          <Link className="btn btn-ghost reader-nav-up" href={`/novels/${novel.novel_id}`}>
            <span aria-hidden="true">☰</span> Danh sách chương
            {tongSo > 0 ? (
              <span className="hint reader-nav-count">
                {soThuTu}/{tongSo}
              </span>
            ) : null}
          </Link>

          {chuongSau ? (
            <Link
              className="btn btn-primary reader-nav-next"
              href={`/chapters/${chuongSau.chapter_id}`}
              prefetch={false}
              rel="next"
            >
              <span className="reader-nav-label">
                <span className="reader-nav-cap">Chương sau</span>
                <span className="truncate reader-nav-title">{chuongSau.title}</span>
              </span>
              <span aria-hidden="true">→</span>
            </Link>
          ) : (
            /* Het truyen: noi ro thay vi de mot cho trong khong giai thich. */
            <span className="hint reader-nav-next reader-nav-end">
              Hết chương hiện có
            </span>
          )}
        </nav>
      ) : null}
    </div>
  );
}
