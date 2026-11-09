"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import {
  useUsersMePartialUpdateMutation,
  zPatchProfileError,
} from "@/shared/api/account";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { type PromptValues, promptSchema } from "../model/prompt-schema";

export function PromptEditor({ prompt }: { prompt: string }) {
  const [save] = useUsersMePartialUpdateMutation();
  const [saved, setSaved] = useState(false);
  const {
    control,
    handleSubmit,
    reset,
    setError,
    clearErrors,
    formState: { errors, isDirty, isSubmitting },
  } = useForm<PromptValues>({
    resolver: zodResolver(promptSchema, {
      error: (issue) =>
        issue.code === "too_big"
          ? "Не более 8000 символов"
          : "Проверьте текст инструкций",
    }),
    mode: "onChange",
    defaultValues: { system_prompt: prompt },
    values: { system_prompt: prompt },
    resetOptions: { keepDirtyValues: true },
  });
  async function submit(values: PromptValues) {
    clearErrors("root");
    setSaved(false);
    const next = { system_prompt: values.system_prompt.trim() };
    try {
      await save({ patchedUpdateRequest: next }).unwrap();
      reset(next, { keepDirtyValues: false });
      setSaved(true);
    } catch (error) {
      applyApiFormErrors({
        error,
        setError,
        fields: ["system_prompt"],
        schema: zPatchProfileError,
        fallback: "Не удалось сохранить инструкции. Попробуйте ещё раз.",
      });
    }
  }
  return (
    <section
      aria-labelledby="prompt-heading"
      className="overflow-hidden rounded-3xl border border-special-300"
    >
      <div className="bg-special-200 px-6 pt-[26px] pb-[34px]">
        <h2 id="prompt-heading" className="text-h5 font-medium">
          Ваши инструкции для ИИ
        </h2>
        <p className="mt-2 text-body-base text-content-500">
          Инструкции из вашего профиля можно изменить. Они применяются к новым
          сообщениям.
        </p>
      </div>
      <form
        noValidate
        onSubmit={handleSubmit(submit)}
        className="flex flex-col gap-3.5 p-6"
        aria-busy={isSubmitting}
      >
        <label
          htmlFor="system-prompt"
          className="text-h6 leading-[29px] font-medium"
        >
          Инструкции для ИИ
        </label>
        <Controller
          name="system_prompt"
          control={control}
          render={({ field }) => (
            <>
              <Textarea
                {...field}
                id="system-prompt"
                maxLength={8000}
                disabled={isSubmitting}
                aria-invalid={!!errors.system_prompt}
                aria-describedby={`prompt-hint prompt-count${errors.system_prompt ? " prompt-field-error" : ""}`}
                placeholder={
                  "Например: Ты — внимательный помощник. Отвечай ясно и по делу.\nУчитывай контекст обсуждения и прикреплённые файлы."
                }
                className="scrollbar-dropdown h-[330px] overflow-y-auto px-5 py-[18px] [scrollbar-gutter:stable]"
                onChange={(event) => {
                  field.onChange(event);
                  clearErrors("root");
                  setSaved(false);
                }}
              />
              <div className="flex flex-wrap justify-between gap-2 text-[13px] leading-[19px] text-content-500">
                <p id="prompt-hint">
                  Оставьте поле пустым, чтобы убрать свои инструкции.
                </p>
                <span id="prompt-count">{field.value.length}/8000</span>
              </div>
            </>
          )}
        />
        {errors.system_prompt && (
          <p
            id="prompt-field-error"
            role="alert"
            className="text-body-sm text-error-600"
          >
            {errors.system_prompt.message}
          </p>
        )}
        {errors.root && (
          <p role="alert" className="text-body-sm text-error-600">
            {errors.root.message}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <output className="text-[13px] leading-[19px] text-content-500">
            {isSubmitting
              ? "Сохранение…"
              : saved && !isDirty
                ? "Инструкции сохранены"
                : isDirty
                  ? "Есть несохранённые изменения"
                  : "Изменения применяются к следующим сообщениям."}
          </output>
          <Button
            type="submit"
            size="sm"
            disabled={!isDirty || !!errors.system_prompt || isSubmitting}
          >
            {isSubmitting ? "Сохранение…" : "Сохранить инструкции"}
          </Button>
        </div>
      </form>
    </section>
  );
}
