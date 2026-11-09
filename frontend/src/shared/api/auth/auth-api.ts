import { generatedAuthApi } from "../__generated__/auth/rtk";

export const authApi = generatedAuthApi.enhanceEndpoints({
  endpoints: {
    usersLogoutCreate: {
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
        } catch {
          return;
        }
        dispatch(generatedAuthApi.util.resetApiState());
      },
    },
    usersLoginCreate: {
      async onQueryStarted(_arg, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
        } catch {
          // Failed login must preserve the current session's cached data.
          return;
        }
        dispatch(generatedAuthApi.util.resetApiState());
      },
    },
  },
});
