// Screen 2 (Dex entry), inside the red lid: back, prev/next and the hero card.
// Ported from design/extracted/markup.html, `profileMode` block (lines 162-242).

import { ICONS } from "@/lib/design";
import type { ProfileHeroProps } from "./contracts";
import { AvatarArt, Burst, Icon } from "./primitives";

export function ProfileHero({
  p,
  accent,
  accentDark,
  showDraft,
  draftLabel,
  onClose,
  onPrev,
  onNext,
  onToggleStar,
  onToggleDraft,
  heroRef,
  screenRef,
  headingRef,
  draftButtonRef,
}: ProfileHeroProps) {
  return (
    <div style={{ position: "relative", maxWidth: 1240, margin: "0 auto", padding: "0 24px 48px", boxSizing: "border-box" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <button
          type="button"
          className="press"
          onClick={onClose}
          aria-keyshortcuts="Escape"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            minHeight: 44,
            padding: "0 4px",
            border: 0,
            background: "transparent",
            font: "inherit",
            fontSize: 15,
            fontWeight: 700,
            color: "#FFFFFF",
          }}
        >
          <Icon d={ICONS.back} size={17} strokeWidth={2.4} />
          {p.backLabel}
        </button>
        <div role="group" aria-label="Flip through builders" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            className="press press-w"
            onClick={onPrev}
            disabled={p.noPrev}
            aria-keyshortcuts="ArrowLeft"
            aria-label={p.prevAria}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              height: 44,
              padding: "0 16px 0 12px",
              borderRadius: 999,
              border: 0,
              background: "#FFFFFF",
              font: "inherit",
              fontSize: 14,
              fontWeight: 700,
              color: "#2A1715",
              boxShadow: "0 4px 0 rgba(42,23,21,.18)",
            }}
          >
            <Icon d={ICONS.prev} size={16} strokeWidth={2.6} />
            {p.prevLabel}
          </button>
          <span className="mono" style={{ color: "#FFFFFF", fontSize: 13, fontWeight: 600, padding: "0 4px" }}>
            {p.pos}
          </span>
          <button
            type="button"
            className="press press-w"
            onClick={onNext}
            disabled={p.noNext}
            aria-keyshortcuts="ArrowRight"
            aria-label={p.nextAria}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              height: 44,
              padding: "0 12px 0 16px",
              borderRadius: 999,
              border: 0,
              background: "#FFFFFF",
              font: "inherit",
              fontSize: 14,
              fontWeight: 700,
              color: "#2A1715",
              boxShadow: "0 4px 0 rgba(42,23,21,.18)",
            }}
          >
            {p.nextLabel}
            <Icon d={ICONS.next} size={16} strokeWidth={2.6} />
          </button>
        </div>
      </div>

      <div
        className="hero"
        ref={heroRef}
        tabIndex={-1}
        style={{
          marginTop: 8,
          background: "#FFFFFF",
          borderRadius: 36,
          padding: 14,
          boxSizing: "border-box",
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 30px",
          boxShadow: "0 8px 0 " + accentDark,
        }}
      >
        <div
          ref={screenRef}
          className="screen-dots"
          style={{
            position: "relative",
            zIndex: 5,
            flex: "1 1 260px",
            maxWidth: 320,
            minHeight: 280,
            borderRadius: 26,
            backgroundColor: p.bg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div aria-hidden="true" style={{ position: "absolute", inset: 0, borderRadius: 26, overflow: "hidden", pointerEvents: "none" }}>
            <span
              className="mono"
              style={{ position: "absolute", left: -8, bottom: -24, fontSize: 120, fontWeight: 600, color: p.fg, opacity: 0.1, letterSpacing: "-0.04em" }}
            >
              {p.dexNum}
            </span>
          </div>
          <span
            className="mono"
            style={{
              position: "absolute",
              left: 14,
              top: 14,
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              background: p.fg,
              color: "#FFFFFF",
              borderRadius: 999,
              padding: "5px 12px",
            }}
          >
            <Icon d={ICONS.eye} size={13} strokeWidth={2.4} />
            {p.dex}
          </span>
          <span
            className="shadow-bob"
            style={{ position: "absolute", bottom: 42, width: 116, height: 16, borderRadius: "50%", background: "rgba(42,23,21,.12)" }}
          />
          <span
            className="bob"
            style={{
              position: "relative",
              display: "block",
              width: 150,
              height: 150,
              borderRadius: "50%",
              overflow: "hidden",
              border: "8px solid #FFFFFF",
              boxSizing: "border-box",
              background: p.fg,
              marginBottom: 26,
            }}
          >
            <AvatarArt av={p.av} bg={p.bg} />
          </span>
        </div>

        <div
          className="card-in"
          style={{ flex: "999 1 400px", minWidth: 0, padding: "16px 10px 10px", display: "flex", flexDirection: "column", gap: 16, animationDelay: ".12s" }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
            <div style={{ minWidth: 0 }}>
              <h1 ref={headingRef} tabIndex={-1} className="display" style={{ margin: 0, fontSize: "clamp(40px, 5vw, 56px)", fontWeight: 700, lineHeight: 1 }}>
                {p.name}
              </h1>
              <p style={{ margin: "8px 0 0", fontSize: 17, fontWeight: 700, color: "#6E5A55" }}>{p.meta}</p>
            </div>
            <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label={p.scoreLabel} style={{ flex: "none" }}>
              <circle cx="38" cy="38" r="29" fill="none" stroke="#F3E6DA" strokeWidth={7} />
              <circle
                cx="38"
                cy="38"
                r="29"
                fill="none"
                stroke={accent}
                strokeWidth={7}
                strokeLinecap="round"
                strokeDasharray={p.dash}
                transform="rotate(-90 38 38)"
              />
              <text x="38" y="40" textAnchor="middle" className="svg-mono" fontSize={19} fontWeight={600} fill="#2A1715">
                {p.score}
              </text>
              <text x="38" y="53" textAnchor="middle" className="svg-body" fontSize={10} fontWeight={800} fill="#6E5A55">
                match
              </text>
            </svg>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {p.chips.map((ch) => (
              <span
                key={ch.label}
                style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 14, fontWeight: 800, padding: "6px 13px", borderRadius: 999, ...ch.style }}
              >
                <Icon d={ch.icon} size={15} strokeWidth={2.2} />
                {ch.label}
              </span>
            ))}
          </div>
          <p style={{ margin: 0, maxWidth: 640, fontSize: 19, fontWeight: 600, lineHeight: 1.5 }}>
            <span
              className="mono"
              style={{
                display: "block",
                fontSize: 11.5,
                fontWeight: 600,
                letterSpacing: ".08em",
                textTransform: "uppercase",
                color: "#6E5A55",
                marginBottom: 4,
              }}
            >
              Dex entry
            </span>
            {p.sum}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 2 }}>
            <button
              type="button"
              className="press press-y display"
              aria-pressed={p.starred}
              onClick={onToggleStar}
              style={{
                position: "relative",
                height: 52,
                padding: "0 22px",
                borderRadius: 999,
                border: 0,
                fontSize: 18,
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                color: "#2A1715",
                ...p.shortStyle,
              }}
            >
              <Icon d={ICONS.star} size={20} fill={p.starFill} stroke="#2A1715" strokeWidth={1.8} linecap={null} />
              {p.shortLabel}
              {p.bursting && <Burst />}
            </button>
            <button
              ref={draftButtonRef}
              type="button"
              className="press press-r display"
              aria-expanded={showDraft}
              aria-controls={showDraft ? "say-hi-draft" : undefined}
              onClick={onToggleDraft}
              style={{
                height: 52,
                padding: "0 22px",
                borderRadius: 999,
                border: 0,
                background: accent,
                color: "#FFFFFF",
                fontSize: 18,
                fontWeight: 600,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                boxShadow: "0 5px 0 " + accentDark,
              }}
            >
              <Icon d={ICONS.mail} size={20} stroke="#FFFFFF" strokeWidth={2.2} />
              {draftLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
