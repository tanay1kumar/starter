import { parseSearch } from "@/lib/parse";

// Screen 0: turns the recruiter's text into search criteria ({ criteria, source }).
// Rules only for now; milestone 4 puts a cached Gemini parse behind lib/parse.

const MAX_CHARS = 8000;

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: 'Send JSON like {"text": "ML intern in Toronto"}.' }, { status: 400 });
  }
  const text = body && typeof body === "object" ? (body as { text?: unknown }).text : undefined;
  if (typeof text !== "string") {
    return Response.json({ error: 'Send JSON like {"text": "ML intern in Toronto"}.' }, { status: 400 });
  }
  if (text.length > MAX_CHARS) {
    return Response.json({ error: "That's over 8,000 characters. Paste just the role description." }, { status: 400 });
  }
  try {
    return Response.json(await parseSearch(text));
  } catch {
    return Response.json({ error: "Couldn't read your search. Try again." }, { status: 500 });
  }
}
