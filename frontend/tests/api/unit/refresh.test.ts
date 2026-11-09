import assert from "node:assert/strict";
import { test } from "node:test";
import { makeStore } from "../../../src/_app/store/store";
import { accountApi } from "../../../src/shared/api/account";

test("401 refreshes cookies and retries the original request once", async () => {
  const NativeRequest = globalThis.Request;
  const nativeFetch = globalThis.fetch;
  const paths: string[] = [];
  let refreshed = false;
  globalThis.Request = class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(
        typeof input === "string" ? new URL(input, "http://localhost") : input,
        init,
      );
    }
  };
  globalThis.fetch = async (input) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    paths.push(path);
    assert.equal(request.credentials, "include");
    if (path === "/api/users/refresh") {
      refreshed = true;
      return new Response(null, { status: 200 });
    }
    return refreshed
      ? Response.json({ id: 1 })
      : Response.json({}, { status: 401 });
  };
  const store = makeStore();
  try {
    const result = await store.dispatch(
      accountApi.endpoints.usersMeRetrieve.initiate(),
    );
    assert.equal(result.isSuccess, true);
    assert.equal(paths.length, 3);
    assert.equal(paths[1], "/api/users/refresh");
    assert.equal(paths[0], paths[2]);
  } finally {
    store.dispatch(accountApi.util.resetApiState());
    globalThis.Request = NativeRequest;
    globalThis.fetch = nativeFetch;
  }
});
