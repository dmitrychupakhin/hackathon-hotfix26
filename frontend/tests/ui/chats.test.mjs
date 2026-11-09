import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { Window } from "happy-dom";

const browser = new Window({ url: "http://localhost:3000/chats" });
const globals = [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "HTMLInputElement",
  "HTMLTextAreaElement",
  "Element",
  "Node",
  "NodeFilter",
  "Document",
  "ShadowRoot",
  "DocumentFragment",
  "MutationObserver",
  "ResizeObserver",
  "Event",
  "MouseEvent",
  "PointerEvent",
  "KeyboardEvent",
  "getComputedStyle",
  "requestAnimationFrame",
  "cancelAnimationFrame",
];
const previous = new Map(
  globals.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]),
);
for (const key of globals)
  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value:
      typeof browser[key] === "function" &&
      [
        "getComputedStyle",
        "requestAnimationFrame",
        "cancelAnimationFrame",
      ].includes(key)
        ? browser[key].bind(browser)
        : browser[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { act, createElement } = await import("react");
const { createRoot } = await import("react-dom/client");
const { Provider } = await import("react-redux");
const { makeStore } = await import("../../src/_app/store/store.ts");
const { baseApi } = await import("../../src/shared/api/base-api.ts");
const { Chats } = await import("../../src/_pages/chats/ui/chats.tsx");
const { ChatSteps } = await import("../../src/_pages/chats/ui/chat-steps.tsx");
const { ChatAnswer } = await import(
  "../../src/_pages/chats/ui/chat-answer.tsx"
);
const { highlightDocument } = await import(
  "../../src/_pages/chats/ui/highlight-document.ts"
);
const { chatsApi } = await import("../../src/shared/api/chats/chats-api.ts");
const { runStreamApi } = await import(
  "../../src/shared/api/chats/run-stream-api.ts"
);
const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
const originalError = console.error;
const chat = (id) => ({
  id,
  title: `Чат ${id}`,
  model_id: "model",
  created_at: "2026-11-08T10:00:00Z",
  updated_at: "2026-11-08T10:00:00Z",
});
const page = (results) => ({
  results,
  count: results.length,
  next: null,
  previous: null,
});
let root, store, host, errors, delayedB, releaseB, requests, submissions;
let previewFixture, assistantCitation, restoredRun;
const citationHash = "a".repeat(64);
const sampleCitation = {
  id: "e1",
  file_id: "file-A",
  file_name: "brief-A.txt",
  quote: "5%",
  start: 7,
  end: 9,
  text_sha256: citationHash,
  version: "v1",
  locations: [],
};
async function settle() {
  await act(async () => {
    for (let i = 0; i < 15; i++) await setImmediate();
  });
}
function findButton(title) {
  return Array.from(host.querySelectorAll("button")).find(
    (button) =>
      button.title === title ||
      button.textContent.trim() === title ||
      button.getAttribute("aria-label") === title,
  );
}
async function click(button) {
  assert.ok(button, "button exists");
  await act(async () => button.click());
  await settle();
}
function assertVisibleChat(id) {
  assert.equal(
    host.querySelectorAll('section[aria-label="Обсуждение"]').length,
    1,
  );
  assert.equal(
    host.querySelectorAll('aside[aria-label="Файлы обсуждения"]').length,
    1,
  );
  assert.equal(
    host.querySelector('section[aria-label="Обсуждение"] h2')?.textContent,
    `Чат ${id}`,
  );
  assert.equal(
    host.querySelectorAll('section[aria-label="Сообщения чата"]').length,
    1,
  );
  assert.ok(
    host
      .querySelector('section[aria-label="Сообщения чата"]')
      .textContent.includes(`Сообщение ${id}`),
  );
  assert.equal(
    errors.filter((message) => /same key|unique.*key/i.test(message)).length,
    0,
  );
}
beforeEach(async () => {
  errors = [];
  requests = [];
  submissions = 0;
  previewFixture = {
    file_id: "file-A",
    name: "brief-A.txt",
    format: "txt",
    text: "😀 5% и 5%",
    text_sha256: citationHash,
    version: "v1",
    locations: [],
    partial: false,
    warnings: [],
    content_url: "/api/chats/A/files/file-A/content",
    offset_unit: "unicode_code_points",
  };
  assistantCitation = undefined;
  restoredRun = undefined;
  delayedB = false;
  releaseB = undefined;
  console.error = (...args) => errors.push(args.map(String).join(" "));
  globalThis.Request = class extends NativeRequest {
    constructor(input, init) {
      super(
        typeof input === "string"
          ? new URL(input, "http://localhost:3000")
          : input,
        init,
      );
    }
  };
  globalThis.fetch = async (input) => {
    const request = input;
    requests.push(request);
    const path = new URL(request.url).pathname;
    if (path === "/api/chats")
      return Response.json(page([chat("A"), chat("B")]));
    if (path === "/api/chats/models")
      return Response.json([{ id: "model", name: "Тестовая модель" }]);
    const id = path.split("/")[3];
    if (path.endsWith("/preview")) return Response.json(previewFixture);
    if (path.endsWith("/files"))
      return Response.json(
        page([
          {
            id: `file-${id}`,
            name: `brief-${id}.pdf`,
            size: 2516582,
            media_type: "application/pdf",
            sha256: "abc",
            created_at: "2026-11-08T10:00:00Z",
          },
        ]),
      );
    if (path.endsWith("/ws-ticket"))
      return Response.json({ detail: ["Pending"] }, { status: 409 });
    if (path.includes("/runs/"))
      return Response.json({
        id: "run-A",
        status: "pending",
        error: "",
        created_at: "now",
        updated_at: "now",
      });
    if (path.endsWith("/messages") && request.method === "POST") {
      submissions += 1;
      return Response.json(
        {
          message: {
            id: "sent-A",
            role: "user",
            content: "Вопрос",
            created_at: "now",
          },
          run: {
            id: submissions === 1 ? "run-A" : `run-A-${submissions}`,
            status: "pending",
            error: "",
            created_at: "now",
            updated_at: "now",
          },
        },
        { status: 202 },
      );
    }
    if (path.endsWith("/messages"))
      return Response.json(
        page([
          {
            id: `message-${id}`,
            role: "user",
            content: `Сообщение ${id}`,
            created_at: "2026-11-08T10:00:00Z",
          },
          ...(assistantCitation
            ? [
                {
                  id: "assistant-A",
                  role: "assistant",
                  content: "Обеспечение 5%",
                  citations: [assistantCitation],
                  created_at: "2026-11-08T10:01:00Z",
                },
              ]
            : []),
        ]),
      );
    if (path === "/api/chats/B" && delayedB)
      await new Promise((resolve) => {
        releaseB = resolve;
      });
    return Response.json({
      ...chat(id),
      latest_run: id === "A" ? restoredRun : null,
    });
  };
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () =>
    root.render(createElement(Provider, { store }, createElement(Chats))),
  );
  await settle();
});
afterEach(async () => {
  releaseB?.();
  await act(async () => {
    root.unmount();
    store.dispatch(baseApi.util.resetApiState());
  });
  await settle();
  host.remove();
  console.error = originalError;
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

test("repeated A/B switching replaces conversation and files without duplicate React keys", async () => {
  for (const id of ["A", "B", "A", "B", "A", "B", "A"]) {
    await click(findButton(`Чат ${id}`));
    assertVisibleChat(id);
  }
});

async function selectFiles(input, files) {
  await act(async () => {
    Object.defineProperty(input, "files", { configurable: true, value: files });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await settle();
}

test("multiple files use individual multipart uploads and keep the queue locked until completion", async () => {
  await click(findButton("Чат A"));
  const fetchFixture = globalThis.fetch;
  const uploaded = [];
  let releaseUpload;
  globalThis.fetch = async (request) => {
    if (request.method !== "POST" || !request.url.endsWith("/files"))
      return fetchFixture(request);
    const form = await request.formData();
    assert.deepEqual([...form.keys()], ["file"]);
    const file = form.get("file");
    uploaded.push({ name: file.name, content: await file.text() });
    if (uploaded.length === 1)
      await new Promise((resolve) => {
        releaseUpload = resolve;
      });
    return Response.json({ id: file.name, name: file.name });
  };
  const input = host.querySelector('input[type="file"]:not([webkitdirectory])');
  assert.equal(input.multiple, true);
  try {
    await selectFiles(input, [
      new File(["first"], "one.txt"),
      new File(["second"], "two.txt"),
    ]);
    assert.equal(uploaded.length, 1);
    assert.equal(findButton("Загрузка…").disabled, true);
    assert.equal(findButton("Загрузить папку").disabled, true);
    assert.ok(host.textContent.includes("Обработано файлов: 0 из 2"));
  } finally {
    releaseUpload?.();
    await settle();
  }
  assert.deepEqual(uploaded, [
    { name: "one.txt", content: "first" },
    { name: "two.txt", content: "second" },
  ]);
  assert.equal(input.value, "");
  assert.equal(findButton("Загрузить файлы").disabled, false);
});

test("folder uploads retain individual filenames and report failures while continuing", async () => {
  await click(findButton("Чат A"));
  const fetchFixture = globalThis.fetch;
  const uploaded = [];
  globalThis.fetch = async (request) => {
    if (request.method !== "POST" || !request.url.endsWith("/files"))
      return fetchFixture(request);
    const file = (await request.formData()).get("file");
    uploaded.push(file.name);
    return file.name === "broken.txt"
      ? Response.json({ detail: "Ошибка обработки" }, { status: 400 })
      : Response.json({ id: file.name, name: file.name });
  };
  const input = host.querySelector("input[webkitdirectory]");
  assert.ok(input);
  const nestedFile = new File(["nested"], "nested.txt");
  Object.defineProperty(nestedFile, "webkitRelativePath", {
    value: "folder/subfolder/nested.txt",
  });
  await selectFiles(input, [new File(["bad"], "broken.txt"), nestedFile]);
  assert.deepEqual(uploaded, ["broken.txt", "nested.txt"]);
  assert.ok(
    host.querySelector('[role="alert"]').textContent.includes("broken.txt"),
  );
  assert.ok(
    host
      .querySelector('[role="alert"]')
      .textContent.includes("Ошибка обработки"),
  );
  assert.equal(findButton("Загрузить папку").disabled, false);
});

test("batch validation prevents uploads exceeding count, file size or filename limits", async () => {
  await click(findButton("Чат A"));
  const input = host.querySelector('input[type="file"]');
  const oversized = new File(["large"], "large.txt");
  Object.defineProperty(oversized, "size", { value: 10 * 1024 * 1024 + 1 });
  for (const [files, message] of [
    [
      Array.from({ length: 64 }, (_, i) => new File(["x"], `${i}.txt`)),
      "Можно добавить ещё: 63",
    ],
    [[new File(["valid"], "valid.txt"), oversized], "10 МиБ"],
    [[new File(["x"], `${"x".repeat(201)}.txt`)], "200 символов"],
  ]) {
    await selectFiles(input, files);
    assert.ok(
      host.querySelector('[role="alert"]').textContent.includes(message),
    );
  }
  assert.equal(
    requests.filter((request) => request.method === "POST").length,
    0,
  );
});
test("a slow previous-chat response cannot append or replace the selected conversation", async () => {
  await click(findButton("Чат A"));
  delayedB = true;
  await click(findButton("Чат B"));
  assert.ok(releaseB);
  await click(findButton("Чат A"));
  releaseB();
  await settle();
  assertVisibleChat("A");
});
test("chat actions live in list menus and file actions live in card menus", async () => {
  await click(findButton("Чат A"));
  assert.equal(
    host
      .querySelector('section[aria-label="Обсуждение"]')
      ?.textContent.includes("Переименовать"),
    false,
  );
  assert.equal(
    host
      .querySelector('textarea[aria-label="Сообщение"]')
      ?.getAttribute("rows"),
    "1",
  );
  assert.equal(host.querySelector('input[type="file"]')?.className, "hidden");
  assert.ok(findButton("Отправить сообщение"));
  await click(findButton("Действия чата «Чат B»"));
  const items = Array.from(document.querySelectorAll('[role="menuitem"]')).map(
    (item) => item.textContent,
  );
  assert.deepEqual(items, ["Переименовать", "Удалить"]);
  const trigger = findButton("Действия чата «Чат B»");
  await act(async () =>
    trigger.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: "Escape",
        code: "Escape",
        bubbles: true,
      }),
    ),
  );
  await settle();
  await click(findButton("Действия файла «brief-A.pdf»"));
  assert.deepEqual(
    Array.from(document.querySelectorAll('[role="menuitem"]')).map(
      (item) => item.textContent,
    ),
    ["Открыть", "Удалить"],
  );
  assert.equal(
    requests.filter((request) => request.method !== "GET").length,
    0,
  );
});

test("an active run remains observed while another conversation is visible", async () => {
  await click(findButton("Чат A"));
  const textarea = host.querySelector("textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      browser.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(textarea, "Вопрос");
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await settle();
  const send = findButton("Отправить сообщение");
  assert.equal(send.disabled, false);
  await click(send);
  assert.ok(findButton("Остановить ответ"));
  await click(findButton("Чат B"));
  assertVisibleChat("B");
  assert.equal(findButton("Остановить ответ"), undefined);
  assert.ok(
    Object.values(store.getState().api.queries).some(
      (query) =>
        query.endpointName === "watchChatRun" &&
        query.originalArgs.chatId === "A",
    ),
  );
  await click(findButton("Чат A"));
  assertVisibleChat("A");
  assert.ok(findButton("Остановить ответ"));
  assert.equal(
    requests.filter((request) => request.url.endsWith("/cancel")).length,
    0,
  );
});

test("chat reload restores its latest run observer without inventing an optimistic answer", async () => {
  restoredRun = {
    id: "restored-A",
    status: "pending",
    error: "",
    created_at: "now",
    updated_at: "now",
  };
  assistantCitation = sampleCitation;
  await click(findButton("Чат A"));
  const stream = Object.values(store.getState().api.queries).find(
    (query) =>
      query.endpointName === "watchChatRun" &&
      query.originalArgs.runId === "restored-A",
  );
  assert.ok(stream);
  await act(async () =>
    store.dispatch(
      runStreamApi.util.updateQueryData(
        "watchChatRun",
        { chatId: "A", runId: "restored-A", attempt: 0 },
        (draft) => {
          draft.answer = "Обеспечение 5%";
        },
      ),
    ),
  );
  await settle();
  assert.equal(
    Array.from(
      host.querySelectorAll('[aria-label="Сообщения чата"] > div'),
    ).filter((message) => message.textContent.includes("Обеспечение 5%"))
      .length,
    1,
  );
});

test("a citation opens a side preview and highlights its exact second occurrence after emoji", async () => {
  assistantCitation = sampleCitation;
  await click(findButton("Чат A"));
  const link = host.querySelector('[aria-label="Источники ответа"] a');
  assert.ok(link);
  assert.equal(link.textContent, "brief-A.txt[«5%»]");
  assert.equal(host.textContent.includes("Показать в документе"), false);
  await click(link);
  const panel = host.querySelector('[aria-label="Предпросмотр документа"]');
  assert.ok(panel);
  assert.equal(panel.textContent.includes("Скопировать ссылку"), false);
  assert.equal(panel.querySelector("textarea,input,[contenteditable]"), null);
  assert.equal(panel.querySelector("mark")?.textContent, "5%");
  assert.equal(panel.querySelector("pre")?.firstChild?.textContent, "😀 5% и ");
  assert.ok(requests.some((request) => request.url.includes("text_sha256=")));
  await click(findButton("Закрыть предпросмотр"));
  assert.equal(
    host.querySelector('[aria-label="Предпросмотр документа"]'),
    null,
  );
  assert.ok(host.querySelector('[aria-label="Файлы обсуждения"]'));
});

test("stale canonical text never highlights another repeated quote", async () => {
  assistantCitation = sampleCitation;
  previewFixture = { ...previewFixture, version: "v2" };
  await click(findButton("Чат A"));
  await click(host.querySelector('[aria-label="Источники ответа"] a'));
  const panel = host.querySelector('[aria-label="Предпросмотр документа"]');
  assert.equal(panel.querySelector("mark"), null);
  assert.ok(
    panel.textContent.includes("Не удалось подтвердить положение цитаты"),
  );
});

test("original-document highlight refuses repeated occurrences and safely marks a unique cross-node quote", () => {
  const document = browser.document;
  const repeated = document.createElement("div");
  repeated.innerHTML = "<p>5% и 5%</p>";
  assert.equal(highlightDocument(repeated, "5%"), false);
  assert.equal(repeated.querySelector("mark"), null);
  const unique = document.createElement("div");
  unique.innerHTML = "<p>Размер <strong>5% и </strong><em>10%</em>.</p>";
  assert.equal(highlightDocument(unique, "5% и 10%"), true);
  assert.equal(
    Array.from(unique.querySelectorAll("mark"))
      .map((mark) => mark.textContent)
      .join(""),
    "5% и 10%",
  );
  // Text-layer highlights must remain translucent so PDF canvas glyphs stay visible.
  assert.equal(
    unique.querySelector("mark").style.backgroundColor,
    "rgba(171, 211, 122, 0.35)",
  );
  assert.equal(unique.querySelector("mark").style.color, "inherit");
});

test("batch answers place each citation under its question and keep a failed item visible", async () => {
  const selected = [];
  await act(async () =>
    root.render(
      createElement(ChatAnswer, {
        chatId: "A",
        content: "legacy flattened answer",
        citations: [sampleCitation],
        payload: {
          parts: [
            {
              id: "q1",
              question: "Какой размер?",
              display_answer: "5%",
              citation_ids: [sampleCitation.id],
            },
            {
              id: "q2",
              question: "Какой срок?",
              display_answer:
                "Не удалось подтвердить ответ: цитата не совпала с документом.",
              citation_ids: [],
            },
          ],
        },
        onPreview: (value) => selected.push(value),
      }),
    ),
  );
  const first = host.querySelector('[aria-label="Ответ на вопрос 1"]');
  const second = host.querySelector('[aria-label="Ответ на вопрос 2"]');
  assert.equal(first.querySelectorAll("a").length, 1);
  assert.equal(second.querySelectorAll("a").length, 0);
  assert.ok(second.textContent.includes("цитата не совпала"));
  await act(async () => first.querySelector("a").click());
  assert.equal(selected[0].citation.id, sampleCitation.id);
  assert.ok(!host.textContent.includes("legacy flattened answer"));
});

test("background refresh after a mutation keeps messages and history usable", async () => {
  await click(findButton("Чат A"));
  await act(async () => {
    store.dispatch(
      baseApi.util.invalidateTags([
        { type: "ChatMessages", id: "A" },
        { type: "Chat", id: "LIST" },
      ]),
    );
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
  await settle();
  assert.equal(host.querySelector('[role="alert"]'), null);
  assertVisibleChat("A");
});

async function submitQuestion(text) {
  const input = host.querySelector("textarea");
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      browser.HTMLTextAreaElement.prototype,
      "value",
    ).set.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await settle();
  await click(findButton("Отправить сообщение"));
}

test("completed steps stay with the last answer across chat switches and reset for the next run", async () => {
  await click(findButton("Чат A"));
  await submitQuestion("Первый вопрос");
  await act(async () => {
    store.dispatch(
      runStreamApi.util.updateQueryData(
        "watchChatRun",
        { chatId: "A", runId: "run-A", attempt: 0 },
        (draft) => {
          draft.steps = [
            {
              step_id: "prepare",
              title: "Документы подготовлены",
              message: "Документы подготовлены",
              status: "completed",
            },
          ];
          draft.terminal = true;
          draft.connection = "closed";
        },
      ),
    );
    await store.dispatch(
      chatsApi.util.upsertQueryData(
        "chatsRunsRetrieve",
        { chatId: "A", id: "run-A" },
        {
          id: "run-A",
          status: "completed",
          error: "",
          created_at: "now",
          updated_at: "now",
        },
      ),
    );
  });
  await settle();
  const steps = () =>
    host.querySelector('section[aria-label="Обсуждение"] ol')?.textContent;
  assert.ok(steps().includes("Документы подготовлены"));
  assert.equal(findButton("Остановить ответ"), undefined);
  assert.equal(host.textContent.includes("Ответ выполняется…"), false);
  await click(findButton("Чат B"));
  assert.equal(steps(), undefined);
  await click(findButton("Чат A"));
  assert.ok(steps().includes("Документы подготовлены"));
  await submitQuestion("Второй вопрос");
  assert.ok(findButton("Остановить ответ"));
  assert.equal(steps().includes("Документы подготовлены"), false);
});

test("empty completed runs hide the steps block; terminal failures retain received steps", async () => {
  await act(async () =>
    root.render(
      createElement(ChatSteps, {
        running: false,
        stream: { connection: "closed", seq: 0, steps: [], terminal: true },
      }),
    ),
  );
  assert.equal(host.textContent, "");
  for (const status of ["failed", "cancelled", "interrupted"]) {
    await act(async () =>
      root.render(
        createElement(ChatSteps, {
          running: false,
          stream: {
            connection: "closed",
            seq: 2,
            terminal: true,
            steps: [
              {
                step_id: "prepare",
                title: "Подготовка документов",
                message: "Подготовка документов",
                status,
              },
            ],
          },
        }),
      ),
    );
    assert.ok(
      host.querySelector("li")?.textContent.includes("Подготовка документов"),
    );
    assert.equal(host.querySelector("output"), null);
  }
});
