"use client";

import { Button as ButtonPrimitive } from "@base-ui/react/button";
import type { VariantProps } from "class-variance-authority";
import type { ReactElement } from "react";
import { cn } from "@/shared/utils/cn";
import { buttonVariants } from "./button-variants";

type ButtonIconProps =
  | {
      icon: ReactElement;
      iconPosition: "only";
      "aria-label": string;
      children?: never;
    }
  | {
      icon?: ReactElement;
      iconPosition?: "left" | "right";
      children?: ButtonPrimitive.Props["children"];
    };

type ButtonProps = Omit<ButtonPrimitive.Props, "children"> &
  Omit<VariantProps<typeof buttonVariants>, "iconOnly"> &
  ButtonIconProps;

function Button({
  variant = "primary",
  size = "md",
  icon,
  iconPosition = "left",
  children,
  className,
  ...props
}: ButtonProps) {
  const classes = buttonVariants({
    variant,
    size,
    iconOnly: iconPosition === "only",
  });
  const iconContent = icon ? (
    <span aria-hidden="true" className="inline-flex shrink-0 items-center">
      {icon}
    </span>
  ) : null;

  return (
    <ButtonPrimitive
      data-slot="button"
      {...props}
      className={
        typeof className === "function"
          ? (state) => cn(classes, className(state))
          : cn(classes, className)
      }
    >
      {iconPosition !== "right" ? iconContent : null}
      {iconPosition !== "only" ? children : null}
      {iconPosition === "right" ? iconContent : null}
    </ButtonPrimitive>
  );
}

export { Button, buttonVariants, type ButtonProps };
