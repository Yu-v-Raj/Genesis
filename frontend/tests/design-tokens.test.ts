import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

import { SIDEBAR_INIT_SCRIPT, SIDEBAR_STORAGE_KEY } from "../lib/sidebar-preference.ts";

const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "app", "globals.css"), "utf8");

function token(name: string): string {
  const match = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  assert.ok(match, `--color-${name} is not a 6-digit hex token`);
  return match[1];
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

// WCAG 2.x AA for normal-size text.
const AA = 4.5;

test("filled primary buttons keep white text at AA contrast", () => {
  assert.ok(contrast(token("primary"), "#ffffff") >= AA, `primary/white is ${contrast(token("primary"), "#ffffff").toFixed(2)}:1`);
});

test("accent buttons and accent text meet AA", () => {
  assert.ok(contrast(token("accent"), token("accent-foreground")) >= AA);
  for (const surface of ["background", "surface", "surface-2", "elevated"]) {
    assert.ok(contrast(token("accent"), token(surface)) >= AA, `accent on ${surface}`);
  }
});

test("body and secondary text meet AA on every surface", () => {
  for (const surface of ["background", "surface", "surface-2", "elevated"]) {
    assert.ok(contrast(token("foreground"), token(surface)) >= AA, `foreground on ${surface}`);
    assert.ok(contrast(token("muted-foreground"), token(surface)) >= AA, `muted-foreground on ${surface}`);
  }
});

test("status colors are readable as text on surfaces", () => {
  for (const tone of ["success", "warning", "danger", "info", "accent-2"]) {
    assert.ok(contrast(token(tone), token("surface")) >= AA, `${tone} on surface`);
  }
});

function runInitScript(stored: string | null, { storageThrows = false } = {}): string | null {
  const attributes = new Map<string, string>();
  const context = {
    localStorage: {
      getItem(key: string) {
        if (storageThrows) throw new Error("SecurityError");
        return key === SIDEBAR_STORAGE_KEY ? stored : null;
      },
    },
    document: { documentElement: { setAttribute: (name: string, value: string) => attributes.set(name, value) } },
  };
  runInNewContext(SIDEBAR_INIT_SCRIPT, context);
  return attributes.get("data-sidebar") ?? null;
}

test("the pre-paint script applies a saved collapsed sidebar", () => {
  assert.equal(runInitScript("true"), "collapsed");
});

test("the pre-paint script leaves the default when nothing is saved or storage is blocked", () => {
  assert.equal(runInitScript(null), null);
  assert.equal(runInitScript("false"), null);
  assert.equal(runInitScript("true", { storageThrows: true }), null);
});

test("the collapsed CSS variant is keyed to the attribute and scoped to the desktop sidebar", () => {
  assert.match(CSS, /@custom-variant sidebar-collapsed \(&:where\(\[data-sidebar="collapsed"\] #app-sidebar, \[data-sidebar="collapsed"\] #app-sidebar \*\)\);/);
});
