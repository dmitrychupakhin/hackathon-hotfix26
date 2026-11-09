"use client";

import { ChevronDownIcon, UserCircleIcon } from "@heroicons/react/20/solid";
import {
  ArrowRightOnRectangleIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useUsersMeRetrieveQuery } from "@/shared/api/account";
import { useUsersLogoutCreateMutation } from "@/shared/api/auth";
import { useNotification } from "@/shared/hooks/use-notification";
import { buttonVariants } from "@/shared/ui/button-variants";
import { ContextMenu } from "@/shared/ui/context-menu";

export function AccountMenu() {
  const { showNotification } = useNotification();
  const pathname = usePathname();
  const router = useRouter();
  const { data, error, isLoading, refetch } = useUsersMeRetrieveQuery();
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const [logoutRequest, { isLoading: loggingOut }] =
    useUsersLogoutCreateMutation();

  async function logout() {
    try {
      await logoutRequest().unwrap();
      showNotification({ message: "Вы вышли из аккаунта" });
      router.replace("/");
      router.refresh();
    } catch {
      showNotification({
        message: "Не удалось выйти. Попробуйте ещё раз.",
        variant: "error",
      });
    }
  }

  if (isLoading)
    return (
      <output
        aria-label="Загрузка профиля"
        aria-busy="true"
        className="h-10 w-32"
      />
    );
  if (data && !error) {
    const name = [data.last_name, data.first_name]
      .filter((part) => part?.trim())
      .join(" ");
    return (
      <div className="min-w-0">
        <ContextMenu
          triggerMode="click"
          label="Меню профиля"
          items={[
            ...(pathname === "/profile"
              ? []
              : [
                  {
                    id: "profile",
                    label: "Профиль",
                    icon: <UserIcon />,
                    onSelect: () => router.push("/profile"),
                  },
                ]),
            {
              id: "logout",
              label: "Выйти",
              icon: <ArrowRightOnRectangleIcon />,
              onSelect: logout,
              disabled: loggingOut,
            },
          ]}
        >
          <button
            type="button"
            disabled={loggingOut}
            className="flex max-w-full min-w-0 cursor-pointer items-center gap-3 rounded-sm text-left text-content-900 outline-none focus-visible:outline-2 focus-visible:outline-accent-600"
          >
            {data.photo && failedPhoto !== data.photo ? (
              // The photo URL comes from the user's profile and may have any backend origin.
              // biome-ignore lint/performance/noImgElement: profile photos are served by the API.
              <img
                src={data.photo}
                alt=""
                width={34}
                height={34}
                className="size-[34px] shrink-0 rounded-full object-cover"
                onError={() => setFailedPhoto(data.photo ?? null)}
              />
            ) : (
              <UserCircleIcon
                aria-hidden="true"
                className="size-[34px] shrink-0 text-content-400"
              />
            )}
            <div className="flex min-w-0 flex-col gap-0">
              <span className="truncate text-body-base">
                {name || "Профиль"}
              </span>
              <span className="-mt-0.5 truncate text-label-sm text-content-400">
                {data.email}
              </span>
            </div>
            <ChevronDownIcon aria-hidden="true" className="size-4 shrink-0" />
          </button>
        </ContextMenu>
      </div>
    );
  }
  if (error && "status" in error && error.status === 401) {
    return (
      <div className="flex gap-3">
        <Link
          href="/register"
          className={buttonVariants({ size: "sm", variant: "secondary" })}
        >
          Регистрация
        </Link>
        <Link href="/login" className={buttonVariants({ size: "sm" })}>
          Вход
        </Link>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={() => refetch()}
      className="text-body-sm text-content-700 underline"
    >
      Повторить загрузку профиля
    </button>
  );
}
