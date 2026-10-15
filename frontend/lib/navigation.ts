/**
 * The single source of truth for Genesis navigation.
 *
 * Only implemented destinations belong here: every `href` must have an `app/<route>/page.tsx`
 * (tests/navigation.test.ts enforces it). Kept free of React so it can be unit tested.
 */

export type NavIconName = "overview" | "agents" | "memory" | "workflows" | "operations" | "tools" | "providers";

export interface NavItem {
  label: string;
  href: string;
  icon: NavIconName;
  description: string;
}

export interface NavGroup {
  /** Shown above the group; `null` for the ungrouped top item. */
  label: string | null;
  items: readonly NavItem[];
}

export const NAVIGATION: readonly NavGroup[] = [
  {
    label: null,
    items: [{ label: "Overview", href: "/", icon: "overview", description: "Health, activity and quick actions." }],
  },
  {
    label: "Build",
    items: [
      { label: "Agents", href: "/agents", icon: "agents", description: "Create, configure and chat with Agents." },
      { label: "Memory", href: "/memory", icon: "memory", description: "What each Agent remembers." },
      { label: "Workflows", href: "/workflows", icon: "workflows", description: "Multi-step work with dependencies." },
    ],
  },
  {
    label: "Operate",
    items: [
      // The URL stays /monitoring; only the label changed.
      { label: "Operations", href: "/monitoring", icon: "operations", description: "Executions, events, logs and services." },
      { label: "Tools", href: "/tools", icon: "tools", description: "Capabilities Agents can call." },
      { label: "Providers", href: "/providers", icon: "providers", description: "Model providers and whether they answer." },
    ],
  },
];

export const NAV_ITEMS: readonly NavItem[] = NAVIGATION.flatMap((group) => group.items);

/** `/` matches only itself; other items also match their nested routes. */
export function isActivePath(href: string, pathname: string | null): boolean {
  if (!pathname) return false;
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (href === "/") return path === "/";
  return path === href || path.startsWith(`${href}/`);
}

export function findNavItem(pathname: string | null): NavItem | undefined {
  return NAV_ITEMS.find((item) => isActivePath(item.href, pathname));
}
