import { useState } from "react";
import {
  useLazyComparisonsAnswersRetrieveQuery,
  useLazyComparisonsReportRetrieveQuery,
} from "@/shared/api/comparisons";
import { Button } from "@/shared/ui/button";
import { ComparisonFeedback } from "./comparison-feedback";
export function ComparisonDownloads({
  id,
  baseline,
  harness,
}: {
  id: string;
  baseline: boolean;
  harness: boolean;
}) {
  const [csv, csvState] = useLazyComparisonsAnswersRetrieveQuery();
  const [report, reportState] = useLazyComparisonsReportRetrieveQuery();
  const [error, setError] = useState<string>();
  const pending = csvState.isFetching || reportState.isFetching;
  async function download(mode: "baseline" | "harness" | "report") {
    setError(undefined);
    try {
      const url = await (mode === "report"
        ? report({ id }, true)
        : csv({ id, mode }, true)
      ).unwrap();
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download =
        mode === "report" ? `comparison-${id}.json` : `answers-${mode}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch {
      setError(
        "Не удалось скачать результат. Проверьте соединение и повторите загрузку.",
      );
    }
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          disabled={pending || !baseline}
          onClick={() => void download("baseline")}
        >
          Скачать baseline CSV
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={pending || !harness}
          onClick={() => void download("harness")}
        >
          Скачать harness CSV
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={pending}
          onClick={() => void download("report")}
        >
          Скачать отчёт JSON
        </Button>
      </div>
      <ComparisonFeedback message={error} />
    </div>
  );
}
