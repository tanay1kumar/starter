// City lookup and distances for the location criterion (Close = within 150 km).

import places from "@/data/places.json";

export interface City {
  name: string;
  lat: number;
  lon: number;
  aliases: string[];
}

export const CITIES: City[] = places.cities;

export const CLOSE_KM = 150;

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
  // "Toronto, Ontario, Canada" -> try the first comma part
  const head = norm(t.split(",")[0]);
  for (const c of CITIES) {
    if (norm(c.name) === head || c.aliases.includes(head)) return c;
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
