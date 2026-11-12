/**
 * One typed function per config endpoint: `GET` / `PUT /api/config`.
 *
 * The config is the live backend settings object, so an update affects the next
 * question immediately and needs no restart.
 */

import type { AppConfig, ConfigUpdate } from "../types";
import { apiRequest } from "./client";

/** `GET /api/config` — the current k, embedder and generator choice. */
export function getConfig(): Promise<AppConfig> {
  return apiRequest<AppConfig>("/config");
}

/** `PUT /api/config` — apply a partial update; omitted fields keep their value. */
export function updateConfig(update: ConfigUpdate): Promise<AppConfig> {
  return apiRequest<AppConfig>("/config", { method: "PUT", json: update });
}
