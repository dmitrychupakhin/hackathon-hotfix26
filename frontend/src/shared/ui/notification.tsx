import {
  CheckCircleIcon,
  ExclamationCircleIcon,
  XCircleIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import type { ReactNode } from "react";
import { cn } from "@/shared/utils/cn";

type NotificationProps = {
  variant?: "success" | "warning" | "error";
  children: ReactNode;
  onDismiss?: () => void;
  className?: string;
};

const variants = {
  success: {
    icon: CheckCircleIcon,
    className: "bg-notification-ok-bg inset-ring-notification-ok",
    iconClass: "text-notification-ok",
  },
  warning: {
    icon: ExclamationCircleIcon,
    className: "bg-notification-warning-bg inset-ring-notification-warning",
    iconClass: "text-notification-warning",
  },
  error: {
    icon: XCircleIcon,
    className: "bg-notification-error-bg inset-ring-error-600",
    iconClass: "text-error-600",
  },
};

function Notification({
  variant = "success",
  children,
  onDismiss,
  className,
}: NotificationProps) {
  const { icon: Icon, className: variantClass, iconClass } = variants[variant];
  return (
    <div
      data-slot="notification"
      className={cn(
        "flex w-full min-w-0 items-start gap-3 rounded-md p-4 font-sans text-body-base text-content-900 inset-ring-1",
        variantClass,
        className,
      )}
    >
      <Icon aria-hidden="true" className={cn("size-6 shrink-0", iconClass)} />
      <div className="min-w-0 flex-1">{children}</div>
      {onDismiss && (
        <button
          type="button"
          aria-label="Закрыть уведомление"
          onClick={onDismiss}
          className={cn(
            "inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded-sm outline-none focus-visible:inset-ring-1 focus-visible:inset-ring-current",
            iconClass,
          )}
        >
          <XMarkIcon className="size-6" />
        </button>
      )}
    </div>
  );
}

export { Notification, type NotificationProps };
