import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { Window } from "happy-dom";

const browser = new Window({ url: "http://localhost:3000/prompt" });
const globals = [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "Element",
  "Node",
  "Document",
  "ShadowRoot",
  "DocumentFragment",
  "MutationObserver",
  "Event",
  "MouseEvent",
  "getComputedStyle",
];
const previous = new Map(
  globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
for (const key of globals)
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value:
      key === "getComputedStyle"
        ? browser.getComputedStyle.bind(browser)
        : browser[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
const { Provider } = await import("react-redux");
const { makeStore } = await import("../../src/_app/store/store.ts");
const { accountApi } = await import("../../src/shared/api/account/index.ts");
const { Prompt } = await import("../../src/_pages/prompt/ui/prompt.tsx");
const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
let store,
  root,
  host,
  profile,
  requests,
  readStatus,
  writeStatus,
  writeError,
  holdWrite,
  releaseWrite,
  holdRead,
  releaseRead;
async function settle() {
  await act(async () => {
    for (let i = 0; i < 12; i++) await setImmediate();
  });
}
const input = () => host.querySelector("textarea");
const button = (text = "Сохранить инструкции") =>
  Array.from(host.querySelectorAll("button")).find(
    (element) => element.textContent.trim() === text,
  );
async function type(value) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      browser.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(input(), value);
    input().dispatchEvent(new Event("input", { bubbles: true }));
  });
  await settle();
}
async function click(element) {
  assert.ok(element);
  await act(async () => element.click());
  await settle();
}
async function mount() {
  store = makeStore();
  root = createRoot(host);
  await act(async () =>
    root.render(createElement(Provider, { store }, createElement(Prompt))),
  );
  await settle();
}
async function restart() {
  await act(async () => {
    root.unmount();
    store.dispatch(accountApi.util.resetApiState());
  });
  await mount();
}
beforeEach(async () => {
  profile = {
    id: 1,
    email: "test@example.com",
    first_name: "Иван",
    system_prompt: "Исходные инструкции",
  };
  requests = [];
  readStatus = 200;
  writeStatus = 200;
  writeError = { detail: ["Service unavailable"] };
  holdWrite = false;
  releaseWrite = undefined;
  holdRead = false;
  releaseRead = undefined;
  globalThis.Request = class extends NativeRequest {
    constructor(value, init) {
      super(
        typeof value === "string"
          ? new URL(value, "http://localhost:3000")
          : value,
        init,
      );
    }
  };
  globalThis.fetch = async (request) => {
    requests.push(request);
    if (request.method === "PATCH") {
      if (holdWrite)
        await new Promise((resolve) => {
          releaseWrite = resolve;
        });
      if (writeStatus >= 400)
        return Response.json(writeError, { status: writeStatus });
      const body = await request.clone().json();
      profile = { ...profile, ...body };
      return new Response(null, { status: 200 });
    }
    if (holdRead)
      await new Promise((resolve) => {
        releaseRead = resolve;
      });
    return readStatus === 200
      ? Response.json(profile)
      : Response.json({ detail: ["Unavailable"] }, { status: readStatus });
  };
  host = document.createElement("div");
  document.body.append(host);
  await mount();
});
afterEach(async () => {
  releaseWrite?.();
  releaseRead?.();
  await act(async () => {
    root.unmount();
    store.dispatch(accountApi.util.resetApiState());
  });
  await settle();
  host.remove();
  globalThis.Request = NativeRequest;
  globalThis.fetch = nativeFetch;
});
after(async () => {
  await browser.happyDOM.close();
  for (const [key, descriptor] of previous) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
  delete globalThis.IS_REACT_ACT_ENVIRONMENT;
});

test("loads saved instructions and PATCHes only the trimmed prompt with internal newlines preserved", async () => {
  assert.equal(input().value, "Исходные инструкции");
  assert.equal(button().disabled, true);
  await type("  Новые инструкции\nВторая строка  ");
  await click(button());
  const patch = requests.find((request) => request.method === "PATCH");
  assert.deepEqual(await patch.clone().json(), {
    system_prompt: "Новые инструкции\nВторая строка",
  });
  assert.equal(input().value, "Новые инструкции\nВторая строка");
  assert.equal(button().disabled, true);
  assert.ok(host.textContent.includes("Инструкции сохранены"));
  await restart();
  assert.equal(input().value, "Новые инструкции\nВторая строка");
});
test("empty prompt clears instructions and 8000/8001 character boundaries are enforced", async () => {
  await type("");
  await click(button());
  assert.equal(profile.system_prompt, "");
  await type("я".repeat(8000));
  assert.equal(button().disabled, false);
  await click(button());
  assert.equal(profile.system_prompt.length, 8000);
  const count = requests.filter((request) => request.method === "PATCH").length;
  await type("я".repeat(8001));
  assert.equal(button().disabled, true);
  assert.ok(host.querySelector('[role="alert"]')?.textContent.includes("8000"));
  await act(async () =>
    host
      .querySelector("form")
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  await settle();
  assert.equal(
    requests.filter((request) => request.method === "PATCH").length,
    count,
  );
});
test("failed save retains the draft and allows retry without editing", async () => {
  writeStatus = 503;
  await type("Черновик");
  await click(button());
  assert.equal(input().value, "Черновик");
  assert.ok(host.querySelector('[role="alert"]'));
  assert.equal(button().disabled, false);
  writeStatus = 200;
  await click(button());
  assert.equal(profile.system_prompt, "Черновик");
  assert.equal(host.querySelector('[role="alert"]'), null);
});
test("server field errors are shown beside the textarea and editing enables resubmission", async () => {
  writeStatus = 400;
  writeError = { system_prompt: ["Недопустимые инструкции"] };
  await type("Черновик");
  await click(button());
  assert.equal(input().getAttribute("aria-invalid"), "true");
  assert.ok(
    host
      .querySelector("#prompt-field-error")
      ?.textContent.includes("Недопустимые инструкции"),
  );
  writeStatus = 200;
  await type("Исправленные инструкции");
  assert.equal(button().disabled, false);
  await click(button());
  assert.equal(profile.system_prompt, "Исправленные инструкции");
});
test("saving disables editing and duplicate submission until the request finishes", async () => {
  holdWrite = true;
  await type("Сохранить один раз");
  await click(button());
  assert.equal(input().disabled, true);
  assert.equal(button("Сохранение…").disabled, true);
  assert.equal(
    requests.filter((request) => request.method === "PATCH").length,
    1,
  );
  releaseWrite();
  await settle();
  assert.equal(input().disabled, false);
  assert.equal(profile.system_prompt, "Сохранить один раз");
});
test("a background profile refresh preserves dirty text and clean forms adopt refreshed values", async () => {
  profile = { ...profile, system_prompt: "Обновлено на сервере" };
  await act(async () => {
    await store.dispatch(
      accountApi.endpoints.usersMeRetrieve.initiate(undefined, {
        forceRefetch: true,
        subscribe: false,
      }),
    );
  });
  await settle();
  assert.equal(input().value, "Обновлено на сервере");
  await type("Мой несохранённый текст");
  profile = { ...profile, system_prompt: "Чужое обновление" };
  await act(async () => {
    await store.dispatch(
      accountApi.endpoints.usersMeRetrieve.initiate(undefined, {
        forceRefetch: true,
        subscribe: false,
      }),
    );
  });
  await settle();
  assert.equal(input().value, "Мой несохранённый текст");
  assert.equal(button().disabled, false);
});
test("loading and retry states do not expose an editable blank prompt", async () => {
  holdRead = true;
  await restart();
  assert.equal(input(), null);
  assert.ok(host.textContent.includes("Загрузка инструкций"));
  readStatus = 503;
  holdRead = false;
  releaseRead();
  await settle();
  assert.equal(input(), null);
  assert.ok(button("Повторить"));
  readStatus = 200;
  await click(button("Повторить"));
  assert.equal(input().value, "Исходные инструкции");
});
