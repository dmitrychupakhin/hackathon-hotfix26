import {
  ArrowUpIcon,
  ChevronDownIcon,
  StopIcon,
} from "@heroicons/react/24/solid";
import { useId, useLayoutEffect, useRef, useState } from "react";
import {
  useChatsMessagesCreateMutation,
  useChatsModelsListQuery,
  useChatsPartialUpdateMutation,
} from "@/shared/api/chats";
import { Button } from "@/shared/ui/button";
import { ContextMenu } from "@/shared/ui/context-menu";
import { Textarea } from "@/shared/ui/textarea";
import { ChatFeedback } from "./chat-feedback";

export function ChatComposer({
  chatId,
  modelId,
  running,
  onRun,
  onCancel,
  cancelling,
}: {
  chatId: string;
  modelId?: string;
  running: boolean;
  onRun: (runId: string, messageId: string) => void;
  onCancel?: () => void;
  cancelling?: boolean;
}) {
  const [text, setText] = useState("");
  const [send, sending] = useChatsMessagesCreateMutation();
  const [update, updating] = useChatsPartialUpdateMutation();
  const models = useChatsModelsListQuery();
  const input = useRef<HTMLTextAreaElement>(null);
  const hintId = useId();
  const busy = running || sending.isLoading || updating.isLoading;
  const modelName =
    models.data?.find((model) => model.id === modelId)?.name ||
    modelId ||
    "По умолчанию";
  useLayoutEffect(() => {
    const field = input.current;
    if (!field) return;
    field.style.height = "48px";
    if (text) {
      // scrollHeight includes padding, but the border-box height also needs borders.
      const borders = field.offsetHeight - field.clientHeight;
      field.style.height = `${Math.min(144, Math.max(48, field.scrollHeight + borders))}px`;
    }
  }, [text]);
  async function submit() {
    if (busy || !text.trim() || text.length > 12000) return;
    try {
      const result = await send({
        chatId,
        chatMessageRequest: { content: text.trim() },
      }).unwrap();
      setText("");
      onRun(result.run.id, result.message.id);
    } catch {
      /* Keep draft and display error. */
    }
  }
  return (
    <form
      className="flex shrink-0 flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="grid grid-cols-[minmax(0,1fr)_48px] items-end gap-3 2xl:grid-cols-[minmax(0,1fr)_203px_48px]">
        <Textarea
          ref={input}
          aria-label="Сообщение"
          aria-describedby={hintId}
          value={text}
          maxLength={12000}
          rows={1}
          placeholder="Напишите сообщение ..."
          disabled={sending.isLoading}
          className="scrollbar-dropdown col-start-1 row-start-1 h-12 min-h-12 min-w-0 resize-none overflow-y-auto py-[11px] [scrollbar-gutter:stable]"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <ContextMenu
          triggerMode="click"
          label="Выбор модели"
          items={(models.data ?? []).map((model) => ({
            id: model.id,
            label: model.name,
            active: model.id === modelId,
            onSelect: async () => {
              try {
                await update({
                  id: chatId,
                  patchedChatRequest: { model_id: model.id },
                }).unwrap();
              } catch {
                /* Shown below. */
              }
            },
          }))}
        >
          <Button
            variant="secondary"
            className="col-span-2 col-start-1 row-start-2 w-full 2xl:col-span-1 2xl:col-start-2 2xl:row-start-1"
            disabled={
              busy || models.isLoading || !!models.error || !models.data?.length
            }
            icon={<ChevronDownIcon />}
            iconPosition="right"
            aria-label={`${modelName}`}
          >
            <span className="truncate">{modelName}</span>
          </Button>
        </ContextMenu>
        <Button
          className="col-start-2 row-start-1 2xl:col-start-3"
          type={running ? "button" : "submit"}
          aria-label={
            running
              ? cancelling
                ? "Ожидание отмены"
                : "Остановить ответ"
              : "Отправить сообщение"
          }
          icon={running ? <StopIcon /> : <ArrowUpIcon />}
          iconPosition="only"
          disabled={running ? cancelling || !onCancel : busy || !text.trim()}
          onClick={running ? onCancel : undefined}
        />
      </div>
      <p id={hintId} className="sr-only">
        Enter — отправить. Shift+Enter — новая строка. До 12000 символов.
      </p>
      <ChatFeedback error={sending.error || updating.error} />
      <ChatFeedback error={models.error} retry={() => models.refetch()} />
    </form>
  );
}
