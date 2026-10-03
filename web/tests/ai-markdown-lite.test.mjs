/**
 * Khối markdown tối giản của trợ lý AI (`components/ai/markdownBlocks.ts`, thuần): đoạn văn / danh sách / khối mã rào ```.
 * Chạy: node --test tests/ai-markdown-lite.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { parseMarkdownLite } from "../src/components/ai/markdownBlocks.ts";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const FENCE = "```";

test("không có mã: hành vi cũ giữ nguyên — đoạn tách bằng dòng trống, danh sách khi MỌI dòng là mục, dòng đơn giữ xuống dòng", () => {
  assert.deepEqual(parseMarkdownLite("Xin chào\nbạn"), [{ kind: "para", lines: ["Xin chào", "bạn"] }]);
  assert.deepEqual(parseMarkdownLite("một\n\nhai"), [
    { kind: "para", lines: ["một"] },
    { kind: "para", lines: ["hai"] },
  ]);
  assert.deepEqual(parseMarkdownLite("- a\n- b\n\n1. c\n2. d"), [
    { kind: "list", items: ["a", "b"] },
    { kind: "list", items: ["c", "d"] },
  ]);
  // Danh sách lẫn dòng thường là ĐOẠN (không đoán nửa vời).
  assert.deepEqual(parseMarkdownLite("- a\nthường")[0].kind, "para");
  assert.deepEqual(parseMarkdownLite(""), []);
});

test("khối mã: rào ```lang … ``` thành khối riêng, nội dung giữ NGUYÊN (thụt lề, dòng trống, ký tự đặc biệt), không bị parse markdown", () => {
  const src = `Mở đầu\n\n${FENCE}js\nconst a = 1;\n\n  if (a) { **không đậm** }\n${FENCE}\n\nKết`;
  assert.deepEqual(parseMarkdownLite(src), [
    { kind: "para", lines: ["Mở đầu"] },
    { kind: "code", lang: "js", text: "const a = 1;\n\n  if (a) { **không đậm** }", closed: true },
    { kind: "para", lines: ["Kết"] },
  ]);
});

test("khối mã ĐANG STREAM (mở, chưa đóng) vẫn là khối mã — không hiện ba dấu huyền thô", () => {
  const b = parseMarkdownLite(`Đây là mã:\n${FENCE}python\nprint("xin chào")\nfor i in`);
  assert.equal(b.length, 2);
  assert.deepEqual(b[1], { kind: "code", lang: "python", text: 'print("xin chào")\nfor i in', closed: false });
  // Rào vừa mở, chưa có chữ nào.
  assert.deepEqual(parseMarkdownLite(FENCE).at(-1), { kind: "code", lang: "", text: "", closed: false });
});

test("khối mã một dòng ```mã``` và nhiều khối liên tiếp", () => {
  assert.deepEqual(parseMarkdownLite(`${FENCE}ls -la${FENCE}`), [{ kind: "code", lang: "", text: "ls -la", closed: true }]);
  const two = parseMarkdownLite(`${FENCE}\na\n${FENCE}\n${FENCE}sh\nb\n${FENCE}`);
  assert.deepEqual(two.map((x) => x.kind), ["code", "code"]);
  assert.deepEqual(two.map((x) => x.text), ["a", "b"]);
});

test("nội dung thù địch: HTML/script chỉ là văn bản trong khối, dòng rất dài không làm hỏng việc tách, rào lẻ không nuốt hết", () => {
  const evil = `${FENCE}html\n<script>alert(1)</script><img src=x onerror=alert(1)>\n${FENCE}`;
  const [b] = parseMarkdownLite(evil);
  assert.equal(b.kind, "code");
  assert.equal(b.text, "<script>alert(1)</script><img src=x onerror=alert(1)>");
  const long = "x".repeat(200_000);
  const t0 = Date.now();
  assert.equal(parseMarkdownLite(`${FENCE}\n${long}\n${FENCE}`)[0].text.length, 200_000);
  assert.ok(Date.now() - t0 < 500, "tuyến tính theo độ dài");
  // Hai dấu huyền (không phải rào) và ba dấu giữa dòng chữ KHÔNG mở khối mã.
  assert.deepEqual(parseMarkdownLite("dùng `` hai và ``` giữa câu"), [{ kind: "para", lines: ["dùng `` hai và ``` giữa câu"] }]);
});

test("markdownLite.tsx: dựng khối mã bằng phần tử React có tabIndex (bàn phím cuộn được), không HTML thô", () => {
  const raw = readFileSync(`${ROOT}src/components/ai/markdownLite.tsx`, "utf8");
  const code = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.match(code, /className="ai-md-code"/);
  assert.match(code, /tabIndex=\{0\}/);
  assert.ok(!code.includes("dangerouslySetInnerHTML") && !/innerHTML/.test(code));
  const css = readFileSync(`${ROOT}src/components/ai/ai.css`, "utf8");
  assert.match(css, /\.ai-md-code\s*\{[^}]*overflow-x:\s*auto/);
});
