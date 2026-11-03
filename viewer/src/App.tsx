import { useEffect } from "react";
import { useStore } from "./store";
import { useT } from "./i18n";
import Header from "./components/Header";
import ResultsView from "./components/ResultsView";
import QuestionsView from "./components/QuestionsView";
import MethodView from "./components/MethodView";

export default function App() {
  const { load, loading, tab, results, questionSet, lang } = useStore();
  const t = useT();
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <div className="app">
      <Header />
      <main className="main">
        {loading ? null : !results && !questionSet ? (
          <div className="card empty">
            <h2>{t.noData}</h2>
            <p className="muted">{t.noDataHint}</p>
          </div>
        ) : tab === "results" && results ? (
          <ResultsView />
        ) : tab === "questions" ? (
          <QuestionsView />
        ) : (
          <MethodView />
        )}
      </main>
      <footer className="footer muted">
        memarena {results?.meta.version ?? ""} ·{" "}
        <a href="https://github.com/diegoperezg7/memarena" target="_blank" rel="noreferrer">
          github.com/diegoperezg7/memarena
        </a>
      </footer>
    </div>
  );
}
