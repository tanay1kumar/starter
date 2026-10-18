import { dataSource } from "@/lib/data";
import { topicHits } from "@/lib/topic";

// Topic search: POST {"query": "..."} -> { hits: {builderId: {similarity, project}}, source, cachedQuery }.
// Embeddings are local (transformers.js) and ranked in Postgres + pgvector when
// DATABASE_URL is set, else over data/embeddings.json. Nothing here calls Gemini.

const MAX_CHARS = 500;

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Send JSON like {"query": "built a RAG pipeline"}.' }, { status: 400 });
  }
  const query = body && typeof body === "object" ? (body as { query?: unknown }).query : undefined;
  if (typeof query !== "string" || !query.trim()) {
    return Response.json({ error: 'Send JSON like {"query": "built a RAG pipeline"}.' }, { status: 400 });
  }
  if (query.length > MAX_CHARS) {
    return Response.json({ error: "That topic is over 500 characters." }, { status: 400 });
  }
  if (dataSource() !== "real") {
    // The sample builders have no project write-ups to compare against.
    return Response.json({ error: "Topic search needs the real data (DATA_SOURCE=real)." }, { status: 409 });
  }
  try {
    return Response.json(await topicHits(query.trim()));
  } catch (err) {
    const missing = (err as NodeJS.ErrnoException)?.code === "ENOENT";
    return Response.json(
      { error: missing ? "No data/embeddings.json yet. Run node scripts/embed.mjs." : "Couldn't run the topic search." },
      { status: missing ? 404 : 500 },
    );
  }
}
