"""Every prompt memarena sends. The judge prompt is published verbatim in docs/judge-prompt.md."""

ANSWER_SYSTEM = (
    "You answer questions about a user's past conversations with an AI assistant. "
    "Use only the memory context provided. Be brief: one or two sentences. "
    "If the context does not contain the answer, reply exactly: I don't know."
)

ANSWER_USER = """Memory context:
<<<
{context}
>>>

Today's date: {question_date}
Question: {question}
Answer:"""

JUDGE_SYSTEM = (
    "You grade answers from a memory system. Reply with JSON only: "
    '{"correct": true|false, "reason": "<one short sentence>"}.'
)

JUDGE_USER = """Question category: {category}
Question: {question}
Gold answer: {answer}
Response to grade: {response}

Rules:
- correct = true if the response contains the gold answer or something equivalent to it.
  Extra details are fine as long as they do not contradict the gold answer.
- If the response only covers part of what the gold answer requires, correct = false.
- Category "temporal": for counts of days, weeks or months, accept an off-by-one difference.
- Category "knowledge-update": the response must give the most recent value. Mentioning the old value
  as history is fine; giving the old value as the current one is wrong.
- Category "abstention": the gold answer says the information is not in the history. correct = true only
  if the response says it does not know or that the information was never mentioned.
  Any invented answer is wrong.

Reply with JSON only."""

QA_SYSTEM = (
    "You write test questions for a memory benchmark from a user's real chat history. "
    "Questions must be about facts the USER said about themselves, their life, plans, preferences, "
    "projects or possessions, not general knowledge the assistant explained. "
    "Reply with JSON only."
)

QA_INSTRUCTIONS = {
    "single-session": (
        "Write ONE question answerable from a single fact the user stated in ONE of these sessions. "
        "The answer must be short (a name, number, place, date or short phrase)."
    ),
    "multi-session": (
        "Write ONE question that can only be answered by combining facts the user stated in AT LEAST TWO "
        "different sessions below (for example a total, a comparison, or a list across sessions)."
    ),
    "temporal": (
        "Write ONE question about time that needs the session dates: how long between two events, "
        "which happened first, or what the user was doing around a date. Use the dates given."
    ),
    "knowledge-update": (
        "Find a fact about the user that CHANGED between an earlier and a later session below "
        "(a new job, a moved date, a changed preference, an updated number). Write ONE question whose "
        'correct answer is the LATEST value. If nothing changed, reply {"skip": true}.'
    ),
    "abstention": (
        "Write ONE question that sounds like it is about these sessions and uses their topic, but whose "
        "answer was NEVER stated. The gold answer must be: The history does not say."
    ),
}

QA_USER = """{instructions}

Sessions (each message has an index in brackets):
{sessions}

Reply with JSON only:
{{"question": "...", "answer": "...", "evidence": [{{"session_id": "...", "message_index": 0}}]}}
Evidence must point to the user messages that contain the answer (empty list for abstention).
If you cannot write a good question from these sessions, reply {{"skip": true}}."""
