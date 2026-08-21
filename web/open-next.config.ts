/**
 * Cấu hình OpenNext cho Cloudflare Workers.
 *
 * VÌ SAO KHÔNG PHẢI STATIC EXPORT: hai route `/novels/[id]` và `/chapters/[id]`
 * nhận id là dữ liệu người dùng lúc chạy. `output: 'export'` bắt mọi route động
 * phải khai `generateStaticParams()`, mà id thì không thể liệt kê lúc build.
 * Muốn xuất tĩnh thì phải đổi sang dạng query (`/novels?id=…`) — tức là đổi URL
 * công khai, đổi liên kết và đổi test. Không làm.
 *
 * ------------------------------------------------------------------
 * VÌ SAO PHẢI KHAI `incrementalCache` + `enableCacheInterception`
 * ------------------------------------------------------------------
 * TRƯỚC ĐÂY file này gọi `defineCloudflareConfig()` không tham số. Điều đó làm
 * `incrementalCache` rơi về mặc định `"dummy"` (xem
 * `node_modules/@opennextjs/cloudflare/dist/api/config.js`,
 * `resolveIncrementalCache(value = "dummy")`). Hậu quả ĐO ĐƯỢC, không phải suy
 * đoán:
 *
 *   `next build` prerender 42 route tĩnh ra `.next/server/app/*.html` + `.rsc`
 *   + `.segments`; `opennextjs-cloudflare build` gói chúng thành
 *   `.open-next/cache/<buildId>/<route>.cache`. Với cache "dummy" thì KHÔNG AI
 *   ĐỌC những tệp đó. Mỗi request tới `/`, `/fanfic`,
 *   `/admin/authors/applications`… đều nạp `server-functions/default/
 *   handler.mjs` (5,2 MB sau bundle) rồi render lại React từ đầu — dù trang đã
 *   được prerender sẵn lúc build và nội dung y hệt.
 *
 * Đó chính là nguồn của Cloudflare Error 1102 ("Worker exceeded resource
 * limits") mà một người dùng thật gặp ở lần đầu vào `/admin/authors/
 * applications`: isolate nguội phải nạp + đánh giá cả đồ thị module 5,2 MB rồi
 * mới render. Trần bộ nhớ 128 MB/isolate là CỐ ĐỊNH ở MỌI gói Cloudflare (kể
 * cả Paid), nên nâng gói không phải cách sửa.
 *
 * `static-assets-incremental-cache` là override CHÍNH CHỦ cho đúng trường hợp
 * này — chú thích của nó nói thẳng: "should only be used for applications that
 * do NOT want revalidation and ONLY want to serve prerendered data". Ứng dụng
 * này đúng như vậy: không ISR, không `revalidate`, không server action.
 * Nó đọc cache qua binding `ASSETS` đã có (`.open-next/assets/cdn-cgi/
 * _next_cache/…` — tiền tố `cdn-cgi/` chỉ Worker đọc được, không lộ ra ngoài),
 * nên KHÔNG thêm KV/D1/R2, không thêm tài nguyên phải trả tiền.
 *
 * `enableCacheInterception: true` là nửa còn lại, và là nửa quan trọng hơn:
 * nó cho tầng routing (chạy trong bundle `middleware/handler.mjs`, 137 KB) trả
 * thẳng HTML/RSC/segment đã prerender. Khi đó `worker.js` KHÔNG chạy tới dòng
 * `await import("./server-functions/default/handler.mjs")` — đồ thị module
 * 5,2 MB không bao giờ được nạp cho 42 route tĩnh. Bằng chứng nhận biết trên
 * response: header `x-opennext-cache: HIT`.
 *
 * An toàn ở đâu: `cacheInterceptor` chỉ chạm các route CÓ trong
 * `prerender-manifest.json` (42 route tĩnh; `dynamicRoutes` rỗng). 10 route
 * động (`/novels/[id]`, `/chapters/[id]`, `/listen/[id]`, `/u/[username]`,
 * `/posts/[postId]`, `/animation/[id]`, `/animation/watch/[id]`,
 * `/admin/users/[user_id]`, `/admin/animation/series/[id]`,
 * `/admin/animation/sources/[id]`) đi qua y như cũ. Nó cũng xử lý ĐÚNG cả ba
 * dạng request của App Router — HTML, `RSC: 1`, và
 * `Next-Router-Segment-Prefetch` (dữ liệu `segmentData` có sẵn trong tệp
 * `.cache`) — nên điều hướng phía client, prefetch và `AudioEngineProvider`
 * sống xuyên route đều giữ nguyên. `enableCacheInterception` chỉ phải tắt khi
 * dùng PPR; dự án này không dùng PPR.
 *
 * QUAN TRỌNG khi deploy: tệp cache chỉ được sao vào `.open-next/assets/
 * cdn-cgi/_next_cache/` bởi lệnh `populateCache` (chạy bên trong
 * `opennextjs-cloudflare deploy|preview|upload`, KHÔNG chạy trong `build`).
 * Vì vậy `package.json` gắn thêm `opennextjs-cloudflare populateCache local`
 * ngay sau `build` — để cả đường deploy dùng `wrangler deploy` trần (staging)
 * cũng có cache. Thiếu bước đó thì không sập, chỉ là mất toàn bộ lợi ích
 * (cache miss → render lại như trước).
 *
 * Không khai `queue` hay `tagCache`: ứng dụng này không dùng ISR, không
 * revalidate, không server action. Thêm KV/D1/R2 vào đây chỉ để "cho đủ" là
 * thêm tài nguyên phải trả tiền và phải bảo trì mà không được gì.
 */
import { defineCloudflareConfig } from "@opennextjs/cloudflare";
import incrementalCache from "@opennextjs/cloudflare/overrides/incremental-cache/static-assets-incremental-cache";

export default defineCloudflareConfig({
  incrementalCache,
  enableCacheInterception: true,
});
