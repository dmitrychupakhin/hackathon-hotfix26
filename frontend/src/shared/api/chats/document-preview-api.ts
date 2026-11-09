import { chatsApi } from "./chats-api";

export type DocumentLocation = {
  page?: number;
  start?: number;
  end?: number;
  [key: string]: unknown;
};
export type ChatCitation = {
  id: string;
  file_id: string;
  file_name: string;
  quote: string;
  start: number;
  end: number;
  text_sha256: string;
  version: string;
  locations: DocumentLocation[];
  anchor_method?: "harness_evidence" | "exact_text_match";
};
export type DocumentPreview = {
  file_id: string;
  name: string;
  format: "pdf" | "docx" | "txt" | "md";
  text: string;
  text_sha256: string;
  version: string;
  locations: DocumentLocation[];
  partial: boolean;
  warnings: string[];
  content_url: string;
  offset_unit: "unicode_code_points";
};
export type PreviewSelection = {
  chatId: string;
  fileId: string;
  citation?: ChatCitation;
};

export const documentPreviewApi = chatsApi.injectEndpoints({
  endpoints: (build) => ({
    chatDocumentPreview: build.query<DocumentPreview, PreviewSelection>({
      query: ({ chatId, fileId, citation }) => ({
        url: `/api/chats/${encodeURIComponent(chatId)}/files/${encodeURIComponent(fileId)}/preview`,
        cache: "no-store",
        params: citation
          ? { text_sha256: citation.text_sha256, version: citation.version }
          : undefined,
      }),
      keepUnusedDataFor: 0,
      providesTags: (_r, _e, { chatId }) => [{ type: "ChatFiles", id: chatId }],
    }),
    chatDocumentContent: build.query<
      string,
      { chatId: string; fileId: string; textSha256: string; version: string }
    >({
      query: ({ chatId, fileId, textSha256, version }) => ({
        url: `/api/chats/${encodeURIComponent(chatId)}/files/${encodeURIComponent(fileId)}/content`,
        params: { text_sha256: textSha256, version },
        responseHandler: async (response: Response) =>
          response.ok
            ? URL.createObjectURL(await response.blob())
            : response.json(),
        cache: "no-store",
      }),
      keepUnusedDataFor: 0,
      async onCacheEntryAdded(_arg, { cacheDataLoaded, cacheEntryRemoved }) {
        try {
          const { data } = await cacheDataLoaded;
          await cacheEntryRemoved;
          URL.revokeObjectURL(data);
        } catch {
          /* No object URL is allocated for failed requests. */
        }
      },
    }),
  }),
});
export const { useChatDocumentPreviewQuery, useChatDocumentContentQuery } =
  documentPreviewApi;
