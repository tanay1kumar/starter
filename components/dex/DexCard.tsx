// One dex card in the matches grid (design markup: <article class="dex-card card-in t-{{c.type}}">),
// plus the plain skeleton card shown while builders are still being "found".

import type { CSSProperties } from "react";
import { ICONS } from "@/lib/design";
import type { CardVM } from "@/lib/viewmodel";
import type { GridSectionProps } from "./contracts";
import { AvatarArt, Burst, Icon } from "./primitives";

interface DexCardProps {
  card: CardVM;
  accent: string;
  onToggleStar: GridSectionProps["onToggleStar"];
  /** Receives the click event from the name button inside the <article> (DexApp FLIPs from the card screen). */
  onOpen: GridSectionProps["onOpen"];
}

const STAT_NUM: CSSProperties = { fontSize: 20, fontWeight: 600 };
const STAT_LABEL: CSSProperties = { fontSize: 12, fontWeight: 700, color: "#6E5A55", marginTop: 2 };
const STAT_SEP: CSSProperties = { borderLeft: "2px dotted rgba(42,23,21,.12)" };

export function DexCard({ card, accent, onToggleStar, onOpen }: DexCardProps) {
  const noRepos = card.repos === null;
  return (
    <article
      className={"dex-card card-in t-" + card.type}
      style={{ position: "relative", background: "#FFFFFF", borderRadius: 30, padding: 10, boxSizing: "border-box", display: "flex", flexDirection: "column", boxShadow: "0 6px 0 rgba(42,23,21,.07)" }}
    >
      <div
        className="card-screen screen-dots"
        style={{ height: 140, borderRadius: 22, backgroundColor: card.bg, position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}
      >
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, borderRadius: 22, overflow: "hidden", pointerEvents: "none" }}>
          <span className="mono" style={{ position: "absolute", left: -4, bottom: -14, fontSize: 68, fontWeight: 600, color: card.fg, opacity: 0.1, letterSpacing: "-0.03em" }}>
            {card.dexNum}
          </span>
        </div>
        <span
          className="mono"
          style={{ position: "absolute", left: 10, top: 10, display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, fontWeight: 600, borderRadius: 999, padding: "4px 10px", ...card.dexStyle }}
        >
          {card.seen && <Icon d={ICONS.eye} size={13} strokeWidth={2.4} label="Seen" />}
          {card.dex}
        </span>
        {card.revealed && (
          <svg className="reveal" width="48" height="48" viewBox="0 0 48 48" role="img" aria-label={card.scoreLabel} style={{ position: "absolute", right: 8, top: 8 }}>
            <circle cx="24" cy="24" r="22" fill="#FFFFFF" />
            <circle cx="24" cy="24" r="17" fill="none" stroke="#F3E6DA" strokeWidth="4.5" />
            <circle cx="24" cy="24" r="17" fill="none" stroke={accent} strokeWidth="4.5" strokeLinecap="round" strokeDasharray={card.dash} transform="rotate(-90 24 24)" />
            <text x="24" y="28.5" textAnchor="middle" className="svg-mono" fontSize="12.5" fontWeight="600" fill="#2A1715">
              {card.score}
            </text>
          </svg>
        )}
        <span style={{ position: "absolute", bottom: 18, width: 64, height: 10, borderRadius: "50%", background: "rgba(42,23,21,.1)" }} />
        <span
          className={("av sprite " + card.avClass).trim()}
          style={{
            position: "relative",
            display: "block",
            width: 80,
            height: 80,
            borderRadius: "50%",
            overflow: "hidden",
            border: "5px solid #FFFFFF",
            boxSizing: "border-box",
            background: card.fg,
            marginBottom: 12,
          }}
        >
          <AvatarArt av={card.av} bg={card.bg} />
        </span>
        {card.revealed && (
          <button
            type="button"
            className="star"
            aria-label={card.starLabel}
            aria-pressed={card.starred}
            onClick={() => onToggleStar(card.id)}
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: 0,
              background: "#FFFFFF",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 3px 0 rgba(42,23,21,.1)",
            }}
          >
            <Icon d={ICONS.star} size={22} fill={card.starFill} stroke={card.starStroke} strokeWidth={1.8} linecap={null} />
            {card.bursting && <Burst />}
          </button>
        )}
      </div>

      {card.revealed ? (
        <div className="reveal" style={{ flex: 1, padding: "14px 10px 10px", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", gap: 11 }}>
          <div>
            <h2 className="display" style={{ margin: 0, fontSize: 23, fontWeight: 600, lineHeight: 1.15 }}>
              <button type="button" className="stretch-btn" onClick={(e) => onOpen(card.id, e)}>
                {card.name}
              </button>
            </h2>
            <p style={{ margin: "3px 0 0", fontSize: 14, fontWeight: 600, color: "#6E5A55" }}>{card.meta}</p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center", gap: 6 }}>
            {card.chips.map((ch) => (
              <span key={ch.label} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 13, fontWeight: 700, padding: "5px 12px", borderRadius: 999, ...ch.style }}>
                <Icon d={ch.icon} size={13} strokeWidth={2.3} />
                {ch.label}
              </span>
            ))}
          </div>
          <div style={{ width: "100%", display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", background: "#FFF6EE", borderRadius: 18, padding: "10px 0" }}>
            <div>
              <div className="mono" style={STAT_NUM}>
                {card.hacks}
              </div>
              <div style={STAT_LABEL}>Hackathons</div>
            </div>
            <div style={STAT_SEP}>
              <div className="mono" style={STAT_NUM}>
                {card.wins}
              </div>
              <div style={STAT_LABEL}>Wins</div>
            </div>
            <div style={STAT_SEP} title={noRepos ? "No GitHub linked on their Devpost profile" : undefined}>
              {/* "Not listed" sits inside the 20px line so the three cells keep the same height. */}
              <div className="mono" style={STAT_NUM}>
                {noRepos ? <span style={{ fontSize: 13, color: "#6E5A55", whiteSpace: "nowrap" }}>Not listed</span> : card.repos}
              </div>
              <div style={STAT_LABEL}>Repos</div>
            </div>
          </div>
          <p style={{ margin: "auto 0 0", fontSize: 14, fontWeight: 600, lineHeight: 1.45, color: "#4A3632" }}>{card.why}</p>
        </div>
      ) : (
        <div aria-hidden="true" style={{ flex: 1, padding: "16px 10px 10px", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
          <div className="shimmer" style={{ width: "60%", height: 22, borderRadius: 10 }} />
          <div className="shimmer" style={{ width: "75%", height: 14, borderRadius: 8 }} />
          <div style={{ display: "flex", gap: 6 }}>
            <div className="shimmer" style={{ width: 72, height: 26, borderRadius: 999 }} />
            <div className="shimmer" style={{ width: 64, height: 26, borderRadius: 999 }} />
          </div>
          <div className="shimmer" style={{ width: "100%", height: 64, borderRadius: 18 }} />
        </div>
      )}
    </article>
  );
}

/** A builder not "found" yet (design: the {{skeletons}} placeholders after the cards). */
export function SkeletonCard() {
  return (
    <div
      aria-hidden="true"
      style={{ background: "#FFFFFF", borderRadius: 30, padding: 10, boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 12, minHeight: 410, boxShadow: "0 6px 0 rgba(42,23,21,.05)" }}
    >
      <div className="shimmer" style={{ height: 140, borderRadius: 22 }} />
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, padding: "6px 10px" }}>
        <div className="shimmer" style={{ width: "60%", height: 22, borderRadius: 10 }} />
        <div className="shimmer" style={{ width: "75%", height: 14, borderRadius: 8 }} />
        <div className="shimmer" style={{ width: "100%", height: 64, borderRadius: 18 }} />
      </div>
    </div>
  );
}
