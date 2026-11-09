"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  useUsersPasswordResetConfirmCreateMutation,
  useUsersPasswordResetCreateMutation,
  zDetailList,
} from "@/shared/api/account";
import { useNotification } from "@/shared/hooks/use-notification";
import { AccountCard } from "@/shared/ui/account-card";
import { Button } from "@/shared/ui/button";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { PasswordRecoveryFields } from "./password-recovery-fields";
import {
  passwordRecoverySchema,
  type RecoveryInput,
  type RecoveryValues,
} from "./password-recovery-schema";

const fields = ["email", "code", "password", "confirm"] as const;

export function PasswordRecoveryPage() {
  const { showNotification } = useNotification();
  const router = useRouter();
  const [requestCode, { isLoading: isRequesting }] =
    useUsersPasswordResetCreateMutation();
  const [resetPassword, { isLoading: isResetting }] =
    useUsersPasswordResetConfirmCreateMutation();
  const [codeSent, setCodeSent] = useState(false);
  const [notice, setNotice] = useState("");
  const {
    control,
    handleSubmit,
    getValues,
    trigger,
    clearErrors,
    setError,
    formState: { errors },
  } = useForm<RecoveryInput, unknown, RecoveryValues>({
    resolver: zodResolver(passwordRecoverySchema, {
      error: (issue) => {
        if (issue.path?.[0] === "email") return "Введите корректный email";
        if (issue.path?.[0] === "code") return "Введите код подтверждения";
        if (issue.path?.[0] === "password") return "Введите пароль";
        if (issue.path?.[0] === "confirm") return "Подтвердите пароль";
      },
    }),
    defaultValues: { email: "", code: "", password: "", confirm: "" },
  });
  const busy = isRequesting || isResetting;

  async function onRequestCode() {
    clearErrors("root");
    if (!(await trigger("email"))) return;
    setCodeSent(false);
    setNotice("");
    try {
      const response = await requestCode({
        emailRequest: { email: getValues("email").trim() },
      }).unwrap();
      const parsed = zDetailList.safeParse(response);
      setNotice(
        parsed.success
          ? parsed.data.detail.filter((message) => message.trim()).join(" ")
          : "",
      );
      setCodeSent(true);
      showNotification({ message: "Код подтверждения отправлен на почту" });
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields,
        fallback: "Не удалось получить код. Попробуйте ещё раз.",
      });
    }
  }

  async function onSubmit(values: RecoveryValues) {
    if (!codeSent || busy) return;
    clearErrors("root");
    try {
      await resetPassword({ resetPasswordRequest: values }).unwrap();
      showNotification({
        message: "Пароль восстановлен. Войдите с новым паролем",
      });
      router.replace("/login");
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields,
        fallback: "Не удалось сбросить пароль. Попробуйте ещё раз.",
      });
    }
  }

  return (
    <form
      className="w-full max-w-[500px]"
      noValidate
      onSubmit={handleSubmit(onSubmit)}
    >
      <AccountCard
        title="Восстановление пароля"
        description="Введите почту и получите проверочный код для сброса пароля"
        footer={
          <>
            {errors.root?.message && (
              <p role="alert" className="text-error-600">
                {errors.root.message}
              </p>
            )}
            {notice && <output>{notice}</output>}
            <Button
              type="submit"
              disabled={!codeSent || busy}
              variant={codeSent ? "primary" : "secondary"}
              className="w-full"
            >
              {isResetting ? "Сброс..." : "Сбросить"}
            </Button>
            <p>
              Передумали?{" "}
              <Link
                href="/login"
                className="rounded-sm text-accent-500 focus-visible:outline-2 focus-visible:outline-accent-600"
              >
                Назад ко входу
              </Link>
            </p>
          </>
        }
      >
        <PasswordRecoveryFields
          control={control}
          codeSent={codeSent}
          clearErrors={clearErrors}
          disabled={busy}
          isRequesting={isRequesting}
          onRequestCode={onRequestCode}
          onEmailChange={() => {
            clearErrors("root");
            setCodeSent(false);
            setNotice("");
          }}
        />
      </AccountCard>
    </form>
  );
}
