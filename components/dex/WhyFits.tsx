// Dex entry: "Why {first} fits your search", one row per search criterion (0-6 rows).
// Ported from design/extracted/markup.html (lines 379-398).

import type { ProfileVM } from "@/lib/viewmodel";
import { Icon } from "./primitives";

export function WhyFits({ p }: { p: ProfileVM }) {
  return (
    <section
      className="card-in"
      style={{ background: "#FFFFFF", borderRadius: 30, padding: "24px 26px", boxShadow: "0 6px 0 rgba(42,23,21,.06)", animationDelay: ".05s" }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <h2 className="display" style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>
          Why {p.first} fits your search
        </h2>
        <span style={{ fontSize: 13.5, fontWeight: 800, padding: "6px 12px", borderRadius: 999, ...p.metStyle }}>{p.metLabel}</span>
      </div>
      {p.crits.length > 0 && (
        <ul
          style={{
            listStyle: "none",
            margin: "16px 0 0",
            padding: 0,
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
            gap: 10,
          }}
        >
          {p.crits.map((k) => (
            <li key={k.key} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: 14, borderRadius: 20, background: "#FFF6EE" }}>
              <span
                style={{
                  flex: "none",
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: k.bg,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Icon d={k.icon} size={15} stroke={k.fg} strokeWidth={3.2} label={k.status} />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 800 }}>{k.label}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#4A3632", marginTop: 2 }}>{k.note}</div>
                <div className="mono" style={{ fontSize: 11.5, fontWeight: 600, color: "#6E5A55", marginTop: 6 }}>
                  {k.src}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
