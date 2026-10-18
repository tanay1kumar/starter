// Dex entry: the trait board with its two views, "Effort" (hexagon radar + rows)
// and "Traits" (nature + six tiles).
// Ported from design/extracted/markup.html (lines 401-492).

import { Fragment, type CSSProperties, type Ref } from "react";
import { ICONS, TYPES } from "@/lib/design";
import type { TypeKey } from "@/lib/types";
import type { ProfileVM } from "@/lib/viewmodel";
import { Icon } from "./primitives";

type TraitTab = "ev" | "iv";

interface TraitBoardProps {
  p: ProfileVM;
  accent: string;
  accentDark: string;
  tab: TraitTab;
  onTab: (tab: TraitTab) => void;
  /** The radar polygon group (pops in on prev/next). */
  radarRef: Ref<SVGGElement>;
}

export function TraitBoard({ p, accent, accentDark, tab, onTab, radarRef }: TraitBoardProps) {
  const evOn = tab === "ev";
  const ivOn = tab === "iv";
  const tabBase: CSSProperties = { height: 40, padding: "0 16px", borderRadius: 999, border: 0, font: "inherit", fontSize: 15, fontWeight: 800 };
  const tabOn: CSSProperties = { background: accent, color: "#FFFFFF", boxShadow: "0 3px 0 " + accentDark };
  const tabOff: CSSProperties = { background: "transparent", color: "#2A1715" };
  return (
    <section
      className="card-in"
      style={{
        flex: "999 1 600px",
        minWidth: 0,
        background: "#FFFFFF",
        borderRadius: 30,
        padding: "24px 28px 26px",
        boxShadow: "0 6px 0 rgba(42,23,21,.06)",
        animationDelay: ".1s",
      }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 14 }}>
        <h2 className="display" style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>
          Trait board
        </h2>
        <div role="group" aria-label="Trait view" style={{ display: "inline-flex", gap: 4, padding: 5, borderRadius: 999, background: "#FFF6EE" }}>
          <button type="button" className="press" aria-pressed={evOn} onClick={() => onTab("ev")} style={{ ...tabBase, ...(evOn ? tabOn : tabOff) }}>
            Effort
          </button>
          <button type="button" className="press" aria-pressed={ivOn} onClick={() => onTab("iv")} style={{ ...tabBase, ...(ivOn ? tabOn : tabOff) }}>
            Traits
          </button>
        </div>
      </div>
      {evOn && <EvView p={p} accent={accent} radarRef={radarRef} />}
      {ivOn && <IvView p={p} />}
    </section>
  );
}

// Axis labels around the hexagon, clockwise from the top (design lines 428-439).
// Each axis has a label and, 15px below it, the EV value.
const AXIS_TEXT: { k: TypeKey; x: number; y: number; anchor: "middle" | "start" | "end" }[] = [
  { k: "ml", x: 170, y: 18, anchor: "middle" },
  { k: "backend", x: 270, y: 89, anchor: "start" },
  { k: "frontend", x: 270, y: 205, anchor: "start" },
  { k: "design", x: 170, y: 276, anchor: "middle" },
  { k: "mobile", x: 70, y: 205, anchor: "end" },
  { k: "hardware", x: 70, y: 89, anchor: "end" },
];

function EvView({ p, accent, radarRef }: { p: ProfileVM; accent: string; radarRef: Ref<SVGGElement> }) {
  return (
    <>
      <p style={{ margin: "10px 0 0", fontSize: 15, fontWeight: 600, lineHeight: 1.5, color: "#6E5A55" }}>
        Effort points {p.first} earned from each project, capped at 510. The shape shows where the time went.
      </p>
      <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", alignItems: "center", gap: "18px 28px" }}>
        <div style={{ flex: "0 1 340px", minWidth: 250 }}>
          <svg viewBox="0 0 340 300" width="100%" role="img" aria-label={p.radarLabel}>
            <polygon
              points="170,45 260.9,97.5 260.9,202.5 170,255 79.1,202.5 79.1,97.5"
              fill="#FFF6EE"
              stroke="#EADBCD"
              strokeWidth={2}
              strokeLinejoin="round"
            />
            <polygon
              points="170,80 230.6,115 230.6,185 170,220 109.4,185 109.4,115"
              fill="#FFFFFF"
              stroke="#EADBCD"
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            <polygon
              points="170,115 200.3,132.5 200.3,167.5 170,185 139.7,167.5 139.7,132.5"
              fill="#FFF6EE"
              stroke="#EADBCD"
              strokeWidth={1.5}
              strokeLinejoin="round"
            />
            <path
              d="M170 150L170 45M170 150L260.9 97.5M170 150L260.9 202.5M170 150L170 255M170 150L79.1 202.5M170 150L79.1 97.5"
              stroke="#EADBCD"
              strokeWidth={1.5}
            />
            <g className="radar-in" ref={radarRef}>
              <polygon points={p.radar.points} fill={accent} fillOpacity={0.22} stroke={accent} strokeWidth={3.5} strokeLinejoin="round" />
              {p.radar.dots.map((d, i) => (
                <circle key={i} cx={d.x} cy={d.y} r={d.r} fill={d.fill} stroke="#FFFFFF" strokeWidth={2.5} />
              ))}
            </g>
            {AXIS_TEXT.map((a) => (
              <Fragment key={a.k}>
                <text x={a.x} y={a.y} textAnchor={a.anchor} className="svg-body" fontSize={13} fontWeight={800} fill={p.radar.f[a.k]}>
                  {TYPES[a.k].label}
                </text>
                <text x={a.x} y={a.y + 15} textAnchor={a.anchor} className="svg-mono" fontSize={12} fontWeight={600} fill="#2A1715">
                  {p.radar.v[a.k]}
                </text>
              </Fragment>
            ))}
          </svg>
        </div>
        <div style={{ flex: "1 1 260px", minWidth: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          {p.evRows.map((r) => (
            <div key={r.key} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "12px 14px", borderRadius: 18, background: r.bg }}>
              <span
                style={{
                  flex: "none",
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: "#FFFFFF",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Icon d={r.icon} size={16} stroke={r.fg} strokeWidth={2.2} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontWeight: 800, color: r.fg }}>{r.label}</span>
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {r.value}
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#4A3632", marginTop: 2 }}>From {r.src}</div>
              </div>
            </div>
          ))}
          {p.hasZeros && <p style={{ margin: "2px 0 0", fontSize: 13.5, fontWeight: 600, color: "#6E5A55" }}>{p.zeros}</p>}
        </div>
      </div>
      <div style={{ marginTop: 18, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <span className="mono" style={{ fontSize: 13.5, fontWeight: 600, color: "#4A3632" }}>
          {p.evTotal} / 510 effort points
        </span>
        <span style={{ padding: "4px 12px", borderRadius: 999, fontSize: 13, fontWeight: 800, ...p.trainedStyle }}>{p.trainedLabel}</span>
      </div>
    </>
  );
}

function IvView({ p }: { p: ProfileVM }) {
  return (
    <>
      <div
        style={{
          marginTop: 14,
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 10,
          padding: "14px 16px",
          borderRadius: 20,
          background: "#FFF6EE",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "7px 14px",
            borderRadius: 999,
            background: "#2A1715",
            color: "#FFFFFF",
            fontSize: 14,
            fontWeight: 800,
          }}
        >
          <Icon d={ICONS.bolt} size={15} stroke="#FFCB3D" strokeWidth={2.4} />
          {p.natureName} nature
        </span>
        <span style={{ fontSize: 15, fontWeight: 700 }}>{p.natureLine}</span>
      </div>
      <p style={{ margin: "12px 0 0", fontSize: 15, fontWeight: 600, lineHeight: 1.5, color: "#6E5A55" }}>
        How {p.first} ranks against the {p.ivPopulation} builders in this scan, from 0 to 31.
      </p>
      <ul
        style={{
          listStyle: "none",
          margin: "14px 0 0",
          padding: 0,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: 10,
        }}
      >
        {p.ivTiles.map((t) => (
          <li
            key={t.label}
            className="card-in"
            style={{ padding: "14px 16px", borderRadius: 20, background: "#FFF6EE", display: "flex", flexDirection: "column", gap: 6 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
              <span className="display" style={{ fontSize: 18, fontWeight: 600 }}>
                {t.label}
              </span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <span className="mono" style={{ fontSize: 17, fontWeight: 600 }}>
                  {t.value}
                </span>
                <span style={{ padding: "3px 10px", borderRadius: 999, fontSize: 12.5, fontWeight: 800, ...t.judgeStyle }}>{t.judge}</span>
              </span>
            </div>
            <span style={{ fontSize: 14, fontWeight: 600, color: "#4A3632" }}>{t.evidence}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
