/**
 * Dựng harness QA giao diện Trợ lý AI bằng esbuild (có sẵn trong web/node_modules) -> scripts/qa/ai_ui/out/.
 * Dùng: node scripts/qa/ai_ui/build.mjs
 */
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const web = path.join(repo, "web");
const require = createRequire(path.join(web, "package.json"));
const esbuild = require("esbuild");

const stubs = path.join(here, "harness/stubs");
const REPLACE = new Map([
  ["@/lib/api", path.join(stubs, "api.ts")],
  ["@/lib/session", path.join(stubs, "session.tsx")],
  ["next/link", path.join(stubs, "next-link.tsx")],
  ["next/navigation", path.join(stubs, "next-navigation.ts")],
]);

/** `companion=false` (mặc định): linh vật thay bằng bản rỗng → harness chat không kéo mã linh vật. `companion=true`: dùng mã THẬT. */
const makeStubPlugin = (companion) => ({
  name: "qa-stubs",
  setup(b) {
    b.onResolve({ filter: /.*/ }, (args) => {
      if (REPLACE.has(args.path)) return { path: REPLACE.get(args.path) };
      if (!companion && (/(^|\/)companion\/AiCompanion$/.test(args.path) || (args.path === "./AiCompanion" && /companion/.test(args.importer)))) {
        return { path: path.join(stubs, "ai-companion.tsx") };
      }
      return undefined;
    });
  },
});

/**
 * `buildHarness()` — harness chat (linh vật TẮT, cờ build = 0) -> out/.
 * `buildHarness({ companion: true })` — harness linh vật (cờ build = 1, mã `AiCompanion` thật, shell có header/Chat Dock/thanh phát
 * giả) -> out-companion/. Hai bản không dùng chung thư mục nên chạy song song được.
 */
export async function buildHarness({ companion = false, flag = "1" } = {}) {
  // `companion` + flag "0": CÙNG shell/mã linh vật thật nhưng cờ build TẮT — để chứng minh "cờ tắt = 0 byte linh vật được tải".
  const out = path.join(here, companion ? (flag === "1" ? "out-companion" : "out-companion-off") : "out");
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({
    entryPoints: { entry: path.join(here, companion ? "harness/entry-companion.tsx" : "harness/entry.tsx") },
    outdir: out,
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    jsx: "automatic",
    sourcemap: false,
    minify: false,
    logLevel: "warning",
    tsconfig: path.join(web, "tsconfig.json"),
    nodePaths: [path.join(web, "node_modules")],
    loader: { ".css": "css", ".woff2": "dataurl", ".woff": "dataurl", ".svg": "dataurl", ".png": "dataurl", ".webp": "dataurl" },
    // Ảnh nền tuyệt đối (/artwork/...) không có trong harness: để nguyên, trình duyệt sẽ 404 vô hại.
    external: ["/artwork/*", "/fonts/*", "/*.svg", "/*.png", "/*.webp"],
    define: {
      // Mọi `process.env.X` khác (cờ tính năng không liên quan) đọc ra `undefined` thay vì ném ReferenceError trên trình duyệt.
      "process.env": "{}",
      "process.env.NODE_ENV": '"production"',
      "process.env.NEXT_PUBLIC_AI_ASSISTANT_ENABLED": '"1"',
      "process.env.NEXT_PUBLIC_AI_COMPANION_ENABLED": companion ? JSON.stringify(flag) : '"0"',
      "process.env.NEXT_PUBLIC_API_BASE": '"http://qa.local"',
    },
    plugins: [makeStubPlugin(companion)],
  });
  fs.copyFileSync(path.join(here, "harness/index.html"), path.join(out, "index.html"));
  return out;
}

/** Bundle `real/inject.ts` (máy chủ SSE giả + công cụ QA) thành MỘT script IIFE để chèn vào bản dựng Next thật. -> out-real/inject.js */
export async function buildInject() {
  const out = path.join(here, "out-real");
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({
    entryPoints: { inject: path.join(here, "real/inject.ts") },
    outdir: out,
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2022",
    logLevel: "warning",
    tsconfig: path.join(web, "tsconfig.json"),
    nodePaths: [path.join(web, "node_modules")],
  });
  return path.join(out, "inject.js");
}

if (import.meta.url === `file://${process.argv[1].replace(/\\/g, "/")}` || process.argv[1]?.endsWith("build.mjs")) {
  buildHarness({ companion: process.argv.includes("--companion") || process.argv.includes("--companion-off"), flag: process.argv.includes("--companion-off") ? "0" : "1" }).then((o) => console.log("ok ->", o)).catch((e) => {
    console.error(e.message ?? e);
    process.exit(1);
  });
}
