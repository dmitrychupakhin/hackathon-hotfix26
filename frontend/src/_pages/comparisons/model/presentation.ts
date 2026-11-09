const checkLabels: Record<string, string> = {
  quote: "Цитата",
  numbers: "Числа",
  calculation: "Расчёт",
  coverage: "Полнота источников",
  semantic_review: "Смысл ответа",
  unknown_evidence: "Ссылка на источник",
  answer_present: "Ответ и подтверждающие источники",
  conflict_evidence: "Подтверждение расхождения",
  answer_schema: "Формат ответа",
  missing_answer: "Наличие ответа",
  critic_format: "Формат проверки критиком",
  review_context_exhausted: "Контекст для проверки критиком",
  review_unavailable: "Доступность проверки критиком",
  clarification_status: "Уточняющий вопрос",
  empty_absence: "Формат ответа «нет в документах»",
  empty_unknown: "Формат ответа «не знаю»",
};
export const checkLabel = (code: string) =>
  checkLabels[code] ?? "Дополнительная проверка";
export const hasRussianExplanation = (message: string) =>
  /[А-Яа-яЁё]/.test(message);
export function candidatePreview(text: string) {
  return text.length > 400 ? `${text.slice(0, 400)}…` : text;
}
const warnings: Record<string, string> = {
  "One paired run is an observation, not a statistical guarantee.":
    "Один сравнительный прогон показывает результат на этом наборе, но не гарантирует такое же улучшение на других данных.",
  "One paired run is an observation, not a statistical guarantee. Raw mode has a different output contract.":
    "Один сравнительный прогон показывает результат на этом наборе, но не гарантирует такое же улучшение на других данных. Режим raw использует другой формат ответа.",
  "Official score does not prove complete semantic correctness; inspect evidence and validation traces.":
    "Оценка по check.py не гарантирует полной смысловой правильности: проверьте цитаты и результаты проверок.",
  "Raw mode without status fields is not a factual-accuracy score.":
    "Режим raw без статусов ответа не даёт оценки фактической точности по этому формату.",
};
export const comparisonWarning = (warning: string) =>
  warnings[warning] ?? warning;
