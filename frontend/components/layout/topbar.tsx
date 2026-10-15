"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import { Menu, Search } from "lucide-react";
import { GenesisMark } from "@/components/brand/genesis-mark";
import { IconButton } from "@/components/ui/button";
import { Kbd } from "@/components/ui/disclosure";
import { isMacPlatform } from "@/lib/commands";
import { findNavItem } from "@/lib/navigation";
import { SystemService } from "@/services/system.service";

/** The backend's reported version, fetched once; hidden when the backend is unreachable. */
function useBackendVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    SystemService.getHealth()
      .then((health) => { if (active) setVersion(health.version); })
      .catch(() => { if (active) setVersion(null); });
    return () => { active = false; };
  }, []);
  return version;
}

const noSubscribe = () => () => {};

/** "⌘K" on Apple platforms, "Ctrl K" elsewhere; null during server rendering (no hint flash). */
function useShortcutHint(): string | null {
  return useSyncExternalStore(noSubscribe, () => (isMacPlatform(navigator.platform) ? "⌘K" : "Ctrl K"), () => null);
}

export function Topbar({ onOpenNavigation, navigationOpen, onOpenPalette, paletteOpen }: { onOpenNavigation: () => void; navigationOpen: boolean; onOpenPalette: () => void; paletteOpen: boolean }) {
  const current = findNavItem(usePathname());
  const version = useBackendVersion();
  const shortcut = useShortcutHint();

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur sm:px-6">
      <IconButton label="Open navigation" aria-haspopup="dialog" aria-expanded={navigationOpen} onClick={onOpenNavigation} className="-ml-1 md:hidden">
        <Menu aria-hidden className="h-4 w-4" />
      </IconButton>
      <GenesisMark className="h-6 w-6 md:hidden" />
      <div className="flex min-w-0 items-baseline gap-2 text-sm">
        <span className="hidden text-muted-foreground md:inline">Genesis</span>
        {current && <span aria-hidden className="hidden text-subtle md:inline">/</span>}
        <span className="truncate font-medium text-foreground">{current?.label ?? "Genesis"}</span>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
      <button
        type="button"
        onClick={onOpenPalette}
        aria-haspopup="dialog"
        aria-expanded={paletteOpen}
        aria-keyshortcuts={shortcut === "⌘K" ? "Meta+K" : "Control+K"}
        aria-label="Search pages and actions"
        className="flex h-8 items-center gap-2 rounded-md border border-border bg-surface px-2 text-xs text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground pointer-coarse:h-10 pointer-coarse:px-3 sm:w-56 sm:px-2.5"
      >
        <Search aria-hidden className="h-3.5 w-3.5 shrink-0" />
        <span className="hidden flex-1 text-left sm:inline">Search or jump to…</span>
        {shortcut && <Kbd className="hidden sm:inline-flex">{shortcut}</Kbd>}
      </button>
      {version && (
        <span title="Backend version" className="hidden rounded-full border border-border bg-surface px-2 py-0.5 font-mono sm:inline text-[11px] text-muted-foreground">
          v{version}
        </span>
      )}
      </div>
    </header>
  );
}
