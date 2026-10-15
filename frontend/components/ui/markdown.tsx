import { Fragment, type ReactNode } from "react";
import { CopyButton } from "@/components/ui/copy-button";
import { parseMarkdown, type Block, type Inline } from "@/lib/markdown";
import { cn } from "@/lib/utils";

function renderInline(nodes: Inline[], keyPrefix: string): ReactNode[] {
  return nodes.map((node, index) => {
    const key = `${keyPrefix}-${index}`;
    switch (node.type) {
      case "text":
        return <Fragment key={key}>{node.value}</Fragment>;
      case "code":
        return <code key={key} className="rounded border border-border bg-surface-2 px-1 py-px font-mono text-[0.85em] text-foreground">{node.value}</code>;
      case "strong":
        return <strong key={key} className="font-semibold text-foreground">{renderInline(node.children, key)}</strong>;
      case "em":
        return <em key={key}>{renderInline(node.children, key)}</em>;
      case "link":
        return <a key={key} href={node.href} target="_blank" rel="noopener noreferrer nofollow" className="text-accent underline decoration-accent/40 underline-offset-2 hover:decoration-accent">{renderInline(node.children, key)}</a>;
    }
  });
}

function renderBlock(block: Block, key: string): ReactNode {
  switch (block.type) {
    case "paragraph":
      return (
        <p key={key}>
          {block.lines.map((line, index) => <Fragment key={index}>{index > 0 && <br />}{renderInline(line, `${key}-${index}`)}</Fragment>)}
        </p>
      );
    case "heading":
      return <p key={key} role="heading" aria-level={block.level + 2} className={cn("font-semibold text-foreground", block.level === 1 ? "text-base" : "text-sm")}>{renderInline(block.children, key)}</p>;
    case "code":
      return (
        <div key={key} className="group/code relative overflow-hidden rounded-md border border-border bg-background">
          <div className="flex items-center justify-between border-b border-border px-3 py-1 text-[11px] text-muted-foreground">
            <span className="font-mono">{block.language ?? "text"}</span>
            <CopyButton value={block.value} label="Copy code" />
          </div>
          <pre className="max-h-96 overflow-auto p-3 font-mono text-xs leading-5 text-foreground"><code>{block.value}</code></pre>
        </div>
      );
    case "list": {
      const items = block.items.map((item, index) => <li key={index} className="pl-1">{renderInline(item, `${key}-${index}`)}</li>);
      return block.ordered
        ? <ol key={key} start={block.start} className="list-decimal space-y-1 pl-5 marker:text-muted-foreground">{items}</ol>
        : <ul key={key} className="list-disc space-y-1 pl-5 marker:text-muted-foreground">{items}</ul>;
    }
    case "quote":
      return <blockquote key={key} className="space-y-2 border-l-2 border-border-strong pl-3 text-muted-foreground">{block.children.map((child, index) => renderBlock(child, `${key}-${index}`))}</blockquote>;
    case "rule":
      return <hr key={key} className="border-border" />;
  }
}

/** Renders Agent output as formatted text. Never uses innerHTML (see lib/markdown.ts). */
export function Markdown({ source, className }: { source: string; className?: string }) {
  return <div className={cn("min-w-0 space-y-3 break-words text-sm leading-6 text-foreground/95", className)}>{parseMarkdown(source).map((block, index) => renderBlock(block, `b${index}`))}</div>;
}
