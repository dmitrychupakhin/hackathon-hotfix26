"use client";

import { CameraIcon } from "@heroicons/react/24/outline";
import { zodResolver } from "@hookform/resolvers/zod";
import Image from "next/image";
import { useRef, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import type { z } from "zod";
import {
  type MeRead,
  useUsersMePartialUpdateMutation,
  useUsersMePhotoPartialUpdateMutation,
  zPatchProfileError,
  zUpdatePhotoError,
  zUpdateRequest,
} from "@/shared/api/account";
import { useNotification } from "@/shared/hooks/use-notification";
import { Button } from "@/shared/ui/button";
import { Card } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import { applyApiFormErrors } from "@/shared/utils/apply-api-form-errors";

type ProfileValues = z.infer<typeof zUpdateRequest>;

function profileValues(user: MeRead): ProfileValues {
  return {
    first_name: user.first_name ?? "",
    last_name: user.last_name ?? "",
    middle_name: user.middle_name ?? "",
  };
}

export function ProfileForm({ user }: { user: MeRead }) {
  const { showNotification } = useNotification();
  const [editing, setEditing] = useState(false);
  const [save] = useUsersMePartialUpdateMutation();
  const [uploadPhoto, { isLoading: isUploading }] =
    useUsersMePhotoPartialUpdateMutation();
  const photoInput = useRef<HTMLInputElement>(null);
  const [photoError, setPhotoError] = useState<string>();

  async function changePhoto(file: File) {
    setPhotoError(undefined);
    try {
      await uploadPhoto({
        patchedUpdatePhotoRequest: { photo: file },
      }).unwrap();
      showNotification({ message: "Фото профиля успешно изменено" });
    } catch (error) {
      applyApiFormErrors<{ photo: string }>({
        error,
        fields: ["photo"],
        schema: zUpdatePhotoError,
        fallback: "Не удалось изменить фото профиля. Попробуйте ещё раз.",
        setError: (_name, value) => setPhotoError(value.message),
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
      });
    }
  }
  const {
    control,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ProfileValues>({
    resolver: zodResolver(zUpdateRequest, {
      error: (issue) =>
        issue.code === "too_big" ? "Не более 64 символов" : "Заполните поле",
    }),
    defaultValues: profileValues(user),
  });
  async function submit(values: ProfileValues) {
    try {
      await save({ patchedUpdateRequest: values }).unwrap();
      showNotification({ message: "Профиль успешно сохранён" });
      reset(values);
      setEditing(false);
    } catch (error) {
      applyApiFormErrors({
        onRootError: (message) =>
          showNotification({ message, variant: "error" }),
        error,
        setError,
        fields: ["first_name", "last_name", "middle_name"],
        schema: zPatchProfileError,
        fallback: "Не удалось сохранить изменения. Попробуйте ещё раз.",
      });
    }
  }
  function cancel() {
    reset(profileValues(user));
    setPhotoError(undefined);
    setEditing(false);
  }
  return (
    <Card bordered padding="none" className="overflow-hidden">
      <form onSubmit={handleSubmit(submit)} noValidate>
        <div className="flex flex-wrap items-center justify-between gap-6 bg-special-200 p-6">
          <div className="flex items-center gap-6">
            <div className="flex size-[76px] shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-content-0 bg-content-200 text-h5">
              {user.photo ? (
                <Image
                  src={user.photo}
                  alt=""
                  width={76}
                  height={76}
                  unoptimized
                  className="size-full object-cover"
                />
              ) : (
                (user.first_name?.[0] ?? "")
              )}
            </div>
            {editing ? (
              <div className="flex flex-col gap-2">
                <input
                  ref={photoInput}
                  type="file"
                  accept="image/*"
                  aria-label="Выберите фото профиля"
                  className="hidden"
                  disabled={isSubmitting || isUploading}
                  onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    event.currentTarget.value = "";
                    if (file) void changePhoto(file);
                  }}
                />
                <button
                  type="button"
                  disabled={isSubmitting || isUploading}
                  onClick={() => photoInput.current?.click()}
                  className="inline-flex cursor-pointer items-center gap-2 rounded-sm text-body-base text-accent-500 outline-none hover:text-accent-600 focus-visible:outline-2 focus-visible:outline-accent-600 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <CameraIcon aria-hidden="true" className="size-6" />
                  {isUploading ? "Загрузка..." : "Сменить фото"}
                </button>
                {photoError && (
                  <p role="alert" className="text-body-sm text-error-600">
                    {photoError}
                  </p>
                )}
              </div>
            ) : (
              <div className="text-h4">
                {user.last_name || "Профиль"}
                <br />
                {[user.first_name, user.middle_name].filter(Boolean).join(" ")}
              </div>
            )}
          </div>
          {editing ? (
            <div className="flex gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={cancel}
                disabled={isSubmitting || isUploading}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={isSubmitting || isUploading}
              >
                Сохранить
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              size="sm"
              onClick={() => {
                reset(profileValues(user));
                setEditing(true);
              }}
            >
              Изменить профиль
            </Button>
          )}
        </div>
        <section className="space-y-6 p-6">
          <div>
            <h2 className="text-h5">Личная информация</h2>
            <p className="mt-2 text-body-sm text-content-500">
              Имя, фамилия и отчество в профиле.
            </p>
          </div>
          <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
            {(
              [
                ["last_name", "Фамилия"],
                ["first_name", "Имя"],
                ["middle_name", "Отчество"],
              ] as const
            ).map(([name, label]) => (
              <Controller
                key={name}
                name={name}
                control={control}
                render={({ field }) => (
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    onValueChange={field.onChange}
                    label={label}
                    error={errors[name]?.message}
                    disabled={!editing || isSubmitting || isUploading}
                  />
                )}
              />
            ))}
          </div>
          {editing && errors.root?.message && (
            <p role="alert" className="text-error-600">
              {errors.root.message}
            </p>
          )}
        </section>
      </form>
    </Card>
  );
}
