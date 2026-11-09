import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { apiModules } from "../../../api.config";
import { baseApi } from "../../../src/shared/api/base-api";
import { requestCookies } from "../fixtures/server-loader.mjs";

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

test("server imports do not register browser endpoints", async () => {
  assert.deepEqual(Object.keys(baseApi.endpoints), []);
  for (const module of Object.keys(apiModules)) {
    await import(`../../../src/shared/api/${module}/index.server.ts`);
  }
  assert.deepEqual(Object.keys(baseApi.endpoints), []);
});

test("server API isolates concurrent users and forces origin, cookies and no-store", async () => {
  const { getAccountServerApi } = await import(
    "../../../src/shared/api/account/index.server"
  );
  const requests: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = async (input, init) => {
    assert.ok(init);
    const url = input instanceof Request ? input.url : input.toString();
    requests.push({ url, init });
    await new Promise<void>((resolve) => setImmediate(resolve));
    return Response.json({
      id: 1,
      email: new Headers(init.headers).get("Cookie"),
    });
  };
  const [alice, bob] = await Promise.all(
    ["session=alice", "session=bob"].map((cookie) =>
      requestCookies.run(cookie, async () => {
        const api = await getAccountServerApi();
        return api.usersMeRetrieve({
          headers: { Cookie: "cannot-override-session", "X-Request": "custom" },
        });
      }),
    ),
  );
  assert.equal(alice.email, "session=alice");
  assert.equal(bob.email, "session=bob");
  assert.equal(requests.length, 2);
  for (const { url, init } of requests) {
    assert.equal(url, "https://backend.example/api/users/me");
    assert.equal(init.cache, "no-store");
    assert.equal(init.redirect, "manual");
    assert.equal(new Headers(init.headers).get("X-Request"), "custom");
    assert.equal(new Headers(init.headers).get("Authorization"), null);
  }
});

test("server API without cookies remains anonymous and returns data directly", async () => {
  const { getUsersServerApi } = await import(
    "../../../src/shared/api/users/index.server"
  );
  globalThis.fetch = async (input, init) => {
    assert.equal(input.toString(), "https://backend.example/api/users/42");
    assert.equal(new Headers(init?.headers).get("Cookie"), null);
    return Response.json({ id: 42, first_name: "User" });
  };
  const api = await getUsersServerApi();
  const user = await api.usersRetrieve({ path: { id: 42 } });
  assert.equal(user.id, 42);
  assert.equal(user.first_name, "User");
});

for (const status of [401, 500]) {
  test(`server API preserves HTTP ${status} and error body`, async () => {
    const { getAccountServerApi, ServerApiError } = await import(
      "../../../src/shared/api/account/index.server"
    );
    const body = { detail: ["Backend error"] };
    globalThis.fetch = async () => Response.json(body, { status });
    const api = await getAccountServerApi();
    await assert.rejects(api.usersMeRetrieve(), (error: unknown) => {
      assert.ok(error instanceof ServerApiError);
      assert.equal(error.status, status);
      assert.deepEqual(error.body, body);
      return true;
    });
  });
}

test("server API propagates network errors without hiding them", async () => {
  const { getAccountServerApi } = await import(
    "../../../src/shared/api/account/index.server"
  );
  const failure = new Error("Network unavailable");
  globalThis.fetch = async () => {
    throw failure;
  };
  const api = await getAccountServerApi();
  await assert.rejects(
    api.usersMeRetrieve(),
    (error: unknown) => error === failure,
  );
});

test("server transport refuses foreign origins before forwarding cookies", async () => {
  const { createServerFetch } = await import(
    "../../../src/shared/api/server-transport"
  );
  let called = false;
  const fetchImplementation: typeof fetch = async () => {
    called = true;
    return Response.json({});
  };
  const serverFetch = createServerFetch(
    "https://backend.example",
    "session=private",
    fetchImplementation,
  );
  await assert.rejects(
    serverFetch("https://foreign.example/api/users/me"),
    /API_ORIGIN/,
  );
  assert.equal(called, false);
});

test("server API preserves non-JSON HTTP errors", async () => {
  const { getAccountServerApi, ServerApiError } = await import(
    "../../../src/shared/api/account/index.server"
  );
  globalThis.fetch = async () => new Response("Unavailable", { status: 503 });
  const api = await getAccountServerApi();
  await assert.rejects(api.usersMeRetrieve(), (error: unknown) => {
    assert.ok(error instanceof ServerApiError);
    assert.equal(error.status, 503);
    assert.equal(error.body, "Unavailable");
    return true;
  });
});
