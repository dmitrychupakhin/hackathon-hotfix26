"use client";

import { Toast } from "@base-ui/react/toast";
import { useCallback } from "react";
import type { NotificationProps } from "@/shared/ui/notification";

export type NotificationPosition =
  | "top-left"
  | "top-center"
  | "top-right"
  | "bottom-left"
  | "bottom-center"
  | "bottom-right";

export type NotificationOptions = Omit<NotificationProps, "children"> & {
  message: NotificationProps["children"];
  position?: NotificationPosition;
  /** Auto-dismiss delay in milliseconds; 0 keeps the notification open. */
  duration?: number;
};

export type NotificationData = Pick<
  NotificationProps,
  "variant" | "className"
> & {
  position: NotificationPosition;
};

/** Must be used inside NotificationProvider. Returns an ID for manual dismissal. */
export function useNotification() {
  const { add, close } = Toast.useToastManager<NotificationData>();

  const showNotification = useCallback(
    ({
      message,
      variant = "success",
      position = "top-right",
      duration = 5000,
      onDismiss,
      className,
    }: NotificationOptions) =>
      add({
        description: message,
        timeout: duration,
        priority: variant === "error" ? "high" : "low",
        onClose: onDismiss,
        data: { variant, position, className },
      }),
    [add],
  );

  return { showNotification, dismissNotification: close };
}
