import assert from "node:assert/strict";
import test from "node:test";

import { parseInline, parseMarkdown } from "../lib/markdown.ts";

test("inline emphasis, code and links", () => {
  assert.deepEqual(parseInline("The result is **100**."), [
    { type: "text", value: "The result is " },
    { type: "strong", children: [{ type: "text", value: "100" }] },
    { type: "text", value: "." },
  ]);
  assert.deepEqual(parseInline("Use `npm test` *now*"), [
    { type: "text", value: "Use " }, { type: "code", value: "npm test" }, { type: "text", value: " " },
    { type: "em", children: [{ type: "text", value: "now" }] },
  ]);
  assert.deepEqual(parseInline("[docs](https://example.com)"), [{ type: "link", href: "https://example.com", children: [{ type: "text", value: "docs" }] }]);
});

test("unsafe links and HTML stay plain text", () => {
  assert.deepEqual(parseInline("[x](javascript:alert(1))"), [{ type: "text", value: "[x](javascript:alert(1))" }]);
  assert.deepEqual(parseInline("<img src=x onerror=alert(1)>"), [{ type: "text", value: "<img src=x onerror=alert(1)>" }]);
});

test("snake_case and lone asterisks are not emphasis", () => {
  assert.deepEqual(parseInline("call send_email_now"), [{ type: "text", value: "call send_email_now" }]);
  assert.deepEqual(parseInline("2 * 3 * 4 = 24"), [{ type: "text", value: "2 * 3 * 4 = 24" }]);
  assert.deepEqual(parseInline("code `a*b*c` here"), [{ type: "text", value: "code " }, { type: "code", value: "a*b*c" }, { type: "text", value: " here" }]);
});

test("blocks: headings, lists, code fences, quotes and rules", () => {
  const blocks = parseMarkdown("# Plan\n\n1. First\n2. Second\n\n- a\n- b\n\n```ts\nconst x = 1;\n```\n> quoted\n\n---\nDone\nnext line");
  assert.deepEqual(blocks.map((block) => block.type), ["heading", "list", "list", "code", "quote", "rule", "paragraph"]);
  const ordered = blocks[1];
  assert.ok(ordered.type === "list" && ordered.ordered && ordered.start === 1 && ordered.items.length === 2);
  const code = blocks[3];
  assert.ok(code.type === "code" && code.language === "ts" && code.value === "const x = 1;");
  const paragraph = blocks[6];
  assert.ok(paragraph.type === "paragraph" && paragraph.lines.length === 2);
});

test("an unterminated code fence keeps its content", () => {
  const [block] = parseMarkdown("```\nline one\nline two");
  assert.ok(block.type === "code" && block.value === "line one\nline two");
});

test("plain replies stay a single paragraph", () => {
  assert.deepEqual(parseMarkdown("84"), [{ type: "paragraph", lines: [[{ type: "text", value: "84" }]] }]);
  assert.deepEqual(parseMarkdown(""), []);
});
