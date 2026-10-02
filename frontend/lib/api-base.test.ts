/**
 * Browser API calls stay on this host. The Next rewrite targets the upstream.
 * Run: node --experimental-strip-types --test lib/api-base.test.ts
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

describe("same-origin API base", () => {
  it("uses /backend-api in the browser and the upstream URL on the server", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL =
      "https://kastree-production-5658.up.railway.app/";
    const { SAME_ORIGIN_API_PREFIX, getApiBaseUrl } = await import("./api.ts");

    const previous = globalThis.window;
    // @ts-expect-error test double for the browser branch
    delete globalThis.window;
    assert.equal(
      getApiBaseUrl(),
      "https://kastree-production-5658.up.railway.app",
    );

    // @ts-expect-error test double for the browser branch
    globalThis.window = {};
    assert.equal(getApiBaseUrl(), SAME_ORIGIN_API_PREFIX);
    assert.equal(SAME_ORIGIN_API_PREFIX, "/backend-api");

    if (previous === undefined) {
      // @ts-expect-error test double for the browser branch
      delete globalThis.window;
    } else {
      globalThis.window = previous;
    }
  });

  it("rewrites /backend-api to the upstream host", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL =
      "https://kastree-production-5658.up.railway.app";
    const { default: nextConfig } = await import("../next.config.mjs");
    const rewrites = await nextConfig.rewrites();
    assert.deepEqual(rewrites, [
      {
        source: "/backend-api/:path*",
        destination:
          "https://kastree-production-5658.up.railway.app/:path*",
      },
    ]);
  });
});
