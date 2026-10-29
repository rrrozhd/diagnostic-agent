# diagnostic-agent

A physician's copilot: it suggests possible diagnoses, tests and treatments, links each claim to its source,
and leaves every decision to the doctor.

[![One-page overview: problem, how it works, guardrails, next steps](docs/demo__deck.png)](docs/demo__deck.pdf)

One-page overview as [PDF](docs/demo__deck.pdf) (source: [docs/demo__deck.html](docs/demo__deck.html)).
Full detail: [docs/product-spec.md](docs/product-spec.md).

## Run

```bash
make langfuse   # local Langfuse on :3000; .env already points at it
make dev
make eval
make ci         # lint, test, build, scan, deploy locally, smoke test
```

Add `OPENROUTER_API_KEY` to `.env`. For CI, set repo secrets `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
`OPENROUTER_API_KEY` (plus `TYPESAFE_API_KEY` once `evals/gate.yaml` has judge questions) and variable
`LANGFUSE_BASE_URL` (Langfuse Cloud or your self-hosted URL).

Note: Langfuse currently holds only the eval datasets and experiment runs. Tracing of the copilot's
responses through Langfuse is planned for a later iteration.

## Sample prompt

Synthetic, de-identified case to paste as a new case:

```text
72-year-old woman, 2 days of fever 38.7 C with rigors, dysuria and urinary frequency, and since this morning right flank pain and new confusion (oriented to person only; baseline fully oriented per daughter). HR 112, BP 98/60, RR 22, SpO2 95% on room air. Right costovertebral angle tenderness. No neck stiffness, no rash. History: atrial fibrillation on warfarin (last INR 2.6, two weeks ago); chronic kidney disease stage 3b (eGFR 38 three months ago); type 2 diabetes on sitagliptin. Allergies: sulfonamide antibiotics (Stevens-Johnson syndrome, 2011). No recent travel. Lives alone, independent. What should I consider?
```

## Layout

- `app/`: API, agent graph, tools, guardrails, retrieval, memory
- `packs/<client>/`: client-specific rules, prompts and templates (`PACK=<client>`)
- `evals/`: golden cases and the eval runner
- `frontend/`: React UI, served by the API in production
