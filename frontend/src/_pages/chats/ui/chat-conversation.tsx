import type { RunStream } from "@/shared/api/chats";
import {
  useChatFilesInfiniteQuery,
  useChatsRetrieveQuery,
  useChatsRunsCancelCreateMutation,
} from "@/shared/api/chats";
import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { ChatComposer } from "./chat-composer";
import { ChatFeedback } from "./chat-feedback";
import { ChatHeader } from "./chat-header";
import { ChatMessages } from "./chat-messages";
import { ChatSteps } from "./chat-steps";
export function ChatConversation({
  chatId,
  running,
  runId,
  messageId,
  stream,
  onRun,
  onRetry,
  onPreview,
}: {
  chatId: string;
  running: boolean;
  runId?: string;
  messageId?: string;
  stream?: RunStream;
  onRun: (runId: string, messageId: string) => void;
  onRetry: () => void;
  onPreview: (selection: PreviewSelection) => void;
}) {
  const chat = useChatsRetrieveQuery({ id: chatId });
  const files = useChatFilesInfiniteQuery(chatId);
  const [cancel, cancelling] = useChatsRunsCancelCreateMutation();
  return (
    <section
      aria-label="Обсуждение"
      data-chat-id={chatId}
      className="flex min-h-[650px] min-w-0 flex-1 flex-col gap-6 border-y border-content-100 px-5 py-6 xl:min-h-0 xl:border-x xl:border-y-0 xl:px-8"
    >
      <ChatFeedback
        loading={chat.isLoading}
        error={chat.error}
        retry={() => chat.refetch()}
      />
      {chat.currentData && (
        <>
          <ChatHeader
            chat={chat.currentData}
            fileCount={files.currentData?.pages[0]?.count}
          />
          <ChatMessages
            chatId={chatId}
            answer={stream?.answer}
            messageId={messageId}
            onPreview={onPreview}
          />
          <div className="flex shrink-0 flex-col gap-3">
            <ChatSteps stream={stream} running={running} />
            <ChatFeedback
              error={stream?.error}
              retry={stream?.connection === "error" ? onRetry : undefined}
            />
            <ChatFeedback error={cancelling.error} />
            <ChatComposer
              key={chatId}
              chatId={chatId}
              modelId={chat.currentData.model_id}
              running={running}
              onRun={onRun}
              cancelling={
                cancelling.isLoading ||
                (cancelling.isSuccess && cancelling.originalArgs?.id === runId)
              }
              onCancel={
                runId
                  ? async () => {
                      try {
                        await cancel({ chatId, id: runId }).unwrap();
                      } catch {
                        /* Shown above. */
                      }
                    }
                  : undefined
              }
            />
          </div>
        </>
      )}
    </section>
  );
}
