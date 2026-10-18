// Grid mode, below the lid (design markup: <section> after the lid): type tabs, dex cards,
// skeletons and the empty state. Additions the design does not have: "no matches" and
// "empty shortlist" states, and "Show more" for long result lists.

import type { CSSProperties } from "react";
import { plural } from "@/lib/format";
import { PAGE_SIZE } from "@/lib/viewmodel";
import type { GridSectionProps } from "./contracts";
import { DexCard, SkeletonCard } from "./DexCard";
import { Icon } from "./primitives";

// Shared with DexStatus so the loading skeletons sit where the cards will.
export const GRID_SECTION: CSSProperties = { maxWidth: 1240, margin: "0 auto", padding: "28px 24px 80px", boxSizing: "border-box" };
export const CARD_GRID: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(268px, 1fr))", gap: 22, marginTop: 22 };

const EMPTY: CSSProperties = {
  marginTop: 22,
  padding: "48px 24px",
  textAlign: "center",
  border: "2px dashed rgba(42,23,21,.15)",
  borderRadius: 30,
  fontWeight: 700,
  color: "#6E5A55",
};

const CHEVRON_DOWN = "M6 9l6 6 6-6";

export function GridSection({ vm, accent, onPickTab, onToggleStar, onOpen, onShowMore, onShowAll }: GridSectionProps) {
  // "Show more" adds one page, so the label promises at most that many.
  const nextPage = Math.min(PAGE_SIZE, vm.moreCount);
  // <main>, like the Dex entry's: the results are the page's main landmark.
  return (
    <main style={GRID_SECTION}>
      <div role="group" aria-label="Filter by type" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {vm.tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className="press"
            aria-pressed={t.pressed}
            onClick={() => onPickTab(t.key)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              height: 42,
              padding: "0 15px",
              borderRadius: 999,
              border: 0,
              font: "inherit",
              fontSize: 15,
              fontWeight: 700,
              ...t.style,
            }}
          >
            <Icon d={t.icon} size={16} stroke={t.dot} strokeWidth={2.2} />
            {t.label}
            <span className="mono" style={{ fontSize: 12, fontWeight: 600, opacity: 0.75 }}>
              {t.count}
            </span>
          </button>
        ))}
      </div>

      <div style={CARD_GRID}>
        {vm.cards.map((c) => (
          <DexCard key={c.id} card={c} accent={accent} onToggleStar={onToggleStar} onOpen={onOpen} />
        ))}
        {Array.from({ length: vm.skeletons }, (_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>

      {vm.noneVisible && <div style={EMPTY}>No builders of this type yet. Try another tab!</div>}
      {vm.noneFound && (
        <div style={EMPTY}>{vm.filters.length ? "No builders match this search yet. Try removing a filter." : "No builders in this scan yet."}</div>
      )}
      {vm.shortlistEmpty && (
        <div style={EMPTY}>
          No one on your shortlist yet.{" "}
          <button
            type="button"
            className="press press-w"
            onClick={onShowAll}
            style={{
              height: 40,
              margin: "0 0 0 6px",
              padding: "0 16px",
              verticalAlign: "middle",
              borderRadius: 999,
              border: 0,
              background: "#FFFFFF",
              font: "inherit",
              fontSize: 15,
              fontWeight: 700,
              color: "#2A1715",
              boxShadow: "0 4px 0 rgba(42,23,21,.18)",
            }}
          >
            Show all builders
          </button>
        </div>
      )}

      {vm.moreCount > 0 && (
        <div style={{ display: "flex", justifyContent: "center", marginTop: 32 }}>
          <button
            type="button"
            className="press press-w"
            data-show-more=""
            onClick={onShowMore}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              height: 44,
              padding: "0 20px 0 16px",
              borderRadius: 999,
              border: 0,
              background: "#FFFFFF",
              font: "inherit",
              fontSize: 15,
              fontWeight: 700,
              color: "#2A1715",
              boxShadow: "0 4px 0 rgba(42,23,21,.18)",
            }}
          >
            <Icon d={CHEVRON_DOWN} size={16} strokeWidth={2.6} />
            Show {nextPage} more {plural(nextPage, "builder")}
          </button>
        </div>
      )}
    </main>
  );
}
