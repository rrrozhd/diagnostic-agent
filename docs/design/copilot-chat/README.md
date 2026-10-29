# Copilot chat design (v0 mockups)

Chat-first design for the physician's copilot: each case is a chat, and each
research step is an artifact opened in a side panel. Live canvas (private until
shared): https://claude.ai/artifact/7xJWgoJvJnQrKqsMxuqxNf

Files are the canvas source (`.dc.html` design components). They render only
inside that canvas, not in the app.

- `Main.dc.html`: case chat. Interactive: working-diagnosis gate, undo,
  citation → source view, artifact tabs.
- `NewCase.dc.html`: new-case empty state.
- `canvas.json`: canvas layout.

## What the UI expects from the backend

To reconcile once the worker lands. Placeholders in the mockups (`[—]`,
`[version]`, `[Interaction DB — licence open]`) mark data it must supply.

| Artifact | Fields the UI shows |
|---|---|
| Inputs | field, parsed value, code (SNOMED/RxNorm), status: recorded / none known / partial / not recorded |
| Differential | name, ICD code, tier (more likely / possible / less likely, important to exclude), can't-miss flag, verified or model-proposed-unverified, findings for / against / missing, per-claim source keys, model-reasoning lines |
| Tests | test, likelihood shift per candidate (large / moderate / small / none), accuracy only when sourced, cost and burden, blocking gaps |
| Treatment | runs only for a marked working diagnosis; option, evidence type, safety-check results (allergy, interactions, dosing, pregnancy) with complete/incomplete state |
| Source | key, claim, matched excerpt, identifier, evidence type, abstract-only vs full text, support verdict, retraction or version check, retrieval time |

Each artifact carries a version and timestamp; chat messages reference artifacts by id.

Not designed yet: artifact version history, choosing a working diagnosis other
than the top candidate, EHR/FHIR intake.
