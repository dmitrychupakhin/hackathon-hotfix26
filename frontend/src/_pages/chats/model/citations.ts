import type {
  ChatCitation,
  DocumentPreview,
  PreviewSelection,
} from "@/shared/api/chats/document-preview-api";

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
export function parseCitations(value: unknown): ChatCitation[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((c) => {
    if (
      !record(c) ||
      typeof c.id !== "string" ||
      typeof c.file_id !== "string" ||
      typeof c.file_name !== "string" ||
      typeof c.quote !== "string" ||
      !c.quote ||
      !Number.isSafeInteger(c.start) ||
      !Number.isSafeInteger(c.end) ||
      Number(c.start) < 0 ||
      Number(c.end) <= Number(c.start) ||
      typeof c.text_sha256 !== "string" ||
      !/^[a-f0-9]{64}$/i.test(c.text_sha256) ||
      typeof c.version !== "string"
    )
      return [];
    return [
      {
        ...c,
        locations: Array.isArray(c.locations) ? c.locations.filter(record) : [],
      } as ChatCitation,
    ];
  });
}

/** AI offsets count Unicode code points; DOM string offsets count UTF-16 units. Never guess repeated quotes. */
export function citationRange(
  preview: Pick<DocumentPreview, "text" | "text_sha256" | "version">,
  citation?: ChatCitation,
) {
  if (
    !citation ||
    citation.text_sha256 !== preview.text_sha256 ||
    citation.version !== preview.version
  )
    return;
  const points = Array.from(preview.text);
  if (
    citation.start < 0 ||
    citation.end > points.length ||
    points.slice(citation.start, citation.end).join("") !== citation.quote
  )
    return;
  return {
    start: points.slice(0, citation.start).join("").length,
    end: points.slice(0, citation.end).join("").length,
  };
}
export function citationPage(citation?: ChatCitation) {
  return (
    citation?.locations.find(
      (location) =>
        Number.isSafeInteger(location.page) && Number(location.page) > 0,
    )?.page ?? 1
  );
}
export function previewLink(selection: PreviewSelection, origin: string) {
  const url = new URL(origin);
  const params = new URLSearchParams({
    chat: selection.chatId,
    file: selection.fileId,
  });
  const c = selection.citation;
  if (c) {
    params.set("citation", c.id);
    params.set("name", c.file_name);
    params.set("start", String(c.start));
    params.set("end", String(c.end));
    params.set("sha256", c.text_sha256);
    params.set("version", c.version);
    params.set("quote", c.quote);
    const page = c.locations.find(
      (location) =>
        Number.isSafeInteger(location.page) && Number(location.page) > 0,
    )?.page;
    if (page) params.set("page", String(page));
  }
  url.hash = params.toString();
  return url.toString();
}
export function parsePreviewLink(hash: string): PreviewSelection | undefined {
  if (hash.length > 64000) return;
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const chatId = p.get("chat"),
    fileId = p.get("file");
  if (!chatId || !fileId || chatId.length > 200 || fileId.length > 200) return;
  const citation = parseCitations([
    {
      id: p.get("citation"),
      file_id: fileId,
      file_name: p.get("name"),
      quote: p.get("quote"),
      start: Number(p.get("start")),
      end: Number(p.get("end")),
      text_sha256: p.get("sha256"),
      version: p.get("version"),
      locations: p.has("page") ? [{ page: Number(p.get("page")) }] : [],
    },
  ])[0];
  return { chatId, fileId, citation };
}
