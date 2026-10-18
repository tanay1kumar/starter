"use client";

// Screen 0, search. Not in the design file; built in its style: the red lid
// with the brand, a big white card holding the search box, example chips and
// "Start scan", then three cards on what the scan does. "Start scan" asks
// /api/parse for criteria and opens /matches with them in the URL.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type SubmitEvent } from "react";
import { Icon } from "@/components/dex/primitives";
import { encodeCriteria } from "@/lib/criteria";
import { ACCENT, ICONS, TYPES, shade } from "@/lib/design";
import { plural } from "@/lib/format";
import type { ParseResult } from "@/lib/parse";
import type { ScanSummary, TypeKey } from "@/lib/types";

const accent = ACCENT;
const accentDark = shade(ACCENT, 0.24);

const PROMPT = "Describe who you're hiring, or paste a job posting.";
const MAX_CHARS = 8000;
const TOO_LONG = "That's over 8,000 characters. Paste just the role description.";
const PARSE_FAILED = "Couldn't read your search. Try again.";
const OFFLINE = "Couldn't reach Talent Dex. Check your connection and try again.";

const ARROW = "M5 12h14M13 6l6 6-6 6";
const ALERT = "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 8v4.5M12 16h.01";
const COMMIT = "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM3 12h6M15 12h6";

const EXAMPLES: { label: string; text: string; type: TypeKey }[] = [
  {
    label: "ML intern, Toronto",
    text: "ML intern for our applied AI team. Ideally a 3rd-year student in Toronto who has won a hackathon.",
    type: "ml",
  },
  {
    label: "Hardware co-op, Hamilton",
    text: "Hardware co-op working on embedded C and sensors. Arduino or ESP32 experience. Any year, near Hamilton.",
    type: "hardware",
  },
  {
    label: "Backend new grad, Waterloo",
    text: "Backend new grad who has built real APIs and databases at hackathons, based in Waterloo.",
    type: "backend",
  },
];

const STEPS: { title: string; line: string; type: TypeKey; icon: string }[] = [
  {
    title: "Reads every project",
    line: "Devpost projects, teams, prizes and demo videos from Ontario hackathons.",
    type: "mobile",
    icon: ICONS.topic,
  },
  {
    title: "Checks who wrote the code",
    line: "Commits made during the hackathon, matched to each teammate's own GitHub.",
    type: "ml",
    icon: COMMIT,
  },
  {
    title: "Shows its work",
    line: "Every number on a Dex entry links back to where it came from.",
    type: "backend",
    icon: ICONS.shield + ICONS.shieldCheck,
  },
];

function scanLine(scan: ScanSummary): string {
  const n = scan.projectsChecked;
  const h = scan.hackathons.length;
  return "Scanning " + n + " " + plural(n, "project") + (h > 0 ? " from " + h + " " + plural(h, "hackathon") : "");
}

export default function SearchScreen() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scan, setScan] = useState<ScanSummary | null>(null);
  /** The parse in flight; also blocks a second "Start scan" while one is running. */
  const request = useRef<AbortController | null>(null);

  // The "Scanning N projects" line. Nothing shows until it loads, or if it fails.
  useEffect(() => {
    const ctrl = new AbortController();
    fetch("/api/scan", { signal: ctrl.signal })
      .then((r) => (r.ok ? (r.json() as Promise<{ scan?: ScanSummary }>) : null))
      .then((d) => {
        if (d?.scan) setScan(d.scan);
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    router.prefetch("/matches");
  }, [router]);

  // Next keeps this page mounted but hidden after "Start scan" navigates away.
  // Cleanup runs when it is hidden: stop any parse in flight and drop the busy
  // label, so Back shows the search ready to edit (the text is kept).
  useLayoutEffect(() => {
    return () => {
      request.current?.abort();
      request.current = null;
      setBusy(false);
      setError(null);
    };
  }, []);

  async function start() {
    if (request.current) return;
    const query = text.trim();
    if (!query) {
      // No search given: /matches without params runs the design's default search (DEFAULT_CRITERIA).
      router.push("/matches");
      return;
    }
    if (query.length > MAX_CHARS) {
      setError(TOO_LONG);
      return;
    }
    const ctrl = new AbortController();
    request.current = ctrl;
    setBusy(true);
    setError(null);
    let message = OFFLINE;
    try {
      const r = await fetch("/api/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: query }),
        signal: ctrl.signal,
      });
      const body = (await r.json().catch(() => null)) as (Partial<ParseResult> & { error?: string }) | null;
      if (ctrl.signal.aborted) return;
      if (r.ok && body?.criteria) {
        // Stay busy until the page is hidden by the navigation.
        router.push("/matches?" + encodeCriteria(body.criteria));
        return;
      }
      message = body?.error || PARSE_FAILED;
    } catch {
      if (ctrl.signal.aborted) return;
    }
    request.current = null;
    setBusy(false);
    setError(message);
  }

  function onSubmit(e: SubmitEvent<HTMLFormElement>) {
    e.preventDefault();
    void start();
  }

  // Cmd/Ctrl+Enter anywhere in the card starts the scan (plain Enter adds a new line).
  function onKeyDown(e: KeyboardEvent<HTMLFormElement>) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void start();
    }
  }

  return (
    <div style={{ minHeight: "100vh", boxSizing: "border-box" }}>
      <div style={{ background: accent, borderRadius: "0 0 48px 48px", position: "relative" }}>
        <div className="lid-dots" style={{ position: "absolute", inset: 0, borderRadius: "0 0 48px 48px", pointerEvents: "none" }} />
        <header style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", padding: "20px 32px" }}>
          <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 10, textDecoration: "none", color: "#FFFFFF" }}>
            <svg aria-hidden="true" width="42" height="42" viewBox="0 0 100 100" style={{ flex: "none" }}>
              <rect x="4" y="9" width="92" height="87" rx="26" fill={accentDark} />
              <rect x="4" y="4" width="92" height="87" rx="26" fill="#FFFFFF" />
              <rect x="28" y="18" width="44" height="58" rx="12" fill={accentDark} transform="translate(0 4) rotate(8 50 47)" />
              <rect x="28" y="18" width="44" height="58" rx="12" fill={accent} transform="rotate(8 50 47)" />
              <g transform="translate(50 47) rotate(8) scale(0.42) translate(-50 -49)">
                <polygon
                  points="50,18 58.82,39.86 82.34,41.49 64.27,56.64 69.98,79.51 50,67 30.02,79.51 35.73,56.64 17.66,41.49 41.18,39.86"
                  fill="#FFFFFF"
                  stroke="#FFFFFF"
                  strokeWidth="10"
                  strokeLinejoin="round"
                />
              </g>
            </svg>
            <span className="display" style={{ fontSize: 25, fontWeight: 700 }}>
              Talent Dex
            </span>
          </Link>
        </header>

        <div style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "10px 24px 40px", boxSizing: "border-box" }}>
          <div style={{ maxWidth: 880, margin: "0 auto" }}>
            <h1 className="display" style={{ margin: 0, fontSize: "clamp(36px, 4.5vw, 52px)", lineHeight: 1.05, fontWeight: 700, color: "#FFFFFF", textAlign: "center" }}>
              Who are you hiring?
            </h1>
            <p style={{ margin: "12px auto 0", maxWidth: 660, fontSize: 17, fontWeight: 700, lineHeight: 1.45, color: "rgba(255,255,255,.9)", textAlign: "center" }}>
              Describe the role in your own words. Talent Dex reads Devpost projects and the GitHub code behind them, then ranks the builders who fit.
            </p>

            <form
              role="search"
              aria-label="Find builders"
              onSubmit={onSubmit}
              onKeyDown={onKeyDown}
              style={{ marginTop: 26, background: "#FFFFFF", borderRadius: 30, padding: 18, boxSizing: "border-box", boxShadow: "0 8px 0 " + accentDark }}
            >
              <label htmlFor="hiring" className="sr-only-td">
                {PROMPT}
              </label>
              <textarea
                id="hiring"
                rows={4}
                value={text}
                placeholder={PROMPT}
                aria-describedby={error ? "hiring-error" : undefined}
                onChange={(e) => {
                  setText(e.target.value);
                  if (error) setError(null);
                }}
                className="placeholder:text-muted"
                style={{
                  display: "block",
                  width: "100%",
                  boxSizing: "border-box",
                  border: 0,
                  background: "#FFF6EE",
                  borderRadius: 22,
                  padding: "18px 20px",
                  font: "inherit",
                  fontSize: 18,
                  fontWeight: 600,
                  lineHeight: 1.5,
                  color: "#2A1715",
                  resize: "vertical",
                }}
              />

              {error && (
                <p
                  id="hiring-error"
                  role="alert"
                  style={{ margin: "12px 0 0", display: "flex", gap: 8, alignItems: "flex-start", padding: "10px 14px", borderRadius: 16, background: "#FFE1DC", color: "#9E2219", fontSize: 14, fontWeight: 700, lineHeight: 1.4 }}
                >
                  <Icon d={ALERT} size={17} strokeWidth={2.4} style={{ flex: "none", marginTop: 1 }} />
                  {error}
                </p>
              )}

              <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "12px 16px" }}>
                <div style={{ flex: "999 1 420px", minWidth: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: "#6E5A55", marginRight: 2 }}>Try one:</span>
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.label}
                      type="button"
                      className="press press-w"
                      aria-controls="hiring"
                      onClick={() => {
                        setText(ex.text);
                        setError(null);
                      }}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 7,
                        height: 38,
                        padding: "0 14px 0 12px",
                        borderRadius: 999,
                        border: 0,
                        background: "#FFF6EE",
                        font: "inherit",
                        fontSize: 15,
                        fontWeight: 700,
                        color: "#2A1715",
                        boxShadow: "0 3px 0 rgba(42,23,21,.12)",
                      }}
                    >
                      <Icon d={TYPES[ex.type].icon} size={16} stroke={TYPES[ex.type].fg} strokeWidth={2.2} />
                      {ex.label}
                    </button>
                  ))}
                </div>
                <button
                  type="submit"
                  className="press press-r display"
                  aria-busy={busy}
                  aria-keyshortcuts="Control+Enter Meta+Enter"
                  style={{
                    flex: "1 0 auto",
                    height: 52,
                    padding: "0 26px",
                    borderRadius: 999,
                    border: 0,
                    background: accent,
                    color: "#FFFFFF",
                    fontSize: 18,
                    fontWeight: 600,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8,
                    boxShadow: "0 5px 0 " + accentDark,
                  }}
                >
                  {busy ? (
                    <>
                      <span className="pulse" aria-hidden="true" style={{ width: 10, height: 10, borderRadius: "50%", background: "#FFFFFF" }} />
                      Reading your search…
                    </>
                  ) : (
                    <>
                      Start scan
                      <Icon d={ARROW} size={20} stroke="#FFFFFF" strokeWidth={2.4} />
                    </>
                  )}
                </button>
              </div>
              <span className="sr-only-td" aria-live="polite">
                {busy ? "Reading your search…" : ""}
              </span>
            </form>

            <p style={{ margin: "18px 0 0", minHeight: 20, fontSize: 14, fontWeight: 700, lineHeight: "20px", color: "rgba(255,255,255,.85)", textAlign: "center" }}>
              {scan && <span className="reveal" style={{ display: "inline-block" }}>{scanLine(scan)}</span>}
            </p>
          </div>
        </div>
      </div>

      <section aria-label="How Talent Dex works" style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 24px 80px", boxSizing: "border-box" }}>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: 22 }}>
          {STEPS.map((s, i) => (
            <li
              key={s.title}
              className="card-in"
              style={{
                display: "flex",
                gap: 14,
                alignItems: "flex-start",
                background: "#FFFFFF",
                borderRadius: 30,
                padding: "24px 26px",
                boxSizing: "border-box",
                boxShadow: "0 6px 0 rgba(42,23,21,.06)",
                animationDelay: 0.05 * (i + 1) + "s",
              }}
            >
              <span style={{ flex: "none", width: 44, height: 44, borderRadius: "50%", background: TYPES[s.type].bg, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Icon d={s.icon} size={20} stroke={TYPES[s.type].fg} strokeWidth={2.4} />
              </span>
              <div style={{ minWidth: 0 }}>
                <h2 className="display" style={{ margin: "2px 0 0", fontSize: 21, fontWeight: 600, lineHeight: 1.2 }}>
                  {s.title}
                </h2>
                <p style={{ margin: "4px 0 0", fontSize: 15, fontWeight: 600, lineHeight: 1.5, color: "#4A3632" }}>{s.line}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
