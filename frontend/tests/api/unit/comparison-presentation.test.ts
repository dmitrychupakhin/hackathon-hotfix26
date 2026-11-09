import assert from "node:assert/strict";
import { test } from "node:test";
import {
  candidatePreview,
  checkLabel,
  comparisonWarning,
} from "../../../src/_pages/comparisons/model/presentation";

test("check labels explain verification without inventing unknown check semantics", () => {
  assert.equal(checkLabel("quote"), "Цитата");
  assert.equal(checkLabel("numbers"), "Числа");
  assert.equal(checkLabel("semantic_review"), "Смысл ответа");
  assert.equal(
    checkLabel("unexpected_future_check"),
    "Дополнительная проверка",
  );
});
test("known warnings preserve uncertainty and unfamiliar messages remain unchanged", () => {
  assert.match(
    comparisonWarning(
      "One paired run is an observation, not a statistical guarantee.",
    ),
    /не гарантирует/,
  );
  assert.equal(
    comparisonWarning("Новое предупреждение"),
    "Новое предупреждение",
  );
});
test("rejected answer preview is an exact bounded prefix, never a generated paraphrase", () => {
  assert.equal(candidatePreview("60 дней"), "60 дней");
  const long = "А".repeat(401);
  assert.equal(candidatePreview(long), `${long.slice(0, 400)}…`);
});
