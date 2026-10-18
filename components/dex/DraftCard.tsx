// Dex entry: "Say hi to {first}" outreach draft with a copy button.
// Ported from design/extracted/markup.html (lines 360-377).

import type { ProfileVM } from "@/lib/viewmodel";
import { Icon } from "./primitives";

interface DraftCardProps {
  p: ProfileVM;
  accent: string;
  copyLabel: string;
  copyIcon: string;
  onCopy: () => void;
}

export function DraftCard({ p, accent, copyLabel, copyIcon, onCopy }: DraftCardProps) {
  return (
    <section
      className="card-in"
      aria-label="Outreach draft"
      style={{ background: "#FFFFFF", borderRadius: 30, padding: "24px 28px", boxShadow: "0 6px 0 " + accent }}
    >
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 className="display" style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>
            Say hi to {p.first}
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: 14, fontWeight: 600, color: "#6E5A55" }}>
            Drafted from their Devpost projects. Fill in the bracketed bits.
          </p>
        </div>
        <button
          type="button"
          className="press press-w"
          onClick={onCopy}
          style={{
            height: 44,
            padding: "0 18px",
            borderRadius: 999,
            border: 0,
            background: "#FFF6EE",
            font: "inherit",
            fontSize: 15,
            fontWeight: 800,
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            boxShadow: "0 4px 0 rgba(42,23,21,.12)",
          }}
        >
          <Icon d={copyIcon} size={16} strokeWidth={2.3} />
          {copyLabel}
        </button>
      </div>
      <div style={{ marginTop: 16, padding: "18px 20px", background: "#FFF6EE", borderRadius: 20, fontSize: 16, fontWeight: 600, lineHeight: 1.6 }}>
        <p className="mono" style={{ margin: "0 0 12px", fontSize: 13, color: "#6E5A55" }}>
          Subject: {p.draftSubject}
        </p>
        <p style={{ margin: 0, whiteSpace: "pre-line" }}>{p.draftBody}</p>
      </div>
    </section>
  );
}
