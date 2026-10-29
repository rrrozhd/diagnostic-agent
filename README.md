# diagnostic-agent

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

## Layout

- `app/`: API, agent graph, tools, guardrails, retrieval, memory
- `packs/<client>/`: client-specific rules, prompts and templates (`PACK=<client>`)
- `evals/`: golden cases and the eval runner
- `frontend/`: React UI, served by the API in production
