import { generatedChatsApi } from "../__generated__/chats/rtk";

export const chatsApi = generatedChatsApi.enhanceEndpoints({
  endpoints: {
    chatsRunsEventsList: { keepUnusedDataFor: 0 },
    chatsList: { providesTags: [{ type: "Chat", id: "LIST" }] },
    chatsRetrieve: { providesTags: (_r, _e, { id }) => [{ type: "Chat", id }] },
    chatsCreate: {
      invalidatesTags: (_r, e) => (e ? [] : [{ type: "Chat", id: "LIST" }]),
    },
    chatsPartialUpdate: {
      invalidatesTags: (_r, e, { id }) =>
        e
          ? []
          : [
              { type: "Chat", id },
              { type: "Chat", id: "LIST" },
            ],
    },
    chatsDestroy: {
      invalidatesTags: (_r, e, { id }) =>
        e
          ? []
          : [
              { type: "Chat", id },
              { type: "Chat", id: "LIST" },
              { type: "ChatMessages", id },
              { type: "ChatFiles", id },
            ],
    },
    chatsMessagesList: {
      providesTags: (_r, _e, { chatId }) => [
        { type: "ChatMessages", id: chatId },
      ],
    },
    chatsMessagesCreate: {
      invalidatesTags: (_r, e, { chatId }) =>
        e
          ? []
          : [
              { type: "ChatMessages", id: chatId },
              { type: "Chat", id: chatId },
              { type: "Chat", id: "LIST" },
            ],
    },
    chatsFilesList: {
      providesTags: (_r, _e, { chatId }) => [{ type: "ChatFiles", id: chatId }],
    },
    chatsFilesCreate(endpoint) {
      const query = endpoint.query;
      if (!query) throw new Error("File upload query is required");
      endpoint.query = (arg) => {
        const body = new FormData();
        body.append("file", arg.chatFileRequest.file);
        return { ...query(arg), body };
      };
      endpoint.invalidatesTags = (_r, e, { chatId }) =>
        e
          ? []
          : [
              { type: "ChatFiles", id: chatId },
              { type: "Chat", id: "LIST" },
            ];
    },
    chatsFilesDestroy: {
      invalidatesTags: (_r, e, { chatId }) =>
        e
          ? []
          : [
              { type: "ChatFiles", id: chatId },
              { type: "Chat", id: "LIST" },
            ],
    },
    chatsRunsRetrieve: {
      providesTags: (_r, _e, { id }) => [{ type: "ChatRun", id }],
    },
    chatsRunsCancelCreate: {
      invalidatesTags: (_r, e, { id }) => (e ? [] : [{ type: "ChatRun", id }]),
    },
  },
});
