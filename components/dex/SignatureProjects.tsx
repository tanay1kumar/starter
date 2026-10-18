// Dex entry: signature projects (tile, prize, name, description, event,
// "Kept building", "{first} wrote N%").
// Ported from design/extracted/markup.html (lines 514-546). Additions: the
// project name links to its Devpost page (evidence for every claim),
// attribution caveat flags show as pills next to the share, and a builder
// with no projects gets a plain empty state instead of an empty grid.

import { ICONS } from "@/lib/design";
import type { ProfileVM } from "@/lib/viewmodel";
import { Icon } from "./primitives";

export function SignatureProjects({ p }: { p: ProfileVM }) {
  return (
    <section
      className="card-in"
      style={{ background: "#FFFFFF", borderRadius: 30, padding: "24px 28px 28px", boxShadow: "0 6px 0 rgba(42,23,21,.06)", animationDelay: ".2s" }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
        <h2 className="display" style={{ margin: 0, fontSize: 26, fontWeight: 600 }}>
          Signature projects
        </h2>
        <span style={{ fontSize: 14, fontWeight: 700, color: "#6E5A55" }}>{p.projCount}</span>
      </div>
      {p.projects.length === 0 && (
        <p
          style={{
            margin: "18px 0 0",
            padding: "28px 24px",
            textAlign: "center",
            border: "2px dashed rgba(42,23,21,.15)",
            borderRadius: 26,
            fontSize: 15,
            fontWeight: 700,
            color: "#6E5A55",
          }}
        >
          No projects to show yet. Looked in Devpost.
        </p>
      )}
      <div style={{ marginTop: 18, display: p.projects.length ? "grid" : "none", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16 }}>
        {p.projects.map((pr) => (
          <article key={pr.id} className="proj" style={{ borderRadius: 26, background: "#FFF6EE", padding: 8 }}>
            <div
              className="screen-dots"
              style={{
                height: 116,
                borderRadius: 20,
                backgroundColor: pr.bg,
                position: "relative",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {/* The tile art is decoration (the name below says it); only the prize is read out. */}
              <span aria-hidden="true" className="display" style={{ fontSize: 46, fontWeight: 700, color: pr.fg }}>
                {pr.abbr}
              </span>
              <span aria-hidden="true" className="mono" style={{ position: "absolute", left: 12, bottom: 10, fontSize: 11, fontWeight: 600, color: pr.fg }}>
                screenshot
              </span>
              {pr.hasPrize && (
                <span
                  style={{
                    position: "absolute",
                    right: 8,
                    top: 8,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    padding: "5px 10px",
                    borderRadius: 999,
                    background: "#FFCB3D",
                    fontSize: 12,
                    fontWeight: 800,
                    color: "#2A1715",
                    boxShadow: "0 2px 0 #C98F0E",
                  }}
                >
                  <Icon d={ICONS.trophy} size={13} stroke="#2A1715" strokeWidth={2.4} />
                  {pr.prize}
                </span>
              )}
            </div>
            <div style={{ padding: "12px 10px 10px", display: "flex", flexDirection: "column", gap: 8 }}>
              <h3 className="display" style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>
                <a href={pr.url} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
                  {pr.name}
                </a>
              </h3>
              <p style={{ margin: 0, fontSize: 14, fontWeight: 600, lineHeight: 1.45, color: "#4A3632" }}>{pr.desc}</p>
              <p className="mono" style={{ margin: 0, fontSize: 12, color: "#6E5A55" }}>
                {pr.event}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {pr.kept && (
                  <span style={{ fontSize: 12, fontWeight: 800, padding: "4px 10px", borderRadius: 999, background: "#DDF5EA", color: "#1A6B4A" }}>
                    Kept building
                  </span>
                )}
                <span className="mono" style={{ fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 999, background: "#FFFFFF" }}>
                  {pr.share}
                </span>
                {pr.flags.map((f, i) => (
                  <span
                    key={i + ":" + f}
                    style={{ fontSize: 12, fontWeight: 800, padding: "4px 10px", borderRadius: 999, background: "#FFF3C4", color: "#7A5D00" }}
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
