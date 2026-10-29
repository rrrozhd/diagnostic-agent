// shortcut: hand-mirrored from app/schemas.py and app/main.py because /api/chat returns a plain dict
// (no OpenAPI schema to generate from); update both together, or type the route's response model.

export type Source = {
  kind: "pubmed" | "reference_db" | "drug_label"
  id: string
  title: string
  url: string
  excerpt: string
  access: "abstract" | "full_text" | "database" | "label"
}

export type Claim = { text: string; sources: Source[] }

export type Likelihood = "more likely" | "possible" | "less likely but important to exclude"

export type Candidate = {
  name: string
  likelihood: Likelihood
  cant_miss: boolean
  findings_for: Claim[]
  findings_against: Claim[]
  missing_findings: string[]
  discriminating_tests: Claim[]
}

export type Differential = {
  candidates: Candidate[]
  missing_inputs: string[]
  evidence_gaps: string[]
}

export type TreatmentOption = {
  name: string
  line: string
  evidence_level: string
  rationale: Claim[]
  warnings: Claim[]
}

export type TreatmentPlan = {
  diagnosis: string
  options: TreatmentOption[]
  evidence_gaps: string[]
}

export type CopilotResponse = {
  kind: "differential" | "treatment" | "clarification"
  message: string
  differential: Differential | null
  treatment: TreatmentPlan | null
}

export type ChatResult = {
  thread_id: string
  refused: boolean
  refusal: string | null
  response: CopilotResponse | null
  cost_usd: number
  model_calls: number
  trace_id: string | null
}

export async function chat(threadId: string, message: string): Promise<ChatResult> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, message }),
  })
  if (!res.ok) throw new Error(`The copilot service returned ${res.status}.`)
  return res.json()
}

// Wording the backend's e2e run uses for the selection turn (scripts/e2e.py TURN2).
export const treatmentRequest = (diagnosis: string) =>
  `I'd like to consider ${diagnosis}. What are the treatment options for this patient?`

// Source URLs are model-produced: only link plain web addresses.
export function safeUrl(url: string): string | null {
  try {
    const u = new URL(url)
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : null
  } catch {
    return null
  }
}
