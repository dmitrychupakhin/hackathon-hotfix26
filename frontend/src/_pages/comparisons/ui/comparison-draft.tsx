import { ChevronDownIcon } from "@heroicons/react/24/outline";
import { useState } from "react";
import { useChatsModelsListQuery } from "@/shared/api/chats";
import { useComparisonsCreateMutation } from "@/shared/api/comparisons";
import { Button } from "@/shared/ui/button";
import { ContextMenu } from "@/shared/ui/context-menu";
import {
  type ComparisonDraftValues,
  comparisonRequestErrors,
  type DraftErrors,
  validateComparisonDraft,
} from "../model/comparison";
import { ComparisonCard } from "./comparison-card";
import { ComparisonFeedback } from "./comparison-feedback";
import { ComparisonFileField } from "./comparison-file-field";
export function ComparisonDraft({
  value,
  onChange,
  onCreated,
}: {
  value: ComparisonDraftValues;
  onChange: (draft: ComparisonDraftValues) => void;
  onCreated: (id: string) => void;
}) {
  const [errors, setErrors] = useState<DraftErrors>({});
  const [create, creation] = useComparisonsCreateMutation();
  const models = useChatsModelsListQuery();
  const change = (
    next: ComparisonDraftValues,
    field: keyof ComparisonDraftValues,
  ) => {
    onChange(next);
    setErrors((previous) => ({
      ...previous,
      [field]: validateComparisonDraft(next)[field],
      root: undefined,
    }));
  };
  const model = models.data?.find((item) => item.id === value.modelId);
  async function submit() {
    const validation = validateComparisonDraft(value);
    setErrors(validation);
    if (
      Object.keys(validation).length ||
      !model ||
      !value.questions ||
      !value.answers ||
      creation.isLoading
    )
      return;
    try {
      const result = await create({
        comparisonCreateRequest: {
          questions: value.questions,
          answers: value.answers,
          documents: value.documents,
          model_id: value.modelId,
        },
      }).unwrap();
      setErrors({});
      onCreated(result.id);
    } catch (error) {
      setErrors(comparisonRequestErrors(error));
    }
  }
  return (
    <form
      aria-label="Новое сравнение"
      className="flex flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <h2 className="text-h5 font-medium">Новый анализ</h2>
      <div className="grid gap-4 2xl:grid-cols-2">
        <ComparisonCard title="1  Добавить вопросы">
          <p className="text-body-sm text-content-500">
            questions.csv организатора. ID, формулировки и принадлежность к
            закупкам сохраняются без изменений.
          </p>
          <ComparisonFileField
            label="Вопросы"
            accept=".csv"
            files={value.questions ? [value.questions] : []}
            disabled={creation.isLoading}
            error={errors.questions}
            onChange={(files) =>
              change({ ...value, questions: files[0] }, "questions")
            }
          />
        </ComparisonCard>
        <ComparisonCard title="2  Добавить эталонные ответы">
          <p className="text-body-sm text-content-500">
            answers_public.json организатора. Эталоны используются только
            оценщиком и не передаются отвечающей модели.
          </p>
          <ComparisonFileField
            label="Эталонные ответы"
            accept=".json"
            files={value.answers ? [value.answers] : []}
            disabled={creation.isLoading}
            error={errors.answers}
            onChange={(files) =>
              change({ ...value, answers: files[0] }, "answers")
            }
          />
        </ComparisonCard>
        <ComparisonCard title="3  Выбрать модель">
          <p className="text-body-sm text-content-500">
            Одна модель в режимах baseline и harness. Harness использует
            сохранённые инструкции из профиля.
          </p>
          <ContextMenu
            triggerMode="click"
            label="Выбор модели сравнения"
            items={(models.data ?? []).map((item) => ({
              id: item.id,
              label: item.name,
              active: item.id === value.modelId,
              onSelect: () => change({ ...value, modelId: item.id }, "modelId"),
            }))}
          >
            <Button
              type="button"
              variant="secondary"
              icon={<ChevronDownIcon />}
              iconPosition="right"
              disabled={
                creation.isLoading || !models.data?.length || !!models.error
              }
            >
              {model?.name || "Выбрать модель"}
            </Button>
          </ContextMenu>
          {models.isLoading && (
            <output className="text-body-sm">Загрузка моделей…</output>
          )}
          <ComparisonFeedback
            message={
              models.error ? "Не удалось загрузить модели." : errors.modelId
            }
            retry={models.error ? () => models.refetch() : undefined}
          />
        </ComparisonCard>
        <ComparisonCard title="4  Добавить документы">
          <p className="text-body-sm text-content-500">
            Для нескольких закупок — ZIP с текстовыми файлами TXT/MD в папках
            packages/P01…P06. PDF, DOCX и другие оригиналы загружайте отдельными
            файлами одной закупки. Вопросы группируются одинаково: один базовый
            запрос на закупку.
          </p>
          <ComparisonFileField
            label="Общие документы"
            multiple
            files={value.documents}
            disabled={creation.isLoading}
            error={errors.documents}
            onChange={(documents) =>
              change({ ...value, documents }, "documents")
            }
          />
        </ComparisonCard>
      </div>
      <p className="text-label-md text-content-500">
        До 10 МиБ на файл, до 32 МиБ суммарно для общих документов. Документы:
        ZIP, PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, JSON и HTML. ZIP проверяется
        сервером; размер распакованных данных также ограничен.
      </p>
      <ComparisonFeedback message={errors.root} />
      <Button
        type="submit"
        disabled={
          creation.isLoading ||
          Object.keys(validateComparisonDraft(value)).length > 0 ||
          !model ||
          !!models.error
        }
        className="self-end"
      >
        {creation.isLoading ? "Загрузка файлов…" : "Запустить сравнение"}
      </Button>
    </form>
  );
}
