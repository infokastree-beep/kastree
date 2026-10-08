/**
 * Production must not serve the auth-free /dev previews.
 * Run: node --experimental-strip-types --test lib/dev-routes.test.ts
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { devPreviewBlocked, isDevPreviewPath } from "./dev-routes.ts";

const here = dirname(fileURLToPath(import.meta.url));

describe("dev preview paths", () => {
  it("matches /dev and its pages only", () => {
    assert.equal(isDevPreviewPath("/dev"), true);
    assert.equal(isDevPreviewPath("/dev/"), true);
    assert.equal(isDevPreviewPath("/dev/statutory-workspace"), true);
    assert.equal(isDevPreviewPath("/development"), false);
    assert.equal(isDevPreviewPath("/device"), false);
    assert.equal(isDevPreviewPath("/year-ends/1/draft"), false);
    assert.equal(isDevPreviewPath("/"), false);
  });

  it("blocks those paths only when Node is in production", () => {
    assert.equal(devPreviewBlocked("/dev/statutory-workspace", "production"), true);
    assert.equal(devPreviewBlocked("/dev", "production"), true);
    assert.equal(devPreviewBlocked("/dev/statutory-workspace", "development"), false);
    assert.equal(devPreviewBlocked("/dev/statutory-workspace", "test"), false);
    assert.equal(devPreviewBlocked("/dev/statutory-workspace", undefined), false);
    assert.equal(devPreviewBlocked("/development", "production"), false);
    assert.equal(devPreviewBlocked("/year-ends/1/draft", "production"), false);
  });

  it("middleware returns the block before the /dev bypass", () => {
    const source = readFileSync(join(here, "../middleware.ts"), "utf8");
    const blocker = source.slice(
      source.indexOf("function productionDevBlock"),
      source.indexOf("const clerkHandler"),
    );
    assert.match(blocker, /devPreviewBlocked\(pathname, process\.env\.NODE_ENV\)/);
    assert.match(blocker, /status: 404/);
    const clerk = source.slice(
      source.indexOf("const clerkHandler"),
      source.indexOf("function safePlaceholderMiddleware"),
    );
    const placeholder = source.slice(source.indexOf("function safePlaceholderMiddleware"));
    for (const body of [clerk, placeholder]) {
      const call = body.indexOf("productionDevBlock(request.nextUrl.pathname)");
      const bypass = body.indexOf('startsWith("/dev")');
      assert.ok(call >= 0, body);
      assert.ok(bypass > call, body);
    }
  });

  it("the dev layout does not render in a production build", () => {
    const source = readFileSync(join(here, "../app/dev/layout.tsx"), "utf8");
    assert.match(source, /process\.env\.NODE_ENV === "production"/);
    assert.match(source, /notFound\(\)/);
  });
});
