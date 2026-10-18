"use client";

// Screens 1 and 2. A port of the design file's `Component extends DCLogic`:
// the same state, timers, FLIP morph, slide on prev/next, shortlist burst,
// copy-to-clipboard and keyboard handling. All derived values come from
// lib/viewmodel.ts; the components under components/dex only render them.

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
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

export default function DexApp() {
  const params = useSearchParams();
  const query = params ? params.toString() : "";
  const search = useMemo(() => decodeCriteria(params ? new URLSearchParams(query) : null), [params, query]);
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // A topic search ("built a RAG pipeline") also needs the builders whose projects are like it.
  const topicQuery = search.topic ? search.topicQuery || search.topic : null;
  const [topic, setTopic] = useState<{ query: string; hits: TopicHits | undefined } | null>(null);

  useEffect(() => {
    let live = true;
    fetch("/api/builders")
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok) throw new Error(body?.error || "Could not load builders (" + r.status + ").");
        return body as Dataset;
      })
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message || "Could not load builders."));
    return () => {
      live = false;
    };
  }, [attempt]);

  useEffect(() => {
    if (!topicQuery) return;
    let live = true;
    fetch("/api/topic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: topicQuery }),
    })
      .then(async (r) => {
        const body = await r.json().catch(() => null);
        if (!r.ok || !body?.hits) throw new Error(body?.error || "topic search failed");
        return body.hits as TopicHits;
      })
      // Without hits the topic row says it couldn't be checked; the rest of the search still runs.
      .then((hits) => live && setTopic({ query: topicQuery, hits }))
      .catch(() => live && setTopic({ query: topicQuery, hits: undefined }));
    return () => {
      live = false;
    };
  }, [topicQuery, attempt]);

  if (error) {
    return (
      <DexStatus
        kind="error"
        message={error}
        onRetry={() => {
          setError(null);
          setAttempt((a) => a + 1);
        }}
      />
    );
  }
  if (!data || (topicQuery && topic?.query !== topicQuery)) return <DexStatus kind="loading" />;
  // A new search remounts the screens, so the scan replays from the start.
  return <DexScreens key={encodeCriteria(search)} data={data} search={search} hits={topicQuery ? topic?.hits : undefined} />;
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

function DexScreens({ data, search, hits }: { data: Dataset; search: Criteria; hits?: TopicHits }) {
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
  const delay = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const startTimers = useCallback(() => {
    clearTimeout(delay.current);
    clearInterval(timer.current);
    delay.current = setTimeout(() => {
      let t = 0;
      timer.current = setInterval(() => {
        t += 1;
        patch({ tick: t });
        if (t >= SCAN_TICKS) clearInterval(timer.current);
      }, TICK_MS);
    }, START_DELAY_MS);
  }, [patch]);
  // The rerun button: back to tick 0, then replay.
  const run = useCallback(() => {
    patch({ tick: 0 });
    startTimers();
  }, [patch, startTimers]);

  const burstTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    // State starts at tick 0, so the first replay only needs the timers.
    startTimers();
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
    () => ({ data, criteria, search, accent, hits, now: data.source === "sample" ? new Date(data.generatedAt) : undefined }),
    [data, criteria, search, accent, hits],
  );
  const { ranked, grid, order } = useMemo(() => deriveGrid(s, ctx), [s, ctx]);
  const profile = useMemo(() => {
    if (!s.open) return null;
    const b = data.builders.find((x) => x.id === s.open);
    if (!b) return null;
    const e = ranked.find((r) => r.b.id === s.open)?.e || evaluate(b, criteria, hits);
    return deriveProfile(s, ctx, s.open, e, order);
  }, [s, ctx, data, ranked, criteria, order, hits]);

  // ---- Refs for motion (design: refs()) ----
  const heroEl = useRef<HTMLDivElement>(null);
  const heroScreenEl = useRef<HTMLDivElement>(null);
  const radarEl = useRef<SVGGElement>(null);
  const badgeEl = useRef<HTMLSpanElement>(null);
  const flipFrom = useRef<DOMRect | null>(null);
  const flipDir = useRef(0);
  const savedY = useRef(0);
  const prevOpen = useRef<string | null>(null);

  // Design: componentDidUpdate. Morph the card into the hero, or slide on prev/next.
  useLayoutEffect(() => {
    const was = prevOpen.current;
    prevOpen.current = s.open;
    if (!s.open || s.open === was) return;
    const from = flipFrom.current;
    const dir = flipDir.current;
    flipFrom.current = null;
    flipDir.current = 0;
    try {
      heroEl.current?.focus({ preventScroll: true });
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

  const close = useCallback(() => {
    const y = savedY.current;
    patch({ open: null, showDraft: false });
    setTimeout(() => {
      try {
        window.scrollTo(0, y);
      } catch {}
    }, 0);
  }, [patch]);

  const toggle = useCallback(
    (id: string) => {
      const willStar = !s.starred[id];
      patch((prev) => ({ starred: { ...prev.starred, [id]: !prev.starred[id] }, ...(willStar ? { burst: id } : {}) }));
      if (willStar) {
        clearTimeout(burstTimer.current);
        burstTimer.current = setTimeout(() => patch({ burst: null }), 700);
        if (badgeEl.current && !reducedMotion()) {
          try {
            badgeEl.current.animate([{ transform: "scale(1)" }, { transform: "scale(1.5)" }, { transform: "scale(1)" }], {
              duration: 420,
              easing: "cubic-bezier(.34,1.56,.64,1)",
            });
          } catch {}
        }
      }
    },
    [s.starred, patch],
  );

  const copy = useCallback(() => {
    try {
      if (profile && navigator.clipboard) navigator.clipboard.writeText("Subject: " + profile.draftSubject + "\n\n" + profile.draftBody).catch(() => {});
    } catch {}
    patch({ copied: true });
    clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => patch({ copied: false }), 1600);
  }, [profile, patch]);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!profile) return;
    if (e.key === "ArrowLeft" && profile.prevId) {
      e.preventDefault();
      flipTo(profile.prevId, -1);
    } else if (e.key === "ArrowRight" && profile.nextId) {
      e.preventDefault();
      flipTo(profile.nextId, 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  };

  const profileMode = !!profile;

  return (
    <div onKeyDown={onKey} style={{ minHeight: "100vh", boxSizing: "border-box" }}>
      <div style={{ background: accent, borderRadius: "0 0 48px 48px", position: "relative" }}>
        <div className="lid-dots" style={{ position: "absolute", inset: 0, borderRadius: "0 0 48px 48px", pointerEvents: "none" }} />
        <Header accent={accent} accentDark={accentDark} seenCount={grid.seenCount} starCount={grid.starCount} badgeRef={badgeEl} />
        {!profileMode && (
          <GridHero
            vm={grid}
            accent={accent}
            accentDark={accentDark}
            onRemoveFilter={(id) => patch((prev) => ({ removed: { ...prev.removed, [id]: true } }))}
            onRestoreFilters={() => patch({ removed: {} })}
            onSort={(sort: SortKey) => patch({ sort })}
            onRerun={run}
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
            onToggleDraft={() => patch((prev) => ({ showDraft: !prev.showDraft, copied: false }))}
            heroRef={heroEl}
            screenRef={heroScreenEl}
          />
        )}
      </div>
      {!profileMode && (
        <GridSection
          vm={grid}
          accent={accent}
          onPickTab={(key: TabKey) => patch({ filter: key })}
          onToggleStar={toggle}
          onOpen={open}
          onShowMore={() => patch((prev) => ({ limit: prev.limit + PAGE_SIZE }))}
        />
      )}
      {profile && (
        <ProfileMain
          p={profile}
          accent={accent}
          accentDark={accentDark}
          showDraft={s.showDraft}
          copyLabel={s.copied ? "Copied!" : "Copy email"}
          copyIcon={s.copied ? ICONS.check : ICONS.copy}
          onCopy={copy}
          tab={s.tab}
          onTab={(tab) => patch({ tab })}
          radarRef={radarEl}
        />
      )}
    </div>
  );
}
