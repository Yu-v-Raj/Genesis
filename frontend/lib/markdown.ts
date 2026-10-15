/**
 * A small Markdown parser for Agent replies.
 *
 * It produces a tree that the UI renders as React elements, never as HTML, so model output
 * cannot inject markup or scripts. Supported: paragraphs and line breaks, headings, fenced
 * code, bullet and numbered lists, block quotes, rules, `code`, **bold**, *italic* and
 * [links](https://…) (http, https and mailto only). Anything else stays plain text.
 */

export type Inline =
  | { type: "text"; value: string }
  | { type: "code"; value: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] };

export type Block =
  | { type: "paragraph"; lines: Inline[][] }
  | { type: "heading"; level: 1 | 2 | 3; children: Inline[] }
  | { type: "code"; language: string | null; value: string }
  | { type: "list"; ordered: boolean; start: number; items: Inline[][] }
  | { type: "quote"; children: Block[] }
  | { type: "rule" };

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

const INLINE_PATTERNS: readonly { type: "code" | "link" | "strong" | "em"; regex: RegExp }[] = [
  { type: "code", regex: /`([^`\n]+)`/ },
  { type: "link", regex: /\[([^\]\n]+)\]\(([^)\s]+)\)/ },
  { type: "strong", regex: /\*\*(?=\S)([^\n]*?\S)\*\*|__(?=\S)([^\n]*?\S)__/ },
  // Underscores are left alone so snake_case identifiers stay intact.
  { type: "em", regex: /(?<![*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\w])/ },
];

export function parseInline(text: string): Inline[] {
  const result: Inline[] = [];
  let rest = text;
  while (rest.length > 0) {
    let best: { type: (typeof INLINE_PATTERNS)[number]["type"]; match: RegExpExecArray } | null = null;
    for (const pattern of INLINE_PATTERNS) {
      const match = pattern.regex.exec(rest);
      if (match && (best === null || match.index < best.match.index)) best = { type: pattern.type, match };
    }
    if (best === null) {
      pushText(result, rest);
      break;
    }
    const { match, type } = best;
    if (match.index > 0) pushText(result, rest.slice(0, match.index));
    if (type === "code") result.push({ type: "code", value: match[1] });
    else if (type === "strong") result.push({ type: "strong", children: parseInline(match[1] ?? match[2]) });
    else if (type === "em") result.push({ type: "em", children: parseInline(match[1]) });
    else if (SAFE_URL.test(match[2])) result.push({ type: "link", href: match[2], children: parseInline(match[1]) });
    else pushText(result, match[0]); // unsafe or relative link: show it as written
    rest = rest.slice(match.index + match[0].length);
  }
  return result;
}

function pushText(target: Inline[], value: string) {
  const previous = target[target.length - 1];
  if (previous?.type === "text") previous.value += value;
  else target.push({ type: "text", value });
}

const FENCE = /^\s*(```|~~~)\s*([\w+#.-]*)\s*$/;
const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const NUMBERED = /^\s{0,3}(\d{1,9})[.)]\s+(.*)$/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }

    const fence = FENCE.exec(line);
    if (fence) {
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith(fence[1])) body.push(lines[index++]);
      index += 1; // closing fence (or end of input for an unterminated block)
      blocks.push({ type: "code", language: fence[2] || null, value: body.join("\n") });
      continue;
    }
    if (RULE.test(line)) { blocks.push({ type: "rule" }); index += 1; continue; }

    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: Math.min(heading[1].length, 3) as 1 | 2 | 3, children: parseInline(heading[2]) });
      index += 1;
      continue;
    }

    if (QUOTE.test(line)) {
      const body: string[] = [];
      while (index < lines.length && QUOTE.test(lines[index])) body.push((QUOTE.exec(lines[index++]) as RegExpExecArray)[1]);
      blocks.push({ type: "quote", children: parseMarkdown(body.join("\n")) });
      continue;
    }

    const bullet = BULLET.exec(line);
    const numbered = NUMBERED.exec(line);
    if (bullet || numbered) {
      const ordered = numbered !== null && bullet === null;
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (index < lines.length) {
        const current = lines[index];
        const item = pattern.exec(current);
        if (item) { items.push(ordered ? item[2] : item[1]); index += 1; continue; }
        // An indented line continues the previous item; a blank line ends the list
        // unless the next line is another item.
        if (current.trim() && /^\s{2,}\S/.test(current) && items.length) { items[items.length - 1] += ` ${current.trim()}`; index += 1; continue; }
        if (!current.trim() && index + 1 < lines.length && pattern.test(lines[index + 1])) { index += 1; continue; }
        break;
      }
      blocks.push({ type: "list", ordered, start: ordered ? Number((numbered as RegExpExecArray)[1]) : 1, items: items.map(parseInline) });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !FENCE.test(lines[index]) && !HEADING.test(lines[index]) && !BULLET.test(lines[index]) && !NUMBERED.test(lines[index]) && !QUOTE.test(lines[index]) && !RULE.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", lines: paragraph.map(parseInline) });
  }
  return blocks;
}
