import { useEffect, useLayoutEffect, useRef } from "react";
import { useChatMessagesInfiniteQuery } from "@/shared/api/chats";
import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { ChatAnswer } from "./chat-answer";
import { ChatFeedback, ChatLoadMore } from "./chat-feedback";
import { ChatMessage } from "./chat-message";
export function ChatMessages({
  chatId,
  answer,
  messageId,
  onPreview,
}: {
  chatId: string;
  answer?: string;
  messageId?: string;
  onPreview: (selection: PreviewSelection) => void;
}) {
  const query = useChatMessagesInfiniteQuery(chatId);
  const scroller = useRef<HTMLDivElement>(null);
  const follow = useRef(true);
  const messages =
    query.currentData?.pages.flatMap((page) => page.results) ?? [];
  const userIndex = messages.findIndex((message) => message.id === messageId);
  const savedAnswer =
    userIndex >= 0 &&
    messages
      .slice(userIndex + 1)
      .some((message) => message.role === "assistant");
  const latest = !query.hasNextPage;
  useEffect(() => {
    if (messageId && query.hasNextPage && !query.isFetching && !query.error)
      void query.fetchNextPage();
  }, [
    messageId,
    query.hasNextPage,
    query.isFetching,
    query.error,
    query.fetchNextPage,
  ]);
  useLayoutEffect(() => {
    if (follow.current && scroller.current)
      scroller.current.scrollTop = scroller.current.scrollHeight;
  });
  return (
    <>
      <section
        ref={scroller}
        onScroll={(event) => {
          const el = event.currentTarget;
          follow.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        aria-label="Сообщения чата"
        className="flex max-h-[60dvh] min-h-64 min-w-0 flex-1 flex-col gap-6 overflow-y-auto xl:mr-3.5 xl:max-h-none xl:min-h-0"
      >
        <ChatFeedback
          loading={query.isLoading}
          error={query.error}
          retry={() => query.refetch()}
        />
        {messages.length === 0 && !query.isLoading && !query.error && (
          <p className="text-content-500">Напишите первое сообщение.</p>
        )}
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            sender={message.role}
            time={new Date(message.created_at).toLocaleTimeString("ru-RU", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          >
            {message.role === "assistant" ? (
              <ChatAnswer
                chatId={chatId}
                content={message.content}
                payload={message.answer_payload}
                citations={message.citations}
                onPreview={onPreview}
              />
            ) : (
              message.content
            )}
          </ChatMessage>
        ))}
        {answer && messageId && !savedAnswer && latest && (
          <ChatMessage sender="assistant" time="Сохранение ответа…">
            {answer}
          </ChatMessage>
        )}
      </section>
      <ChatLoadMore
        hasNext={query.hasNextPage}
        busy={query.isFetching}
        onLoad={() => {
          follow.current = false;
          void query.fetchNextPage();
        }}
      />
    </>
  );
}
