import type { SerializedError } from "@reduxjs/toolkit";
import type { FetchBaseQueryError } from "@reduxjs/toolkit/query";
import type {
  ChatsFilesListApiResponse,
  ChatsListApiResponse,
  ChatsMessagesListApiResponse,
} from "../__generated__/chats/rtk";
import { chatsApi } from "./chats-api";

function pageError(
  error: FetchBaseQueryError | SerializedError | undefined,
): FetchBaseQueryError {
  if (error && "status" in error) return error;
  return {
    status: "CUSTOM_ERROR",
    error: "Не удалось загрузить данные. Попробуйте снова.",
  };
}

// Delegate transport to generated operations; keep accumulated pages in RTK Query.
export const paginatedChatsApi = chatsApi.injectEndpoints({
  endpoints: (build) => ({
    chatHistory: build.infiniteQuery<ChatsListApiResponse, void, number>({
      infiniteQueryOptions: {
        initialPageParam: 1,
        getNextPageParam: (last, _pages, page) =>
          last.next ? page + 1 : undefined,
      },
      async queryFn({ pageParam }, { dispatch }) {
        const request = dispatch(
          chatsApi.endpoints.chatsList.initiate(
            { page: pageParam, pageSize: 30 },
            { forceRefetch: true },
          ),
        );
        const result = await request;
        request.unsubscribe();
        return result.data && !result.error
          ? { data: result.data }
          : {
              error: pageError(result.error),
            };
      },
      providesTags: [{ type: "Chat", id: "LIST" }],
    }),
    chatMessages: build.infiniteQuery<
      ChatsMessagesListApiResponse,
      string,
      number
    >({
      infiniteQueryOptions: {
        initialPageParam: 1,
        getNextPageParam: (last, _pages, page) =>
          last.next ? page + 1 : undefined,
      },
      async queryFn({ pageParam, queryArg: chatId }, { dispatch }) {
        const request = dispatch(
          chatsApi.endpoints.chatsMessagesList.initiate(
            { chatId, page: pageParam, pageSize: 30 },
            { forceRefetch: true },
          ),
        );
        const result = await request;
        request.unsubscribe();
        return result.data && !result.error
          ? { data: result.data }
          : {
              error: pageError(result.error),
            };
      },
      providesTags: (_r, _e, chatId) => [{ type: "ChatMessages", id: chatId }],
    }),
    chatFiles: build.infiniteQuery<ChatsFilesListApiResponse, string, number>({
      infiniteQueryOptions: {
        initialPageParam: 1,
        getNextPageParam: (last, _pages, page) =>
          last.next ? page + 1 : undefined,
      },
      async queryFn({ pageParam, queryArg: chatId }, { dispatch }) {
        const request = dispatch(
          chatsApi.endpoints.chatsFilesList.initiate(
            { chatId, page: pageParam, pageSize: 30 },
            { forceRefetch: true },
          ),
        );
        const result = await request;
        request.unsubscribe();
        return result.data && !result.error
          ? { data: result.data }
          : {
              error: pageError(result.error),
            };
      },
      providesTags: (_r, _e, chatId) => [{ type: "ChatFiles", id: chatId }],
    }),
  }),
});
export const {
  useChatHistoryInfiniteQuery,
  useChatMessagesInfiniteQuery,
  useChatFilesInfiniteQuery,
} = paginatedChatsApi;
