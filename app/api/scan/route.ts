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
      : "Could not read the scan summary.";
    return Response.json({ error: message }, { status: missing ? 404 : 500 });
  }
}
