import { useMemo, useState } from "react";
import { Check, Download, Save, X } from "lucide-react";
import { useStore } from "../store";
import { useT } from "../i18n";
import type { Question } from "../types";

export default function QuestionsView() {
  const { questionSet, results, history, editable, dirty, savedAt, updateQuestion, saveQuestions } = useStore();
  const t = useT();
  const [filter, setFilter] = useState<string>("all");
  const qs: Question[] = questionSet?.questions ?? results?.questions ?? [];
  const canEdit = Boolean(questionSet);
  const sessions = useMemo(() => new Map((history?.sessions ?? []).map((s) => [s.id, s])), [history]);
  const shown = qs.filter((q) => filter === "all" || q.status === filter || q.category === filter);
  const counts = { pending: 0, approved: 0, rejected: 0 } as Record<string, number>;
  qs.forEach((q) => (counts[q.status] = (counts[q.status] ?? 0) + 1));

  return (
    <div className="stack">
      <section className="card">
        <p className="muted">{t.reviewHint}</p>
        <div className="toolbar">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label={t.filter}>
            <option value="all">{t.all} ({qs.length})</option>
            <option value="pending">{t.pending} ({counts.pending})</option>
            <option value="approved">{t.approved} ({counts.approved})</option>
            <option value="rejected">{t.rejected} ({counts.rejected})</option>
            {Object.entries(t.cats).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          {canEdit ? (
            <button className="btn primary" onClick={saveQuestions} disabled={!dirty && editable}>
              {editable ? <Save size={16} /> : <Download size={16} />}
              {editable ? t.save : t.download}
            </button>
          ) : null}
          {dirty ? <span className="badge warn">{t.unsaved}</span> : savedAt ? <span className="badge ok">{t.saved}</span> : null}
        </div>
      </section>
      {shown.map((q) => (
        <section key={q.id} className="card qcard">
          <div className="qcard-head">
            <span className="chip">{t.cats[q.category] ?? q.category}</span>
            <span className={"chip status-" + q.status}>{t[q.status]}</span>
            <span className="muted small mono">{q.id}</span>
            {q.question_date ? <span className="muted small">{t.questionDate} {q.question_date}</span> : null}
          </div>
          {canEdit ? (
            <>
              <label className="field">
                <span>{t.questions}</span>
                <textarea rows={2} value={q.question} onChange={(e) => updateQuestion(q.id, { question: e.target.value })} />
              </label>
              <label className="field">
                <span>{t.gold}</span>
                <textarea rows={2} value={q.answer} onChange={(e) => updateQuestion(q.id, { answer: e.target.value })} />
              </label>
            </>
          ) : (
            <>
              <p className="qtitle">{q.question}</p>
              <p><span className="label">{t.gold}</span> {q.answer}</p>
            </>
          )}
          <div className="evidence">
            <span className="label">{t.evidence}</span>
            {q.evidence.length === 0 ? (
              <p className="muted small">{t.noEvidence}</p>
            ) : (
              q.evidence.map((e, i) => {
                const s = sessions.get(e.session_id);
                const msg = s && e.message_index != null ? s.messages[e.message_index] : null;
                return (
                  <blockquote key={i}>
                    <div className="muted small mono">
                      {e.session_id}
                      {e.message_index != null ? ` #${e.message_index}` : ""}
                      {s?.started_at ? ` · ${s.started_at.slice(0, 10)}` : ""}
                      {!s && history ? ` · ${t.missingSession}` : ""}
                    </div>
                    {msg ? <div className="small">{msg.role}: {msg.content.length > 500 ? msg.content.slice(0, 500) + "…" : msg.content}</div> : null}
                  </blockquote>
                );
              })
            )}
          </div>
          {canEdit ? (
            <div className="toolbar">
              <button className={"btn" + (q.status === "approved" ? " ok-on" : "")} onClick={() => updateQuestion(q.id, { status: "approved" })}>
                <Check size={16} /> {t.approve}
              </button>
              <button className={"btn" + (q.status === "rejected" ? " bad-on" : "")} onClick={() => updateQuestion(q.id, { status: "rejected" })}>
                <X size={16} /> {t.reject}
              </button>
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
