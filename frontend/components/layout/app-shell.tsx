"use client";

import { useEffect, useState, type ReactNode } from "react";
import { MotionConfig } from "framer-motion";
import { CommandPalette } from "@/components/layout/command-palette";
import { Brand, Sidebar, SidebarNav } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Dialog } from "@/components/ui/dialog";
import { useSidebarCollapsed } from "@/hooks/use-sidebar-preference";
import { isMacPlatform, isPaletteShortcut } from "@/lib/commands";

/**
 * The persistent application frame, rendered once by the root layout. Layouts do not
 * re-render on navigation, so sidebar state survives moving between pages.
 *
 * Pages render inside <main>, which is the scroll container. Nothing here applies a
 * transform to that subtree, so pages' `position: fixed` overlays keep working.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // The one global shortcut listener: ⌘K (macOS) / Ctrl+K toggles the palette. Any other key,
  // including a plain "k" typed into a field, passes through untouched. It does not open over
  // another dialog (that dialog owns focus until it closes).
  useEffect(() => {
    const isMac = isMacPlatform(navigator.platform);
    function onKeyDown(event: KeyboardEvent) {
      if (!isPaletteShortcut(event, isMac)) return;
      const otherDialog = document.querySelector('[aria-modal="true"]:not([data-command-palette])');
      if (otherDialog) return;
      event.preventDefault();
      setPaletteOpen((open) => !open);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <MotionConfig reducedMotion="user">
      <a
        href="#main-content"
        className="sr-only z-[60] rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>
      <div className="flex h-dvh w-full overflow-hidden">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Topbar onOpenNavigation={() => setDrawerOpen(true)} navigationOpen={drawerOpen} onOpenPalette={() => setPaletteOpen(true)} paletteOpen={paletteOpen} />
          <main id="main-content" tabIndex={-1} className="min-w-0 flex-1 overflow-y-auto focus:outline-none">
            {children}
          </main>
        </div>
      </div>
      <Dialog open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Navigation" hideTitle variant="drawer" className="[&>div:last-child]:px-0 [&>div:last-child]:pt-0">
        <div className="flex h-full flex-col">
          <div className="px-4 pb-3"><Brand /></div>
          <SidebarNav onNavigate={() => setDrawerOpen(false)} />
        </div>
      </Dialog>
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} sidebarCollapsed={collapsed} onToggleSidebar={() => setCollapsed(!collapsed)} />}
    </MotionConfig>
  );
}
