"use client";

import { useUsersMeRetrieveQuery } from "@/shared/api/account";
import { ProfileAccess } from "./profile-access";
import { ProfileForm } from "./profile-form";

export function Profile() {
  const { data, isLoading, isError, refetch } = useUsersMeRetrieveQuery();
  return (
    <div className="mx-auto max-w-[1536px]">
      <header className="mb-6">
        <h1 className="text-h3 font-medium">Профиль</h1>
        <p className="mt-2 text-body-base text-content-500">
          Личные данные, контакты и настройки входа.
        </p>
      </header>
      {isLoading ? (
        <p>Загрузка профиля...</p>
      ) : isError || !data ? (
        <div role="alert">
          Не удалось загрузить профиль.{" "}
          <button type="button" className="underline" onClick={() => refetch()}>
            Повторить
          </button>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_384px]">
          <ProfileForm key={data.id} user={data} />
          <ProfileAccess email={data.email} />
        </div>
      )}
    </div>
  );
}
