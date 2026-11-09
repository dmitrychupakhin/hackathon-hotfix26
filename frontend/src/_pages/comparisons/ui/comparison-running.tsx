import { z } from "zod";
import { useChatsModelsListQuery } from "@/shared/api/chats";
import type { ComparisonJobRead } from "@/shared/api/comparisons";
import { stageLabel, statusLabels } from "../model/comparison";
import { ComparisonCard } from "./comparison-card";

const progressSchema = z.object({
  run_states: z
    .record(
      z.string(),
      z.object({
        status: z.string(),
        metrics_final: z.boolean().optional(),
        step: z
          .object({
            title: z.string(),
            message: z.string(),
            status: z.string().optional(),
            kind: z.string().optional(),
            details: z
              .object({
                batch: z.number().int().positive().optional(),
                batches: z.number().int().positive().optional(),
              })
              .optional(),
          })
          .nullish(),
        error: z.unknown().optional(),
        metrics: z
          .object({
            model_calls: z.number().optional(),
            transport_attempts: z.number().optional(),
            known_total_tokens: z.number().optional(),
          })
          .optional(),
      }),
    )
    .optional(),
});
const runStatus: Record<string, string> = {
  queued: "В очереди",
  running: "Выполняется",
  completed: "Завершён",
  failed: "Технический отказ",
  cancelled: "Отменён",
  interrupted: "Прерван",
};
export function ComparisonRunning({ job }: { job: ComparisonJobRead }) {
  const models = useChatsModelsListQuery();
  const progress = progressSchema.safeParse(
    "progress" in job ? job.progress : {},
  );

  return (
    <>
      <ComparisonCard title="Обработка сравнения">
        <output className="text-body-base">
          {statusLabels[job.status]} · {stageLabel(job.stage)}
        </output>
        <p className="text-body-sm text-content-500">
          Baseline и harness работают с одинаковыми вопросами и документами.
          После генерации ответы проверяются по эталонам.
        </p>
        {progress.success &&
          Object.entries(progress.data.run_states ?? {}).map(([mode, run]) => (
            <div key={mode} className="flex flex-col gap-1 text-body-sm">
              <p>
                {mode === "baseline" ? "Baseline" : "Harness"}:{" "}
                {runStatus[run.status] ?? run.status}
                {run.metrics?.model_calls != null
                  ? ` · ${run.metrics_final === false ? "запросов начато" : "запросов"} ${run.metrics.model_calls}`
                  : ""}
                {run.metrics?.transport_attempts != null
                  ? ` · HTTP-попыток ${run.metrics.transport_attempts}`
                  : ""}
                {run.metrics?.known_total_tokens != null
                  ? ` · токенов ${run.metrics.known_total_tokens}`
                  : ""}
              </p>
              {run.step && (
                <>
                  <p className="font-medium">{run.step.title}</p>
                  {run.step.message && (
                    <p className="text-content-500">{run.step.message}</p>
                  )}
                  {run.step.details?.batch != null &&
                    run.step.details.batches != null && (
                      <p className="text-content-500">
                        Порция {run.step.details.batch}/
                        {run.step.details.batches}
                      </p>
                    )}
                </>
              )}
            </div>
          ))}
      </ComparisonCard>
      <ComparisonCard title="Исходные данные запуска">
        <p className="text-body-sm">
          Модель:{" "}
          {models.data?.find((model) => model.id === job.model_id)?.name ??
            job.model_id}
        </p>
        <p className="text-body-sm text-content-500">
          Режимы: baseline без дополнительных проверок и harness с проверками и
          сохранёнными инструкциями.
        </p>
      </ComparisonCard>
    </>
  );
}
