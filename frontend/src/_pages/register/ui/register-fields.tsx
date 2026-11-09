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
import type { RegisterOutput, RegisterValues } from "./register-schema";

type Props = {
  control: Control<RegisterValues, unknown, RegisterOutput>;
  clearErrors: UseFormClearErrors<RegisterValues>;
  disabled: boolean;
  codeSent: boolean;
  isRequesting: boolean;
  onRequestCode: () => void;
  onCredentialsChange: () => void;
};

export function RegisterFields({
  control,
  clearErrors,
  disabled,
  codeSent,
  isRequesting,
  onRequestCode,
  onCredentialsChange,
}: Props) {
  const email = useController({ control, name: "email" });
  const code = useController({ control, name: "code" });
  const password = useController({ control, name: "password" });
  const confirm = useController({ control, name: "confirm" });

  function update(field: ControllerRenderProps<RegisterValues>, value: string) {
    field.onChange(value);
    clearErrors(field.name);
    if (field.name !== "code") onCredentialsChange();
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
      <PasswordInput
        {...password.field}
        onValueChange={(value) => update(password.field, value)}
        disabled={disabled}
        error={password.fieldState.error?.message}
        autoComplete="new-password"
        label={<span className="text-body-sm">Пароль</span>}
        placeholder="Придумайте пароль"
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
      <ConfirmationCode
        {...code.field}
        onValueChange={(value) => update(code.field, value)}
        error={code.fieldState.error?.message}
        codeSent={codeSent}
        isRequesting={isRequesting}
        disabled={disabled}
        onRequestCode={onRequestCode}
      />
    </div>
  );
}
