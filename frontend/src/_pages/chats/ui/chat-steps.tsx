import type { RunStream } from "@/shared/api/chats";
import { essentialRunSteps } from "@/shared/api/chats/run-events";

const labels = {
  started: "Выполняется",
  completed: "Завершено",
  failed: "Проверка не пройдена",
  cancelled: "Отменено",
  interrupted: "Прервано",
};
const markers = {
  started: "◌",
  completed: "✓",
  failed: "!",
  cancelled: "−",
  interrupted: "!",
};
export function ChatSteps({
  stream,
  running,
}: {
  stream?: RunStream;
  running: boolean;
}) {
  if (!running && !stream?.steps.length) return null;
  const steps = essentialRunSteps(stream?.steps ?? []);
  const connectionNotice =
    stream?.connection === "reconnecting"
      ? "Восстановление соединения…"
      : stream?.connection === "error"
        ? "События временно недоступны"
        : running && stream?.terminal
          ? "Сохранение результата…"
          : running && !stream?.steps.length
            ? "Ответ выполняется…"
            : undefined;
  return (
    <div className="flex shrink-0 flex-col gap-1 rounded-xl border border-content-100 p-4">
      <h3 className="text-[15px] leading-[22px] font-semibold">Этапы работы</h3>
      {connectionNotice && (
        <output className="text-[13px] leading-[19px] text-content-500">
          {connectionNotice}
        </output>
      )}
      <ol className="flex max-h-48 flex-col gap-1 overflow-y-auto">
        {steps.map((step) => (
          <li
            key={step.step_id}
            title={step.message}
            className="flex items-start gap-1.5 text-[13px] leading-[19px] text-content-500"
          >
            <span aria-hidden="true">{markers[step.status]}</span>
            <span>
              {step.title}
              <span className="sr-only"> — {labels[step.status]}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
