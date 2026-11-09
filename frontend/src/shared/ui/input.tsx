"use client";

import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { Field } from "@base-ui/react/field";
import { Input as InputPrimitive } from "@base-ui/react/input";
import { InformationCircleIcon } from "@heroicons/react/24/outline";
import { XMarkIcon } from "@heroicons/react/24/solid";
import { cva, type VariantProps } from "class-variance-authority";
import {
  type ReactElement,
  type ReactNode,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { cn } from "@/shared/utils/cn";

const inputVariants = cva(
  "flex w-full min-w-0 items-center gap-3 rounded-md bg-dom-light font-sans font-normal text-content-900 transition-interaction inset-ring-1 inset-ring-special-300 focus-within:bg-content-0 focus-within:inset-ring-special-302 has-[[aria-invalid=true]]:bg-dom-light has-[[aria-invalid=true]]:inset-ring-error-600 has-[[aria-invalid=true]]:focus-within:bg-dom-light has-[[aria-invalid=true]]:focus-within:inset-ring-error-600 has-[input:disabled]:cursor-not-allowed has-[input:disabled]:opacity-50",
  {
    variants: {
      size: {
        sm: "h-11 px-4 py-3 text-body-sm [&_svg]:size-5",
        md: "h-12 px-4 py-3 text-body-base [&_svg]:size-6",
      },
    },
    defaultVariants: { size: "md" },
  },
);

const inputControlClasses =
  "h-full w-full min-w-0 flex-1 border-0 bg-transparent p-0 font-sans text-[length:inherit] leading-[inherit] shadow-none outline-none placeholder:text-special-302 placeholder:opacity-100 disabled:cursor-not-allowed [&::-webkit-search-cancel-button]:appearance-none";

type InputProps = Omit<
  InputPrimitive.Props,
  | "size"
  | "value"
  | "defaultValue"
  | "onValueChange"
  | "children"
  | "render"
  | "className"
> &
  VariantProps<typeof inputVariants> & {
    value?: string;
    defaultValue?: string;
    onValueChange?: (value: string) => void;
    label?: ReactNode;
    error?: string;
    invalid?: boolean;
    icon?: ReactElement;
    endAdornment?: ReactNode;
    clearable?: boolean;
    clearLabel?: string;
    onClear?: () => void;
    className?: string;
    inputClassName?: InputPrimitive.Props["className"];
  };

function Input({
  value,
  defaultValue = "",
  onValueChange,
  label,
  error,
  invalid,
  icon,
  endAdornment,
  clearable = true,
  clearLabel = "Очистить поле",
  onClear,
  size = "md",
  id,
  name,
  form,
  disabled,
  readOnly,
  ref,
  className,
  inputClassName,
  "aria-invalid": ariaInvalid,
  "aria-describedby": describedBy,
  ...props
}: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [internalValue, setInternalValue] = useState(defaultValue);
  const currentValue = value ?? internalValue;
  const isInvalid = error
    ? true
    : (invalid ??
      (ariaInvalid === true || ariaInvalid === "true" ? true : undefined));

  useImperativeHandle(ref, () => inputRef.current as HTMLInputElement, []);

  useEffect(() => {
    if (value !== undefined) return;
    const ownerForm = inputRef.current?.form;
    if (!ownerForm || (form && ownerForm.id !== form)) return;
    function handleReset(event: Event) {
      queueMicrotask(() => {
        if (!event.defaultPrevented) setInternalValue(defaultValue);
      });
    }
    ownerForm.addEventListener("reset", handleReset);
    return () => ownerForm.removeEventListener("reset", handleReset);
  }, [value, defaultValue, form]);

  function updateValue(nextValue: string) {
    if (value === undefined) setInternalValue(nextValue);
    onValueChange?.(nextValue);
  }

  return (
    <Field.Root
      data-slot="input-field"
      name={name}
      disabled={disabled}
      invalid={isInvalid}
      className={cn("flex min-w-0 flex-col gap-0.5", className)}
    >
      {label != null ? (
        <Field.Label
          className={cn(
            "font-sans font-normal text-content-900",
            size === "sm" ? "text-body-sm" : "text-body-base",
          )}
        >
          {label}
        </Field.Label>
      ) : null}
      <div data-slot="input-surface" className={inputVariants({ size })}>
        {icon ? (
          <span
            aria-hidden="true"
            className="inline-flex shrink-0 items-center text-special-302 [&_svg]:pointer-events-none [&_svg]:shrink-0"
          >
            {icon}
          </span>
        ) : null}
        <InputPrimitive
          {...props}
          data-slot="input"
          id={inputId}
          name={name}
          form={form}
          ref={inputRef}
          value={currentValue}
          onValueChange={updateValue}
          disabled={disabled}
          readOnly={readOnly}
          aria-invalid={isInvalid ?? ariaInvalid}
          aria-describedby={
            [describedBy, error ? errorId : undefined]
              .filter(Boolean)
              .join(" ") || undefined
          }
          className={
            typeof inputClassName === "function"
              ? (state) => cn(inputControlClasses, inputClassName(state))
              : cn(inputControlClasses, inputClassName)
          }
        />
        {endAdornment}
        {clearable && !disabled && currentValue.length > 0 ? (
          <ButtonPrimitive
            type="button"
            aria-label={clearLabel}
            disabled={disabled || readOnly || !currentValue}
            className="inline-flex shrink-0 cursor-pointer items-center rounded-sm text-special-302 outline-none focus-visible:inset-ring-[1.5px] focus-visible:inset-ring-accent-600 data-disabled:cursor-default [&_svg]:pointer-events-none [&_svg]:shrink-0"
            onClick={() => {
              updateValue("");
              onClear?.();
              inputRef.current?.focus();
            }}
          >
            <XMarkIcon />
          </ButtonPrimitive>
        ) : null}
      </div>
      {error ? (
        <Field.Error
          id={errorId}
          match
          className="flex items-end gap-1 text-label-md font-medium text-error-600"
        >
          <InformationCircleIcon
            aria-hidden="true"
            className="size-3.5 shrink-0"
          />
          {error}
        </Field.Error>
      ) : null}
    </Field.Root>
  );
}

export { Input, type InputProps, inputVariants, inputControlClasses };
