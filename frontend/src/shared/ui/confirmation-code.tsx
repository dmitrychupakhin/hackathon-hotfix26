"use client";

import { CurrencyBangladeshiIcon } from "@heroicons/react/24/outline";
import { type ComponentProps, useEffect, useRef, useState } from "react";
import { Button } from "./button";
import { Input } from "./input";

type ConfirmationCodeProps = Omit<
  ComponentProps<typeof Input>,
  "disabled" | "label" | "icon" | "className"
> & {
  codeSent: boolean;
  isRequesting: boolean;
  disabled?: boolean;
  onRequestCode: () => void;
};

export function ConfirmationCode({
  codeSent,
  isRequesting,
  disabled = false,
  onRequestCode,
  ...props
}: ConfirmationCodeProps) {
  const busy = disabled || isRequesting;
  const cooldownUntil = useRef(0);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const coolingDown = secondsLeft > 0;

  useEffect(() => {
    if (!coolingDown) return;
    const timer = window.setInterval(() => {
      setSecondsLeft(
        Math.max(0, Math.ceil((cooldownUntil.current - Date.now()) / 1000)),
      );
    }, 250);
    return () => window.clearInterval(timer);
  }, [coolingDown]);

  function requestCode() {
    if (busy || Date.now() < cooldownUntil.current) return;
    cooldownUntil.current = Date.now() + 30_000;
    setSecondsLeft(30);
    onRequestCode();
  }
  return (
    <div className="flex flex-col gap-3 sm:grid sm:grid-cols-[minmax(0,1fr)_auto] sm:grid-rows-[auto_3rem_auto] sm:gap-x-3 sm:gap-y-0.5">
      <Input
        {...props}
        disabled={busy || !codeSent}
        autoComplete="one-time-code"
        label={<span className="text-body-sm">Код подтверждения</span>}
        placeholder="Введите код с почты"
        icon={<CurrencyBangladeshiIcon />}
        className="w-full min-w-0 sm:col-start-1 sm:row-span-3 sm:row-start-1 sm:grid sm:grid-rows-subgrid"
      />
      <Button
        type="button"
        variant={codeSent ? "secondary" : "primary"}
        disabled={busy || coolingDown}
        onClick={requestCode}
        className="w-40 shrink-0 tabular-nums sm:col-start-2 sm:row-start-2"
      >
        {coolingDown
          ? `Повторить ${secondsLeft} с`
          : isRequesting
            ? "Отправка..."
            : "Получить код"}
      </Button>
    </div>
  );
}
