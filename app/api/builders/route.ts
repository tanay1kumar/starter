import { dataSource, loadDataset } from "@/lib/data";

// Reads the cached pipeline output. Nothing here calls Devpost, GitHub,
// People Data Labs or Gemini.
export async function GET() {
  const source = dataSource();
  try {
    const data = await loadDataset(source);
    return Response.json(data);
  } catch (err) {
    const missing = (err as NodeJS.ErrnoException)?.code === "ENOENT";
    const message = missing
      ? `No ${source === "real" ? "data/builders.json" : "data/sample.json"} yet. Run the pipeline or set DATA_SOURCE=sample.`
      : "Could not read the builders data.";
    return Response.json({ error: message }, { status: missing ? 404 : 500 });
  }
}
