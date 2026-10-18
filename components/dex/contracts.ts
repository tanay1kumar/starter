// Props for the screen 1 / screen 2 components. DexApp (the state machine,
// ported from the design's Component class) owns all state and passes view
// models from lib/viewmodel.ts plus callbacks. Components never hold app state.

import type { MouseEvent, Ref } from "react";
import type { SortKey } from "@/lib/scoring";
import type { GridVM, ProfileVM, TabKey } from "@/lib/viewmodel";

export interface HeaderProps {
  accent: string;
  accentDark: string;
  seenCount: number;
  starCount: number;
  /** Shortlist count badge; DexApp animates it on shortlist. */
  badgeRef: Ref<HTMLSpanElement>;
}

/** Grid mode, inside the red lid: "New scan", headline, filter chips, sort, rerun, scan progress. */
export interface GridHeroProps {
  vm: GridVM;
  accent: string;
  accentDark: string;
  onRemoveFilter: (id: string) => void;
  onRestoreFilters: () => void;
  onSort: (sort: SortKey) => void;
  onRerun: () => void;
}

/** Grid mode, below the lid: type tabs, dex cards, skeletons, empty states, "Show more". */
export interface GridSectionProps {
  vm: GridVM;
  accent: string;
  onPickTab: (key: TabKey) => void;
  onToggleStar: (id: string) => void;
  /** Must be called from the card's name button so DexApp can find the card for the FLIP morph. */
  onOpen: (id: string, e: MouseEvent<HTMLElement>) => void;
  onShowMore: () => void;
}

/** Profile mode, inside the red lid: back, prev/next, and the hero card. */
export interface ProfileHeroProps {
  p: ProfileVM;
  accent: string;
  accentDark: string;
  showDraft: boolean;
  draftLabel: string;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onToggleStar: () => void;
  onToggleDraft: () => void;
  /** The hero card (focused on open, slides on prev/next). */
  heroRef: Ref<HTMLDivElement>;
  /** The coloured "screen" inside the hero (FLIP morph target). */
  screenRef: Ref<HTMLDivElement>;
}

/** Profile mode, below the lid: draft, why-fits, trait board, field notes, signature projects. */
export interface ProfileMainProps {
  p: ProfileVM;
  accent: string;
  accentDark: string;
  showDraft: boolean;
  copyLabel: string;
  copyIcon: string;
  onCopy: () => void;
  tab: "ev" | "iv";
  onTab: (tab: "ev" | "iv") => void;
  /** The radar polygon group (pops in on prev/next). */
  radarRef: Ref<SVGGElement>;
}
