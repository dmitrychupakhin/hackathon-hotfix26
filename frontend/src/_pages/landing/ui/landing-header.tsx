import Image from "next/image";
import Link from "next/link";
import logo from "@/shared/assets/img/landing/logo.svg";
import { AccountMenu } from "@/widgets/account-menu";

export function LandingHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-special-300 bg-content-0">
      <div className="mx-auto grid h-19 w-[calc(100%-64px)] max-w-[1480px] grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center max-[800px]:grid-cols-[auto_minmax(0,1fr)] max-[640px]:w-[calc(100%-32px)]">
        <Link
          href="/"
          aria-label="Betelgeuse — главная"
          className="flex items-center gap-3"
        >
          <Image src={logo} width={36} height={44} alt="" />
          <span className="text-xl font-semibold tracking-tight text-content-900">
            Betelgeuse
          </span>
        </Link>
        <nav
          aria-label="Навигация"
          className="flex gap-6 text-body-base text-content-900 max-[800px]:hidden"
        >
          <a href="#about">О проекте</a>
          <a href="#faq">Частые вопросы</a>
          <a href="#footer">Контакты</a>
        </nav>
        <div className="flex min-w-0 justify-end">
          <AccountMenu />
        </div>
      </div>
    </header>
  );
}
