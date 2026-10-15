"use client";

/**
 * An inline script that runs once, while the server HTML is parsed (before first paint).
 *
 * On the client the element is rendered as inert `text/plain`, which avoids React's dev
 * warning about rendering <script> tags; `suppressHydrationWarning` accepts the type
 * difference. Pattern from the Next.js guide "Preventing flash before hydration".
 */
export function InlineScript({ html }: { html: string }) {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
