import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { setImmediate } from "node:timers/promises";
import { Window } from "happy-dom";
import { comparisonResultFixture } from "../api/fixtures/comparison-result.ts";

const browser = new Window({ url: "http://localhost:3000/comparisons" });
const globals = [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "HTMLInputElement",
  "Element",
  "Node",
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
    value: [
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
const { comparisonsApi } = await import(
  "../../src/shared/api/comparisons/index.ts"
);
const { Comparisons } = await import(
  "../../src/_pages/comparisons/ui/comparisons.tsx"
);
const NativeRequest = globalThis.Request;
const nativeFetch = globalThis.fetch;
const job = (id, status = "completed") => ({
  id,
  model_id: "model",
  status,
  stage: status === "running" ? "importing" : status,
  result: status === "completed" ? comparisonResultFixture() : null,
  error: "",
  created_at:
    id === "historic" ? "2026-11-08T10:00:00Z" : "2026-11-08T11:00:00Z",
  updated_at: "2026-11-08T11:00:00Z",
});
let root, store, host, requests, jobs, readStatus, writeStatus, total, uploaded;
const button = (text) =>
  Array.from(host.querySelectorAll("button")).find(
    (item) =>
      item.textContent.trim() === text ||
      item.getAttribute("aria-label") === text,
  );
const selected = () =>
  host.querySelector('section[aria-label="Выбранное сравнение"]');
const history = (index) =>
  host.querySelectorAll(
    'aside[aria-label="История сравнений"] button[aria-pressed]',
  )[index];
async function settle() {
  await act(async () => {
    for (let i = 0; i < 12; i++) await setImmediate();
  });
}
async function click(element) {
  assert.ok(element, "button exists");
  await act(async () => element.click());
  await settle();
}
async function chooseFile(label, files) {
  const input = host.querySelector(`input[aria-label="${label}"]`);
  Object.defineProperty(input, "files", { configurable: true, value: files });
  await act(async () =>
    input.dispatchEvent(new Event("change", { bubbles: true })),
  );
  await settle();
}
async function validDraft() {
  await chooseFile("Вопросы", [new File(["questions"], "questions.csv")]);
  await chooseFile("Эталонные ответы", [new File(["answers"], "answers.json")]);
  await chooseFile("Общие документы", [
    new File(["one"], "one.pdf"),
    new File(["two"], "two.docx"),
  ]);
  await click(button("Выбрать модель"));
  await act(async () =>
    Array.from(document.querySelectorAll('[role="menuitem"]'))
      .find((item) => item.textContent === "Тестовая модель")
      .click(),
  );
  await settle();
}
beforeEach(async () => {
  requests = [];
  jobs = [job("historic"), job("live", "running")];
  readStatus = 200;
  writeStatus = 202;
  total = 2;
  uploaded = undefined;
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
  globalThis.fetch = async (request) => {
    requests.push(request);
    const url = new URL(request.url);
    if (url.pathname === "/api/chats/models")
      return Response.json([{ id: "model", name: "Тестовая модель" }]);
    if (request.method === "POST") {
      if (writeStatus !== 202)
        return Response.json(
          { questions: ["Проверьте вопросы"] },
          { status: writeStatus },
        );
      uploaded = await request.clone().formData();
      const created = job("created", "running");
      jobs.unshift(created);
      total++;
      return Response.json(created, { status: 202 });
    }
    if (readStatus !== 200)
      return Response.json({ detail: ["Unavailable"] }, { status: readStatus });
    if (url.pathname === "/api/comparisons") {
      const second = url.searchParams.get("page") === "2";
      return Response.json({
        count: total,
        next: total > 30 && !second ? "?page=2" : null,
        previous: second ? "?page=1" : null,
        results: second ? [job("second-page")] : jobs,
      });
    }
    return Response.json(
      jobs.find((item) => item.id === url.pathname.split("/").at(-1)),
    );
  };
  store = makeStore();
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () =>
    root.render(createElement(Provider, { store }, createElement(Comparisons))),
  );
  await settle();
});
afterEach(async () => {
  await act(async () => {
    root.unmount();
    store.dispatch(comparisonsApi.util.resetApiState());
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

test("uploading a valid draft opens the created run and clears the submitted files", async () => {
  assert.equal(button("Запустить сравнение").disabled, true);
  await validDraft();
  assert.equal(button("Запустить сравнение").disabled, false);
  await click(button("Запустить сравнение"));
  assert.ok(selected().textContent.includes("Подготовка документов"));
  assert.equal(host.querySelector("form").parentElement.hidden, true);
  assert.deepEqual(
    uploaded.getAll("documents").map((file) => file.name),
    ["one.pdf", "two.docx"],
  );
  await click(button("Новый анализ +"));
  assert.equal(host.querySelector("form").parentElement.hidden, false);
  assert.equal(
    !!host.querySelector('button[aria-label="Убрать questions.csv"]'),
    false,
  );
});
test("viewing history preserves draft files and displays real category and per-question scores", async () => {
  await chooseFile("Вопросы", [new File(["q"], "draft.csv")]);
  await click(history(0));
  assert.ok(selected().textContent.includes("50% / 100%"));
  assert.ok(selected().textContent.includes("Совпадает с эталоном"));
  const row = Array.from(selected().querySelectorAll("tr")).find(
    (row) => row.querySelector("th")?.textContent === "P2",
  );
  assert.ok(row.textContent.includes("Ошибка"));
  assert.ok(row.textContent.includes("Верно"));
  await click(button("Новый анализ +"));
  assert.ok(host.querySelector("form").textContent.includes("draft.csv"));
});
test("413 and field errors preserve the draft and can be retried", async () => {
  await validDraft();
  writeStatus = 413;
  await click(button("Запустить сравнение"));
  assert.ok(
    host.querySelector("form").textContent.includes("Сервер отклонил размер"),
  );
  assert.ok(host.querySelector("form").textContent.includes("questions.csv"));
  writeStatus = 400;
  await click(button("Запустить сравнение"));
  assert.ok(
    host.querySelector("form").textContent.includes("Проверьте вопросы"),
  );
  writeStatus = 202;
  await click(button("Запустить сравнение"));
  assert.ok(selected());
});
test("unsupported result data show a data error rather than demo results", async () => {
  jobs[0].result = null;
  await click(history(0));
  assert.ok(selected().textContent.includes("Не удалось отобразить результат"));
  assert.equal(selected().querySelector("table"), null);
});
test("network errors retain the last running stage and retry restores the selected query", async () => {
  await click(history(1));
  readStatus = 503;
  await act(async () => {
    await store.dispatch(
      comparisonsApi.endpoints.comparisonsRetrieve.initiate(
        { id: "live" },
        { forceRefetch: true, subscribe: false },
      ),
    );
  });
  await settle();
  assert.ok(selected().textContent.includes("Не удалось обновить"));
  assert.ok(selected().textContent.includes("Подготовка документов"));
  readStatus = 200;
  await click(selected().querySelector("button"));
  assert.equal(selected().querySelector('[role="alert"]'), null);
});
test("selected polling transitions to completed and stops requesting the terminal run", async () => {
  await click(history(1));
  jobs[1] = job("live", "completed");
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2200));
  });
  await settle();
  assert.ok(selected().textContent.includes("Результат сравнения"));
  const count = requests.filter((request) =>
    request.url.endsWith("/live"),
  ).length;
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 2200));
  });
  await settle();
  assert.equal(
    requests.filter((request) => request.url.endsWith("/live")).length,
    count,
  );
});
test("history pagination requests page two and server failure is shown without an invented result", async () => {
  total = 31;
  await act(async () => {
    await store.dispatch(
      comparisonsApi.endpoints.comparisonsList.initiate(
        { page: 1, pageSize: 30 },
        { forceRefetch: true, subscribe: false },
      ),
    );
  });
  await settle();
  await click(button("Далее"));
  assert.ok(
    requests.some(
      (request) => new URL(request.url).searchParams.get("page") === "2",
    ),
  );
  await click(button("Назад"));
  jobs[1] = {
    ...job("live", "failed"),
    error: "Не удалось разобрать входные файлы",
  };
  await click(history(1));
  assert.ok(
    selected().textContent.includes("Не удалось разобрать входные файлы"),
  );
  assert.equal(selected().querySelector("progress"), null);
});

test("completed results show both original answers, sources, metrics and caught validation errors", async () => {
  const fixture = comparisonResultFixture();
  fixture.before.rows[1] = {
    ...fixture.before.rows[1],
    question: "Каков срок?",
    answer: {
      status: "ответ",
      answer: "60 дней",
      quote: "60 календарных дней",
      file: "contract.txt",
    },
  };
  fixture.after.rows[0] = {
    ...fixture.after.rows[0],
    question: "Каков срок?",
    answer: {
      status: "ответ",
      answer: "75 дней",
      quote: "75 календарных дней",
      file: "amendment.txt",
    },
    checks: [{ code: "quote", passed: true, message: "Цитата найдена" }],
    validation_failures: [
      {
        candidate: { answer: "60 дней" },
        checks: [
          {
            code: "amendment",
            passed: false,
            message: "Пропущено изменение срока",
          },
        ],
      },
    ],
  };
  fixture.after.run_metrics = {
    model_calls: 5,
    transport_attempts: 7,
    elapsed_seconds: 12.5,
    input_tokens: 1000,
    output_tokens: 200,
    known_total_tokens: 1200,
    cost: null,
    currency: null,
  };
  jobs[0].result = fixture;
  await click(history(0));
  const text = selected().textContent;
  for (const fragment of [
    "Каков срок?",
    "60 дней",
    "75 дней",
    "contract.txt",
    "amendment.txt",
    "Пропущено изменение срока",
    "Цитата найдена",
    "Запросы: 5",
    "HTTP-попыток: 7",
    "12,5",
    "Не рассчитана",
    "Тестовая модель",
  ])
    assert.ok(text.includes(fragment), fragment);
});
test("baseline technical failure preserves harness results and displays N/A instead of a fabricated score", async () => {
  const fixture = comparisonResultFixture();
  jobs[0].result = {
    ...fixture,
    before: {
      ...fixture.before,
      available: false,
      status: "failed",
      error: {
        code: "context_budget_exceeded",
        message: "Контекст не помещается",
      },
      correct: null,
      errors: null,
      careful: null,
      trust_index: null,
      rows: [],
      by_type: {},
    },
    delta: null,
  };
  await click(history(0));
  assert.ok(
    selected().textContent.includes(
      "Технический отказ: Контекст не помещается",
    ),
  );
  assert.ok(selected().textContent.includes("66.7"));
  assert.ok(selected().textContent.includes("Н/Д"));
  assert.equal(button("Скачать baseline CSV").disabled, true);
  assert.equal(button("Скачать harness CSV").disabled, false);
  assert.equal(button("Скачать отчёт JSON").disabled, false);
  assert.equal(
    selected().textContent.includes("Не удалось отобразить результат"),
    false,
  );
});

test("running comparison exposes actual harness step and batch without raw document payloads", async () => {
  jobs[1].progress = {
    run_states: {
      baseline: {
        status: "failed",
        metrics_final: true,
        metrics: { model_calls: 0 },
      },
      harness: {
        status: "running",
        metrics_final: false,
        metrics: { model_calls: 3 },
        step: {
          title: "Чтение документов порциями",
          message: "Проверяются исходные фрагменты",
          status: "started",
          kind: "evidence_scan",
          details: {
            batch: 2,
            batches: 6,
            raw_document: "PRIVATE RAW DOCUMENT PAYLOAD",
          },
        },
      },
    },
  };
  await click(history(1));
  const text = selected().textContent;
  for (const value of [
    "Чтение документов порциями",
    "Проверяются исходные фрагменты",
    "Порция 2/6",
    "запросов начато 3",
    "Baseline: Технический отказ",
  ])
    assert.ok(text.includes(value), value);
  assert.equal(text.includes("PRIVATE RAW DOCUMENT PAYLOAD"), false);
});

test("verification details use Russian labels while retaining raw technical reasons and rejected answers", async () => {
  const fixture = comparisonResultFixture();
  fixture.warning =
    "One paired run is an observation, not a statistical guarantee.";
  fixture.after.rows[0].checks = [
    { code: "quote", passed: true, message: "Quote verified" },
    { code: "numbers", passed: true, message: "All answer numbers verified" },
    {
      code: "semantic_review",
      passed: true,
      message: "Ответ соответствует изменению извещения",
    },
    { code: "future_check", passed: true, message: "Future check details" },
  ];
  fixture.after.rows[0].validation_failures = [
    {
      candidate: { answer: "Ошибочно: 60 дней" },
      checks: [
        {
          code: "semantic_review",
          passed: false,
          message: "Пропущено изменение срока",
        },
      ],
    },
  ];
  jobs[0].result = fixture;
  await click(history(0));
  const text = selected().textContent;
  for (const value of [
    "Итоговые проверки (4)",
    "Пройдена: Цитата",
    "Пройдена: Числа",
    "Смысл ответа",
    "Дополнительная проверка",
    "Техническая причина",
    "Отклонённый ответ: Ошибочно: 60 дней",
    "Не пройдена: Смысл ответа",
    "не гарантирует такое же улучшение",
  ])
    assert.ok(text.includes(value), value);
  const technicalReason = [...selected().querySelectorAll("details")].find(
    (detail) =>
      detail.querySelector(":scope > summary")?.textContent.trim() ===
        "Техническая причина" && detail.textContent.includes("Quote verified"),
  );
  assert.ok(technicalReason);
  assert.equal(technicalReason.open, false);
});
