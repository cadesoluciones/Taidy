import { apiGet } from "./client";

export interface PipelineActivity {
  name: string;
  type: string;
  depends_on: Array<{ activity: string; conditions: string[] }>;
}

export interface PipelineDependencies {
  activities: PipelineActivity[];
}

/** Real, synchronous call to Microsoft Fabric on every invocation -- never
 * polled, only fetched when the user picks a pipeline on PipelinesPage. */
export function fetchPipelineDependencies(name: string): Promise<PipelineDependencies> {
  return apiGet<PipelineDependencies>(`/pipelines/${encodeURIComponent(name)}/dependencies`);
}
