"use client";

import { useCallback, useSyncExternalStore } from "react";
import { SIDEBAR_ATTRIBUTE, SIDEBAR_COLLAPSED, SIDEBAR_STORAGE_KEY } from "@/lib/sidebar-preference";

/**
 * Whether the desktop sidebar is collapsed.
 *
 * The <html> attribute set before first paint (see lib/sidebar-preference.ts) is the source of
 * truth, so React state always agrees with what is on screen. The shell lives in the root
 * layout, so the value survives navigation; localStorage keeps it across reloads when
 * available.
 */
const CHANGE_EVENT = "genesis:sidebar-preference";

function apply(collapsed: boolean): void {
  if (collapsed) document.documentElement.setAttribute(SIDEBAR_ATTRIBUTE, SIDEBAR_COLLAPSED);
  else document.documentElement.removeAttribute(SIDEBAR_ATTRIBUTE);
}

function read(): boolean {
  return document.documentElement.getAttribute(SIDEBAR_ATTRIBUTE) === SIDEBAR_COLLAPSED;
}

function subscribe(onChange: () => void): () => void {
  // Another tab changed the preference: follow it.
  function onStorage(event: StorageEvent) {
    if (event.key !== SIDEBAR_STORAGE_KEY) return;
    apply(event.newValue === "true");
    onChange();
  }
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function useSidebarCollapsed(): [boolean, (collapsed: boolean) => void] {
  const collapsed = useSyncExternalStore(subscribe, read, () => false);
  const setCollapsed = useCallback((value: boolean) => {
    apply(value);
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(value));
    } catch {
      // Storage unavailable: the attribute still holds the value for this session.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return [collapsed, setCollapsed];
}
