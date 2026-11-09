import assert from "node:assert/strict";
import test from "node:test";
import { proxyRewrites } from "../../../proxy.config";

test("direct Next serves the ticket's /ai path through a separate AI upstream", () => {
  assert.deepEqual(
    proxyRewrites({
      API_ORIGIN: "http://127.0.0.1:8011",
      AI_ORIGIN: "http://127.0.0.1:8012",
    }).fallback,
    [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8011/api/:path*",
      },
      {
        source: "/ai/api/v1/runs/:runId/ws",
        destination: "http://127.0.0.1:8012/api/v1/runs/:runId/ws",
      },
    ],
  );
});

test("public nginx origin retains its /ai prefix and proxies only the run socket", () => {
  const routes = proxyRewrites({
    API_ORIGIN: "https://company-corp.ru",
  }).fallback;
  assert.equal(
    routes[1].destination,
    "https://company-corp.ru/ai/api/v1/runs/:runId/ws",
  );
  assert.equal(routes.length, 2);
});

test("internal proxy upstreams cannot contain credentials or paths", () => {
  for (const value of [
    "https://user:password@example.org",
    "https://example.org/private",
    "file:///tmp/file",
    "https://example.org?key=secret",
  ]) {
    assert.throws(() => proxyRewrites({ AI_ORIGIN: value }));
  }
});
