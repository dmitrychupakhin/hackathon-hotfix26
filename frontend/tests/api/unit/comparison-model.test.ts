import assert from "node:assert/strict";
import { test } from "node:test";
import {
  categoryRows,
  comparisonRequestErrors,
  comparisonResultSchema,
  stageLabel,
  validateComparisonDraft,
} from "../../../src/_pages/comparisons/model/comparison";
import { comparisonResultFixture } from "../fixtures/comparison-result";

const file = (name = "data.pdf", size = 1) =>
  new File([new Uint8Array(size)], name);
const draft = () => ({
  questions: file("questions.csv"),
  answers: file("answers.json"),
  documents: [file()],
  modelId: "model",
});
test("comparison form validates required files, names, formats, byte and document limits", () => {
  assert.deepEqual(validateComparisonDraft(draft()), {});
  assert.ok(validateComparisonDraft({ documents: [], modelId: "" }).questions);
  assert.ok(
    validateComparisonDraft({ ...draft(), answers: file("empty.txt", 0) })
      .answers,
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), questions: file("bad.exe") })
      .questions,
  );
  assert.ok(
    validateComparisonDraft({
      ...draft(),
      questions: file(`${"a".repeat(197)}.pdf`),
    }).questions,
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), questions: file("bad\nname.pdf") })
      .questions,
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), questions: file("path/name.pdf") })
      .questions,
  );
  assert.ok(
    validateComparisonDraft({
      ...draft(),
      questions: file("big.csv", 10 * 1024 * 1024 + 1),
    }).questions,
  );
  assert.deepEqual(
    validateComparisonDraft({
      ...draft(),
      questions: file("valid.CSV", 10 * 1024 * 1024),
    }),
    {},
  );
  assert.ok(
    validateComparisonDraft({
      ...draft(),
      documents: Array.from({ length: 65 }, () => file()),
    }).documents,
  );
  assert.ok(
    validateComparisonDraft({
      ...draft(),
      documents: Array.from({ length: 4 }, () =>
        file("nine.pdf", 9 * 1024 * 1024),
      ),
    }).documents,
  );
});
test("result adapter validates loose API records and computes category correctness from real counts", () => {
  const result = comparisonResultSchema.parse(comparisonResultFixture());
  assert.deepEqual(categoryRows(result), [
    ["Тарифы", 50, 100],
    ["Условия", 0, 0],
  ]);
  assert.equal(
    comparisonResultSchema.safeParse({
      ...comparisonResultFixture(),
      before: {},
    }).success,
    false,
  );
  const negative = comparisonResultFixture();
  negative.before.trust_index = -100;
  assert.equal(comparisonResultSchema.safeParse(negative).success, true);
  negative.before.trust_index = -101;
  assert.equal(comparisonResultSchema.safeParse(negative).success, false);
});
test("empty categories and zero question counts produce no invalid chart widths", () => {
  const result = comparisonResultSchema.parse(comparisonResultFixture());
  result.before.by_type = { Пустая: { верно: 0, обман: 0, осторожно: 0 } };
  result.after.by_type = {};
  assert.deepEqual(categoryRows(result), [["Пустая", 0, 0]]);
});
test("server field, general, oversized-payload and network failures get actionable messages", () => {
  assert.deepEqual(
    comparisonRequestErrors({
      data: { questions: ["Плохой файл"], model_id: ["Модель недоступна"] },
    }),
    { questions: "Плохой файл", modelId: "Модель недоступна" },
  );
  assert.equal(
    comparisonRequestErrors({ data: { detail: ["Ошибка данных"] } }).root,
    "Ошибка данных",
  );
  assert.match(comparisonRequestErrors({ status: 413 }).root ?? "", /размер/);
  assert.ok(comparisonRequestErrors({ status: "FETCH_ERROR" }).root);
  assert.equal(stageLabel("unknown_future_stage"), "Обработка данных");
});

test("official CSV/JSON formats are required and only document input accepts ZIP, never images", () => {
  assert.deepEqual(
    validateComparisonDraft({ ...draft(), documents: [file("packages.zip")] }),
    {},
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), questions: file("questions.zip") })
      .questions,
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), answers: file("answers.csv") })
      .answers,
  );
  assert.ok(
    validateComparisonDraft({ ...draft(), documents: [file("image.png")] })
      .documents,
  );
});
test("technical failure keeps other mode scores and never renders unavailable mode as zero", () => {
  const fixture = comparisonResultFixture();
  const result = comparisonResultSchema.parse({
    ...fixture,
    before: {
      ...fixture.before,
      available: false,
      correct: null,
      errors: null,
      careful: null,
      trust_index: null,
      rows: [],
      by_type: {},
      error: {
        code: "context_budget_exceeded",
        message: "Контекст не помещается",
      },
    },
    delta: null,
  });
  assert.equal(result.before.trust_index, null);
  assert.equal(result.after.trust_index, 66.7);
  assert.equal(result.delta, null);
  assert.deepEqual(categoryRows(result), [
    ["Тарифы", null, 100],
    ["Условия", null, 0],
  ]);
});
