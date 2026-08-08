/**
 * Cấu hình OpenNext cho Cloudflare Workers.
 *
 * VÌ SAO KHÔNG PHẢI STATIC EXPORT: hai route `/novels/[id]` và `/chapters/[id]`
 * nhận id là dữ liệu người dùng lúc chạy. `output: 'export'` bắt mọi route động
 * phải khai `generateStaticParams()`, mà id thì không thể liệt kê lúc build.
 * Muốn xuất tĩnh thì phải đổi sang dạng query (`/novels?id=…`) — tức là đổi URL
 * công khai, đổi liên kết và đổi test. Không làm.
 *
 * Không khai `incrementalCache`, `queue` hay `tagCache`: ứng dụng này không
 * dùng ISR, không revalidate, không server action. Mọi trang tương tác đều là
 * client component và tự gọi API qua trình duyệt. Thêm KV/D1/R2 vào đây chỉ để
 * "cho đủ" là thêm tài nguyên phải trả tiền và phải bảo trì mà không được gì.
 */
import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig();
