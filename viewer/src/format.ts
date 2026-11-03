export const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const ms = (x: number | null | undefined) => (x == null ? "–" : x < 10 ? `${x.toFixed(1)} ms` : `${Math.round(x).toLocaleString()} ms`);
export const secs = (x: number | null | undefined) => (x == null ? "–" : x < 1 ? `${(x * 1000).toFixed(0)} ms` : x < 120 ? `${x.toFixed(1)} s` : `${(x / 60).toFixed(1)} min`);
export const num = (x: number | null | undefined) => (x == null ? "–" : Math.round(x).toLocaleString());
export const usd = (x: number | null | undefined) => (x == null ? "–" : `$${x.toFixed(x < 0.01 ? 4 : 3)}`);
