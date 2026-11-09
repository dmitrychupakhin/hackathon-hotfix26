import { Button } from "@/shared/ui/button";
import { chatError } from "../model/chat-utils";

export function ChatFeedback({
  loading,
  error,
  retry,
}: {
  loading?: boolean;
  error?: unknown;
  retry?: () => void;
}) {
  if (loading)
    return <output className="text-sm text-content-500">Загрузка…</output>;
  if (!error) return null;
  return (
    <div role="alert" className="flex flex-col gap-2 text-sm text-error-600">
      <p>{typeof error === "string" ? error : chatError(error)}</p>
      {retry && (
        <Button variant="secondary" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
export function ChatLoadMore({
  hasNext,
  busy,
  onLoad,
}: {
  hasNext?: boolean;
  busy: boolean;
  onLoad: () => void;
}) {
  if (!hasNext) return null;
  return (
    <Button variant="secondary" disabled={busy} onClick={onLoad}>
      {busy ? "Загрузка…" : "Показать ещё"}
    </Button>
  );
}
