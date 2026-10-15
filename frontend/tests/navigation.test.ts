import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { NAVIGATION, NAV_ITEMS, findNavItem, isActivePath } from "../lib/navigation.ts";

const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "app");

test("every navigation item points at an implemented page", () => {
  for (const item of NAV_ITEMS) {
    const page = item.href === "/" ? join(APP_DIR, "page.tsx") : join(APP_DIR, item.href.slice(1), "page.tsx");
    assert.ok(existsSync(page), `${item.label} links to ${item.href}, which has no page`);
  }
});

test("navigation has no placeholders and no duplicate destinations", () => {
  const hrefs = NAV_ITEMS.map((item) => item.href);
  assert.equal(new Set(hrefs).size, hrefs.length);
  for (const label of ["Settings", "Core", "Plugins", "Monitoring"]) {
    assert.ok(!NAV_ITEMS.some((item) => item.label === label), `${label} should not be in the navigation`);
  }
  assert.deepEqual(NAVIGATION.map((group) => group.label), [null, "Build", "Operate"]);
});

test("Operations keeps the /monitoring URL", () => {
  assert.equal(NAV_ITEMS.find((item) => item.label === "Operations")?.href, "/monitoring");
});

test("the overview is active only on the root path", () => {
  assert.equal(isActivePath("/", "/"), true);
  assert.equal(isActivePath("/", "/agents"), false);
  assert.equal(isActivePath("/", null), false);
});

test("sections stay active on nested paths and trailing slashes, but not on lookalike paths", () => {
  assert.equal(isActivePath("/agents", "/agents"), true);
  assert.equal(isActivePath("/agents", "/agents/"), true);
  assert.equal(isActivePath("/agents", "/agents/123"), true);
  assert.equal(isActivePath("/agents", "/agents-archive"), false);
});

test("exactly one item is active for each route", () => {
  for (const path of ["/", "/agents", "/memory", "/workflows", "/monitoring", "/tools", "/providers"]) {
    assert.equal(NAV_ITEMS.filter((item) => isActivePath(item.href, path)).length, 1, path);
  }
  assert.equal(findNavItem("/monitoring")?.label, "Operations");
  assert.equal(findNavItem("/unknown"), undefined);
});
