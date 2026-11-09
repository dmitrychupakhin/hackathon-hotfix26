import { EnvelopeIcon } from "@heroicons/react/24/outline";
import {
  type Control,
  type ControllerRenderProps,
  type UseFormClearErrors,
  useController,
} from "react-hook-form";
import { ConfirmationCode } from "@/shared/ui/confirmation-code";
import { Input } from "@/shared/ui/input";
import { PasswordInput } from "@/shared/ui/password-input";
import type { RecoveryInput, RecoveryValues } from "./password-recovery-schema";

type Props = {
  control: Control<RecoveryInput, unknown, RecoveryValues>;
  clearErrors: UseFormClearErrors<RecoveryInput>;
  disabled: boolean;
  codeSent: boolean;
  isRequesting: boolean;
  onRequestCode: () => void;
  onEmailChange: () => void;
};

export function PasswordRecoveryFields({
  control,
  clearErrors,
  disabled,
  codeSent,
  isRequesting,
  onRequestCode,
  onEmailChange,
}: Props) {
  const email = useController({ control, name: "email" });
  const code = useController({ control, name: "code" });
  const password = useController({ control, name: "password" });
  const confirm = useController({ control, name: "confirm" });

  function update(field: ControllerRenderProps<RecoveryInput>, value: string) {
    field.onChange(value);
    clearErrors(field.name);
    if (field.name === "email") onEmailChange();
  }

  return (
    <div className="flex flex-col gap-4">
      <Input
        {...email.field}
        onValueChange={(value) => update(email.field, value)}
        disabled={disabled}
        error={email.fieldState.error?.message}
        type="email"
        autoComplete="email"
        label={<span className="text-body-sm">Электронная почта</span>}
        placeholder="Введите ваш email"
        icon={<EnvelopeIcon />}
      />
      <ConfirmationCode
        {...code.field}
        onValueChange={(value) => update(code.field, value)}
        error={code.fieldState.error?.message}
        codeSent={codeSent}
        isRequesting={isRequesting}
        disabled={disabled}
        onRequestCode={onRequestCode}
      />
      <PasswordInput
        {...password.field}
        onValueChange={(value) => update(password.field, value)}
        disabled={disabled}
        error={password.fieldState.error?.message}
        autoComplete="new-password"
        label={<span className="text-body-sm">Новый пароль</span>}
        placeholder="Придумайте новый пароль"
      />
      <PasswordInput
        {...confirm.field}
        onValueChange={(value) => update(confirm.field, value)}
        disabled={disabled}
        error={confirm.fieldState.error?.message}
        autoComplete="new-password"
        label={<span className="text-body-sm">Подтверждение пароля</span>}
        placeholder="Повторите пароль"
      />
    </div>
  );
}
