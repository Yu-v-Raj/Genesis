import type { Metadata, Viewport } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { InlineScript } from "@/components/inline-script";
import { AppShell } from "@/components/layout/app-shell";
import { SIDEBAR_INIT_SCRIPT } from "@/lib/sidebar-preference";
import "./globals.css";

export const metadata: Metadata = {
  title: "Genesis",
  description: "Agent Operating System",
};

export const viewport: Viewport = {
  themeColor: "#07090f",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        {/* Applies the saved sidebar width before first paint; see lib/sidebar-preference.ts. */}
        <InlineScript html={SIDEBAR_INIT_SCRIPT} />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
