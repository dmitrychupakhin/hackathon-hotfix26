import type { ReactNode } from "react";
import { Card } from "@/shared/ui/card";

type AccountCardProps = {
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
};

export function AccountCard({
  title,
  description,
  children,
  footer,
}: AccountCardProps) {
  return (
    <Card className="flex w-full max-w-[500px] flex-col gap-6 p-5 shadow-[-12px_12px_35.7px_0_#84848433] sm:gap-8 sm:p-8">
      <header className="text-center text-special-100">
        <h1 className="text-h5 font-medium sm:text-h3">{title}</h1>
        <p className="text-body-base">{description}</p>
      </header>
      {children}
      <footer className="flex flex-col gap-4 text-center text-special-100">
        {footer}
      </footer>
    </Card>
  );
}
