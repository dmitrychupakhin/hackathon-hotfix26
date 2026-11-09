import { EnvelopeIcon, KeyIcon } from "@heroicons/react/24/outline";
import Link from "next/link";
import { Button } from "@/shared/ui/button";
import { Card } from "@/shared/ui/card";

export function ProfileAccess({ email }: { email: string }) {
  return (
    <Card bordered className="flex h-fit flex-col gap-6">
      <div>
        <h2 className="text-h5 font-medium">Вход в аккаунт</h2>
        <p className="mt-2 text-body-sm text-content-500">
          Электронная почта и пароль для входа в аккаунт.
        </p>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <EnvelopeIcon className="size-6 shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-body-lg font-medium">Почта</p>
            <p className="break-all text-body-sm text-content-500">{email}</p>
          </div>
        </div>
        <Button
          variant="secondary"
          size="sm"
          render={<Link href="/change-email" />}
          nativeButton={false}
          aria-label="Изменить электронную почту"
        >
          Изменить
        </Button>
      </div>
      <div className="border-t border-special-300" />
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-3 text-body-lg font-medium">
          <KeyIcon className="size-6" />
          Пароль
        </span>
        <Button
          variant="secondary"
          size="sm"
          render={<Link href="/change-password" />}
          nativeButton={false}
          aria-label="Изменить пароль"
        >
          Изменить
        </Button>
      </div>
    </Card>
  );
}
