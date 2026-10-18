// Server-side dataset loading for the API routes.
// DATA_SOURCE=sample (default) reads data/sample.json; DATA_SOURCE=real reads data/builders.json.

import { promises as fs } from "node:fs";
import path from "node:path";
import type { Dataset } from "./types";

export type DataSource = "sample" | "real";

export function dataSource(): DataSource {
  return process.env.DATA_SOURCE === "real" ? "real" : "sample";
}

export async function loadDataset(source: DataSource = dataSource()): Promise<Dataset> {
  const file = source === "real" ? "builders.json" : "sample.json";
  const raw = await fs.readFile(path.join(process.cwd(), "data", file), "utf8");
  const data = JSON.parse(raw) as Dataset;
  if (data.version !== 1 || !Array.isArray(data.builders)) {
    throw new Error(`data/${file} is not a Talent Dex dataset (version 1)`);
  }
  return data;
}
