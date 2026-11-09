import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { makeStore } from "../../../src/_app/store/store";
import { accountApi } from "../../../src/shared/api/account";
import { authApi } from "../../../src/shared/api/auth";
import { usersApi } from "../../../src/shared/api/users";

const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
let store: ReturnType<typeof makeStore>;
let requests: Request[];
let mutationStatus: number;
const user = { id: 1, email: "test@example.com", first_name: "Before" };

beforeEach(() => {
  // Browser fetch accepts relative URLs; Node's Request requires an origin.
  globalThis.Request = class extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(
        typeof input === "string" ? new URL(input, "http://localhost") : input,
        init,
      );
    }
  };
  requests = [];
  mutationStatus = 200;
  globalThis.fetch = async (input) => {
    const request = input as Request;
    requests.push(request);
    if (new URL(request.url).pathname === "/api/users/logout") {
      return mutationStatus === 200
        ? new Response(null, { status: 204 })
        : Response.json({ detail: ["Failed"] }, { status: mutationStatus });
    }
    if (request.method !== "GET") {
      return mutationStatus === 200
        ? new Response(null, { status: 200 })
        : Response.json({ detail: ["Failed"] }, { status: mutationStatus });
    }
    return Response.json(user);
  };
  store = makeStore();
});

afterEach(() => {
  store.dispatch(accountApi.util.resetApiState());
  globalThis.Request = NativeRequest;
  globalThis.fetch = nativeFetch;
});

async function settle() {
  await setImmediate();
  await Promise.all(store.dispatch(accountApi.util.getRunningQueriesThunk()));
  await setImmediate();
}

const getMe = () =>
  store.dispatch(accountApi.endpoints.usersMeRetrieve.initiate());
const patchMe = () =>
  store.dispatch(
    accountApi.endpoints.usersMePartialUpdate.initiate({
      patchedUpdateRequest: { first_name: "After" },
    }),
  );
const login = () =>
  store.dispatch(
    authApi.endpoints.usersLoginCreate.initiate({
      loginRequest: {
        email: "test@example.com",
        password: "test-password",
        remember_me: false,
      },
    }),
  );

test("logout calls the backend with session credentials", async () => {
  await store.dispatch(authApi.endpoints.usersLogoutCreate.initiate()).unwrap();
  assert.equal(requests.length, 1);
  assert.equal(new URL(requests[0].url).pathname, "/api/users/logout");
  assert.equal(requests[0].method, "POST");
  assert.equal(requests[0].credentials, "include");
});

test("identical subscriptions share a request and preserve credentials", async () => {
  const first = getMe();
  const second = getMe();
  await Promise.all([first.unwrap(), second.unwrap()]);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].credentials, "include");
  assert.equal(new URL(requests[0].url).pathname, "/api/users/me");
  first.unsubscribe();
  second.unsubscribe();
});

test("profile success refreshes active current-user and user queries", async () => {
  await getMe().unwrap();
  await store
    .dispatch(usersApi.endpoints.usersRetrieve.initiate({ id: 1 }))
    .unwrap();
  await patchMe().unwrap();
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 4);
  const patch = requests.find((r) => r.method === "PATCH");
  assert.ok(patch);
  assert.deepEqual(await patch.json(), { first_name: "After" });
});

test("profile failure preserves cache without refetching", async () => {
  await getMe().unwrap();
  mutationStatus = 400;
  await assert.rejects(patchMe().unwrap());
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 1);
  assert.deepEqual(
    accountApi.endpoints.usersMeRetrieve.select()(store.getState()).data,
    user,
  );
});

for (const status of [200, 400]) {
  test(`email confirmation ${status} refreshes profile only on success`, async () => {
    await getMe().unwrap();
    mutationStatus = status;
    const confirmation = store
      .dispatch(
        accountApi.endpoints.usersEmailConfirmCreate.initiate({
          emailWithCodeRequest: { email: "new@example.com", code: "123" },
        }),
      )
      .unwrap();
    if (status === 200) await confirmation;
    else await assert.rejects(confirmation);
    await settle();
    assert.equal(
      requests.filter((r) => r.method === "GET").length,
      status === 200 ? 2 : 1,
    );
    const request = requests.find((r) => r.method === "POST");
    assert.ok(request);
    assert.equal(new URL(request.url).pathname, "/api/users/email/confirm");
    assert.deepEqual(await request.json(), {
      email: "new@example.com",
      code: "123",
    });
  });
}

test("invalidation drops unsubscribed cache without requesting it again", async () => {
  const subscription = getMe();
  await subscription.unwrap();
  subscription.unsubscribe();
  await patchMe().unwrap();
  await settle();
  assert.equal(requests.filter((r) => r.method === "GET").length, 1);
  assert.equal(
    accountApi.endpoints.usersMeRetrieve.select()(store.getState())
      .isUninitialized,
    true,
  );
});

test("successful login clears previous account data without eager /me", async () => {
  const subscription = getMe();
  await subscription.unwrap();
  subscription.unsubscribe();
  await login().unwrap();
  await settle();
  assert.deepEqual(store.getState().api.queries, {});
  assert.equal(requests.filter((r) => r.method === "GET").length, 1);
});

test("failed login preserves previous account data", async () => {
  await getMe().unwrap();
  mutationStatus = 401;
  await assert.rejects(login().unwrap());
  await settle();
  assert.deepEqual(
    accountApi.endpoints.usersMeRetrieve.select()(store.getState()).data,
    user,
  );
});

test("stores are isolated", async () => {
  const other = makeStore();
  await getMe().unwrap();
  assert.deepEqual(other.getState().api.queries, {});
  other.dispatch(accountApi.util.resetApiState());
});

test("photo upload sends multipart data and refreshes the current user", async () => {
  await getMe().unwrap();
  const photo = new File(["photo bytes"], "avatar.png", { type: "image/png" });
  await store
    .dispatch(
      accountApi.endpoints.usersMePhotoPartialUpdate.initiate({
        patchedUpdatePhotoRequest: { photo },
      }),
    )
    .unwrap();
  await settle();
  const request = requests.find(
    (request) => new URL(request.url).pathname === "/api/users/me/photo",
  );
  assert.ok(request);
  assert.equal(request.method, "PATCH");
  assert.match(
    request.headers.get("content-type") ?? "",
    /^multipart\/form-data; boundary=/,
  );
  const form = await request.formData();
  const uploaded = form.get("photo");
  assert.ok(uploaded instanceof File);
  assert.equal(uploaded.name, "avatar.png");
  assert.equal(await uploaded.text(), "photo bytes");
  assert.equal(
    requests.filter((request) => request.method === "GET").length,
    2,
  );
});

test("successful logout clears cached profile and other session data", async () => {
  const subscription = getMe();
  await subscription.unwrap();
  subscription.unsubscribe();
  await store.dispatch(authApi.endpoints.usersLogoutCreate.initiate()).unwrap();
  await settle();
  assert.deepEqual(store.getState().api.queries, {});
  assert.equal(
    accountApi.endpoints.usersMeRetrieve.select()(store.getState()).data,
    undefined,
  );
});

test("failed logout preserves cached profile", async () => {
  await getMe().unwrap();
  mutationStatus = 500;
  await assert.rejects(
    store.dispatch(authApi.endpoints.usersLogoutCreate.initiate()).unwrap(),
  );
  await settle();
  assert.deepEqual(
    accountApi.endpoints.usersMeRetrieve.select()(store.getState()).data,
    user,
  );
});

test("prompt PATCH sends only system_prompt and refreshes the active profile", async () => {
  await getMe().unwrap();
  await store
    .dispatch(
      accountApi.endpoints.usersMePartialUpdate.initiate({
        patchedUpdateRequest: {
          system_prompt: "Инструкции для следующих сообщений",
        },
      }),
    )
    .unwrap();
  await settle();
  const request = requests.find((item) => item.method === "PATCH");
  assert.ok(request);
  assert.equal(new URL(request.url).pathname, "/api/users/me");
  assert.deepEqual(await request.json(), {
    system_prompt: "Инструкции для следующих сообщений",
  });
  assert.equal(request.credentials, "include");
  assert.equal(requests.filter((item) => item.method === "GET").length, 2);
});
