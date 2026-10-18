"use client";

// Screens 1 and 2. A port of the design file's `Component extends DCLogic`:
// the same state, timers, FLIP morph, slide on prev/next, shortlist burst,
// copy-to-clipboard and keyboard handling. All derived values come from
// lib/viewmodel.ts; the components under components/dex only render them.
//
// Focus follows the screen: opening a Dex entry focuses its name (screen readers
// read it out), closing it returns focus to the card that opened it, "Say hi"
// moves focus into the draft and Escape brings it back to the button, and a
// control that goes away hands focus to its neighbour. Nothing traps focus.

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { flushSync } from "react-dom";
import { activeCriteria, decodeCriteria, encodeCriteria } from "@/lib/criteria";
import { ACCENT, ICONS, reducedMotion, shade } from "@/lib/design";
import { evaluate, type SortKey, type TopicHits } from "@/lib/scoring";
import type { Criteria, Dataset } from "@/lib/types";
import {
  PAGE_SIZE,
  SCAN_TICKS,
  START_DELAY_MS,
  TICK_MS,
  deriveGrid,
  deriveProfile,
  initialState,
  type DexState,
  type TabKey,
} from "@/lib/viewmodel";
import { DexStatus } from "./DexStatus";
import { GridHero } from "./GridHero";
import { GridSection } from "./GridSection";
import { Header } from "./Header";
import { ProfileHero } from "./ProfileHero";
import { ProfileMain } from "./ProfileMain";

const OFFLINE = "Couldn't reach Talent Dex. Check your connection and try again.";
const LOAD_FAILED = "Couldn't load builders. Try again.";
/** The topic check gives up after this and the topic row says it couldn't check. A topic that
 *  wasn't embedded ahead of time loads the local model first, which takes a few seconds. */
const TOPIC_TIMEOUT_MS = 15_000;

export default function DexApp() {
  const params = useSearchParams();
  const query = params ? params.toString() : "";
  const search = useMemo(() => decodeCriteria(params ? new URLSearchParams(query) : null), [params, query]);
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // A topic search ("built a RAG pipeline") also needs the builders whose projects are like it.
  // The topic has its own "Try again" (topicAttempt); `attempt` is the answer's try number.
  const topicQuery = search.topic ? search.topicQuery || search.topic : null;
  const [topic, setTopic] = useState<{ query: string; attempt: number; hits: TopicHits | undefined } | null>(null);
  const [topicAttempt, setTopicAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    fetch("/api/builders")
      .then(
        async (r) => {
          const body = await r.json().catch(() => null);
          if (!r.ok) {
            // A warning, not an error: under next dev an error puts an issue badge on this frame.
            console.warn("/api/builders answered " + r.status);
            throw new Error(body?.error || LOAD_FAILED);
          }
          // Anything but a dataset would leave the loading frame up for good.
          if (!Array.isArray(body?.builders)) throw new Error("Couldn't read the builders data.");
          return body as Dataset;
        },
        () => {
          // fetch() itself failed: the server is down or the network is gone.
          throw new Error(OFFLINE);
        },
      )
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message || LOAD_FAILED));
    return () => {
      live = false;
    };
  }, [attempt]);

  useEffect(() => {
    if (!topicQuery) return;
    let live = true;
    const stop = new AbortController();
    const timeout = setTimeout(() => stop.abort(), TOPIC_TIMEOUT_MS);
    fetch("/api/topic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: topicQuery }),
      signal: stop.signal,
    })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !body?.hits) throw new Error(body?.error || "topic search failed");
        return body.hits as TopicHits;
      })
      // Without hits the topic row says it couldn't be checked; the rest of the search still runs.
      .then((hits) => live && setTopic({ query: topicQuery, attempt: topicAttempt, hits }))
      .catch(() => live && setTopic({ query: topicQuery, attempt: topicAttempt, hits: undefined }))
      .finally(() => clearTimeout(timeout));
    return () => {
      live = false;
      clearTimeout(timeout);
      stop.abort();
    };
  }, [topicQuery, attempt, topicAttempt]);

  const topicPending = !!topicQuery && topic?.query !== topicQuery;
  const topicChecking = !!topicQuery && !topicPending && topic?.attempt !== topicAttempt;

  // "Try again" goes away while it works. Once the answer is on screen, focus moves to the
  // grid's headline, or back to the topic's "Try again" if the topic failed again. Only when
  // nothing else took focus in the meantime. (The builders' error frame refocuses its own.)
  const refocus = useRef<"grid" | "topic" | null>(null);
  useEffect(() => {
    if (!refocus.current || !data || topicPending || topicChecking) return;
    const target = refocus.current === "topic" && !topic?.hits ? "[data-topic-retry]" : null;
    refocus.current = null;
    if (document.activeElement && document.activeElement !== document.body) return;
    focusFirst([target, "[data-grid-headline]"]);
  }, [data, topic, topicPending, topicChecking]);

  if (error) {
    return (
      <DexStatus
        kind="error"
        message={error}
        focusRetry={attempt > 0}
        onRetry={() => {
          refocus.current = "grid";
          setError(null);
          setTopic(null);
          setAttempt((a) => a + 1);
        }}
      />
    );
  }
  if (!data || topicPending) return <DexStatus kind="loading" label={data ? "Checking projects for this topic…" : undefined} />;
  // A new search remounts the screens, so the scan replays from the start.
  return (
    <DexScreens
      key={encodeCriteria(search)}
      data={data}
      search={search}
      hits={topicQuery ? topic?.hits : undefined}
      topicChecking={topicChecking}
      onRetryTopic={() => {
        refocus.current = "topic";
        setTopicAttempt((a) => a + 1);
      }}
    />
  );
}

function storageKey(data: Dataset, what: string) {
  return "talentdex:v1:" + data.source + ":" + what;
}

function readMap(store: Storage | null, key: string): Record<string, boolean> | null {
  try {
    const raw = store ? store.getItem(key) : null;
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : null;
  } catch {
    return null;
  }
}

function writeMap(store: Storage | null, key: string, value: Record<string, boolean>) {
  try {
    if (store) store.setItem(key, JSON.stringify(value));
  } catch {
    /* storage can be unavailable (private mode); the app works without it */
  }
}

function safeStorage(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

/** A builder's card in the grid: its name button (opens the Dex entry) or its star. */
function cardSelector(id: string, part: "open" | "star"): string {
  return 'article[data-id="' + CSS.escape(id) + '"] ' + (part === "open" ? ".stretch-btn" : ".star");
}

/** Focus the first of these selectors that is on the page; skips empty entries. */
function focusFirst(selectors: (string | null | false | undefined)[]): boolean {
  for (const sel of selectors) {
    const el = sel ? document.querySelector<HTMLElement>(sel) : null;
    if (el) {
      el.focus();
      return true;
    }
  }
  return false;
}

/**
 * Copy text to the clipboard; false when the browser refuses. Pages served over plain
 * http (the demo opened from another device on the venue wifi) have no Clipboard API,
 * so that case copies from a hidden textarea instead.
 */
async function writeClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* fall through to the textarea */
  }
  const back = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  back?.focus();
  return ok;
}

interface DexScreensProps {
  data: Dataset;
  search: Criteria;
  hits?: TopicHits;
  /** The topic check is running again after "Try again". */
  topicChecking: boolean;
  onRetryTopic: () => void;
}

function DexScreens({ data, search, hits, topicChecking, onRetryTopic }: DexScreensProps) {
  const accent = ACCENT;
  const accentDark = shade(accent, 0.24);

  const [s, setS] = useState<DexState>(() => {
    const demo = Object.fromEntries((data.demo?.shortlist || []).map((id) => [id, true]));
    const st = initialState(readMap(safeStorage("local"), storageKey(data, "shortlist")) || demo);
    st.seen = readMap(safeStorage("session"), storageKey(data, "seen")) || {};
    return st;
  });
  const patch = useCallback((p: Partial<DexState> | ((prev: DexState) => Partial<DexState>)) => {
    setS((prev) => ({ ...prev, ...(typeof p === "function" ? p(prev) : p) }));
  }, []);

  useEffect(() => writeMap(safeStorage("local"), storageKey(data, "shortlist"), s.starred), [data, s.starred]);
  useEffect(() => writeMap(safeStorage("session"), storageKey(data, "seen"), s.seen), [data, s.seen]);

  // ---- Scan replay (design: run()) ----
  // Under prefers-reduced-motion the replay still runs: its counter and the cards it
  // reveals are information, not decoration. app/globals.css drops their transitions,
  // pop-ins and the decorative sweep, so numbers and cards change in place, unmoving.
  const delay = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const tickNow = useRef(0);
  useEffect(() => {
    tickNow.current = s.tick;
  }, [s.tick]);
  const startTimers = useCallback(
    (from: number) => {
      clearTimeout(delay.current);
      clearInterval(timer.current);
      delay.current = setTimeout(
        () => {
          let t = from;
          timer.current = setInterval(() => {
            t += 1;
            patch({ tick: t });
            if (t >= SCAN_TICKS) clearInterval(timer.current);
          }, TICK_MS);
        },
        from === 0 ? START_DELAY_MS : 0,
      );
    },
    [patch],
  );
  // The rerun button: back to tick 0, then replay.
  const run = useCallback(() => {
    patch({ tick: 0 });
    startTimers(0);
  }, [patch, startTimers]);

  const burstTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    // State starts at tick 0, so the first replay only needs the timers. Next keeps this
    // page mounted but hidden while the search screen shows; when it comes back, the
    // replay carries on from where it was instead of scanning again.
    if (tickNow.current < SCAN_TICKS) startTimers(tickNow.current);
    return () => {
      clearTimeout(delay.current);
      clearInterval(timer.current);
      clearTimeout(burstTimer.current);
      clearTimeout(copyTimer.current);
    };
  }, [startTimers]);

  // ---- Derived view models ----
  const criteria = useMemo(() => activeCriteria(search, s.removed), [search, s.removed]);
  const ctx = useMemo(
    () => ({ data, criteria, search, accent, hits, topicChecking, now: data.source === "sample" ? new Date(data.generatedAt) : undefined }),
    [data, criteria, search, accent, hits, topicChecking],
  );
  const { ranked, grid, order } = useMemo(() => deriveGrid(s, ctx), [s, ctx]);
  const profile = useMemo(() => {
    if (!s.open) return null;
    const b = data.builders.find((x) => x.id === s.open);
    if (!b) return null;
    const e = ranked.find((r) => r.b.id === s.open)?.e || evaluate(b, criteria, hits);
    return deriveProfile(s, ctx, s.open, e, order);
  }, [s, ctx, data, ranked, criteria, order, hits]);

  // ---- Refs for motion and focus (design: refs()) ----
  const heroEl = useRef<HTMLDivElement>(null);
  const heroScreenEl = useRef<HTMLDivElement>(null);
  const headingEl = useRef<HTMLHeadingElement>(null);
  const draftButtonEl = useRef<HTMLButtonElement>(null);
  const draftHeadingEl = useRef<HTMLHeadingElement>(null);
  const radarEl = useRef<SVGGElement>(null);
  const badgeEl = useRef<HTMLSpanElement>(null);
  const flipFrom = useRef<DOMRect | null>(null);
  const flipDir = useRef(0);
  const savedY = useRef(0);
  const openedFrom = useRef<string | null>(null);
  const prevOpen = useRef<string | null>(null);

  // Design: componentDidUpdate. Focus the entry's name, then morph the card into the
  // hero, or slide on prev/next. Reduced motion: focus only, no morph and no slide.
  useLayoutEffect(() => {
    const was = prevOpen.current;
    prevOpen.current = s.open;
    if (!s.open || s.open === was) return;
    const from = flipFrom.current;
    const dir = flipDir.current;
    flipFrom.current = null;
    flipDir.current = 0;
    try {
      headingEl.current?.focus({ preventScroll: true });
    } catch {}
    if (reducedMotion()) return;
    try {
      if (from && heroScreenEl.current) {
        const to = heroScreenEl.current.getBoundingClientRect();
        const sc = from.width / to.width;
        const dx = from.left + from.width / 2 - (to.left + to.width / 2);
        const dy = from.top + from.height / 2 - (to.top + to.height / 2);
        heroScreenEl.current.animate(
          [{ transform: "translate(" + dx + "px," + dy + "px) scale(" + sc + ")" }, { transform: "none" }],
          { duration: 560, easing: "cubic-bezier(.2,.9,.25,1.08)" },
        );
      } else if (dir && heroEl.current) {
        heroEl.current.animate(
          [{ opacity: 0, transform: "translateX(" + dir * 56 + "px)" }, { opacity: 1, transform: "none" }],
          { duration: 380, easing: "cubic-bezier(.2,.9,.3,1.15)" },
        );
        radarEl.current?.animate(
          [{ transform: "scale(0)", opacity: 0 }, { transform: "scale(1)", opacity: 1 }],
          { duration: 700, easing: "cubic-bezier(.34,1.56,.64,1)" },
        );
      }
    } catch {}
  }, [s.open]);

  // ---- Actions (design: open, flipTo, close, toggle, copy, onKey) ----
  const open = useCallback(
    (id: string, e: MouseEvent<HTMLElement>) => {
      let rect: DOMRect | null = null;
      try {
        const art = e.currentTarget.closest("article");
        const scr = art ? art.querySelector(".card-screen") : null;
        if (scr) rect = scr.getBoundingClientRect();
      } catch {}
      savedY.current = window.scrollY || 0;
      openedFrom.current = id;
      flipFrom.current = rect;
      flipDir.current = 0;
      patch((prev) => ({ open: id, seen: { ...prev.seen, [id]: true }, showDraft: false, copied: false }));
      try {
        window.scrollTo(0, 0);
      } catch {}
    },
    [patch],
  );

  const flipTo = useCallback(
    (id: string, dir: number) => {
      flipFrom.current = null;
      flipDir.current = dir;
      patch((prev) => ({ open: id, seen: { ...prev.seen, [id]: true }, showDraft: false, copied: false }));
    },
    [patch],
  );

  // Back to the grid at the scroll position it had, with focus on the card that opened
  // the entry (after prev/next, the shown builder's card if that one is gone; in the
  // shortlist view, after taking the shown builder off, the card next to theirs; failing
  // all of those, the headline).
  const close = useCallback(() => {
    const y = savedY.current;
    const ids = [openedFrom.current, s.open, profile?.nextId, profile?.prevId];
    flushSync(() => patch({ open: null, showDraft: false }));
    try {
      window.scrollTo(0, y);
    } catch {}
    focusFirst([...ids.map((id) => id && cardSelector(id, "open")), "[data-grid-headline]"]);
  }, [s.open, profile?.nextId, profile?.prevId, patch]);

  const toggle = useCallback(
    (id: string) => {
      const willStar = !s.starred[id];
      // Reduced motion: no sparks and no badge pop (the burst timer only exists for the sparks).
      const motion = willStar && !reducedMotion();
      const star = () =>
        patch((prev) => ({ starred: { ...prev.starred, [id]: !prev.starred[id] }, ...(motion ? { burst: id } : {}) }));
      // In the shortlist view, taking someone off removes their card: focus a neighbour's star.
      const ids = grid.cards.map((c) => c.id);
      const i = ids.indexOf(id);
      if (!willStar && s.shortlistOnly && !s.open && i >= 0) {
        flushSync(star);
        focusFirst([ids[i + 1] && cardSelector(ids[i + 1], "star"), ids[i - 1] && cardSelector(ids[i - 1], "star"), "[data-shortlist-toggle]"]);
      } else {
        star();
      }
      if (motion) {
        clearTimeout(burstTimer.current);
        burstTimer.current = setTimeout(() => patch({ burst: null }), 700);
        if (badgeEl.current) {
          try {
            badgeEl.current.animate([{ transform: "scale(1)" }, { transform: "scale(1.5)" }, { transform: "scale(1)" }], {
              duration: 420,
              easing: "cubic-bezier(.34,1.56,.64,1)",
            });
          } catch {}
        }
      }
    },
    [s.starred, s.shortlistOnly, s.open, grid.cards, patch],
  );

  const copy = useCallback(() => {
    if (!profile) return;
    void writeClipboard("Subject: " + profile.draftSubject + "\n\n" + profile.draftBody).then((ok) => {
      patch({ copied: ok ? "ok" : "failed" });
      clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => patch({ copied: false }), 1600);
    });
  }, [profile, patch]);

  // "Say hi" moves focus into the draft; "Hide draft" leaves it on the button.
  const toggleDraft = useCallback(() => {
    const opening = !s.showDraft;
    flushSync(() => patch({ showDraft: opening, copied: false }));
    if (opening) draftHeadingEl.current?.focus();
  }, [s.showDraft, patch]);

  const closeDraft = useCallback(() => {
    flushSync(() => patch({ showDraft: false, copied: false }));
    draftButtonEl.current?.focus();
  }, [patch]);

  // Keys on the Dex entry. Listened for on the document, not the page's root element, so
  // they still work after a click on plain text has left focus on <body>. Keys with a
  // modifier (Alt+Left is the browser's Back) and keys typed into fields are left alone.
  const profileOpen = !!profile;
  const prevId = profile?.prevId ?? null;
  const nextId = profile?.nextId ?? null;
  const showDraft = s.showDraft;
  useEffect(() => {
    if (!profileOpen) return;
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      if (e.target instanceof HTMLElement && (e.target.isContentEditable || e.target.matches("input, textarea, select"))) return;
      if (e.key === "ArrowLeft" && prevId) {
        e.preventDefault();
        flipTo(prevId, -1);
      } else if (e.key === "ArrowRight" && nextId) {
        e.preventDefault();
        flipTo(nextId, 1);
      } else if (e.key === "Escape") {
        // The innermost thing closes first: the draft, then the Dex entry.
        e.preventDefault();
        if (showDraft) closeDraft();
        else close();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [profileOpen, prevId, nextId, showDraft, flipTo, close, closeDraft]);

  // ---- Grid actions that remove the control that has focus ----
  const removeFilter = useCallback(
    (id: string) => {
      // Focus the next chip's ×, else the previous one's, else "Restore filters".
      const ids = grid.filters.map((f) => f.id);
      const i = ids.indexOf(id);
      flushSync(() => patch((prev) => ({ removed: { ...prev.removed, [id]: true } })));
      focusFirst([...[ids[i + 1], ids[i - 1]].map((f) => f && '[data-filter="' + CSS.escape(f) + '"]'), "[data-restore-filters]"]);
    },
    [grid.filters, patch],
  );

  const restoreFilters = useCallback(() => {
    // The button goes away once nothing is removed: focus the first chip's ×.
    flushSync(() => patch({ removed: {} }));
    focusFirst(["[data-filter]"]);
  }, [patch]);

  // The empty shortlist view's "Show all builders": the button goes with the view, so the
  // headline takes focus.
  const showAll = useCallback(() => {
    flushSync(() => patch({ shortlistOnly: false }));
    focusFirst(["[data-grid-headline]"]);
  }, [patch]);

  const showMore = useCallback(() => {
    // Focus the first card the button added, so Tab carries on through the new ones.
    const first = s.limit;
    flushSync(() => patch((prev) => ({ limit: prev.limit + PAGE_SIZE })));
    const added = Array.from(document.querySelectorAll("article[data-id]")).slice(first);
    const target = added.map((a) => a.querySelector<HTMLElement>(".stretch-btn")).find((b) => b);
    if (target) target.focus();
    else focusFirst(["[data-show-more]"]);
  }, [s.limit, patch]);

  const profileMode = !!profile;
  const copyState = s.copied;

  return (
    <div style={{ minHeight: "100vh", boxSizing: "border-box" }}>
      <div style={{ background: accent, borderRadius: "0 0 48px 48px", position: "relative" }}>
        <div className="lid-dots" style={{ position: "absolute", inset: 0, borderRadius: "0 0 48px 48px", pointerEvents: "none" }} />
        <Header
          accent={accent}
          accentDark={accentDark}
          seenCount={grid.seenCount}
          starCount={grid.starCount}
          badgeRef={badgeEl}
          shortlistOn={grid.shortlistOn}
          onToggleShortlist={profileMode ? undefined : () => patch((prev) => ({ shortlistOnly: !prev.shortlistOnly }))}
        />
        {!profileMode && (
          <GridHero
            vm={grid}
            accent={accent}
            accentDark={accentDark}
            onRemoveFilter={removeFilter}
            onRestoreFilters={restoreFilters}
            onSort={(sort: SortKey) => patch({ sort })}
            onRerun={run}
            onRetryTopic={onRetryTopic}
          />
        )}
        {profile && (
          <ProfileHero
            p={profile}
            accent={accent}
            accentDark={accentDark}
            showDraft={s.showDraft}
            draftLabel={s.showDraft ? "Hide draft" : "Say hi"}
            onClose={close}
            onPrev={() => profile.prevId && flipTo(profile.prevId, -1)}
            onNext={() => profile.nextId && flipTo(profile.nextId, 1)}
            onToggleStar={() => toggle(profile.id)}
            onToggleDraft={toggleDraft}
            heroRef={heroEl}
            screenRef={heroScreenEl}
            headingRef={headingEl}
            draftButtonRef={draftButtonEl}
          />
        )}
      </div>
      {!profileMode && (
        <GridSection
          vm={grid}
          accent={accent}
          onPickTab={(key: TabKey) => patch({ filter: key, shortlistOnly: false })}
          onToggleStar={toggle}
          onOpen={open}
          onShowMore={showMore}
          onShowAll={showAll}
        />
      )}
      {profile && (
        <ProfileMain
          p={profile}
          accent={accent}
          accentDark={accentDark}
          showDraft={s.showDraft}
          copyLabel={copyState === "ok" ? "Copied!" : copyState === "failed" ? "Couldn't copy" : "Copy email"}
          copyIcon={copyState === "ok" ? ICONS.check : copyState === "failed" ? ICONS.alert : ICONS.copy}
          copyStatus={
            copyState === "ok" ? "Email copied." : copyState === "failed" ? "Couldn't copy the email. Select the text to copy it yourself." : ""
          }
          onCopy={copy}
          tab={s.tab}
          onTab={(tab) => patch({ tab })}
          radarRef={radarEl}
          draftHeadingRef={draftHeadingEl}
        />
      )}
    </div>
  );
}
