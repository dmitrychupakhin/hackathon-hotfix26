import { Button } from "@/shared/ui/button";
export function ComparisonFeedback({
  message,
  retry,
}: {
  message?: string;
  retry?: () => void;
}) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 text-body-sm text-error-600"
    >
      <p>{message}</p>
      {retry && (
        <Button variant="secondary" size="sm" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
