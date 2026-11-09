"use client";

import { EnvelopeIcon } from "@heroicons/react/24/outline";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";
import {
  useUsersEmailConfirmCreateMutation,
  useUsersEmailCreateMutation,
  zConfirmUpdateEmailError,
  zUpdateEmailError,
} from "@/shared/api/account";
import { useNotification } from "@/shared/hooks/use-notification";
import { AccountCard } from "@/shared/ui/account-card";
import { Button } from "@/shared/ui/button";
import { ConfirmationCode } from "@/shared/ui/confirmation-code";
import { Input } from "@/shared/ui/input";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { changeEmailSchema } from "./change-email-schema";

type Values = z.infer<typeof changeEmailSchema>;

export function ChangeEmailPage() {
  const { showNotification } = useNotification();
  const router = useRouter();
  const [requestCode, { isLoading: isRequesting }] =
    useUsersEmailCreateMutation();
  const [confirmEmail, { isLoading: isSaving }] =
    useUsersEmailConfirmCreateMutation();
  const [codeSent, setCodeSent] = useState(false);
  const [isRedirecting, startTransition] = useTransition();
  const {
    control,
    handleSubmit,
    getValues,
    trigger,
    clearErrors,
    setValue,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(changeEmailSchema, {
      error: (issue) =>
        issue.path?.[0] === "email"
          ? "Введите корректный email"
          : "Введите код подтверждения",
    }),
    mode: "onBlur",
    defaultValues: { email: "", code: "" },
  });
  const busy = isRequesting || isSaving || isSubmitting || isRedirecting;

  async function onRequestCode() {
    if (busy) return;
    clearErrors("root");
    if (!(await trigger("email"))) return;
    setCodeSent(false);
    setValue("code", "");
    clearErrors("code");
    try {
      await requestCode({
        newEmailRequest: { email: getValues("email").trim() },
      }).unwrap();
      setCodeSent(true);
      showNotification({
        message: "Код подтверждения отправлен на новую почту",
      });
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: ["email"],
        schema: zUpdateEmailError,
        fallback: "Не удалось отправить код. Попробуйте ещё раз.",
      });
    }
  }

  async function submit(values: Values) {
    if (!codeSent || isRequesting || isSaving) return;
    clearErrors("root");
    try {
      await confirmEmail({ emailWithCodeRequest: values }).unwrap();
      showNotification({ message: "Электронная почта успешно изменена" });
      reset();
      setCodeSent(false);
      startTransition(() => {
        router.replace("/profile");
      });
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: ["email", "code"],
        schema: zConfirmUpdateEmailError,
        fallback:
          "Не удалось сменить почту. Проверьте код и попробуйте ещё раз.",
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
        title="Смена почты"
        description="Введите новую электронную почту. Мы отправим на неё код, чтобы подтвердить изменение"
        footer={
          <>
            {errors.root?.message && (
              <p role="alert" className="text-error-600">
                {errors.root.message}
              </p>
            )}
            {codeSent && (
              <output>
                Код отправлен на новую почту. Введите его, чтобы сохранить
                изменения.
              </output>
            )}
            <Button
              type="submit"
              disabled={!codeSent || busy}
              variant={codeSent ? "primary" : "secondary"}
              className="w-full"
            >
              {isSaving || isRedirecting ? "Сохранение..." : "Сменить почту"}
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
          <Controller
            name="email"
            control={control}
            render={({ field, fieldState }) => (
              <Input
                {...field}
                onValueChange={(value) => {
                  field.onChange(value);
                  setCodeSent(false);
                  setValue("code", "");
                  clearErrors(["email", "code"]);
                  clearErrors("root");
                }}
                label={<span className="text-body-sm">Электронная почта</span>}
                placeholder="Введите новый email"
                type="email"
                autoComplete="email"
                icon={<EnvelopeIcon />}
                disabled={busy}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            name="code"
            control={control}
            render={({ field, fieldState }) => (
              <ConfirmationCode
                {...field}
                onValueChange={field.onChange}
                error={fieldState.error?.message}
                codeSent={codeSent}
                isRequesting={isRequesting}
                disabled={busy}
                onRequestCode={onRequestCode}
              />
            )}
          />
        </div>
      </AccountCard>
    </form>
  );
}
