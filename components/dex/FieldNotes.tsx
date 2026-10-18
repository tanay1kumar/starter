// Dex entry: field notes (school, program, graduating, last active), profile
// links and the identity verify line.
// Ported from design/extracted/markup.html (lines 494-511). Additions from the
// brief: a missing fact reads "Not listed" plus where we looked, and a link that
// is not on the builder's own Devpost profile reads "Not linked on Devpost".

import { Fragment, type CSSProperties } from "react";
import { ICONS } from "@/lib/design";
import type { ProfileVM } from "@/lib/viewmodel";
import { Icon } from "./primitives";

const pill: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  height: 40,
  padding: "0 14px",
  borderRadius: 999,
  background: "#FFF6EE",
  fontSize: 14,
  fontWeight: 700,
  textDecoration: "none",
};

export function FieldNotes({ p }: { p: ProfileVM }) {
  return (
    <section
      className="card-in"
      style={{
        flex: "1 1 280px",
        maxWidth: 400,
        minWidth: 0,
        background: "#FFFFFF",
        borderRadius: 30,
        padding: "24px 26px",
        boxShadow: "0 6px 0 rgba(42,23,21,.06)",
        animationDelay: ".15s",
      }}
    >
      <h2 className="display" style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>
        Field notes
      </h2>
      <dl style={{ margin: "14px 0 0", display: "grid", gridTemplateColumns: "auto 1fr", gap: "12px 16px", fontSize: 15 }}>
        {p.notes.map((n) => (
          <Fragment key={n.label}>
            <dt style={{ fontWeight: 700, color: "#6E5A55" }}>{n.label}</dt>
            {n.missing ? (
              <dd style={{ margin: 0, textAlign: "right", fontWeight: 700, color: "#6E5A55" }}>
                {n.value}
                <span style={{ display: "block", marginTop: 2, fontSize: 12.5, fontWeight: 600 }}>{n.hint}</span>
              </dd>
            ) : (
              <dd style={{ margin: 0, textAlign: "right", fontWeight: 700 }}>{n.value}</dd>
            )}
          </Fragment>
        ))}
      </dl>
      <div style={{ marginTop: 16, display: "flex", flexWrap: "wrap", gap: 8 }}>
        {p.links.map((l) =>
          l.href ? (
            <a key={l.label} href={l.href} target="_blank" rel="noreferrer" className="pill-link" style={pill}>
              {l.label}
              <Icon d={ICONS.external} size={13} strokeWidth={2.4} />
            </a>
          ) : (
            <span key={l.label} style={{ ...pill, color: "#6E5A55" }}>
              {l.label}: Not linked on Devpost
            </span>
          ),
        )}
      </div>
      <p
        style={{
          margin: "14px 0 0",
          display: "flex",
          gap: 8,
          alignItems: "flex-start",
          padding: "12px 14px",
          borderRadius: 16,
          background: "#DDF5EA",
          color: "#1A6B4A",
          fontSize: 14,
          fontWeight: 700,
          lineHeight: 1.4,
        }}
      >
        <svg
          aria-hidden="true"
          width="17"
          height="17"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2.4}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ flex: "none", marginTop: 1 }}
        >
          <path d={ICONS.shield} />
          <path d={ICONS.shieldCheck} />
        </svg>
        {p.verify}
      </p>
    </section>
  );
}
