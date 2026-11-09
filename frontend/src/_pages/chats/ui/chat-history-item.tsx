import { ChatItemMenu } from "./chat-item-menu";
export function ChatHistoryItem({
  name,
  active,
  running,
  onSelect,
  onRename,
  onDelete,
}: {
  name: string;
  active: boolean;
  running?: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`group relative flex h-[50px] shrink-0 items-center rounded-xl ${active ? "bg-accent-100" : "text-content-500"}`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        title={name}
        className="flex h-full min-w-0 flex-1 items-center gap-2 rounded-xl pr-1 pl-3 text-left text-body-base outline-none focus-visible:outline-2 focus-visible:outline-accent-600"
      >
        <span className="truncate">{name}</span>
        {running && (
          <span className="size-1.5 shrink-0 rounded-full bg-accent-600">
            <span className="sr-only">Ответ выполняется</span>
          </span>
        )}
      </button>
      <ChatItemMenu
        label={`Действия чата «${name}»`}
        items={[
          { id: "rename", label: "Переименовать", onSelect: onRename },
          {
            id: "delete",
            label: "Удалить",
            variant: "destructive",
            disabled: running,
            onSelect: onDelete,
          },
        ]}
      />
    </div>
  );
}
