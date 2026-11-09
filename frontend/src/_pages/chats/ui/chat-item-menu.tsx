import { EllipsisHorizontalIcon } from "@heroicons/react/20/solid";
import { ContextMenu, type ContextMenuItem } from "@/shared/ui/context-menu";

export function ChatItemMenu({
  label,
  items,
}: {
  label: string;
  items: ContextMenuItem[];
}) {
  return (
    <ContextMenu triggerMode="click" label={label} items={items}>
      <button
        type="button"
        aria-label={label}
        className="inline-flex size-9 shrink-0 items-center justify-center rounded-md text-content-500 outline-none hover:bg-accent-100 focus-visible:outline-2 focus-visible:outline-accent-600 [@media(hover:hover)]:opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 data-popup-open:opacity-100"
      >
        <EllipsisHorizontalIcon aria-hidden="true" className="size-5" />
      </button>
    </ContextMenu>
  );
}
