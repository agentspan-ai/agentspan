import { fetchWithContext, useFetchContext } from "plugins/fetch";
import { useQuery, UseQueryResult } from "react-query";
import { useAuthHeaders } from "utils/query";

export interface EvalCheck {
  id: string;
  check: string;
  passed: boolean;
  message?: string;
  score?: number;
  reasoning?: string;
}

export interface EvalCase {
  id: string;
  name: string;
  passed: boolean;
  error?: string;
  agentName?: string;
  model?: string;
  tags?: string[];
  prompt?: string;
  output?: string;
  checks?: EvalCheck[];
}

export interface EvalRun {
  id: string;
  agentName: string;
  timestamp: string;
  totalCases: number;
  passedCases: number;
  tags?: string[];
  createdBy?: string;
  name?: string;
  strategy?: string;
  ranBy?: string;
  dataset?: string;
  cases?: EvalCase[];
}

export interface EvalRunsPage {
  totalHits: number;
  results: EvalRun[];
}

export interface DatasetCase {
  name: string;
  prompt: string;
  assertions?: string[];
  tags?: string[];
  semanticCriteria?: string;
}

export interface Dataset {
  name: string;
  updatedAt?: string;
  pushedBy?: string;
  caseCount?: number;
  cases?: DatasetCase[];
}

export function useEvalRuns(
  start = 0,
  size = 20,
): UseQueryResult<EvalRunsPage> {
  const fetchContext = useFetchContext();
  const headers = useAuthHeaders();
  return useQuery(
    [fetchContext.stack, "eval/runs", start, size],
    () =>
      fetchWithContext(`eval/runs?start=${start}&size=${size}`, fetchContext, {
        headers,
      }),
    { keepPreviousData: true },
  );
}

export function useEvalRun(id: string): UseQueryResult<EvalRun> {
  const fetchContext = useFetchContext();
  const headers = useAuthHeaders();
  return useQuery(
    [fetchContext.stack, "eval/runs", id],
    () => fetchWithContext(`eval/runs/${id}`, fetchContext, { headers }),
    { enabled: !!id },
  );
}

export function useDatasets(): UseQueryResult<Dataset[]> {
  const fetchContext = useFetchContext();
  const headers = useAuthHeaders();
  return useQuery([fetchContext.stack, "eval/datasets"], () =>
    fetchWithContext("eval/datasets", fetchContext, { headers }),
  );
}

export function useDataset(name: string): UseQueryResult<Dataset> {
  const fetchContext = useFetchContext();
  const headers = useAuthHeaders();
  return useQuery(
    [fetchContext.stack, "eval/datasets", name],
    () =>
      fetchWithContext(`eval/datasets/${encodeURIComponent(name)}`, fetchContext, {
        headers,
      }),
    { enabled: !!name },
  );
}
