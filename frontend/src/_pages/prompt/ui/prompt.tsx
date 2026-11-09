"use client";

import { useUsersMeRetrieveQuery } from "@/shared/api/account";
import { Button } from "@/shared/ui/button";
import { PromptEditor } from "./prompt-editor";
import { PromptGuidance } from "./prompt-guidance";

export function Prompt() {
  const { data, isLoading, isError, refetch } = useUsersMeRetrieveQuery();
  return (
    <div className="mx-auto max-w-[1536px]">
      <header className="mb-6">
        <h1 className="text-h3 font-medium">Инструкции для ИИ</h1>
        <p className="mt-2 text-body-base text-content-500">
          Настройте инструкции, которые будут добавляться к запросам модели.
        </p>
      </header>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_384px]">
        <div className="flex min-w-0 flex-col gap-4">
          {isLoading && !data && <output>Загрузка инструкций…</output>}
          {isError && (
            <div
              role="alert"
              className="flex flex-wrap items-center gap-3 text-body-sm text-error-600"
            >
              <p>Не удалось загрузить инструкции. Попробуйте ещё раз.</p>
              <Button variant="secondary" size="sm" onClick={() => refetch()}>
                Повторить
              </Button>
            </div>
          )}
          {data && (
            <PromptEditor key={data.id} prompt={data.system_prompt ?? ""} />
          )}
        </div>
        <PromptGuidance />
      </div>
    </div>
  );
}
