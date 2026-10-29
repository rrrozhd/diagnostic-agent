# Plan: end-to-end MVP (one step)

## Build

- `app/graph.py`: guardrail → refusal | agent, compiled with a checkpointer so
  the physician's selection turn continues the same `thread_id`.
- `app/guardrails.py`: Jev questions on the initial prompt (`jev-1.13.0`),
  pass/fail thresholds in config.
- `app/agents/`: one deep agent (`create_deep_agent`, model
  `openrouter:anthropic/claude-sonnet-5.5`) with subagents
  `diagnostic_researcher` and `treatment_researcher`; `response_format` schemas
  carry source IDs per claim.
- `app/tools.py`: PubMed E-utilities search/fetch; (done in another session: `query_reference_db`, read-only SQL over `data/reference.db`, replacing a fixed-query PrimeKG lookup over
  `data/primekg`); drug information via openFDA/DailyMed labels.
- `packs/default/refusal.md`: the predefined refusal text.
- `app/main.py`: `POST /api/chat {thread_id, message}`.
- `evals/e2e_cases.jsonl`: two synthetic cases (distinct presentations; one
  has a drug allergy relevant to first-line treatment) and one guardrail-fail prompt.
- `scripts/e2e.py`: drives both turns over HTTP, writes one JSON transcript
  per run (inputs, outputs, cost, trace id).

## Acceptance

1. `uv run pytest` passes with a nonzero count, including both graph branches
   with a fake model and fake Jev.
2. `uv run python scripts/e2e.py` against the running service (real OpenRouter,
   Jev, PubMed, openFDA) exits 0 and writes transcripts for 2 cases + 1 refusal.
3. Per case, turn 1 (initial prompt): ≥3 candidate diagnoses, each with ≥1
   source whose ID resolves (PMID via E-utilities esummary, or an existing
   PrimeKG node id) and ≥1 discriminating test.
4. Per case, turn 2 (physician selects one listed diagnosis, same `thread_id`):
   ≥2 treatment options, each with ≥1 resolving source.
5. The allergy case marks any option in the allergen's drug class with a
   warning instead of recommending it plainly.
6. No app-produced field matches `packs/default/banned_phrases.txt`.
7. The refusal prompt returns `refusal.md` verbatim, with no agent or model
   call in its trace.
8. Each transcript records the run's cost.

## Config, not code

Model ids, Jev build and thresholds, API base URLs, rate limits, timeouts
(`ChatOpenRouter` timeout is in ms) and the refusal text live in config or the
pack. Run the code audit before recording evidence.

## Boundary cases

- Selection names a diagnosis not in the turn-1 list: ask the physician to pick
  from the list; no treatment research.
- A source API is down: claim shown as "source not checked", run still completes.
- Jev call fails: treat as guardrail fail (refusal), logged.

## Restrictions

- Synthetic, de-identified cases only.
- Never set `temperature`/`top_p`/`top_k`; structured output via
  `json_schema` / `ProviderStrategy`.
- Measure one paid call's cost first; stop and ask if a full run is estimated above $5.
- No commits or pushes without the owner's instruction.
