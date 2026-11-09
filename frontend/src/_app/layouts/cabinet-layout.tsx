"use client";

import {
  ChatBubbleBottomCenterTextIcon,
  CpuChipIcon,
  PresentationChartLineIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import logo from "@/shared/assets/img/landing/logo.svg";
import { AccountMenu } from "@/widgets/account-menu";

const workspace = [
  ["Чаты", ChatBubbleBottomCenterTextIcon],
  ["Инструкции для ИИ", CpuChipIcon],
  ["Сравнения", PresentationChartLineIcon],
] as const;

export function CabinetLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isChats = pathname === "/chats";
  const isComparisons = pathname === "/comparisons";
  const isPrompt = pathname === "/prompt";
  return (
    <div className="min-h-dvh bg-content-0 text-special-100 lg:flex">
      <aside className="border-b border-special-300 bg-dom-light p-6 lg:min-h-dvh lg:w-64 lg:shrink-0 lg:border-r lg:border-b-0">
        <Link href="/" aria-label="Главная" className="block h-11">
          <Image src={logo} width={36} height={44} alt="" className="block" />
        </Link>
        <nav
          aria-label="Личный кабинет"
          className="mt-[19px] border-t border-special-300 pt-5"
        >
          <p className="text-label-md text-content-400">АККАУНТ</p>
          <Link
            href="/profile"
            aria-current={pathname === "/profile" ? "page" : undefined}
            className={`mt-2 flex items-center gap-3 rounded-xl px-4 py-3 ${pathname === "/profile" ? "bg-accent-100" : "text-content-500"}`}
          >
            <span className="flex size-[30px] items-center justify-center">
              <UserIcon className="size-4" />
            </span>
            Профиль
          </Link>
          <p className="mt-5 text-label-md text-content-400">
            РАБОЧЕЕ ПРОСТРАНСТВО
          </p>
          {workspace.map(([label, Icon]) => (
            <Link
              key={label}
              href={
                label === "Чаты"
                  ? "/chats"
                  : label === "Инструкции для ИИ"
                    ? "/prompt"
                    : "/comparisons"
              }
              aria-current={
                (
                  label === "Чаты"
                    ? isChats
                    : label === "Инструкции для ИИ"
                      ? isPrompt
                      : isComparisons
                )
                  ? "page"
                  : undefined
              }
              className={`mt-2 flex items-center gap-3 rounded-xl px-4 py-3 ${(label === "Чаты" ? isChats : label === "Инструкции для ИИ" ? isPrompt : isComparisons) ? "bg-accent-100 text-special-100" : "text-content-500"}`}
            >
              <span className="flex size-[30px] items-center justify-center">
                <Icon className="size-5" />
              </span>
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex h-[88px] items-center border-b border-special-300 px-6 text-body-base">
          <div className="flex min-w-0 flex-wrap items-center">
            <span className="text-content-500">Личный кабинет</span>
            <span className="mx-3 text-content-200">/</span>
            <span>
              {isChats
                ? "Чаты"
                : isPrompt
                  ? "Инструкции для ИИ"
                  : isComparisons
                    ? "Сравнения"
                    : "Профиль"}
            </span>
          </div>
          <div className="ml-auto min-w-0 pl-4">
            <AccountMenu />
          </div>
        </header>
        <main className={isChats ? "" : "px-4 py-10 sm:px-8 xl:px-16"}>
          {children}
        </main>
      </div>
    </div>
  );
}
