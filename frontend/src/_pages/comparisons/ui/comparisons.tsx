"use client";

import { useState } from "react";
import {
  comparisonsApi,
  useComparisonsRetrieveQuery,
} from "@/shared/api/comparisons";
import {
  type ComparisonDraftValues,
  comparisonTitle,
  emptyDraft,
  isComparisonActive,
} from "../model/comparison";
import { ComparisonDraft } from "./comparison-draft";
import { ComparisonFeedback } from "./comparison-feedback";
import { ComparisonHistory } from "./comparison-history";
import { ComparisonResult } from "./comparison-result";
import { ComparisonRunning } from "./comparison-running";

function SelectedComparison({ id }: { id: string }) {
  const cached = comparisonsApi.endpoints.comparisonsRetrieve.useQueryState({
    id,
  });
  const status = cached.currentData?.status;
  const query = useComparisonsRetrieveQuery(
    { id },
    {
      pollingInterval: !status || isComparisonActive(status) ? 2000 : 0,
      skipPollingIfUnfocused: true,
    },
  );
  const job = query.currentData;
  return (
    <section aria-label="Выбранное сравнение" className="flex flex-col gap-6">
      {query.isLoading && <output>Загрузка сравнения…</output>}
      <ComparisonFeedback
        message={
          query.error
            ? "Не удалось обновить сравнение. Последние полученные данные сохранены."
            : undefined
        }
        retry={() => query.refetch()}
      />
      {job && (
        <>
          <h2 className="text-h5 font-medium">
            {comparisonTitle(job.created_at)}
          </h2>
          {isComparisonActive(job.status) ? (
            <ComparisonRunning job={job} />
          ) : job.status === "failed" ? (
            <ComparisonFeedback
              message={
                job.error ||
                "Не удалось завершить сравнение. Проверьте входные файлы и создайте новый анализ."
              }
            />
          ) : (
            <ComparisonResult job={job} />
          )}
        </>
      )}
    </section>
  );
}
export function Comparisons() {
  const [selected, setSelected] = useState<string>();
  const [page, setPage] = useState(1);
  const [draft, setDraft] = useState<ComparisonDraftValues>(emptyDraft);
  return (
    <div className="mx-auto max-w-[1536px]">
      <header className="mb-6">
        <h1 className="text-h3 font-medium">Сравнения</h1>
        <p className="mt-2 text-body-base text-content-500">
          Сравнивайте baseline и harness одной модели на одинаковых исходных
          данных.
        </p>
      </header>
      <div className="grid items-start gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <ComparisonHistory
          selected={selected}
          page={page}
          onPage={setPage}
          onSelect={setSelected}
          onNew={() => setSelected(undefined)}
        />
        <div className="flex min-w-0 flex-col gap-6 rounded-3xl border border-special-300 p-6">
          <div hidden={selected !== undefined}>
            <ComparisonDraft
              value={draft}
              onChange={setDraft}
              onCreated={(id) => {
                setDraft(emptyDraft());
                setPage(1);
                setSelected(id);
              }}
            />
          </div>
          {selected && <SelectedComparison key={selected} id={selected} />}
        </div>
      </div>
    </div>
  );
}
