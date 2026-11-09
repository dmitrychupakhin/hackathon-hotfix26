import {
  comparisonsApi,
  useComparisonsListQuery,
} from "@/shared/api/comparisons";
import { Button } from "@/shared/ui/button";
import {
  comparisonTitle,
  isComparisonActive,
  statusLabels,
} from "../model/comparison";
import { ComparisonFeedback } from "./comparison-feedback";
import { ComparisonHistoryItem } from "./comparison-history-item";
export function ComparisonHistory({
  selected,
  page,
  onPage,
  onSelect,
  onNew,
}: {
  selected?: string;
  page: number;
  onPage: (page: number) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const args = { page, pageSize: 30 };
  const cached = comparisonsApi.endpoints.comparisonsList.useQueryState(args);
  const query = useComparisonsListQuery(args, {
    pollingInterval: cached.currentData?.results.some((job) =>
      isComparisonActive(job.status),
    )
      ? 5000
      : 0,
    skipPollingIfUnfocused: true,
  });
  return (
    <aside
      aria-label="История сравнений"
      className="flex min-w-0 flex-col gap-4 self-start rounded-3xl border border-special-300 px-5 py-6"
    >
      <h2 className="text-h6">История запусков</h2>
      <Button onClick={onNew}>Новый анализ +</Button>
      {query.isLoading && <output>Загрузка истории…</output>}
      <ComparisonFeedback
        message={
          query.error ? "Не удалось обновить историю сравнений." : undefined
        }
        retry={() => query.refetch()}
      />
      {!query.error && query.currentData?.count === 0 && (
        <p className="text-body-sm text-content-500">Сравнений пока нет.</p>
      )}
      {query.currentData?.results.map((job) => (
        <ComparisonHistoryItem
          key={job.id}
          title={comparisonTitle(job.created_at)}
          status={statusLabels[job.status]}
          active={job.id === selected}
          onSelect={() => onSelect(job.id)}
        />
      ))}
      {(query.currentData?.count ?? 0) > 30 && (
        <nav
          aria-label="Страницы истории"
          className="flex items-center justify-between gap-2 text-label-md"
        >
          <Button
            size="sm"
            variant="secondary"
            disabled={page === 1 || query.isFetching}
            onClick={() => onPage(page - 1)}
          >
            Назад
          </Button>
          <span>{page}</span>
          <Button
            size="sm"
            variant="secondary"
            disabled={!query.currentData?.next || query.isFetching}
            onClick={() => onPage(page + 1)}
          >
            Далее
          </Button>
        </nav>
      )}
    </aside>
  );
}
