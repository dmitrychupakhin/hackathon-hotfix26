"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  useUsersRegisterConfirmCreateMutation,
  useUsersRegisterCreateMutation,
  zDetailList,
} from "@/shared/api/registration";
import { useNotification } from "@/shared/hooks/use-notification";
import { AuthCard } from "@/shared/ui/auth-card";
import { Button } from "@/shared/ui/button";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { RegisterFields } from "./register-fields";
import {
  type RegisterOutput,
  type RegisterValues,
  registerSchema,
} from "./register-schema";

const registerErrorFields = ["email", "password", "confirm", "code"] as const;

export function RegisterPage() {
  const { showNotification } = useNotification();
  const router = useRouter();
  const [requestCode, { isLoading: isRequesting }] =
    useUsersRegisterCreateMutation();
  const [confirmRegistration, { isLoading: isConfirming }] =
    useUsersRegisterConfirmCreateMutation();
  const [codeSent, setCodeSent] = useState(false);
  const [notice, setNotice] = useState("");
  const {
    control,
    handleSubmit,
    getValues,
    trigger,
    setError,
    clearErrors,
    formState: { errors },
  } = useForm<RegisterValues, unknown, RegisterOutput>({
    resolver: zodResolver(registerSchema, {
      error: (issue) => {
        if (issue.path?.[0] === "email") return "Введите корректный email";
        if (issue.path?.[0] === "password") return "Введите пароль";
        if (issue.path?.[0] === "confirm") return "Подтвердите пароль";
        if (issue.path?.[0] === "code") return "Введите код подтверждения";
      },
    }),
    defaultValues: { email: "", password: "", confirm: "", code: "" },
  });
  const busy = isRequesting || isConfirming;

  function invalidateCode() {
    setCodeSent(false);
    setNotice("");
    clearErrors("root");
  }

  async function onRequestCode() {
    clearErrors("root");
    if (!(await trigger(["email", "password", "confirm"]))) return;
    setCodeSent(false);
    setNotice("");
    const { email, password, confirm } = getValues();
    try {
      const response = await requestCode({
        registerRequest: { email: email.trim(), password, confirm },
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
        fields: registerErrorFields,
        fallback: "Не удалось получить код. Попробуйте ещё раз.",
      });
    }
  }

  async function onConfirm(values: RegisterOutput) {
    if (!codeSent || busy) return;
    clearErrors("root");
    try {
      await confirmRegistration({
        confirmRegisterRequest: { email: values.email, code: values.code },
      }).unwrap();
      showNotification({ message: "Регистрация завершена. Войдите в аккаунт" });
      router.replace("/login");
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: registerErrorFields,
        fallback: "Не удалось подтвердить регистрацию. Попробуйте ещё раз.",
      });
    }
  }

  return (
    <form
      className="w-full max-w-[480px]"
      noValidate
      onSubmit={handleSubmit(onConfirm)}
    >
      <AuthCard
        title="Создание аккаунта"
        description="Введите почту и получите проверочный код для регистрации"
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
              variant={codeSent ? "primary" : "secondary"}
              disabled={!codeSent || busy}
              className="w-full"
            >
              {isConfirming ? "Подтверждение..." : "Создать аккаунт"}
            </Button>
            <p>
              Уже есть аккаунт?{" "}
              <Link href="/login" className="text-accent-500 hover:underline">
                Войти
              </Link>
            </p>
          </>
        }
      >
        <RegisterFields
          control={control}
          codeSent={codeSent}
          clearErrors={clearErrors}
          disabled={busy}
          isRequesting={isRequesting}
          onRequestCode={onRequestCode}
          onCredentialsChange={invalidateCode}
        />
      </AuthCard>
    </form>
  );
}
