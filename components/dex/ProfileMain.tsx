// Screen 2 (Dex entry), below the red lid: outreach draft, why-fits, trait
// board, field notes and signature projects.
// Ported from design/extracted/markup.html, `profileMode` <main> (lines 357-548).

import type { ProfileMainProps } from "./contracts";
import { DraftCard } from "./DraftCard";
import { FieldNotes } from "./FieldNotes";
import { SignatureProjects } from "./SignatureProjects";
import { TraitBoard } from "./TraitBoard";
import { WhyFits } from "./WhyFits";

export function ProfileMain({ p, accent, accentDark, showDraft, copyLabel, copyIcon, onCopy, tab, onTab, radarRef }: ProfileMainProps) {
  return (
    <main
      style={{ maxWidth: 1240, margin: "0 auto", padding: "32px 24px 80px", boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 24 }}
    >
      {showDraft && <DraftCard p={p} accent={accent} copyLabel={copyLabel} copyIcon={copyIcon} onCopy={onCopy} />}

      <WhyFits p={p} />

      <div style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start" }}>
        <TraitBoard p={p} accent={accent} accentDark={accentDark} tab={tab} onTab={onTab} radarRef={radarRef} />
        <FieldNotes p={p} />
      </div>

      <SignatureProjects p={p} />
    </main>
  );
}
