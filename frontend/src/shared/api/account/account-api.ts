import { generatedAccountApi } from "../__generated__/account/rtk";

export const accountApi = generatedAccountApi.enhanceEndpoints({
  endpoints: {
    usersEmailConfirmCreate: {
      invalidatesTags: (_result, error) =>
        error ? [] : ["CurrentUser", "User"],
    },
    usersMePhotoPartialUpdate(endpoint) {
      const originalQuery = endpoint.query;
      if (!originalQuery) throw new Error("Photo endpoint must define a query");
      endpoint.query = (args) => {
        const request = originalQuery(args);
        const body = new FormData();
        const photo = args.patchedUpdatePhotoRequest.photo;
        if (photo) body.append("photo", photo);
        return { ...request, body };
      };
      endpoint.invalidatesTags = (_result, error) =>
        error ? [] : ["CurrentUser", "User"];
    },
    usersMeRetrieve: { providesTags: ["CurrentUser"] },
    usersMeUpdate: {
      invalidatesTags: (_result, error) =>
        error ? [] : ["CurrentUser", "User"],
    },
    usersMePartialUpdate: {
      invalidatesTags: (_result, error) =>
        error ? [] : ["CurrentUser", "User"],
    },
  },
});
