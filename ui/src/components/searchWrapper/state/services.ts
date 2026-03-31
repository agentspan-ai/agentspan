/**
 * Core OSS search service fetchers.
 *
 * These fetch workflow definitions and schedulers — core OSS features.
 *
 * Enterprise search categories (users, groups, applications, webhooks,
 * integrations, prompts, user forms) are registered by enterprise plugins
 * via the plugin registry's searchProviders mechanism.
 */

import { queryClient } from "queryClient";
import { fetchWithContext, fetchContextNonHook } from "plugins/fetch";
import _uniq from "lodash/uniq";
import _isEmpty from "lodash/isEmpty";

import { SearchMachineContext } from "./types";

const fetchContext = fetchContextNonHook();

const ACCESS = "READ";

export const fetchForWorkflowDef = async ({
  authHeaders: headers,
  workflowDefinitions,
}: SearchMachineContext) => {
  if (!_isEmpty(workflowDefinitions)) {
    return workflowDefinitions;
  }

  const path = `/metadata/workflow?short=true&access=${ACCESS}`; // TODO: migrate to agent API
  try {
    const response = await queryClient.fetchQuery(
      [fetchContext.stack, path],
      () => fetchWithContext(path, fetchContext, { headers }),
    );
    return _uniq(response).sort();
  } catch {
    return Promise.reject("Error fetching agents ");
  }
};

export const fetchForScheduleNames = async ({
  authHeaders: headers,
  schedulers,
}: SearchMachineContext) => {
  if (!_isEmpty(schedulers)) {
    return schedulers;
  }

  const path = `/scheduler/schedules`;
  try {
    const response = await queryClient.fetchQuery(
      [fetchContext.stack, path],
      () => fetchWithContext(path, fetchContext, { headers }),
    );
    return _uniq(response.map(({ name }: any) => name)).sort();
  } catch {
    return Promise.reject("Error fetching schedules ");
  }
};
