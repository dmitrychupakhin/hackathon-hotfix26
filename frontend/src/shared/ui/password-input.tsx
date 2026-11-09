"use client";

import { EyeIcon, EyeSlashIcon, KeyIcon } from "@heroicons/react/24/outline";
import { useState } from "react";
import { Input, type InputProps } from "@/shared/ui/input";

type PasswordInputProps = Omit<
  InputProps,
  "type" | "icon" | "endAdornment" | "clearable"
>;

function PasswordInput({ disabled, readOnly, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const VisibilityIcon = visible ? EyeIcon : EyeSlashIcon;

  return (
    <Input
      {...props}
      disabled={disabled}
      readOnly={readOnly}
      type={visible ? "text" : "password"}
      icon={<KeyIcon />}
      endAdornment={
        <button
          type="button"
          aria-label={visible ? "Скрыть пароль" : "Показать пароль"}
          aria-pressed={visible}
          disabled={disabled}
          onClick={() => setVisible((current) => !current)}
          className="-mr-2.5 flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-sm text-special-302 focus-visible:outline-2 focus-visible:outline-accent-600 disabled:cursor-not-allowed"
        >
          <VisibilityIcon aria-hidden="true" className="size-6" />
        </button>
      }
    />
  );
}

export { PasswordInput, type PasswordInputProps };
