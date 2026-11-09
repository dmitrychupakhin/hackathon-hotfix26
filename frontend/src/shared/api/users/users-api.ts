import { generatedUsersApi } from "../__generated__/users/rtk";

export const usersApi = generatedUsersApi.enhanceEndpoints({
  endpoints: {
    usersRetrieve: {
      providesTags: (_result, _error, { id }) => [{ type: "User", id }],
    },
  },
});
