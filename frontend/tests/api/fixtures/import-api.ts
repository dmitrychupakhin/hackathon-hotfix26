import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { apiModules } from "../../../api.config";
import { makeStore } from "../../../src/_app/store/store";
import { baseApi } from "../../../src/shared/api/base-api";

const expected = Object.fromEntries(
  Object.keys(apiModules).map((module) => [
    module,
    JSON.parse(
      readFileSync(
        `src/shared/api/__generated__/${module}/manifest.json`,
        "utf8",
      ),
    ) as { endpoints: string[]; hooks: string[] },
  ]),
);

async function main() {
  assert.deepEqual(Object.keys(baseApi.endpoints), []);
  const module = process.argv[2];
  assert.ok(module in expected);
  const imported = await import(`../../../src/shared/api/${module}/index.ts`);
  const manualEndpoints =
    module === "chats"
      ? ["watchChatRun", "chatHistory", "chatMessages", "chatFiles"]
      : [];
  assert.deepEqual(
    Object.keys(baseApi.endpoints).sort(),
    [...expected[module].endpoints, ...manualEndpoints].sort(),
  );
  assert.equal(imported[`${module}Api`], baseApi);
  for (const hook of expected[module].hooks)
    assert.equal(typeof imported[hook], "function");

  if (module === "account") {
    const { accountApi } = await import("../../../src/shared/api/account");
    const store = makeStore();
    await store.dispatch(
      accountApi.util.upsertQueryData("usersMeRetrieve", undefined, {
        id: 1,
        email: "test@example.com",
      }),
    );
    const before = store.getState();
    const { authApi } = await import("../../../src/shared/api/auth");
    assert.equal(authApi, baseApi);
    assert.equal(store.getState(), before);
    assert.equal(
      accountApi.endpoints.usersMeRetrieve.select()(store.getState()).data?.id,
      1,
    );
    assert.deepEqual(
      Object.keys(baseApi.endpoints).sort(),
      [...expected.account.endpoints, ...expected.auth.endpoints].sort(),
    );
    store.dispatch(baseApi.util.resetApiState());
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
