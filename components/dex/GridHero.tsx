// Grid mode, inside the red lid (design markup: <sc-if value="{{gridMode}}"> in the lid):
// "New scan", the headline, removable filter chips, sort, rerun, and the scan progress panel.

import Link from "next/link";
import type { CSSProperties } from "react";
import { ICONS } from "@/lib/design";
import { plural } from "@/lib/format";
import type { SortKey } from "@/lib/scoring";
import type { GridHeroProps } from "./contracts";
import { Icon } from "./primitives";

// Shared with DexStatus so the loading / error frame lines up with the real grid.
export const LID_INNER: CSSProperties = { position: "relative", maxWidth: 1240, margin: "0 auto", padding: "0 24px 40px", boxSizing: "border-box" };
export const HEADLINE: CSSProperties = { margin: 0, fontSize: "clamp(36px, 4.5vw, 52px)", lineHeight: 1.05, fontWeight: 700, color: "#FFFFFF" };
export const SCAN_PANEL: CSSProperties = {
  position: "relative",
  overflow: "hidden",
  marginTop: 26,
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "14px 24px",
  padding: "14px 18px",
  background: "#FFF6EE",
  borderRadius: 24,
  boxShadow: "inset 0 4px 0 rgba(42,23,21,.08)",
};
export const SCAN_STATUS: CSSProperties = { position: "relative", display: "flex", alignItems: "center", gap: 10, fontSize: 15, fontWeight: 700, minHeight: 30 };

export function NewScanLink() {
  return (
    <Link href="/" style={{ display: "inline-flex", alignItems: "center", gap: 6, minHeight: 44, fontSize: 15, fontWeight: 700, color: "#FFFFFF", textDecoration: "none" }}>
      <Icon d={ICONS.back} size={17} strokeWidth={2.4} />
      New scan
    </Link>
  );
}

const WHITE_SHADOW = "0 4px 0 rgba(42,23,21,.18)";

export function GridHero({ vm, accent, onRemoveFilter, onRestoreFilters, onSort, onRerun }: GridHeroProps) {
  return (
    <div style={LID_INNER}>
      <NewScanLink />
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 20, marginTop: 2 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0, flex: "1 1 480px" }}>
          <h1 className="display" style={HEADLINE}>
            {vm.headline}
          </h1>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
            {vm.filters.map((f) => (
              <span
                key={f.id}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  height: 38,
                  padding: "0 4px 0 13px",
                  borderRadius: 999,
                  fontSize: 15,
                  fontWeight: 700,
                  boxSizing: "border-box",
                  boxShadow: "0 3px 0 rgba(42,23,21,.18)",
                  ...f.style,
                }}
              >
                <Icon d={f.icon} size={16} strokeWidth={2.2} />
                {f.label}
                <button
                  type="button"
                  aria-label={f.removeLabel}
                  onClick={() => onRemoveFilter(f.id)}
                  style={{
                    width: 30,
                    height: 30,
                    borderRadius: "50%",
                    border: 0,
                    background: "transparent",
                    color: "inherit",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                  }}
                >
                  <Icon d={ICONS.close} size={13} strokeWidth={2.8} linejoin={null} />
                </button>
              </span>
            ))}
            {vm.anyRemoved && (
              <button
                type="button"
                className="press"
                onClick={onRestoreFilters}
                style={{
                  height: 38,
                  padding: "0 15px",
                  borderRadius: 999,
                  border: "2px dashed rgba(255,255,255,.7)",
                  background: "transparent",
                  font: "inherit",
                  fontSize: 15,
                  fontWeight: 700,
                  color: "#FFFFFF",
                }}
              >
                Restore filters
              </button>
            )}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label htmlFor="sort" style={{ fontSize: 15, fontWeight: 700, color: "#FFFFFF" }}>
            Sort by
          </label>
          <select
            id="sort"
            value={vm.sort}
            onChange={(e) => onSort(e.target.value as SortKey)}
            style={{
              height: 44,
              padding: "0 14px",
              borderRadius: 999,
              border: 0,
              background: "#FFFFFF",
              font: "inherit",
              fontSize: 15,
              fontWeight: 700,
              color: "#2A1715",
              cursor: "pointer",
              boxShadow: WHITE_SHADOW,
            }}
          >
            <option value="match">Best match</option>
            <option value="wins">Most wins</option>
            <option value="hacks">Most hackathons</option>
          </select>
          <button
            type="button"
            className="press press-w"
            onClick={onRerun}
            aria-label="Run the scan again"
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: 0,
              background: "#FFFFFF",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#2A1715",
              boxShadow: WHITE_SHADOW,
            }}
          >
            <Icon d={ICONS.rerun} size={19} strokeWidth={2.4} />
          </button>
        </div>
      </div>

      <div style={SCAN_PANEL}>
        {vm.scanning && <span className="sweep" aria-hidden="true" />}
        <div aria-live="polite" style={SCAN_STATUS}>
          {vm.scanning && (
            <>
              <span className="pulse" style={{ width: 11, height: 11, borderRadius: "50%", background: accent }} />
              <span>{vm.phase}</span>
              <span className="mono" style={{ color: "#6E5A55", fontWeight: 600 }}>
                {vm.scanned} / {vm.total}
              </span>
            </>
          )}
          {vm.done && (
            <>
              <span style={{ width: 26, height: 26, borderRadius: "50%", background: "#DDF5EA", display: "inline-flex", alignItems: "center", justifyContent: "center" }}>
                <Icon d={ICONS.check} size={15} stroke="#1A6B4A" strokeWidth={3.2} />
              </span>
              <span>
                Scan complete! {vm.total} {plural(vm.total, "project")} checked.
              </span>
            </>
          )}
        </div>
        <div aria-hidden="true" style={{ position: "relative", flex: "1 1 260px", maxWidth: 460, height: 16, borderRadius: 999, background: "#F1E2D4", overflow: "hidden" }}>
          <div className="stripes" style={{ height: "100%", width: vm.progress, backgroundColor: "#FFCB3D", borderRadius: 999, transition: "width .15s linear" }} />
        </div>
      </div>
    </div>
  );
}
