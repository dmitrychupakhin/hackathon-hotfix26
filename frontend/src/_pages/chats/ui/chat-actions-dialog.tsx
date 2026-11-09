import { useEffect, useId, useRef, useState } from "react";
import {
  type ChatRead,
  useChatsDestroyMutation,
  useChatsPartialUpdateMutation,
} from "@/shared/api/chats";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { ChatFeedback } from "./chat-feedback";

export function ChatActionsDialog({
  chat,
  mode,
  onClose,
  onDelete,
}: {
  chat: ChatRead;
  mode: "rename" | "delete";
  onClose: () => void;
  onDelete: (id: string) => void;
}) {
  const [title, setTitle] = useState(chat.title || "");
  const [update, updating] = useChatsPartialUpdateMutation();
  const [destroy, deleting] = useChatsDestroyMutation();
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const busy = updating.isLoading || deleting.isLoading;
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={onClose}
      onClose={onClose}
      className="m-auto w-[min(90vw,440px)] rounded-xl bg-content-0 p-6 text-content-900 backdrop:bg-content-900/40"
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            if (mode === "rename")
              await update({
                id: chat.id,
                patchedChatRequest: { title: title.trim() },
              }).unwrap();
            else {
              await destroy({ id: chat.id }).unwrap();
              onDelete(chat.id);
            }
            onClose();
          } catch {
            /* Display the mutation error in the dialog. */
          }
        }}
      >
        <h3 id={titleId} className="text-h6">
          {mode === "rename" ? "Название чата" : "Удалить чат?"}
        </h3>
        {mode === "rename" ? (
          <Input
            label="Название"
            value={title}
            onValueChange={setTitle}
            required
            maxLength={200}
          />
        ) : (
          <p>Переписка и файлы этого чата будут удалены.</p>
        )}
        <ChatFeedback error={updating.error || deleting.error} />
        <div className="flex flex-wrap justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={onClose}
          >
            Отмена
          </Button>
          <Button
            type="submit"
            disabled={busy || (mode === "rename" && !title.trim())}
          >
            {mode === "rename" ? "Сохранить" : "Удалить"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
