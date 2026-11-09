import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { NextRequest } from "next/server";
import { config, proxy } from "../../../proxy";

const originalFetch = globalThis.fetch;
const originalOrigin = process.env.API_ORIGIN;
beforeEach(() => {
  process.env.API_ORIGIN = "https://backend.example";
});
afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalOrigin === undefined) delete process.env.API_ORIGIN;
  else process.env.API_ORIGIN = originalOrigin;
});

test("expired access transparently refreshes on chat deep link instead of visiting login/profile", async () => {
  const calls: string[] = [];
  globalThis.fetch = async (input) => {
    const url = input instanceof Request ? input.url : input.toString();
    calls.push(url);
    if (url.endsWith("/api/users/me"))
      return Response.json({ detail: "expired" }, { status: 401 });
    assert.ok(url.endsWith("/api/users/refresh"));
    return Response.json(
      {},
      {
        headers: {
          "Set-Cookie": "access=fresh; Path=/; HttpOnly; SameSite=Lax",
        },
      },
    );
  };
  const request = new NextRequest("https://site.test/chats?chat=abc", {
    headers: { Cookie: "access=expired; refresh=valid" },
  });
  const response = await proxy(request);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("location"), null);
  assert.equal(response.headers.get("x-middleware-next"), "1");
  assert.match(response.headers.getSetCookie().join(";"), /access=fresh/);
  assert.equal(request.cookies.get("access")?.value, "fresh");
  assert.match(
    response.headers.get("x-middleware-request-cookie") || "",
    /access=fresh/,
  );
  assert.equal(new URL(request.url).search, "?chat=abc");
  assert.equal(calls.length, 2);
});

test("all protected routes match proxy and redirect to login with their local return URL", async () => {
  for (const path of [
    "/chats",
    "/prompt",
    "/comparisons",
    "/profile",
    "/change-email",
    "/change-password",
  ]) {
    assert.ok(config.matcher.includes(`${path}/:path*`));
    const response = await proxy(
      new NextRequest(`https://site.test${path}?chat=abc`),
    );
    const location = response.headers.get("location");
    assert.ok(location);
    const redirect = new URL(location);
    assert.equal(redirect.pathname, "/login");
    assert.equal(redirect.searchParams.get("next"), `${path}?chat=abc`);
  }
});

test("authenticated login follows safe next rather than replacing the chat URL with profile", async () => {
  globalThis.fetch = async () => Response.json({ id: 1 });
  for (const [next, destination] of [
    ["/chats?chat=abc", "/chats?chat=abc"],
    ["//evil.test/chats", "/profile"],
  ]) {
    const login = new URL("https://site.test/login");
    login.searchParams.set("next", next);
    const response = await proxy(
      new NextRequest(login, { headers: { Cookie: "access=valid" } }),
    );
    assert.equal(
      response.headers.get("location"),
      `https://site.test${destination}`,
    );
  }
});
