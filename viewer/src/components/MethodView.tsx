import { useStore } from "../store";
import { useT } from "../i18n";

export default function MethodView() {
  const r = useStore((s) => s.results)!;
  const t = useT();
  return (
    <div className="stack">
      <section className="card">
        <p>{t.methodIntro}</p>
        <h2>{t.systemsUsed}</h2>
        <ul className="plain">
          {r.systems.map((s) => (
            <li key={s.name}>
              <span className="sys-name">{s.name}</span> <span className="muted small">{s.description}</span>
            </li>
          ))}
        </ul>
      </section>
      <section className="card">
        <h2>{t.judgePrompt}</h2>
        <pre className="code">{r.prompts.judge_system}</pre>
        <pre className="code">{r.prompts.judge_user}</pre>
      </section>
      <section className="card">
        <h2>{t.answerPrompt}</h2>
        <pre className="code">{r.prompts.answer_system}</pre>
        <pre className="code">{r.prompts.answer_user}</pre>
      </section>
    </div>
  );
}
