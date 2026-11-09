import { useChatsModelsListQuery } from "@/shared/api/chats";
import type { ComparisonJobRead } from "@/shared/api/comparisons";
import {
  categoryRows,
  comparisonResultSchema,
  type EvaluatedSide,
  errorMessage,
} from "../model/comparison";
import { comparisonWarning } from "../model/presentation";
import { ComparisonAnswers } from "./comparison-answers";
import { ComparisonCard } from "./comparison-card";
import { ComparisonChart } from "./comparison-chart";
import { ComparisonDownloads } from "./comparison-downloads";
import { ComparisonFeedback } from "./comparison-feedback";

function RunMetrics({ label, side }: { label: string; side: EvaluatedSide }) {
  const m = side.run_metrics;
  const number = (v: number | null | undefined) =>
    v == null ? "Н/Д" : v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  return (
    <div className="flex flex-col gap-2 text-body-sm">
      <h3 className="font-medium">{label}</h3>
      {!side.available && (
        <output className="text-error-600">
          Технический отказ: {errorMessage(side.error)} Индекс доверия не
          вычислен.
        </output>
      )}
      <p>
        Запросы: {number(m?.model_calls)}
        {m?.transport_attempts != null
          ? ` (HTTP-попыток: ${number(m.transport_attempts)})`
          : ""}{" "}
        · Время: {number(m?.elapsed_seconds)} с
      </p>
      <p>
        Токены: вход {number(m?.input_tokens)}, выход {number(m?.output_tokens)}
        ; всего {number(m?.known_total_tokens)}
        {m?.missing_usage_calls
          ? ` (неполные данные: ${m.missing_usage_calls} запросов без usage)`
          : ""}
      </p>
      {m?.context_window_tokens_final != null && (
        <p>
          Итоговый бюджет окна: {number(m.context_window_tokens_final)} токенов
          · Уменьшений контекста: {number(m.context_reductions)}
        </p>
      )}
      <p>
        Стоимость:{" "}
        {m?.cost == null
          ? "Не рассчитана: нет подтверждённых данных о тарифе"
          : `${number(m.cost)} ${m.currency ?? "(валюта не указана)"}`}
      </p>
    </div>
  );
}
export function ComparisonResult({ job }: { job: ComparisonJobRead }) {
  const models = useChatsModelsListQuery();
  const parsed = comparisonResultSchema.safeParse(job.result);
  if (!parsed.success)
    return (
      <ComparisonFeedback message="Не удалось отобразить результат сравнения: данные отсутствуют или имеют неподдерживаемый формат." />
    );
  const result = parsed.data;
  const metrics = [
    ["Верно", "correct"],
    ["Ошибка", "errors"],
    ["Осторожный ответ", "careful"],
    ["Индекс доверия", "trust_index"],
  ] as const;
  return (
    <>
      <ComparisonCard title="Результат сравнения">
        <p className="text-body-sm">
          Модель:{" "}
          {models.data?.find((model) => model.id === job.model_id)?.name ??
            job.model_id}
        </p>
        <p className="text-body-sm text-content-500">
          Вопросов: {result.before.questions}. Baseline — без проверок; harness
          — с проверками и сохранёнными инструкциями.
          {result.before.grouping === "per_package" &&
          result.after.grouping === "per_package"
            ? " Одинаковая группировка: один базовый запрос на закупку."
            : " Исторический запуск: группировка не сохранена в отчёте."}
        </p>
        <p className="text-label-md text-content-500">
          Индекс доверия = (верные ответы − ошибки) / все вопросы × 100. «Не
          знаю» не добавляет и не отнимает баллы. Н/Д означает отсутствие
          оценки, а не нулевой результат.
        </p>
        <div className="scrollbar-dropdown overflow-x-auto">
          <table className="w-full min-w-[400px] text-left text-body-sm">
            <thead>
              <tr>
                {["Показатель", "Baseline", "Harness", "Изменение"].map(
                  (label) => (
                    <th key={label} scope="col" className="p-2 font-medium">
                      {label}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {metrics.map(([label, key]) => (
                <tr key={key} className="border-t border-content-100">
                  <th scope="row" className="p-2 font-normal">
                    {label}
                  </th>
                  <td className="p-2">{result.before[key] ?? "Н/Д"}</td>
                  <td className="p-2">{result.after[key] ?? "Н/Д"}</td>
                  <td className="p-2">
                    {result.delta?.[key] == null
                      ? "Н/Д"
                      : `${result.delta?.[key] > 0 ? "+" : ""}${result.delta?.[key]}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <RunMetrics label="Baseline" side={result.before} />
          <RunMetrics label="Harness" side={result.after} />
        </div>
        <ComparisonDownloads
          id={job.id}
          baseline={result.before.available}
          harness={result.after.available}
        />
      </ComparisonCard>
      <div className="grid min-w-0 gap-4 2xl:grid-cols-2">
        <ComparisonChart
          title="Доля верных ответов по категориям"
          rows={categoryRows(result)}
          percentage
        />
        <ComparisonChart
          title="Исходы ответов"
          max={Math.max(result.before.questions, result.after.questions, 1)}
          rows={[
            ["Верно", result.before.correct, result.after.correct],
            ["Ошибка", result.before.errors, result.after.errors],
            ["Осторожно", result.before.careful, result.after.careful],
          ]}
        />
      </div>
      <ComparisonAnswers result={result} />
      {result.warning && (
        <p className="text-body-sm text-content-500">
          {comparisonWarning(result.warning)}
        </p>
      )}
    </>
  );
}
