// City lookup and distances for the location criterion (Close = within 150 km).

import places from "@/data/places.json";

export interface City {
  name: string;
  lat: number;
  lon: number;
  aliases: string[];
  /** Province code, e.g. "ON". */
  region: string;
}

export const CITIES: City[] = places.cities;

export const CLOSE_KM = 150;

const PROVINCES: Record<string, string> = {
  on: "ON", ont: "ON", ontario: "ON", qc: "QC", quebec: "QC", "québec": "QC", bc: "BC", "british columbia": "BC",
  ab: "AB", alberta: "AB", mb: "MB", manitoba: "MB", sk: "SK", saskatchewan: "SK", ns: "NS", "nova scotia": "NS",
};

function norm(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, " ");
}

/** Resolve a free-text place ("Toronto, ON", "north york") to a known city. */
export function findCity(text: string | null | undefined): City | null {
  if (!text) return null;
  const t = norm(text);
  for (const c of CITIES) {
    if (norm(c.name) === t || c.aliases.includes(t)) return c;
  }
  // "Toronto, Ontario, Canada": the first comma part names the city, and every other part must
  // agree with it, so "London, England" or "Waterloo, Iowa" never become the Ontario cities.
  const [head, ...rest] = t.split(",").map(norm).filter(Boolean);
  if (!head) return null;
  for (const c of CITIES) {
    if (norm(c.name) !== head && !c.aliases.includes(head)) continue;
    if (rest.every((p) => p === "canada" || PROVINCES[p] === c.region)) return c;
  }
  return null;
}

export function distanceKm(a: City, b: City): number {
  const R = 6371;
  const rad = (d: number) => (d * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
