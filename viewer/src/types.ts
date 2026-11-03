export type Category = "single-session" | "multi-session" | "temporal" | "knowledge-update" | "abstention";

export interface Evidence {
  session_id: string;
  message_index: number | null;
}

export interface Question {
  id: string;
  category: Category;
  question: string;
  answer: string;
  evidence: Evidence[];
  question_date: string | null;
  status: "pending" | "approved" | "rejected";
  source: string;
  note: string;
}

export interface QuestionSet {
  version: number;
  meta: Record<string, unknown>;
  questions: Question[];
}

export interface Message {
  role: string;
  content: string;
  timestamp: string | null;
}

export interface Session {
  id: string;
  title: string;
  started_at: string | null;
  source: string;
  messages: Message[];
}

export interface History {
  version: number;
  sessions: Session[];
}

export interface SystemEntry {
  name: string;
  kind: "baseline" | "memory";
  description: string;
  ingest_seconds?: number;
  ingest_tokens?: number;
  ingest_cost?: number;
  error?: string;
}

export interface Answer {
  system: string;
  question_id: string;
  category: Category;
  response: string;
  correct: boolean;
  judge_reason: string;
  retrieval_ms: number;
  context_tokens_approx: number;
  truncated: boolean;
  prompt_tokens: number;
  completion_tokens: number;
  answer_cost: number;
  retrieval_cost: number;
  judge_cost: number;
  retrieved: string[];
}

export interface SystemSummary {
  n: number;
  correct: number;
  accuracy: number | null;
  by_category: Record<string, { n: number; correct: number; accuracy: number }>;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  ingest_seconds: number | null;
  avg_prompt_tokens: number | null;
  cost_usd: number;
  judge_cost_usd: number;
  error: string | null;
}

export interface Results {
  meta: {
    tool: string;
    version: string;
    created_at: string;
    hardware: string;
    answer_model: string;
    judge_model: string;
    embed_model: string;
    memory_llm: string;
    top_k: number;
    max_context_tokens: number;
    history: { sessions: number; messages: number; approx_tokens: number; first_date: string | null; last_date: string | null };
    dataset: { name?: string; license?: string; url?: string };
    status: string;
    abort_reason?: string;
    recorded?: boolean;
    judge_audit?:
      | string
      | {
          checked: number;
          false_positives: Record<string, number>;
          false_negatives: Record<string, number>;
          categories?: string[];
          corrected_accuracy?: Record<string, number>;
        };
  };
  prompts: Record<string, string>;
  categories: Category[];
  systems: SystemEntry[];
  questions: Question[];
  answers: Answer[];
  summary: Record<string, SystemSummary>;
  cost: { total_usd: number; by_provider: Record<string, number> };
}
