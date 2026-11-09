import { PlusIcon } from "@heroicons/react/20/solid";
import { useState } from "react";
import type { ChatRead } from "@/shared/api/chats";
import {
  useChatHistoryInfiniteQuery,
  useChatsCreateMutation,
} from "@/shared/api/chats";
import { Button } from "@/shared/ui/button";
import { ChatActionsDialog } from "./chat-actions-dialog";
import { ChatFeedback, ChatLoadMore } from "./chat-feedback";
import { ChatHistoryItem } from "./chat-history-item";
export function ChatHistory({
  selected,
  onSelect,
  running,
  onDelete,
}: {
  selected?: string;
  onSelect: (id: string) => void;
  running: string[];
  onDelete: (id: string) => void;
}) {
  const [action, setAction] = useState<{
    chat: ChatRead;
    mode: "rename" | "delete";
  }>();
  const query = useChatHistoryInfiniteQuery();
  const [create, creation] = useChatsCreateMutation();
  return (
    <aside
      aria-label="История обсуждений"
      className="flex min-h-0 shrink-0 flex-col gap-5 px-5 pt-7 pb-6 xl:w-72 xl:overflow-y-auto"
    >
      <h1 className="text-h6">Обсуждения</h1>
      <Button
        icon={<PlusIcon />}
        iconPosition="right"
        disabled={creation.isLoading}
        onClick={async () => {
          try {
            const chat = await create({
              chatRequest: { title: "Новый чат" },
            }).unwrap();

            onSelect(chat.id);
          } catch {
            /* Shown below. */
          }
        }}
      >
        Новый чат
      </Button>
      <ChatFeedback error={creation.error} />
      <p className="text-[11px] leading-4 font-semibold text-content-500">
        НЕДАВНИЕ
      </p>
      <ChatFeedback
        loading={query.isLoading}
        error={query.error}
        retry={() => query.refetch()}
      />
      {!query.error &&
        query.currentData?.pages.flatMap((page) => page.results).length ===
          0 && (
          <p className="text-sm text-content-500">
            Создайте первое обсуждение.
          </p>
        )}
      <div className="flex flex-col">
        {query.currentData?.pages
          .flatMap((page) => page.results)
          .map((chat) => (
            <ChatHistoryItem
              key={chat.id}
              name={chat.title || "Без названия"}
              active={selected === chat.id}
              running={running.includes(chat.id)}
              onSelect={() => onSelect(chat.id)}
              onRename={() => setAction({ chat, mode: "rename" })}
              onDelete={() => setAction({ chat, mode: "delete" })}
            />
          ))}
      </div>
      <ChatLoadMore
        hasNext={query.hasNextPage}
        busy={query.isFetching}
        onLoad={() => void query.fetchNextPage()}
      />
      {action && (
        <ChatActionsDialog
          key={`${action.chat.id}-${action.mode}`}
          chat={action.chat}
          mode={action.mode}
          onClose={() => setAction(undefined)}
          onDelete={onDelete}
        />
      )}
    </aside>
  );
}
