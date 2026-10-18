// The red lid's header (design markup: <header> at the top of the lid):
// logo + brand, the "Seen N" pill and the "Shortlist" pill with its count badge.

import Link from "next/link";
import { ICONS } from "@/lib/design";
import type { HeaderProps } from "./contracts";
import { Icon } from "./primitives";

/** Logo + "Talent Dex", linking home. Shared with DexStatus (loading / error frame). */
export function BrandLink({ accent, accentDark }: { accent: string; accentDark: string }) {
  return (
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
  );
}

export function Header({ accent, accentDark, seenCount, starCount, badgeRef }: HeaderProps) {
  return (
    <header style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", padding: "20px 32px" }}>
      <BrandLink accent={accent} accentDark={accentDark} />
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, height: 44, padding: "0 14px", borderRadius: 999, background: accentDark, color: "#FFFFFF", fontSize: 15, fontWeight: 700 }}>
          <Icon d={ICONS.eye} size={17} strokeWidth={2.2} />
          Seen <span className="mono" style={{ fontWeight: 600 }}>{seenCount}</span>
        </span>
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            height: 44,
            padding: "0 8px 0 16px",
            borderRadius: 999,
            background: "#FFFFFF",
            fontSize: 15,
            fontWeight: 700,
            color: "#2A1715",
            boxShadow: "0 4px 0 rgba(42,23,21,.18)",
          }}
        >
          <Icon d={ICONS.star} size={17} fill="#FFCB3D" stroke="#C98F0E" strokeWidth={1.6} linecap={null} />
          Shortlist
          <span
            ref={badgeRef}
            className="mono"
            style={{
              minWidth: 26,
              height: 26,
              borderRadius: 999,
              background: accent,
              color: "#FFFFFF",
              fontSize: 12,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {starCount}
          </span>
        </span>
      </div>
    </header>
  );
}
