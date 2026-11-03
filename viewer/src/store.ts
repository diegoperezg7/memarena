import { create } from "zustand";
import type { History, Question, QuestionSet, Results } from "./types";
import type { Lang } from "./i18n";

type Tab = "results" | "questions" | "method";
type Theme = "light" | "dark" | null;

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: preference just is not remembered */
  }
}

function initialLang(): Lang {
  const saved = read("memarena-lang");
  if (saved === "en" || saved === "es") return saved;
  return navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

interface State {
  loading: boolean;
  results: Results | null;
  questionSet: QuestionSet | null;
  history: History | null;
  editable: boolean;
  dirty: boolean;
  savedAt: number | null;
  tab: Tab;
  lang: Lang;
  theme: Theme;
  load: () => Promise<void>;
  setTab: (t: Tab) => void;
  setLang: (l: Lang) => void;
  toggleTheme: () => void;
  updateQuestion: (id: string, patch: Partial<Question>) => void;
  saveQuestions: () => Promise<void>;
}

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export const useStore = create<State>((set, get) => ({
  loading: true,
  results: null,
  questionSet: null,
  history: null,
  editable: false,
  dirty: false,
  savedAt: null,
  tab: "results",
  lang: initialLang(),
  theme: (read("memarena-theme") as Theme) ?? null,
  load: async () => {
    const manifest = (await getJson<Record<string, string>>("data/manifest.json")) ?? {};
    const [results, questionSet, history, ping] = await Promise.all([
      manifest.results ? getJson<Results>(manifest.results) : Promise.resolve(null),
      manifest.questions ? getJson<QuestionSet>(manifest.questions) : Promise.resolve(null),
      manifest.history ? getJson<History>(manifest.history) : Promise.resolve(null),
      getJson<{ editable: boolean }>("api/ping"),
    ]);
    set({
      results,
      questionSet,
      history,
      editable: Boolean(ping?.editable),
      loading: false,
      tab: (["results", "questions", "method"] as Tab[]).find((x) => window.location.hash.includes(x)) ?? (results ? "results" : "questions"),
    });
  },
  setTab: (tab) => set({ tab }),
  setLang: (lang) => {
    write("memarena-lang", lang);
    document.documentElement.lang = lang;
    set({ lang });
  },
  toggleTheme: () => {
    const current =
      get().theme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    write("memarena-theme", next);
    document.documentElement.setAttribute("data-theme", next);
    set({ theme: next });
  },
  updateQuestion: (id, patch) => {
    const qs = get().questionSet;
    if (!qs) return;
    set({
      questionSet: { ...qs, questions: qs.questions.map((q) => (q.id === id ? { ...q, ...patch } : q)) },
      dirty: true,
    });
  },
  saveQuestions: async () => {
    const qs = get().questionSet;
    if (!qs) return;
    const body = JSON.stringify(qs, null, 1);
    if (get().editable) {
      const r = await fetch("api/questions", { method: "PUT", body, headers: { "Content-Type": "application/json" } });
      if (r.ok) set({ dirty: false, savedAt: Date.now() });
      return;
    }
    const url = URL.createObjectURL(new Blob([body], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "questions.json";
    a.click();
    URL.revokeObjectURL(url);
    set({ dirty: false, savedAt: Date.now() });
  },
}));
