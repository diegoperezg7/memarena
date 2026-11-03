let locale = "en-US";
export const setLocale = (lang: string) => {
  locale = lang === "es" ? "es-ES" : "en-US";
};
export const pct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const ms = (x: number | null | undefined) => (x == null ? "–" : x < 10 ? `${x.toFixed(1)} ms` : `${Math.round(x).toLocaleString(locale)} ms`);
export const secs = (x: number | null | undefined) => (x == null ? "–" : x < 1 ? `${(x * 1000).toFixed(0)} ms` : x < 120 ? `${x.toFixed(1)} s` : `${(x / 60).toFixed(1)} min`);
export const num = (x: number | null | undefined) => (x == null ? "–" : Math.round(x).toLocaleString(locale));
export const usd = (x: number | null | undefined) => (x == null ? "–" : `$${x.toFixed(x < 0.01 ? 4 : 3)}`);
