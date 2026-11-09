import type { PreviewSelection } from "@/shared/api/chats/document-preview-api";
import { parseCitations } from "../model/citations";
import { ChatCitations } from "./chat-citations";

type AnswerPart = {
  id: string;
  question: string;
  display_answer: string;
  citation_ids: string[];
};
function parts(value: unknown): AnswerPart[] {
  if (
    !value ||
    typeof value !== "object" ||
    !("parts" in value) ||
    !Array.isArray(value.parts)
  )
    return [];
  return value.parts.filter(
    (part): part is AnswerPart =>
      part !== null &&
      typeof part === "object" &&
      typeof part.id === "string" &&
      typeof part.question === "string" &&
      typeof part.display_answer === "string" &&
      Array.isArray(part.citation_ids) &&
      part.citation_ids.every((id: unknown) => typeof id === "string"),
  );
}

export function ChatAnswer({
  chatId,
  content,
  payload,
  citations,
  onPreview,
}: {
  chatId: string;
  content: string;
  payload: unknown;
  citations: unknown;
  onPreview: (selection: PreviewSelection) => void;
}) {
  const items = parts(payload);
  const sources = parseCitations(citations);
  if (!items.length)
    return (
      <>
        {content}
        <ChatCitations
          chatId={chatId}
          value={citations}
          onPreview={onPreview}
        />
      </>
    );
  return (
    <div className="flex flex-col gap-5">
      {items.map((item, index) => (
        <section key={item.id} aria-label={`Ответ на вопрос ${index + 1}`}>
          <p className="mb-1 font-medium">
            {index + 1}. {item.question}
          </p>
          <p>{item.display_answer}</p>
          <ChatCitations
            chatId={chatId}
            value={sources.filter((source) =>
              item.citation_ids.includes(source.id),
            )}
            onPreview={onPreview}
          />
        </section>
      ))}
    </div>
  );
}
