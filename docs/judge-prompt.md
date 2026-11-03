# Judge prompt

memarena grades every answer with an LLM judge. This is the exact prompt, copied from
[`src/memarena/prompts.py`](../src/memarena/prompts.py). The judge model, provider and temperature (0)
are written into every `results.json`, so a run can always be audited.

## System

```text
You grade answers from a memory system. Reply with JSON only: {"correct": true|false, "reason": "<one short sentence>"}.
```

## User

```text
Question category: {category}
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

Reply with JSON only.
```

## Answer prompt (same for every system)

Every memory system only decides **what context** reaches the answer model. The answer model and this
prompt are the same for all systems, so differences in accuracy come from memory, not from prompting.

```text
You answer questions about a user's past conversations with an AI assistant. Use only the memory context provided. Be brief: one or two sentences. If the context does not contain the answer, reply exactly: I don't know.

Memory context:
<<<
{context}
>>>

Today's date: {question_date}
Question: {question}
Answer:
```
