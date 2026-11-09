import type { EvaluatedComparison, EvaluatedRow } from "../model/comparison";
import {
  candidatePreview,
  checkLabel,
  hasRussianExplanation,
} from "../model/presentation";

const verdictLabels = {
  верно: "Верно",
  обман: "Ошибка",
  осторожно: "Осторожный ответ",
};
function CheckDetail({ check }: { check: EvaluatedRow["checks"][number] }) {
  return (
    <div>
      <p>
        {check.passed ? "✓ Пройдена" : "✕ Не пройдена"}:{" "}
        {checkLabel(check.code)}
      </p>
      {hasRussianExplanation(check.message) && (
        <p className="text-content-500">{check.message}</p>
      )}
      <details>
        <summary className="cursor-pointer text-content-500">
          Техническая причина
        </summary>
        <p className="mt-1">
          {check.code}: {check.message}
        </p>
      </details>
    </div>
  );
}
function AnswerDetail({ row }: { row?: EvaluatedRow }) {
  if (!row) return <p>Нет оценки</p>;
  const rejected = row.validation_failures.flatMap((failure) =>
    failure.checks.filter((check) => !check.passed),
  );
  return (
    <div className="flex min-w-0 flex-col gap-2 [overflow-wrap:anywhere]">
      <p className="font-medium">{verdictLabels[row.verdict]}</p>
      {row.answer && (
        <>
          <p>
            {row.answer.status}: {row.answer.answer || "—"}
          </p>
          {row.answer.quote &&
            !row.evidence.some(
              (item) =>
                typeof item.text === "string" || typeof item.quote === "string",
            ) && (
              <blockquote className="border-l-2 border-accent-500 pl-2">
                «{row.answer.quote}»
                {row.answer.file && (
                  <span className="block text-content-500">
                    {row.answer.file}
                  </span>
                )}
              </blockquote>
            )}
        </>
      )}
      {row.evidence.map((evidence, index) =>
        typeof (evidence.text ?? evidence.quote) === "string" ? (
          <blockquote
            key={`${String(evidence.id ?? index)}`}
            className="border-l-2 border-accent-500 pl-2"
          >
            «{String(evidence.text ?? evidence.quote)}»
            <span className="block text-content-500">
              {String(evidence.file ?? evidence.file_name ?? "")}
            </span>
          </blockquote>
        ) : null,
      )}
      <p className="text-content-500">Оценщик: {row.reason || "—"}</p>
      {!!row.checks.length && (
        <details>
          <summary className="cursor-pointer">
            Итоговые проверки ({row.checks.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {row.checks.map((check, i) => (
              <li key={`${check.code}-${i}`}>
                <CheckDetail check={check} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {!!rejected.length && (
        <details>
          <summary className="cursor-pointer">
            Пойманные ошибки ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {row.validation_failures.map((failure, i) => {
              const candidate = failure.candidate;
              const text =
                typeof candidate === "object" &&
                candidate !== null &&
                "answer" in candidate &&
                typeof candidate.answer === "string"
                  ? candidate.answer
                  : undefined;
              return (
                <li key={`${text ?? "candidate"}-${i}`}>
                  {text && <p>Отклонённый ответ: {candidatePreview(text)}</p>}
                  {failure.checks
                    .filter((check) => !check.passed)
                    .map((check, index) => (
                      <div key={`${check.code}-${index}`}>
                        <CheckDetail check={check} />
                      </div>
                    ))}
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </div>
  );
}
export function ComparisonAnswers({ result }: { result: EvaluatedComparison }) {
  const before = new Map(result.before.rows.map((row) => [row.id, row]));
  const after = new Map(result.after.rows.map((row) => [row.id, row]));
  const ids = new Set([...before.keys(), ...after.keys()]);
  return (
    <section className="scrollbar-dropdown min-w-0 overflow-x-auto rounded-xl border border-special-300 p-3">
      <h3 className="mb-2 text-body-base font-medium">
        Ответы, цитаты и причины оценки
      </h3>
      <table className="w-full min-w-[640px] table-fixed text-left text-label-md">
        <thead>
          <tr>
            {[
              "ID вопроса",
              "Вопрос и категория",
              "Baseline — было",
              "Harness — стало",
            ].map((label, i) => (
              <th
                key={label}
                scope="col"
                className={`p-3 font-medium ${i === 0 ? "w-24" : ""}`}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...ids].map((id) => {
            const a = before.get(id);
            const b = after.get(id);
            return (
              <tr key={id} className="border-t border-content-100 align-top">
                <th scope="row" className="break-words p-3 font-normal">
                  {id}
                </th>
                <td className="break-words p-3">
                  <p>
                    {a?.question ??
                      b?.question ??
                      "Формулировка не сохранена в старом запуске"}
                  </p>
                  <p className="mt-2 text-content-500">{a?.type ?? b?.type}</p>
                </td>
                <td className="p-3">
                  <AnswerDetail row={a} />
                </td>
                <td className="p-3">
                  <AnswerDetail row={b} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!ids.size && (
        <p className="p-3 text-body-sm text-content-500">
          Оценки отдельных вопросов отсутствуют.
        </p>
      )}
    </section>
  );
}
