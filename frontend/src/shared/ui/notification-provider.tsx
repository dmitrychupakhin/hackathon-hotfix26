"use client";

import { Toast } from "@base-ui/react/toast";
import type { ReactNode } from "react";
import type {
  NotificationData,
  NotificationPosition,
} from "@/shared/hooks/use-notification";
import { cn } from "@/shared/utils/cn";
import { Notification } from "./notification";

const positions: Record<NotificationPosition, string> = {
  "top-left": "top-4 left-4",
  "top-center": "top-4 left-1/2 -translate-x-1/2",
  "top-right": "top-4 right-4",
  "bottom-left": "bottom-4 left-4",
  "bottom-center": "bottom-4 left-1/2 -translate-x-1/2",
  "bottom-right": "bottom-4 right-4",
};

function NotificationViewport() {
  const { toasts, close } = Toast.useToastManager<NotificationData>();

  return (
    <Toast.Portal>
      <Toast.Viewport
        aria-label="Уведомления"
        className="pointer-events-none fixed top-0 left-0 size-0"
      >
        {Object.entries(positions).map(([position, className]) => (
          <div
            key={position}
            className={cn(
              "fixed flex max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-sm flex-col gap-3 overflow-y-auto",
              className,
            )}
          >
            {toasts
              .filter((toast) => toast.data?.position === position)
              .map((toast) => (
                <Toast.Root
                  key={toast.id}
                  toast={toast}
                  swipeDirection={[]}
                  className="pointer-events-auto opacity-100 outline-none transition-opacity duration-200 ease-out data-starting-style:opacity-0 data-ending-style:opacity-0 data-limited:hidden motion-reduce:transition-none focus-visible:rounded-md focus-visible:outline-2 focus-visible:outline-accent-600"
                >
                  <Notification
                    variant={toast.data?.variant}
                    className={toast.data?.className}
                    onDismiss={() => close(toast.id)}
                  >
                    <Toast.Description className="break-words">
                      {toast.description}
                    </Toast.Description>
                  </Notification>
                </Toast.Root>
              ))}
          </div>
        ))}
      </Toast.Viewport>
    </Toast.Portal>
  );
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider timeout={5000}>
      {children}
      <NotificationViewport />
    </Toast.Provider>
  );
}
