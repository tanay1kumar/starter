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
  /** The grid is showing only the shortlist. */
  shortlistOn: boolean;
  /** Grid only: makes the Shortlist pill a toggle for the shortlist view. */
  onToggleShortlist?: () => void;
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
  /** "Try again" after the topic's project check failed: checks the topic only. */
  onRetryTopic: () => void;
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
  /** The empty shortlist view's "Show all builders": turns the shortlist view off. */
  onShowAll: () => void;
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
  /** The hero card (slides on prev/next). */
  heroRef: Ref<HTMLDivElement>;
  /** The coloured "screen" inside the hero (FLIP morph target). */
  screenRef: Ref<HTMLDivElement>;
  /** The builder's name (h1): focused whenever the entry opens or flips. */
  headingRef: Ref<HTMLHeadingElement>;
  /** "Say hi": focus comes back here when Escape closes the draft. */
  draftButtonRef: Ref<HTMLButtonElement>;
}

/** Profile mode, below the lid: draft, why-fits, trait board, field notes, signature projects. */
export interface ProfileMainProps {
  p: ProfileVM;
  accent: string;
  accentDark: string;
  showDraft: boolean;
  copyLabel: string;
  copyIcon: string;
  /** Read out after "Copy email": whether it worked. */
  copyStatus: string;
  onCopy: () => void;
  tab: "ev" | "iv";
  onTab: (tab: "ev" | "iv") => void;
  /** The radar polygon group (pops in on prev/next). */
  radarRef: Ref<SVGGElement>;
  /** The draft's heading: focused when "Say hi" opens it. */
  draftHeadingRef: Ref<HTMLHeadingElement>;
}
