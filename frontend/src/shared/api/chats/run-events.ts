export type RunStep = {
  step_id: string;
  kind?: string;
  title: string;
  message: string;
  status: "started" | "completed" | "failed" | "cancelled" | "interrupted";
  updated_seq?: number;
};
export type RunEvent = {
  seq: number;
  run_id: string;
  type: string;
  data: Record<string, unknown>;
};
export type RunStream = {
  connection:
    | "connecting"
    | "connected"
    | "reconnecting"
    | "polling"
    | "closed"
    | "error";
  seq: number;
  steps: RunStep[];
  answer?: string;
  answerItems?: Record<string, { index: number; text: string }>;
  error?: string;
  terminal: boolean;
};
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
export function parseRunEvent(
  value: unknown,
  runId: string,
): RunEvent | undefined {
  if (
    !record(value) ||
    value.run_id !== runId ||
    !Number.isSafeInteger(value.seq) ||
    Number(value.seq) < 1 ||
    typeof value.type !== "string" ||
    !record(value.data)
  )
    return;
  return {
    seq: Number(value.seq),
    run_id: runId,
    type: value.type,
    data: value.data,
  };
}
export function applyRunEvent(state: RunStream, event: RunEvent) {
  if (event.seq <= state.seq) return;
  state.seq = event.seq;
  if (event.type === "harness.step") {
    const d = event.data;
    if (
      typeof d.step_id === "string" &&
      typeof d.title === "string" &&
      typeof d.message === "string" &&
      (d.status === "started" ||
        d.status === "completed" ||
        d.status === "failed" ||
        d.status === "cancelled" ||
        d.status === "interrupted")
    ) {
      const step: RunStep = {
        step_id: d.step_id,
        ...(typeof d.kind === "string" ? { kind: d.kind } : {}),
        title: d.title,
        message: d.message,
        status: d.status,
        updated_seq: event.seq,
      };
      const index = state.steps.findIndex((s) => s.step_id === step.step_id);
      if (index === -1) state.steps.push(step);
      else state.steps[index] = step;
    }
  }
  if (event.type === "answer.completed" && record(event.data.answer)) {
    const answer = event.data.answer;
    const text =
      answer.clarification_question ||
      answer.answer ||
      (answer.origin === "fallback"
        ? "Не удалось подтвердить ответ в пределах проверок."
        : answer.status);
    if (typeof text === "string") {
      const index = event.data.question_index;
      const question = event.data.question;
      if (
        typeof answer.id === "string" &&
        Number.isSafeInteger(index) &&
        record(question) &&
        typeof question.text === "string" &&
        Number(event.data.question_count) > 1
      ) {
        state.answerItems ??= {};
        state.answerItems[answer.id] = {
          index: Number(index),
          text: `${Number(index) + 1}. ${question.text}\n${text}`,
        };
        state.answer = Object.values(state.answerItems)
          .sort((a, b) => a.index - b.index)
          .map((item) => item.text)
          .join("\n\n");
      } else state.answer = text;
    }
  }
  if (
    [
      "run.completed",
      "run.failed",
      "run.cancelled",
      "run.interrupted",
    ].includes(event.type)
  ) {
    state.terminal = true;
    if (
      record(event.data.error) &&
      typeof event.data.error.message === "string"
    )
      state.error =
        event.data.error.code === "run_timeout"
          ? "Превышено время выполнения запроса."
          : event.data.error.message;
    if (event.type !== "run.completed") {
      for (const step of state.steps)
        if (step.status === "started")
          step.status =
            event.type === "run.cancelled"
              ? "cancelled"
              : event.type === "run.failed"
                ? "failed"
                : "interrupted";
    }
  }
}

// The journal keeps every call and retry. The chat shows the latest real step
// in each operational phase, so repeated tools/scans do not flood the page.
const phases: Record<string, string> = {
  prepare: "prepare",
  context_reduction: "prepare",
  chat_plan: "prepare",
  evidence_scan: "sources",
  answer: "answer",
  plain: "answer",
  baseline: "answer",
  raw: "answer",
  tool: "tools",
  validation: "validation",
  semantic_review: "review",
  verification_scan: "verification_scan",
  repair: "repair",
  result: "result",
};
export function essentialRunSteps(steps: RunStep[]): RunStep[] {
  const latest = new Map<string, RunStep>();
  for (const step of steps) {
    const phase = step.kind ? phases[step.kind] : step.step_id;
    if (!phase) continue;
    const previous = latest.get(phase);
    if (
      !previous ||
      ((previous.status !== "started" || step.status === "started") &&
        (step.updated_seq ?? 0) >= (previous.updated_seq ?? 0))
    )
      latest.set(phase, step);
  }
  return [...latest.values()];
}
export function buildRunSocketUrl(
  path: string,
  ticket: string,
  seq: number,
  origin: string,
) {
  const base = new URL(origin);
  if (!["http:", "https:", "ws:", "wss:"].includes(base.protocol))
    throw new Error("Недопустимый адрес WebSocket");
  if (!/^\/ai\/api\/v1\/runs\/[^/?#]+\/ws$/.test(path))
    throw new Error("Недопустимый путь WebSocket");
  const url = new URL(path, base);
  url.protocol =
    base.protocol === "https:" || base.protocol === "wss:" ? "wss:" : "ws:";
  url.searchParams.set("ticket", ticket);
  url.searchParams.set("after", String(seq));
  return url;
}
