import type {
  DefinitionsFromApi,
  OverrideResultType,
} from "@reduxjs/toolkit/query";
import { generatedComparisonsApi } from "../__generated__/comparisons/rtk";

type Definitions = DefinitionsFromApi<typeof generatedComparisonsApi>;
type DownloadDefinitions = Omit<
  Definitions,
  "comparisonsAnswersRetrieve" | "comparisonsReportRetrieve"
> & {
  comparisonsAnswersRetrieve: OverrideResultType<
    Definitions["comparisonsAnswersRetrieve"],
    string
  >;
  comparisonsReportRetrieve: OverrideResultType<
    Definitions["comparisonsReportRetrieve"],
    string
  >;
};
async function downloadResponse(response: Response) {
  return response.ok
    ? URL.createObjectURL(await response.blob())
    : response.json();
}
async function releaseDownloadUrl(
  _arg: unknown,
  lifecycle: {
    cacheDataLoaded: Promise<{ data: string }>;
    cacheEntryRemoved: Promise<void>;
  },
) {
  try {
    const { data } = await lifecycle.cacheDataLoaded;
    await lifecycle.cacheEntryRemoved;
    URL.revokeObjectURL(data);
  } catch {
    // Failed downloads allocate no object URL.
  }
}
export const comparisonsApi = generatedComparisonsApi.enhanceEndpoints<
  never,
  DownloadDefinitions
>({
  endpoints: {
    comparisonsAnswersRetrieve(endpoint) {
      const query = endpoint.query;
      if (!query) throw new Error("CSV download must define a query");
      endpoint.query = (arg) => ({
        ...query(arg),
        cache: "no-store",
        responseHandler: downloadResponse,
      });
      endpoint.keepUnusedDataFor = 0;
      endpoint.onCacheEntryAdded = releaseDownloadUrl;
    },
    comparisonsReportRetrieve(endpoint) {
      const query = endpoint.query;
      if (!query) throw new Error("Report download must define a query");
      endpoint.query = (arg) => ({
        ...query(arg),
        cache: "no-store",
        responseHandler: downloadResponse,
      });
      endpoint.keepUnusedDataFor = 0;
      endpoint.onCacheEntryAdded = releaseDownloadUrl;
    },
    comparisonsList: { providesTags: [{ type: "Comparison", id: "LIST" }] },
    comparisonsRetrieve: {
      providesTags: (_result, _error, { id }) => [{ type: "Comparison", id }],
      async onQueryStarted(_arg, { getCacheEntry, dispatch, queryFulfilled }) {
        const previousStatus = getCacheEntry().data?.status;
        try {
          const { data } = await queryFulfilled;
          if (
            (data.status === "completed" || data.status === "failed") &&
            previousStatus !== data.status
          )
            dispatch(
              generatedComparisonsApi.util.invalidateTags([
                { type: "Comparison", id: "LIST" },
              ]),
            );
        } catch {
          /* Network failure must preserve the last known server state. */
        }
      },
    },
    comparisonsCreate(endpoint) {
      const query = endpoint.query;
      if (!query) throw new Error("Comparison creation must define a query");
      endpoint.query = (arg) => {
        const { questions, answers, documents, model_id } =
          arg.comparisonCreateRequest;
        const body = new FormData();
        body.append("questions", questions);
        body.append("answers", answers);
        for (const file of documents) body.append("documents", file);
        if (model_id) body.append("model_id", model_id);
        return { ...query(arg), body };
      };
      endpoint.invalidatesTags = (_result, error) =>
        error ? [] : [{ type: "Comparison", id: "LIST" }];
    },
  },
});
