import assert from "node:assert/strict";
import { test } from "node:test";
import {
  applyRunEvent,
  buildRunSocketUrl,
  essentialRunSteps,
  parseRunEvent,
  type RunStream,
} from "../../../src/shared/api/chats/run-events";

const state = (): RunStream => ({
  connection: "connected",
  seq: 0,
  steps: [],
  terminal: false,
});
const event = (seq: number, type: string, data: Record<string, unknown>) => ({
  seq,
  type,
  data,
  run_id: "ai-run",
});
test("events validate resource and cursor; heartbeat cannot advance replay", () => {
  assert.equal(
    parseRunEvent({ type: "heartbeat", cursor: 100 }, "ai-run"),
    undefined,
  );
  assert.equal(parseRunEvent(event(1, "run.started", {}), "other"), undefined);
  assert.equal(
    parseRunEvent(event(-1, "run.started", {}), "ai-run"),
    undefined,
  );
  assert.equal(
    parseRunEvent(event(1.5, "run.started", {}), "ai-run"),
    undefined,
  );
  assert.equal(
    parseRunEvent({ ...event(1, "harness.step", {}), data: [] }, "ai-run"),
    undefined,
  );
  assert.deepEqual(
    parseRunEvent(event(3, "run.started", {}), "ai-run"),
    event(3, "run.started", {}),
  );
});
test("replayed events are ignored and step completion replaces its start", () => {
  const stream = state();
  const step = {
    step_id: "prepare",
    title: "Подготовка",
    message: "Подготовка",
    status: "started",
  };
  applyRunEvent(stream, event(1, "harness.step", step));
  applyRunEvent(
    stream,
    event(2, "harness.step", { ...step, status: "completed" }),
  );
  applyRunEvent(stream, event(1, "harness.step", step));
  assert.equal(stream.steps.length, 1);
  assert.equal(stream.steps[0].status, "completed");
  assert.equal(stream.seq, 2);
});
test("clarification is displayed instead of an empty answer; interrupted steps are closed", () => {
  const stream = state();
  applyRunEvent(
    stream,
    event(1, "harness.step", {
      step_id: "x",
      title: "Проверка",
      message: "Проверка",
      status: "started",
    }),
  );
  applyRunEvent(
    stream,
    event(2, "answer.completed", {
      answer: {
        answer: "",
        clarification_question: "Какой период?",
        status: "не знаю",
      },
    }),
  );
  applyRunEvent(stream, event(3, "run.interrupted", {}));
  assert.equal(stream.answer, "Какой период?");
  assert.equal(stream.steps[0].status, "interrupted");
  assert.equal(stream.terminal, true);
});
test("malformed and unknown events do not create fake UI steps", () => {
  const stream = state();
  applyRunEvent(
    stream,
    event(1, "harness.step", { step_id: "x", status: "invented" }),
  );
  applyRunEvent(stream, event(2, "llm.finished", { text: "unverified" }));
  assert.deepEqual(stream.steps, []);
  assert.equal(stream.answer, undefined);
});

test("independent answers accumulate in question order without overwriting accepted results", () => {
  const stream = state();
  const completed = (index: number, status: string, answer: string) => ({
    question_index: index,
    question_count: 2,
    question: { text: `Вопрос ${index + 1}` },
    answer: {
      id: `message.q${index + 1}`,
      status,
      answer,
      origin: status === "не знаю" ? "fallback" : "model",
    },
  });
  applyRunEvent(
    stream,
    event(1, "answer.completed", completed(1, "не знаю", "")),
  );
  applyRunEvent(
    stream,
    event(2, "answer.completed", completed(0, "ответ", "18000 руб.")),
  );
  assert.equal(
    stream.answer,
    "1. Вопрос 1\n18000 руб.\n\n2. Вопрос 2\nНе удалось подтвердить ответ в пределах проверок.",
  );
  applyRunEvent(
    stream,
    event(1, "answer.completed", completed(1, "ответ", "ошибка повтора")),
  );
  assert.ok(!stream.answer.includes("ошибка повтора"));
});
test("code-checked chat answer is displayed without a warning when independent review is unavailable", () => {
  const stream = state();
  applyRunEvent(
    stream,
    event(1, "answer.completed", {
      question_index: 0,
      question_count: 2,
      question: { text: "Какой размер?" },
      answer: {
        id: "message.q01",
        status: "ответ",
        answer: "18000 рублей",
        origin: "model",
        reason: "independent_review_incomplete",
        evidence: [{ source_file_id: "file-1", text: "18000 рублей" }],
        checks: [
          { code: "quote", passed: true },
          {
            code: "review_unavailable",
            passed: false,
            message: "provider_timeout",
          },
        ],
      },
    }),
  );
  assert.equal(stream.answer, "1. Какой размер?\n18000 рублей");
  assert.equal(stream.error, undefined);
});

test("socket URL preserves upstream path, encodes ticket and resumes after cursor", () => {
  const url = buildRunSocketUrl(
    "/ai/api/v1/runs/ai-run/ws",
    "a&b",
    12,
    "https://example.test",
  );
  assert.equal(url.protocol, "wss:");
  assert.equal(url.searchParams.get("ticket"), "a&b");
  assert.equal(url.searchParams.get("after"), "12");
  assert.equal(
    buildRunSocketUrl("/ai/api/v1/runs/x/ws", "t", 0, "http://localhost")
      .protocol,
    "ws:",
  );
  assert.throws(() =>
    buildRunSocketUrl(
      "//attacker.test/ws",
      "secret",
      0,
      "https://example.test",
    ),
  );
  assert.throws(() =>
    buildRunSocketUrl("/api/chats/x", "secret", 0, "https://example.test"),
  );
});

test("model planning is a real preparation step", () => {
  const stream = state();
  applyRunEvent(
    stream,
    event(1, "harness.step", {
      step_id: "plan",
      kind: "chat_plan",
      title: "Подготовка независимых частей ответа",
      message: "Подготовка независимых частей ответа",
      status: "started",
    }),
  );
  assert.equal(essentialRunSteps(stream.steps)[0]?.step_id, "plan");
});

test("chat keeps the latest real step per phase, without exposing internal events", () => {
  const stream = state();
  for (let index = 1; index <= 20; index++) {
    applyRunEvent(
      stream,
      event(index, "harness.step", {
        step_id: `tool-${index}`,
        kind: "tool",
        title: "Чтение документа",
        message: "Инструмент выполнен",
        status: "completed",
      }),
    );
  }
  applyRunEvent(
    stream,
    event(21, "harness.step", {
      step_id: "review",
      kind: "semantic_review",
      title: "Проверка критиком",
      message: "Критик работает",
      status: "started",
    }),
  );
  applyRunEvent(
    stream,
    event(22, "harness.step", {
      step_id: "internal",
      kind: "private_reasoning",
      title: "PRIVATE",
      message: "PRIVATE",
      status: "completed",
    }),
  );
  assert.deepEqual(
    essentialRunSteps(stream.steps).map((step) => step.step_id),
    ["tool-20", "review"],
  );
  applyRunEvent(
    stream,
    event(23, "harness.step", {
      step_id: "review-scan",
      kind: "verification_scan",
      title: "Проверена порция",
      message: "Порция прочитана",
      status: "completed",
    }),
  );
  assert.equal(
    essentialRunSteps(stream.steps).find(
      (step) => step.kind === "semantic_review",
    )?.status,
    "started",
  );
  assert.ok(
    essentialRunSteps(stream.steps).some(
      (step) => step.step_id === "review-scan",
    ),
  );
  applyRunEvent(
    stream,
    event(24, "run.failed", { error: { message: "Истёк срок выполнения" } }),
  );
  assert.equal(
    stream.steps.find((step) => step.step_id === "review")?.status,
    "failed",
  );
  assert.equal(stream.error, "Истёк срок выполнения");
});

test("completed independent scan cannot hide the later failed critic", () => {
  const stream = state();
  const review = {
    step_id: "review",
    kind: "semantic_review",
    title: "Критик",
    message: "Проверка ответа",
    status: "started",
  };
  applyRunEvent(stream, event(1, "harness.step", review));
  applyRunEvent(
    stream,
    event(2, "harness.step", {
      step_id: "scan",
      kind: "verification_scan",
      title: "Поиск подтверждений",
      message: "Документы прочитаны",
      status: "completed",
    }),
  );
  applyRunEvent(
    stream,
    event(3, "harness.step", {
      ...review,
      status: "failed",
      message: "Критик не завершил проверку",
    }),
  );
  const displayed = essentialRunSteps(stream.steps);
  assert.equal(
    displayed.find((step) => step.step_id === "review")?.status,
    "failed",
  );
  assert.equal(
    displayed.find((step) => step.step_id === "scan")?.status,
    "completed",
  );
});

test("run timeout has a clear Russian message", () => {
  const stream = state();
  applyRunEvent(
    stream,
    event(1, "run.failed", {
      error: { code: "run_timeout", message: "Run deadline exceeded" },
    }),
  );
  assert.equal(stream.error, "Превышено время выполнения запроса.");
  assert.equal(stream.terminal, true);
});

test("latest update determines a phase after steps complete, not creation order", () => {
  const stream = state();
  const step = (id: string, status: string) => ({
    step_id: id,
    kind: "tool",
    title: "Инструмент",
    message: "Результат",
    status,
  });
  applyRunEvent(stream, event(1, "harness.step", step("first", "started")));
  applyRunEvent(stream, event(2, "harness.step", step("second", "completed")));
  applyRunEvent(stream, event(3, "harness.step", step("first", "failed")));
  assert.equal(essentialRunSteps(stream.steps)[0]?.step_id, "first");
  assert.equal(essentialRunSteps(stream.steps)[0]?.status, "failed");
});
