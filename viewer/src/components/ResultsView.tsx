import { Fragment, useMemo, useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronRight, Clock, X } from "lucide-react";
import { useStore } from "../store";
import { useT } from "../i18n";
import { ms, num, pct, secs, usd } from "../format";
import type { Answer } from "../types";

export default function ResultsView() {
  const r = useStore((s) => s.results)!;
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  const [cat, setCat] = useState<string>("all");
  const m = r.meta;
  const systems = useMemo(
    () =>
      [...r.systems].sort(
        (a, b) => (r.summary[b.name]?.accuracy ?? -1) - (r.summary[a.name]?.accuracy ?? -1),
      ),
    [r],
  );
  const answers = useMemo(() => {
    const map = new Map<string, Answer>();
    for (const a of r.answers) map.set(`${a.system}::${a.question_id}`, a);
    return map;
  }, [r]);
  const questions = r.questions.filter((q) => cat === "all" || q.category === cat);
  const best = Math.max(...systems.map((s) => r.summary[s.name]?.accuracy ?? 0));

  return (
    <div className="stack">
      <section className="card meta">
        <div className="meta-head">
          {m.recorded ? (
            <span className="badge accent">
              <Clock size={14} /> {t.recorded} · {m.created_at.slice(0, 10)}
            </span>
          ) : null}
          {m.status === "aborted" ? (
            <span className="badge warn">
              <AlertTriangle size={14} /> {t.aborted}: {m.abort_reason}
            </span>
          ) : null}
          {m.recorded ? <span className="muted small">{t.recordedNote}</span> : null}
        </div>
        <dl className="meta-grid">
          <div><dt>{t.answerModel}</dt><dd className="mono">{m.answer_model}</dd></div>
          <div><dt>{t.judgeModel}</dt><dd className="mono">{m.judge_model}</dd></div>
          <div><dt>{t.embedModel}</dt><dd className="mono">{m.embed_model}</dd></div>
          <div><dt>{t.memoryLlm}</dt><dd className="mono">{m.memory_llm}</dd></div>
          <div>
            <dt>{t.history}</dt>
            <dd>
              {m.history.sessions} {t.sessions} · {num(m.history.messages)} {t.messages} · ~{num(m.history.approx_tokens)} {t.tokens}
            </dd>
          </div>
          <div><dt>{t.hardware}</dt><dd>{m.hardware}</dd></div>
          {m.judge_audit ? (
            <div className="wide">
              <dt>{t.judgeAudit}</dt>
              <dd>{m.judge_audit}</dd>
            </div>
          ) : null}
          {m.dataset?.name ? (
            <div className="wide">
              <dt>{t.data}</dt>
              <dd>
                {m.dataset.url ? <a href={m.dataset.url} target="_blank" rel="noreferrer">{m.dataset.name}</a> : m.dataset.name}
                {m.dataset.license ? ` · ${m.dataset.license}` : ""}
              </dd>
            </div>
          ) : null}
        </dl>
      </section>

      <section className="leaders">
        {systems.map((s) => {
          const sm = r.summary[s.name];
          return (
            <div key={s.name} className={"card leader" + (sm?.accuracy === best && !s.error ? " top" : "")}>
              <div className="leader-head">
                <span className="sys-name">{s.name}</span>
                <span className={"chip " + (s.kind === "baseline" ? "" : "accent")}>
                  {s.kind === "baseline" ? t.baseline : t.memory}
                </span>
              </div>
              {s.error ? (
                <div className="err small">{s.error}</div>
              ) : (
                <>
                  <div className="big">{pct(sm?.accuracy)}</div>
                  <div className="bar"><span style={{ width: `${(sm?.accuracy ?? 0) * 100}%` }} /></div>
                  <div className="muted small">
                    {sm?.correct}/{sm?.n} {t.correct} · p95 {ms(sm?.latency_p95_ms)} · {usd(sm?.cost_usd)}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </section>

      <section className="card">
        <h2>{t.byCategory}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t.system}</th>
                <th className="num">{t.accuracy}</th>
                {r.categories.map((c) => (
                  <th key={c} className="num">{t.cats[c]}</th>
                ))}
                <th className="num">{t.p50}</th>
                <th className="num">{t.p95}</th>
                <th className="num">{t.ingest}</th>
                <th className="num">{t.promptTokens}</th>
                <th className="num">{t.cost}</th>
              </tr>
            </thead>
            <tbody>
              {systems.map((s) => {
                const sm = r.summary[s.name];
                return (
                  <tr key={s.name}>
                    <td><span className="sys-name">{s.name}</span></td>
                    <td className="num strong">{pct(sm?.accuracy)}</td>
                    {r.categories.map((c) => (
                      <td key={c} className="num">
                        {sm?.by_category[c] ? (
                          <span title={`${sm.by_category[c].correct}/${sm.by_category[c].n}`}>{pct(sm.by_category[c].accuracy)}</span>
                        ) : "–"}
                      </td>
                    ))}
                    <td className="num mono">{ms(sm?.latency_p50_ms)}</td>
                    <td className="num mono">{ms(sm?.latency_p95_ms)}</td>
                    <td className="num mono">{secs(sm?.ingest_seconds)}</td>
                    <td className="num mono">{num(sm?.avg_prompt_tokens)}</td>
                    <td className="num mono">{usd(sm?.cost_usd)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">{t.latencyNote}</p>
        <p className="muted small">
          {t.totalSpent}: <span className="mono">{usd(r.cost.total_usd)}</span>
        </p>
      </section>

      <section className="card">
        <div className="section-head">
          <h2>{t.perQuestion}</h2>
          <select value={cat} onChange={(e) => setCat(e.target.value)} aria-label={t.filter}>
            <option value="all">{t.all}</option>
            {r.categories.map((c) => (
              <option key={c} value={c}>{t.cats[c]}</option>
            ))}
          </select>
        </div>
        <p className="muted small">{t.perQuestionHint}</p>
        <p className="muted small legend">
          {t.marksLegend}{" "}
          {systems.map((s, i) => (
            <span key={s.name}>
              {i ? " · " : ""}
              <span className="mono">{s.name}</span>
            </span>
          ))}
        </p>
        <div className="qlist">
          {questions.map((q) => {
            const isOpen = open === q.id;
            return (
              <Fragment key={q.id}>
                <button className={"qrow" + (isOpen ? " open" : "")} onClick={() => setOpen(isOpen ? null : q.id)} aria-expanded={isOpen}>
                  {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <span className="qtext">
                    <span className="chip">{t.cats[q.category]}</span> {q.question}
                  </span>
                  <span className="marks">
                    {systems.map((s) => {
                      const a = answers.get(`${s.name}::${q.id}`);
                      return (
                        <span key={s.name} title={s.name} className={"mark " + (a ? (a.correct ? "ok" : "bad") : "none")}>
                          {a ? a.correct ? <Check size={13} /> : <X size={13} /> : "·"}
                        </span>
                      );
                    })}
                  </span>
                </button>
                {isOpen ? (
                  <div className="qdetail">
                    <div className="gold">
                      <span className="label">{t.gold}</span> {q.answer}
                      {q.question_date ? <span className="muted small"> · {t.questionDate} {q.question_date}</span> : null}
                    </div>
                    <div className="answers">
                      {systems.map((s) => {
                        const a = answers.get(`${s.name}::${q.id}`);
                        if (!a) return null;
                        return (
                          <div key={s.name} className={"answer " + (a.correct ? "ok" : "bad")}>
                            <div className="answer-head">
                              <span className="sys-name">{s.name}</span>
                              <span className={"badge " + (a.correct ? "ok" : "bad")}>
                                {a.correct ? <Check size={13} /> : <X size={13} />} {a.correct ? t.correct : t.wrong}
                              </span>
                              <span className="muted small mono">{ms(a.retrieval_ms)} · {num(a.prompt_tokens)} tok{a.truncated ? ` · ${t.truncated}` : ""}</span>
                            </div>
                            <p><span className="label">{t.response}</span> {a.response}</p>
                            <p className="muted small"><span className="label">{t.judge}</span> {a.judge_reason}</p>
                            <details>
                              <summary className="small">{t.retrieved} ({a.retrieved.length})</summary>
                              {a.retrieved.length ? (
                                <ol className="retrieved">
                                  {a.retrieved.map((x, i) => <li key={i}>{x}</li>)}
                                </ol>
                              ) : (
                                <p className="muted small">{t.nothingRetrieved}</p>
                              )}
                            </details>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </Fragment>
            );
          })}
        </div>
      </section>
    </div>
  );
}
