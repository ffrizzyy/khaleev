/**
 * One typed function per eval endpoint in SPEC's API surface.
 *
 * The routes land in T17; the exported shapes (`GoldenSet`, `EvalRun`,
 * `EvalRunDetail`, `EvalRunSummary`) come from the persisted data model in
 * `src/types/index.ts`, so the dashboard can be built against them without a
 * second contract.
 */

import type { EvalRun, EvalRunDetail, EvalRunSummary, GoldenSet } from "../types";
import { apiRequest } from "./client";

/** `GET /api/documents/{id}/golden` — the document's golden set, read-only. */
export function getGoldenSet(documentId: number): Promise<GoldenSet> {
  return apiRequest<GoldenSet>(`/documents/${documentId}/golden`);
}

/**
 * `POST /api/documents/{id}/evals` — start a run.
 *
 * `k` defaults to the server's configured retrieval size (5) when omitted;
 * every run records the k it actually used so hit rate stays comparable.
 */
export function startEval(documentId: number, k?: number): Promise<EvalRun> {
  return apiRequest<EvalRun>(`/documents/${documentId}/evals`, {
    method: "POST",
    json: { k },
  });
}

/** `GET /api/evals/{run_id}` — one run with its per-entry results. */
export function getEvalRun(runId: number): Promise<EvalRunDetail> {
  return apiRequest<EvalRunDetail>(`/evals/${runId}`);
}

/** `GET /api/documents/{id}/evals` — chronological run history. */
export function listEvalRuns(documentId: number): Promise<EvalRunSummary[]> {
  return apiRequest<EvalRunSummary[]>(`/documents/${documentId}/evals`);
}
