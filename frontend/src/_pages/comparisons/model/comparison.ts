import { z } from "zod";
import {
  zComparisonResult,
  zCreateComparisonError,
} from "@/shared/api/comparisons";

export const isComparisonActive = (status?: string) =>
  status === "pending" || status === "running";
export const statusLabels = {
  pending: "Ожидает запуска",
  running: "Выполняется",
  completed: "Завершено",
  failed: "Ошибка",
};
export function comparisonTitle(date: string) {
  return `Запуск ${new Date(date).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" })}`;
}
export function stageLabel(stage: string) {
  const stages: Record<string, string> = {
    pending: "Ожидание запуска",
    parsing: "Разбор вопросов и эталонов",
    parsed: "Вопросы и эталоны разобраны",
    importing: "Подготовка документов",
    running: "Выполнение baseline и harness",
    evaluating: "Оценка ответов по эталонам",
    completed: "Сравнение завершено",
    failed: "Сравнение не завершено",
  };
  return stages[stage] ?? "Обработка данных";
}
export type ComparisonDraftValues = {
  questions?: File;
  answers?: File;
  documents: File[];
  modelId: string;
};
export type DraftErrors = Partial<
  Record<keyof ComparisonDraftValues | "root", string>
>;
export const emptyDraft = (): ComparisonDraftValues => ({
  documents: [],
  modelId: "",
});
export const comparisonAccept =
  ".zip,.txt,.md,.csv,.json,.html,.htm,.pdf,.docx,.pptx,.xlsx";
function fileError(file: File, accept = comparisonAccept) {
  if (file.size === 0 || file.size > 10 * 1024 * 1024)
    return "Файл должен быть непустым и не больше 10 МиБ.";
  if (
    !file.name ||
    file.name.length > 200 ||
    /[/\\]/.test(file.name) ||
    [...file.name].some(
      (character) =>
        character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127,
    )
  )
    return "Недопустимое имя файла: до 200 символов без управляющих символов и разделителей пути.";
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!accept.split(",").includes(extension))
    return "Этот формат файла не поддерживается.";
}
export function validateComparisonDraft(
  draft: ComparisonDraftValues,
): DraftErrors {
  const errors: DraftErrors = {};
  for (const field of ["questions", "answers"] as const) {
    const file = draft[field];
    const error = file
      ? fileError(file, field === "questions" ? ".csv" : ".json")
      : "Выберите файл.";
    if (error) errors[field] = error;
  }
  if (draft.documents.length < 1 || draft.documents.length > 64)
    errors.documents = "Добавьте от 1 до 64 документов.";
  else if (
    draft.documents.reduce((sum, file) => sum + file.size, 0) >
    32 * 1024 * 1024
  )
    errors.documents = "Общий размер документов не должен превышать 32 МиБ.";
  else {
    const error = draft.documents.map((file) => fileError(file)).find(Boolean);
    if (error) errors.documents = error;
  }
  if (!draft.modelId) errors.modelId = "Выберите модель.";
  return errors;
}
export function comparisonRequestErrors(error: unknown): DraftErrors {
  if (typeof error === "object" && error !== null) {
    if ("status" in error && error.status === 413)
      return {
        root: "Сервер отклонил размер загрузки. Уменьшите размер файлов и попробуйте снова.",
      };
    const parsed = zCreateComparisonError.safeParse(
      "data" in error ? error.data : undefined,
    );
    if (parsed.success) {
      const result: DraftErrors = {};
      const data = parsed.data;
      if ("detail" in data)
        return {
          root: data.detail.join(" ") || "Не удалось выполнить запрос.",
        };
      for (const [server, field] of [
        ["questions", "questions"],
        ["answers", "answers"],
        ["documents", "documents"],
        ["model_id", "modelId"],
      ] as const) {
        if (server in data) {
          const messages = z.array(z.string()).safeParse(data[server]);
          if (messages.success && messages.data.length)
            result[field] = messages.data.join(" ");
        }
      }
      const general = data.non_field_errors;
      if (general?.length) result.root = general.join(" ");
      if (Object.keys(result).length) return result;
    }
  }
  return {
    root: "Не удалось выполнить запрос. Проверьте соединение и попробуйте снова.",
  };
}

const count = z.number().int().nonnegative();
const verdict = z.enum(["верно", "обман", "осторожно"]);
const check = z.object({
  code: z.string(),
  message: z.string(),
  passed: z.boolean(),
  method: z.string().optional(),
});
const answer = z.object({
  id: z.string().optional(),
  status: z.string().nullable().optional(),
  answer: z.string().default(""),
  quote: z.string().default(""),
  file: z.string().default(""),
});
const evaluationRow = z.object({
  id: z.string(),
  type: z.string(),
  verdict,
  reason: z.string(),
  question: z.string().optional(),
  answer: answer.nullable().optional(),
  evidence: z.array(z.record(z.string(), z.unknown())).optional().default([]),
  checks: z.array(check).optional().default([]),
  validation_failures: z
    .array(z.object({ candidate: z.unknown(), checks: z.array(check) }))
    .optional()
    .default([]),
});
const categoryCounts = z.object({
  верно: count.optional().default(0),
  обман: count.optional().default(0),
  осторожно: count.optional().default(0),
});
const metrics = z
  .object({
    model_calls: count.optional(),
    transport_attempts: count.optional(),
    context_window_tokens_final: count.nullable().optional(),
    context_reductions: count.nullable().optional(),
    input_tokens: count.optional(),
    output_tokens: count.optional(),
    known_total_tokens: count.optional(),
    missing_usage_calls: count.optional(),
    elapsed_seconds: z.number().nonnegative().nullable().optional(),
    cost: z.number().nullable().optional(),
    currency: z.string().nullable().optional(),
  })
  .passthrough();
const evaluation = z.object({
  available: z.boolean().optional().default(true),
  status: z.string().optional(),
  error: z.unknown().optional(),
  questions: count,
  correct: count.nullable(),
  errors: count.nullable(),
  careful: count.nullable(),
  trust_index: z.number().min(-100).max(100).nullable(),
  by_type: z.record(z.string(), categoryCounts),
  rows: z.array(evaluationRow),
  run_metrics: metrics.nullable().optional(),
  grouping: z.string().optional(),
});
export const comparisonResultSchema = zComparisonResult.extend({
  before: evaluation,
  after: evaluation,
  delta: z
    .object({
      correct: z.number().nullable(),
      errors: z.number().nullable(),
      careful: z.number().nullable(),
      trust_index: z.number().nullable(),
    })
    .nullable(),
});
export type EvaluatedComparison = z.infer<typeof comparisonResultSchema>;
export type EvaluatedSide = EvaluatedComparison["before"];
export type EvaluatedRow = EvaluatedSide["rows"][number];
export function errorMessage(error: unknown): string {
  if (typeof error === "string") return error;
  if (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof error.message === "string"
  )
    return error.message;
  return "Режим не завершён: оценка недоступна.";
}
export function categoryRows(
  result: EvaluatedComparison,
): [string, number | null, number | null][] {
  const kinds = new Set([
    ...Object.keys(result.before.by_type),
    ...Object.keys(result.after.by_type),
  ]);
  return [...kinds].map((kind) => {
    const ratio = (side: EvaluatedSide) => {
      if (!side.available) return null;
      const values = side.by_type[kind];
      if (!values) return 0;
      const n = values.верно + values.обман + values.осторожно;
      return n ? Math.round((values.верно / n) * 1000) / 10 : 0;
    };
    return [kind, ratio(result.before), ratio(result.after)];
  });
}
