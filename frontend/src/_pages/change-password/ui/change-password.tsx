"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";
import {
  useUsersPasswordCreateMutation,
  zUpdatePasswordError,
} from "@/shared/api/account";
import { useNotification } from "@/shared/hooks/use-notification";
import { AccountCard } from "@/shared/ui/account-card";
import { Button } from "@/shared/ui/button";
import { PasswordInput } from "@/shared/ui/password-input";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { changePasswordSchema } from "./change-password-schema";

type Values = z.infer<typeof changePasswordSchema>;

export function ChangePasswordPage() {
  const router = useRouter();
  const { showNotification } = useNotification();
  const [save, { isLoading }] = useUsersPasswordCreateMutation();
  const [isRedirecting, startTransition] = useTransition();
  const {
    control,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(changePasswordSchema, {
      error: (issue) =>
        issue.path?.[0] === "old_password"
          ? "Введите текущий пароль"
          : issue.path?.[0] === "confirm"
            ? "Подтвердите новый пароль"
            : "Введите новый пароль",
    }),
    mode: "onBlur",
    defaultValues: { old_password: "", password: "", confirm: "" },
  });
  const busy = isLoading || isSubmitting || isRedirecting;

  async function submit(values: Values) {
    try {
      await save({ updatePasswordRequest: values }).unwrap();
      reset();
      showNotification({
        message: "Пароль успешно изменён",
        variant: "success",
      });
      startTransition(() => {
        router.replace("/profile");
      });
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: ["old_password", "password", "confirm"],
        schema: zUpdatePasswordError,
        fallback: "Не удалось сменить пароль. Попробуйте ещё раз.",
      });
    }
  }

  return (
    <form
      className="w-full max-w-[500px]"
      noValidate
      onSubmit={handleSubmit(submit)}
    >
      <AccountCard
        title="Смена пароля"
        description="Введите текущий пароль и придумайте новый, чтобы защитить ваш аккаунт"
        footer={
          <>
            {errors.root?.message && (
              <p role="alert" className="text-error-600">
                {errors.root.message}
              </p>
            )}
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Сохранение..." : "Сменить пароль"}
            </Button>
            <p>
              Передумали?{" "}
              <Link
                href="/profile"
                className="rounded-sm text-accent-500 focus-visible:outline-2 focus-visible:outline-accent-600"
              >
                Вернуться в профиль
              </Link>
            </p>
          </>
        }
      >
        <div className="flex flex-col gap-4">
          {(
            [
              [
                "old_password",
                "Текущий пароль",
                "Введите текущий пароль",
                "current-password",
              ],
              [
                "password",
                "Новый пароль",
                "Придумайте новый пароль",
                "new-password",
              ],
              [
                "confirm",
                "Подтверждение нового пароля",
                "Повторите новый пароль",
                "new-password",
              ],
            ] as const
          ).map(([name, label, placeholder, autoComplete]) => (
            <Controller
              key={name}
              name={name}
              control={control}
              render={({ field, fieldState }) => (
                <PasswordInput
                  {...field}
                  onValueChange={field.onChange}
                  label={<span className="text-body-sm">{label}</span>}
                  placeholder={placeholder}
                  autoComplete={autoComplete}
                  disabled={busy}
                  error={fieldState.error?.message}
                />
              )}
            />
          ))}
        </div>
      </AccountCard>
    </form>
  );
}
