// Small building blocks shared by the grid and the Dex entry.

import type { CSSProperties } from "react";
import type { AvatarShape } from "@/lib/design";

interface IconProps {
  d: string;
  size: number;
  stroke?: string;
  strokeWidth?: number;
  fill?: string;
  /** Pass null to omit (some design icons set no linecap / linejoin). */
  linecap?: "round" | null;
  linejoin?: "round" | null;
  style?: CSSProperties;
  /** When set, the icon is announced (role="img" + aria-label); otherwise it is aria-hidden. */
  label?: string;
}

/** A 24x24 stroked path icon, as used throughout the design file. */
export function Icon({ d, size, stroke = "currentColor", strokeWidth = 2.2, fill = "none", linecap = "round", linejoin = "round", style, label }: IconProps) {
  const a11y = label ? { role: "img" as const, "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg
      {...a11y}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill}
      stroke={stroke}
      strokeWidth={strokeWidth}
      strokeLinecap={linecap ?? undefined}
      strokeLinejoin={linejoin ?? undefined}
      style={style}
    >
      <path d={d} />
    </svg>
  );
}

/** Eight sparks that fly out when someone is shortlisted. */
export function Burst() {
  return (
    <span className="burst" aria-hidden="true">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
        <span key={i} className={"spark s" + i} />
      ))}
    </span>
  );
}

/** The abstract avatar drawing (inside the round avatar frame). */
export function AvatarArt({ av, bg }: { av: AvatarShape; bg: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 100 100" width="100%" height="100%">
      <rect x={av.rx} y={av.ry} width={av.rs} height={av.rs} rx={10} fill={bg} transform={av.rt} />
      <circle cx={av.cx} cy={av.cy} r={av.cr} fill={av.cf} />
      <line x1={av.x1} y1={av.y1} x2={av.x2} y2={av.y2} stroke="#FFFFFF" strokeWidth={6} strokeLinecap="round" />
    </svg>
  );
}
