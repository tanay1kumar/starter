"use client";

// The page frame before builders arrive (loading) or when they fail to load (error).
// Also the Suspense fallback of app/matches/page.tsx (a server component), so it uses
// no hooks and renders the same on the server and the client.

import { ACCENT, ICONS, shade } from "@/lib/design";
import { SkeletonCard } from "./DexCard";
import { HEADLINE, LID_INNER, NewScanLink, RETRY_BUTTON, SCAN_PANEL, SCAN_STATUS } from "./GridHero";
import { CARD_GRID, GRID_SECTION } from "./GridSection";
import { BrandLink } from "./Header";
import { Icon } from "./primitives";

interface DexStatusProps {
  kind: "loading" | "error";
  message?: string;
  /** What the loading line waits for; "Loading builders" unless the builders are already in. */
  label?: string;
  onRetry?: () => void;
  /** Focus "Try again" when the error shows: it failed again after the recruiter pressed it. */
  focusRetry?: boolean;
}

const ALERT = "M12 6v8M12 18h.01";

export function DexStatus({ kind, message, label, onRetry, focusRetry }: DexStatusProps) {
  const accent = ACCENT;
  const accentDark = shade(accent, 0.24);
  const loading = kind === "loading";
  return (
    <div style={{ minHeight: "100vh", boxSizing: "border-box" }}>
      <div style={{ background: accent, borderRadius: "0 0 48px 48px", position: "relative" }}>
        <div className="lid-dots" style={{ position: "absolute", inset: 0, borderRadius: "0 0 48px 48px", pointerEvents: "none" }} />
        {/* No Seen / Shortlist pills yet; minHeight keeps the header as tall as it is with them (44px pills). */}
        <header
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
            padding: "20px 32px",
            minHeight: 84,
            boxSizing: "border-box",
          }}
        >
          <BrandLink accent={accent} accentDark={accentDark} />
        </header>

        <div style={LID_INNER}>
          <NewScanLink />
          <h1 className="display" style={{ ...HEADLINE, margin: "2px 0 0" }}>
            {loading ? "Scouting for you…" : "Something went wrong"}
          </h1>
          <div style={SCAN_PANEL}>
            {loading && <span className="sweep" aria-hidden="true" />}
            <div aria-live="polite" style={SCAN_STATUS}>
              {loading ? (
                // Shown only if loading takes a while, so a fast load goes straight to the scan.
                <span className="after-wait" style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                  <span className="pulse" style={{ width: 11, height: 11, borderRadius: "50%", background: accent }} />
                  <span>{label || "Loading builders"}</span>
                </span>
              ) : (
                <>
                  <span style={{ flex: "none", width: 26, height: 26, borderRadius: "50%", background: "#FFE1DC", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                    <Icon d={ALERT} size={15} stroke="#9E2219" strokeWidth={3.2} />
                  </span>
                  <span>{message || "Couldn't load builders. Try again."}</span>
                </>
              )}
            </div>
            {!loading && onRetry && (
              <button
                type="button"
                className="press press-w"
                // The button it replaced went away while loading, so put focus back on it.
                autoFocus={focusRetry}
                onClick={onRetry}
                style={RETRY_BUTTON}
              >
                <Icon d={ICONS.rerun} size={17} strokeWidth={2.4} />
                Try again
              </button>
            )}
          </div>
        </div>
      </div>

      {loading && (
        <section style={GRID_SECTION}>
          <div style={CARD_GRID}>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </section>
      )}
    </div>
  );
}
