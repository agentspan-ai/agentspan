import { queryClient } from "queryClient";
import { fetchWithContext, fetchContextNonHook } from "plugins/fetch";
import { getErrors } from "../utils/utils";
import { HasAuthHeaders } from "types/common";

const fetchContext = fetchContextNonHook();

export const fetchExecution = async ({
  authHeaders: headers,
  executionId,
}: HasAuthHeaders & { executionId: string }) => {
  const url = `agent/executions/${executionId}/full`;
  // Introspection removed — was: `/workflow/introspection/records?workflowId=${executionId}`

  try {
    const workflowExecution = await queryClient.fetchQuery(
      [fetchContext.stack, url],
      () => fetchWithContext(url, fetchContext, { headers }),
    );

    return workflowExecution;
  } catch (error) {
    const errorDetails = await getErrors(error as Response);
    return Promise.reject({ originalError: error, errorDetails });
  }
};
