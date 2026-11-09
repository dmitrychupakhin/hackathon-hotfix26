import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { parseCitations, previewLink } from "../model/citations";

export function ChatCitations({
  chatId,
  value,
  onPreview,
}: {
  chatId: string;
  value: unknown;
  onPreview: (selection: PreviewSelection) => void;
}) {
  const citations = parseCitations(value);
  if (!citations.length) return null;
  return (
    <section
      className="mt-2 flex flex-wrap gap-x-3 gap-y-1 whitespace-normal text-body-sm"
      aria-label="Источники ответа"
    >
      {citations.map((citation) => (
        <a
          key={citation.id}
          href={previewLink(
            { chatId, fileId: citation.file_id, citation },
            "http://local.invalid",
          ).replace("http://local.invalid/", "")}
          className="break-words text-accent-600 underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-accent-500"
          onClick={(event) => {
            event.preventDefault();
            onPreview({ chatId, fileId: citation.file_id, citation });
          }}
        >
          {citation.file_name}[«{citation.quote}»]
        </a>
      ))}
    </section>
  );
}
