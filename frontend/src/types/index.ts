/**
 * The HTTP contract with the FastAPI backend, mirrored one-for-one from
 * `backend/src/khaleev/api/schemas.py`.
 *
 * Every response type is declared exactly once here and reused by
 * `src/api/*` and the components, so a backend field rename has a single
 * place to change on the frontend. Timestamps arrive as ISO-8601 strings
 * because JSON has no datetime; page numbers are 1-based throughout
 * (assumption A1).
 */

export type GeneratorChoice = "ollama" | "cloud";

/** One source reference: the 1-based page and a supporting quote. */
export interface Citation {
  page: number;
  quote: string;
}

/** A grounded answer: prose plus at least one page citation. */
export interface AnswerResponse {
  answer: string;
  citations: Citation[];
}

/** A natural-language question about one selected document. */
export interface AskRequest {
  question: string;
}

/** A library row: what `GET /api/documents` lists. */
export interface Document {
  id: number;
  title: string;
  page_count: number;
  /** ISO-8601 timestamp. */
  created_at: string;
}

/** A single document plus the dedupe key the list does not need. */
export interface DocumentDetail extends Document {
  content_hash: string;
}

/** One page's extracted text, rebuilt from that page's stored chunks. */
export interface PageText {
  document_id: number;
  page_number: number;
  text: string;
}

/** The outcome of a delete; the row and its files are gone when `deleted`. */
export interface DeleteDocumentResponse {
  id: number;
  deleted: boolean;
}

/** The settings the UI may read: retrieval size and model choices. */
export interface AppConfig {
  /** Top-k retrieved chunks per question. */
  k: number;
  /** Embedding model id. */
  embedder: string;
  generator: GeneratorChoice;
  ollama_base_url: string;
  ollama_model: string;
}

/** A partial config update; omitted fields keep their current value. */
export interface ConfigUpdate {
  k?: number | null;
  embedder?: string | null;
  generator?: GeneratorChoice | null;
}

/** A curated Q&A entry from a document's golden set. */
export interface GoldenEntry {
  question: string;
  expected_answer: string;
  /** 1-based page numbers the answer is expected to be drawn from. */
  expected_pages: number[];
}

/** A document's golden set, read-only from the UI (F4). */
export interface GoldenSet {
  document_id: number;
  /** Content hash of the golden-set file, used for run comparability. */
  revision: string;
  entries: GoldenEntry[];
}

/** A JSON value as stored in `eval_runs.config`. */
export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

/** The persisted config a run's metrics are only comparable within. */
export type EvalRunConfig = { [key: string]: JsonValue };

/** One persisted eval run with its aggregate metrics (F5, F6). */
export interface EvalRun {
  id: number;
  document_id: number;
  /** ISO-8601 timestamp. */
  created_at: string;
  /** Top-k used by the run; hit rate is comparable only at the same k. */
  k: number;
  embedder_id: string;
  scorer_id: string;
  hit_rate: number;
  faithfulness: number;
  /** Golden-set revision plus scorer version and the run's settings. */
  config: EvalRunConfig;
}

/** One golden entry's result inside an eval run. */
export interface EvalRunEntry {
  golden_index: number;
  hit: boolean;
  answer: string;
  claims: number;
  supported_claims: number;
  faithfulness: number;
}

/** A single run read back with its per-entry results. */
export interface EvalRunDetail extends EvalRun {
  entries: EvalRunEntry[];
}

/**
 * A history row. `comparable` is computed by the backend from the persisted
 * config only; `flagged` is its inverse, surfaced for the dashboard (AC10).
 */
export interface EvalRunSummary extends EvalRun {
  comparable: boolean;
  flagged: boolean;
}
