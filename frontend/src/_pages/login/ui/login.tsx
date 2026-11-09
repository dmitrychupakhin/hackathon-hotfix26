"use client";

import { EnvelopeIcon } from "@heroicons/react/24/outline";
import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";
import { useUsersLoginCreateMutation, zDetailList } from "@/shared/api/auth";
import { afterLoginPath } from "@/shared/auth/navigation";
import { useNotification } from "@/shared/hooks/use-notification";
import { AuthCard } from "@/shared/ui/auth-card";
import { Button } from "@/shared/ui/button";
import { Checkbox } from "@/shared/ui/checkbox";
import { Input } from "@/shared/ui/input";
import { PasswordInput } from "@/shared/ui/password-input";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";
import { loginSchema } from "./login-schema";

type LoginInput = z.input<typeof loginSchema>;
type LoginValues = z.output<typeof loginSchema>;

export function LoginPage() {
  const { showNotification } = useNotification();
  const router = useRouter();
  const [login] = useUsersLoginCreateMutation();
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput, unknown, LoginValues>({
    resolver: zodResolver(loginSchema, {
      error: (issue) => {
        if (issue.path?.[0] === "email") return "Введите корректный email";
        if (issue.path?.[0] === "password") return "Введите пароль";
      },
    }),
    defaultValues: { email: "", password: "", remember_me: false },
  });

  async function onSubmit(values: LoginValues) {
    try {
      await login({
        loginRequest: {
          email: values.email,
          password: values.password,
          remember_me: values.remember_me,
        },
      }).unwrap();
      showNotification({ message: "Вы вошли в аккаунт" });
      router.replace(
        afterLoginPath(window.location.search, window.location.hash),
      );
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: [],
        schema: zDetailList,
        fallback: "Не удалось войти. Проверьте данные и попробуйте ещё раз.",
      });
    }
  }

  return (
    <form
      className="w-full max-w-[480px]"
      noValidate
      onSubmit={handleSubmit(onSubmit)}
    >
      <AuthCard
        title="Войдите в свой аккаунт"
        description="Введите учетные данные для продолжения"
        footer={
          <>
            {errors.root?.message && (
              <p role="alert" className="text-error-600">
                {errors.root.message}
              </p>
            )}
            <Button type="submit" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Вход..." : "Войти"}
            </Button>
            <p>
              Нет аккаунта?{" "}
              <Link
                href="/register"
                className="text-accent-500 hover:underline"
              >
                Зарегистрироваться
              </Link>
            </p>
          </>
        }
      >
        <Controller
          name="email"
          control={control}
          render={({ field }) => (
            <Input
              {...field}
              onValueChange={field.onChange}
              error={errors.email?.message}
              type="email"
              autoComplete="username"
              label={<span className="text-body-sm">Почта</span>}
              placeholder="Введите ваш email"
              icon={<EnvelopeIcon />}
            />
          )}
        />
        <Controller
          name="password"
          control={control}
          render={({ field }) => (
            <PasswordInput
              {...field}
              onValueChange={field.onChange}
              error={errors.password?.message}
              autoComplete="current-password"
              label={<span className="text-body-sm">Пароль</span>}
              placeholder="Введите ваш пароль"
            />
          )}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Controller
            name="remember_me"
            control={control}
            render={({ field }) => (
              <Checkbox
                name={field.name}
                checked={field.value}
                onCheckedChange={field.onChange}
                onBlur={field.onBlur}
                ref={field.ref}
                label="Запомнить меня"
              />
            )}
          />
          <Link
            href="/password-recovery"
            className="text-accent-500 hover:underline"
          >
            Забыли пароль?
          </Link>
        </div>
      </AuthCard>
    </form>
  );
}
