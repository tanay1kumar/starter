import { dataSource, loadDataset } from "@/lib/data";

// The cached scan's summary ({ source, scan }) for screen 0's "Scanning N projects" line.
// Reads the same dataset as /api/builders; nothing here calls Devpost or GitHub.
export async function GET() {
  const source = dataSource();
  try {
    const data = await loadDataset(source);
    return Response.json({ source, scan: data.scan });
  } catch (err) {
    const missing = (err as NodeJS.ErrnoException)?.code === "ENOENT";
    const message = missing
      ? `No ${source === "real" ? "data/builders.json" : "data/sample.json"} yet. Run the pipeline or set DATA_SOURCE=sample.`
      : "Couldn't read the scan summary.";
    // The page gets a plain line; the server log gets the reason (never the data).
    if (!missing) console.error("/api/scan: " + (err instanceof Error ? err.message : String(err)));
    return Response.json({ error: message }, { status: missing ? 404 : 500 });
  }
}
