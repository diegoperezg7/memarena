import { BarChart3, FileQuestion, Moon, ScrollText, Sun } from "lucide-react";
import { useStore } from "../store";
import { useT } from "../i18n";
import Icon from "./Icon";

export default function Header() {
  const { tab, setTab, lang, setLang, toggleTheme, results, questionSet } = useStore();
  const t = useT();
  const tabs = [
    { id: "results" as const, label: t.results, icon: BarChart3, show: Boolean(results) },
    { id: "questions" as const, label: t.questions, icon: FileQuestion, show: Boolean(questionSet || results) },
    { id: "method" as const, label: t.method, icon: ScrollText, show: Boolean(results) },
  ].filter((x) => x.show);
  return (
    <header className="header">
      <div className="header-row">
        <div className="brand">
          <Icon />
          <div>
            <div className="brand-name">memarena</div>
            <div className="brand-tag muted">{t.tagline}</div>
          </div>
        </div>
        <div className="header-actions">
          <div className="seg" role="group" aria-label={t.language}>
            {(["en", "es"] as const).map((l) => (
              <button key={l} className={lang === l ? "on" : ""} onClick={() => setLang(l)} aria-pressed={lang === l}>
                {l.toUpperCase()}
              </button>
            ))}
          </div>
          <button className="icon-btn" onClick={toggleTheme} aria-label={t.theme} title={t.theme}>
            <Sun className="only-dark" size={18} />
            <Moon className="only-light" size={18} />
          </button>
        </div>
      </div>
      <nav className="tabs">
        {tabs.map(({ id, label, icon: I }) => (
          <button key={id} className={tab === id ? "tab on" : "tab"} onClick={() => setTab(id)}>
            <I size={16} />
            {label}
          </button>
        ))}
      </nav>
    </header>
  );
}
