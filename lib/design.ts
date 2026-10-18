// Design tokens and helpers ported 1:1 from design/talent-dex-v3.html
// (the `Component extends DCLogic` class: types(), judge(), avatar(), shade()).

import type { CSSProperties } from "react";
import type { CritStatus, TypeKey } from "./types";

export const INK = "#2A1715";
export const MUTED = "#6E5A55";
export const BODY_INK = "#4A3632";
export const PAPER = "#FFF6EE";
export const ACCENT = "#E8382B";
export const SHORTLIST = "#FFCB3D";
export const SHORTLIST_SHADOW = "#C98F0E";

export interface TypeStyle {
  label: string;
  bg: string;
  fg: string;
  icon: string;
}

export const TYPES: Record<TypeKey, TypeStyle> = {
  ml: { label: "ML / AI", bg: "#EEE8FF", fg: "#5B3FD6", icon: "M3 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0M3 18a2 2 0 1 0 4 0a2 2 0 1 0-4 0M17 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M10 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M6.5 7.5l4 3M6.5 16.5l4-3M14 12h3" },
  backend: { label: "Backend", bg: "#DDF5EA", fg: "#1A6B4A", icon: "M4 5h16v5H4zM4 14h16v5H4zM7.5 7.5h.01M7.5 16.5h.01" },
  frontend: { label: "Frontend", bg: "#FFE9DC", fg: "#B4441A", icon: "M3 5h18v14H3zM3 9h18M6 7h.01M8.5 7h.01" },
  design: { label: "Design", bg: "#FFE3EE", fg: "#AD2A5F", icon: "M12 3l6 8-6 10-6-10zM12 10v4" },
  mobile: { label: "Mobile", bg: "#DDEFFF", fg: "#1D65B8", icon: "M7 3h10v18H7zM11 18h2" },
  hardware: { label: "Hardware", bg: "#FFF3C4", fg: "#7A5D00", icon: "M7 7h10v10H7zM10 10h4v4h-4zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4" },
};

/** Radar axis order (clockwise from the top). */
export const AXES: TypeKey[] = ["ml", "backend", "frontend", "design", "mobile", "hardware"];

export const TRAIT_LABELS = ["Ships demos", "Wins", "Ownership", "Teamwork", "Persistence", "Documentation"] as const;
export const NATURES = ["Builder", "Competitor", "Leader", "Teammate", "Finisher", "Explainer"] as const;

export const ICONS = {
  all: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  year: "M2 9l10-5 10 5-10 5-10-5zM6 11v5c0 1.4 2.7 3 6 3s6-1.6 6-3v-5",
  loc: "M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 1 1 13 0c0 5.4-6.5 11-6.5 11zM12 12.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z",
  win: "M8 4h8v5a4 4 0 0 1-8 0V4zM8 6H5a3 3 0 0 0 3.3 4M16 6h3a3 3 0 0 1-3.3 4M12 13v4M8.5 20h7M10 17h4",
  topic: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  eye: "M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  star: "M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z",
  back: "M19 12H5M11 6l-6 6 6 6",
  prev: "M15 6l-6 6 6 6",
  next: "M9 6l6 6-6 6",
  close: "M6 6l12 12M18 6L6 18",
  rerun: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  check: "M5 12.5l4.5 4.5L19 7.5",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  bolt: "M13 3L5 13h6l-1 8 8-10h-6z",
  external: "M8 16L16 8M9 8h7v7",
  shield: "M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6z",
  shieldCheck: "M9 12l2 2 4-4",
  trophy: "M8 4h8v5a4 4 0 0 1-8 0V4zM8 6H5a3 3 0 0 0 3.3 4M16 6h3a3 3 0 0 1-3.3 4M12 13v4M8.5 20h7M10 17h4",
  question: "M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5h.01",
} as const;

export interface StatusStyle {
  bg: string;
  fg: string;
  icon: string;
  status: string;
}

export const STATUS: Record<CritStatus, StatusStyle> = {
  met: { bg: "#DDF5EA", fg: "#1A6B4A", icon: "M5 12.5l4.5 4.5L19 7.5", status: "Matches" },
  close: { bg: "#FFF3C4", fg: "#7A5D00", icon: "M5 13c2-3 4-3 7 0s5 3 7 0", status: "Close" },
  miss: { bg: "#F3E6DA", fg: "#6E5A55", icon: "M7 7l10 10M17 7L7 17", status: "Does not match" },
  // Not in the design: the brief requires missing data to read "Not listed".
  unknown: { bg: "#F3E6DA", fg: "#6E5A55", icon: ICONS.question, status: "Not listed" },
};

/** Darken a hex colour by fraction f (design: shade(accent, 0.24) for the chunky shadows). */
export function shade(hex: string, f: number): string {
  const n = parseInt(String(hex).replace("#", ""), 16);
  if (isNaN(n)) return "#B8261C";
  const c = (v: number) => Math.max(0, Math.round(v * (1 - f))).toString(16).padStart(2, "0");
  return "#" + c((n >> 16) & 255) + c((n >> 8) & 255) + c(n & 255);
}

export interface AvatarShape {
  rx: number;
  ry: number;
  rs: number;
  rt: string;
  cx: number;
  cy: number;
  cr: number;
  cf: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** Deterministic abstract avatar from an id (no photos are ever used). */
export function avatar(id: string): AvatarShape {
  let h = 7;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const r = () => {
    h = (Math.imul(h, 1664525) + 1013904223) >>> 0;
    return h / 4294967296;
  };
  const rs = Math.round(44 + r() * 22);
  const rx = Math.round(6 + r() * 40);
  const ry = Math.round(6 + r() * 40);
  const rot = Math.round(r() * 90);
  const cx = Math.round(30 + r() * 45);
  const cy = Math.round(35 + r() * 45);
  const cr = Math.round(16 + r() * 12);
  const x1 = Math.round(10 + r() * 30);
  const y1 = Math.round(55 + r() * 30);
  const a = r() * Math.PI;
  return {
    rx, ry, rs,
    rt: "rotate(" + rot + " " + (rx + rs / 2) + " " + (ry + rs / 2) + ")",
    cx, cy, cr,
    cf: r() > 0.45 ? "#FFCB3D" : "#FFFFFF",
    x1, y1,
    x2: Math.round(x1 + Math.cos(a) * 42),
    y2: Math.round(y1 - Math.sin(a) * 42),
  };
}

/** IV judge label + pill style (design: judge(v, accent)). */
export function judge(v: number, accent: string): [string, CSSProperties] {
  if (v >= 31) return ["Best", { background: accent, color: "#FFFFFF" }];
  if (v >= 30) return ["Fantastic", { background: "#FFE1DC", color: "#9E2219" }];
  if (v >= 26) return ["Very good", { background: "#DDF5EA", color: "#1A6B4A" }];
  if (v >= 16) return ["Pretty good", { background: "#DDEFFF", color: "#1D65B8" }];
  if (v >= 1) return ["Decent", { background: "#F3E6DA", color: "#4A3632" }];
  return ["Not yet", { background: "#F3E6DA", color: "#6E5A55" }];
}

export function reducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}
