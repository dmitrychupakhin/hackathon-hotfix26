import assert from "node:assert/strict";
import { test } from "node:test";
import { makeStore } from "../../../src/_app/store/store";
import { passwordRecoverySchema } from "../../../src/_pages/password-recovery/ui/password-recovery-schema";
import { accountApi } from "../../../src/shared/api/account";

test("password recovery validates input and normalizes email", () => {
  const valid = {
    email: " user@example.com ",
    code: "123",
    password: "secret",
    confirm: "secret",
  };
  assert.equal(passwordRecoverySchema.parse(valid).email, "user@example.com");
  for (const change of [
    { email: "invalid" },
    { code: "" },
    { password: "" },
    { confirm: "other" },
  ]) {
    assert.equal(
      passwordRecoverySchema.safeParse({ ...valid, ...change }).success,
      false,
    );
  }
});

test("password recovery sends email and confirmation to the generated endpoints", async () => {
  const NativeRequest = globalThis.Request;
  const nativeFetch = globalThis.fetch;
  const requests: { path: string; body: unknown }[] = [];
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
    requests.push({
      path: new URL(request.url).pathname,
      body: await request.json(),
    });
    return Response.json({ detail: ["OK"] });
  };
  const store = makeStore();
  try {
    await store
      .dispatch(
        accountApi.endpoints.usersPasswordResetCreate.initiate({
          emailRequest: { email: "user@example.com" },
        }),
      )
      .unwrap();
    const values = {
      email: "user@example.com",
      code: "123",
      password: "secret",
      confirm: "secret",
    };
    await store
      .dispatch(
        accountApi.endpoints.usersPasswordResetConfirmCreate.initiate({
          resetPasswordRequest: values,
        }),
      )
      .unwrap();
    assert.deepEqual(requests, [
      {
        path: "/api/users/password/reset",
        body: { email: "user@example.com" },
      },
      { path: "/api/users/password/reset/confirm", body: values },
    ]);
  } finally {
    store.dispatch(accountApi.util.resetApiState());
    globalThis.Request = NativeRequest;
    globalThis.fetch = nativeFetch;
  }
});
