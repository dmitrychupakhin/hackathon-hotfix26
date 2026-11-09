"use client";

import { ContextMenu as ContextMenuPrimitive } from "@base-ui/react/context-menu";
import { Menu } from "@base-ui/react/menu";
import type { ReactElement } from "react";
import { cn } from "@/shared/utils/cn";

type ContextMenuItem = {
  id: string;
  label: string;
  icon?: ReactElement;
  iconPosition?: "left" | "right";
  variant?: "default" | "destructive";
  active?: boolean;
  disabled?: boolean;
  onSelect?: ContextMenuPrimitive.Item.Props["onClick"];
};

type ContextMenuProps = Omit<ContextMenuPrimitive.Root.Props, "children"> & {
  children: ReactElement;
  items: readonly ContextMenuItem[];
  label?: string;
  className?: string;
  triggerMode?: "context" | "click";
};

function ContextMenu({
  children,
  items,
  label = "Контекстное меню",
  className,
  triggerMode = "context",
  ...props
}: ContextMenuProps) {
  const popup = (
    <ContextMenuPrimitive.Portal>
      <ContextMenuPrimitive.Positioner
        align={triggerMode === "click" ? "end" : undefined}
        sideOffset={triggerMode === "click" ? 8 : undefined}
        className="isolate z-50 outline-none"
      >
        <ContextMenuPrimitive.Popup
          data-slot="context-menu"
          aria-label={label}
          className={cn(
            "max-h-(--available-height) min-w-context-menu max-w-(--available-width) overflow-y-auto rounded-xl bg-content-0 p-1.5 font-sans text-body-base font-normal text-special-100 shadow-context-menu outline-none inset-ring-1 inset-ring-context-menu-border",
            className,
          )}
        >
          <ContextMenuPrimitive.Group>
            {items.map((item) => {
              const icon = item.icon ? (
                <span
                  aria-hidden="true"
                  className="inline-flex size-6 shrink-0 items-center [&_svg]:size-6 [&_svg]:shrink-0"
                >
                  {item.icon}
                </span>
              ) : null;

              return (
                <ContextMenuPrimitive.Item
                  key={item.id}
                  data-slot="context-menu-item"
                  data-active={item.active || undefined}
                  disabled={item.disabled}
                  label={item.label}
                  onClick={item.onSelect}
                  className={cn(
                    "flex h-10 min-w-0 cursor-pointer items-center gap-3 rounded-md px-3 py-2 transition-interaction outline-none select-none data-highlighted:rounded-sm data-highlighted:bg-special-200 data-active:rounded-sm data-active:bg-accent-200 data-active:data-highlighted:bg-accent-200 not-data-disabled:active:rounded-sm not-data-disabled:active:bg-accent-200 data-disabled:cursor-not-allowed data-disabled:opacity-50 [&_svg]:pointer-events-none",
                    item.variant === "destructive"
                      ? "text-error-600"
                      : "text-special-100",
                  )}
                >
                  {item.iconPosition !== "right" ? icon : null}
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.iconPosition === "right" ? icon : null}
                </ContextMenuPrimitive.Item>
              );
            })}
          </ContextMenuPrimitive.Group>
        </ContextMenuPrimitive.Popup>
      </ContextMenuPrimitive.Positioner>
    </ContextMenuPrimitive.Portal>
  );
  if (triggerMode === "click") {
    return (
      <Menu.Root {...props}>
        <Menu.Trigger data-slot="context-menu-trigger" render={children} />
        {popup}
      </Menu.Root>
    );
  }
  return (
    <ContextMenuPrimitive.Root {...props}>
      <ContextMenuPrimitive.Trigger
        data-slot="context-menu-trigger"
        tabIndex={0}
        render={children}
      />
      {popup}
    </ContextMenuPrimitive.Root>
  );
}

export { ContextMenu, type ContextMenuProps, type ContextMenuItem };
