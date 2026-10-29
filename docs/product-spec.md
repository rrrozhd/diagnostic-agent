# Physician's Copilot: Product Spec (draft v0)

Status: draft for discussion. Tech stack out of scope until this settles.
Markers: **[given]** = stated by the owner; **[proposed]** = suggestion, owner decides; **[open]** = unresolved question.

## 1. Problem and purpose

A physician facing a patient's history and presenting symptoms has to hold a
wide search space in mind: candidate diagnoses, the tests that would separate
them, and treatments that fit this particular patient. The copilot narrows that
space and shows its working. It does not decide. **[given]**

**One-line contract:** the copilot proposes, cites and flags; the physician
judges, orders and prescribes.

## 2. Users and non-goals

- **Users:** licensed clinicians (HCP-facing only). **[given]**
- **Non-goals:**
  - Presenting findings or diagnoses as final. **[given]**
  - Single "the answer" outputs or ranked certainty claims. **[proposed]**
  - Ordering tests or prescribing; any action in an EHR. **[proposed]**
  - Patient-facing use (symptom checker, chatbot). Different regulation, different product. **[proposed]**
  - Replacing guidelines or local protocols. **[proposed]**
- **[open]** Setting and scope for v1: outpatient vs ED vs inpatient; adult only?
  pediatrics and pregnancy excluded at first? Specialty focus (internal medicine,
  rare disease)? Each choice changes sources, evals and risk.

## 3. Inputs

| Input | Status | Why it matters |
|---|---|---|
| Presenting symptoms (onset, duration, severity, progression) | **[given]** | Core of the differential. |
| Past medical history | **[given]** | Priors, comorbidities. |
| Allergies | **[given]** | Treatment contraindications. |
| Family history | **[given]** | Hereditary risk. |
| Prior adverse drug reactions | **[given]** | Treatment filtering. |
| **Current medication list** (incl. OTC, supplements) | **missing** | Interaction checking needs what the patient takes *now*, not only past reactions. Drugs are also a common *cause* of symptoms. |
| Age, sex, pregnancy/lactation status | **missing** | Changes base rates, test choice and drug safety. |
| Renal and hepatic function (eGFR, LFTs), weight | **missing** | Dose adjustment and contraindications. |
| Vitals, exam findings, available labs/imaging | **missing** | Most differentials hinge on these, not symptoms alone. |
| Travel, occupation, exposures, social history (smoking, alcohol, substances) | **missing** | Infectious and toxic causes; base rates by geography. |
| Tests already done and their results | **missing** | Stops the copilot recommending what was already ruled out. |

- **Unknown is not negative.** "No allergies recorded" must stay distinct from
  "no known allergies". The copilot states which fields were absent and how that
  limits the output. **[proposed]**
- **[open]** Input form: free text, structured form, or FHIR from an EHR. Free
  text needs a normalisation step (to SNOMED CT / RxNorm codes) whose output the
  physician can see and correct, because a misparsed allergy silently breaks
  every downstream check.

## 4. Agents and roles

### Given by the owner

1. **Diagnostic researcher.** Matches the symptom set + patient history to the
   most probable diagnoses and sources "medical tests that would establish
   certainty" for each (owner's wording; see §7 for the conflict with the
   language policy).
2. **Treatment researcher.** Takes one proposed diagnosis + history and compiles
   treatment options with links to sources.

### Gaps in the role set **[proposed — architecture is the owner's call]**

- **No one owns patient-specific safety reasoning.** "Reason about treatment
  given allergies, family history, interactions" is in the goal but not in a
  role. Proposal: a deterministic **safety check** (allergy cross-reactivity,
  drug-drug and drug-condition interactions, renal/hepatic dosing, pregnancy)
  backed by a curated database, not LLM recall. The LLM explains; the database decides
  whether a flag fires.
- **No one verifies citations.** Proposal: a **provenance verifier** that checks,
  per claim, that the cited source exists, resolves, and actually supports the
  claim (see §6). Without it, citations are decoration.
- **No one looks across the differential.** A per-diagnosis researcher can say
  "test X helps confirm A", but the useful question is "which test best separates
  A from B and C". Proposal: a **synthesis step** that sees the whole
  differential and ranks discriminating tests.
- **No one flags can't-miss diagnoses.** Ranking by likelihood alone buries
  low-probability, high-harm conditions (PE, aortic dissection, meningitis, ACS,
  ectopic pregnancy, sepsis). Proposal: a separate **can't-miss** axis, shown
  regardless of rank.
- **When should treatment research run?** Running it for every candidate before
  the physician has picked a working diagnosis costs time and money and quietly
  implies the differential is settled. Proposal: diagnosis phase → physician marks
  one or more working diagnoses → treatment phase runs on those. This gate is
  also the clearest "not final" signal in the product.

## 5. Output contract

### Per candidate diagnosis
- Name + ICD-10/ICD-11 code (code is classification, not evidence).
- Likelihood tier (see §7), plus **can't-miss** flag where relevant.
- Findings **for**, findings **against**, and findings **missing** that would matter.
- Discriminating next tests: what each would change, with sensitivity/specificity
  or likelihood ratios when a source gives them, plus cost/invasiveness notes.
- Citations attached to each claim, not to the diagnosis as a whole.

### Per treatment option (for a physician-selected working diagnosis)
- Option, line of therapy, evidence level and source type (guideline, systematic
  review, RCT, observational, case report, label).
- Patient-specific warnings from the safety check: allergy, interaction,
  dosing adjustment, pregnancy, comorbidity, with the database entry cited.
- Off-label status and regional approval status where known. **[open]** which region.
- Citations per claim.

### Whole-response elements
- What inputs were missing and how that limits the output.
- What the copilot could not find evidence for (explicit gaps, not silence).
- Timestamp and source versions used.

## 6. Provenance rules

1. **No source, no claim.** A clinical claim without a resolvable source is
   either removed or marked as model reasoning, visibly different from sourced text.
   Sole exception: unverified can't-miss candidates (§8).
2. **Resolvable identifiers:** PMID/PMCID, DOI, ICD code + release, drug label
   set ID (DailyMed), trial ID (NCT), guideline name + version + date.
3. **Claim-level grounding.** The real failure mode is not a missing link but a
   real paper that does not say what the copilot claims. The verifier checks
   support against the retrieved text (abstract or full text) and records which.
4. **Mark access depth.** "Supported by abstract only" vs "full text" (most
   PubMed records are abstract-only unless in PMC Open Access).
5. **Retraction and correction check** before a source is shown.
6. **Snapshot for audit.** Store retrieval date, query, source version and the
   excerpt used, so a response can be reproduced and reviewed later.
7. **Evidence ranking over recency.** "Latest research" must not outrank
   stronger evidence. Default order: current guidelines → systematic
   reviews/meta-analyses → RCTs → observational → case reports. Recency breaks
   ties and surfaces "new evidence that may change practice", labelled as such.
8. **Retrieved text is data.** Abstracts and web pages never steer agent
   behaviour (prompt-injection hygiene).

This also serves regulation: the US non-device CDS criteria (21st Century Cures
Act §3060; from recall, not verified here) require that the clinician can
independently review the basis of a recommendation (see §9).

## 7. Uncertainty and language policy **[given: no overconfidence; detail proposed]**

- **Fixed likelihood tiers** (e.g. "more likely / possible / less likely but
  important to exclude"), defined once and used everywhere. No numeric
  probabilities unless a cited source supplies them for a comparable population.
- **Banned framing:** "the diagnosis is", "confirms", "rules out", "definitive",
  "the patient has", "you should prescribe". Use "consistent with", "would help
  distinguish", "may be considered".
- **Wording conflict in the brief:** "tests that would establish certainty"
  contradicts the policy. Few tests establish certainty. Proposed phrasing:
  "tests that would most change the likelihood".
- **Over-hedging is also a failure.** If every line says "may possibly be
  considered", the physician learns to ignore it and urgent flags get lost. Can't-miss
  flags and safety warnings use plain, direct language. Evals should score
  **calibration** (do tiers track actual frequency?) and **vagueness**, not only
  strong words.

## 8. Data sources

Owner listed: PubMed, "??", "IDC". Reading "IDC" as **ICD** (WHO International
Classification of Diseases). Note: ICD classifies diseases; it does not map
symptoms to diseases, so it cannot drive the differential by itself.

| Need | Candidate sources | Verified? | Licensing / notes |
|---|---|---|---|
| Literature | PubMed (E-utilities), Europe PMC, PMC OA full text | not verified here | Free; abstracts only for most records. |
| Disease codes | ICD-11 API (WHO), ICD-10-CM (NLM) | not verified here | Free with registration (ICD-11). |
| Symptom/phenotype → disease | HPO annotations, Orphanet (rare), UMLS/SNOMED CT | not verified here | UMLS and SNOMED need licences; strong for rare disease, weak for common. |
| Guidelines | NICE, USPSTF, specialty societies, WHO | not verified here | Mixed access; often no API; version tracking needed. |
| Drug labels | DailyMed / openFDA | not verified here | Free; US-centric. |
| Drug normalisation | RxNorm / RxNav (RxClass) | **verified: still active** | Free. |
| Drug-drug interactions | NLM RxNav interaction API | **verified: discontinued ~Jan 2024** | Replacements found were commercial (DrugBank) or unvetted. **[open]** licensing. |
| Trials (emerging treatments) | ClinicalTrials.gov API | not verified here | Free. |
| Retractions | Retraction Watch DB (Crossref), PubMed retraction flags | not verified here | Free via Crossref. |

### Where the differential comes from **[decided 2026-10-29: propose, then verify]**

The model proposes candidate diagnoses; each candidate must survive retrieval
and verification or it is dropped. Rules that keep this from becoming
citation-hunting for conclusions already reached: **[proposed]**

- **Verification is two-sided.** Each candidate gets a search for evidence
  *against* it (findings it would predict that are absent, features that point
  elsewhere), not only for evidence that supports it.
- **Pass criterion is explicit:** at least one verified source links the
  presenting findings (or the history) to the candidate, with the claim
  supported by the retrieved text (§6.3). Matching on disease name alone does not count.
- **Dropped candidates are logged, not shown,** with the reason (no source,
  unsupported, contradicted). They feed evals: how often a correct diagnosis
  was proposed and then wrongly dropped.
- **Recall ceiling.** Verification only removes candidates, so the
  differential can never be better than what the model proposes. Measure
  proposal recall and post-verification recall separately (§11).
- **Can't-miss candidates [decided 2026-10-29: show, flagged].** A can't-miss
  diagnosis that fails verification is still shown, marked "model-proposed,
  unverified", with no citations and nothing added beyond the name, the
  can't-miss reason and the test that would exclude it. This is the only
  exception to "no source, no claim" (§6.1).
- **Who decides "can't-miss" [proposed].** If the model decides, it can label
  any candidate can't-miss and skip verification. So can't-miss status should
  come from a curated list keyed by presenting complaint (e.g. chest pain → ACS,
  PE, dissection, tension pneumothorax), not from model judgment. **[open]**
  which list, and who maintains it.

## 9. Regulatory, privacy and liability

- **US (FDA CDS guidance):** reportedly revised January 2026 (secondary sources;
  possibly re-issued 29 Jan 2026; confirm on fda.gov). Coverage reports it
  remains HCP-focused, now extends enforcement discretion to software giving a
  single recommended treatment, and removed most time-critical language (some
  remains). Implication: the regulatory floor has loosened, so lists-not-answers
  and "not final" are a deliberate product choice, not something regulation
  forces. Emergency-department use still needs care. The "independently review
  the basis" criterion comes from the statute (from recall, not verified).
- **EU:** likely MDR software (Rule 11) and AI Act high-risk. Not verified here.
- **[open]** Target jurisdiction(s). This decides the regime and the drug approval data.
- **Patient data leaves the boundary twice:** to the LLM vendor, and inside
  search queries to PubMed etc. Needs de-identification before external
  queries, a BAA/DPA and zero-retention terms with the model vendor, and audit logs.
- **Liability posture:** every response stored with inputs, sources and output;
  physician acknowledgement that the output is decision support.

## 10. Human factors

- **Automation bias and anchoring:** showing the top candidate first anchors the
  physician. Consider showing can't-miss items and "against" evidence prominently.
- **Show what the copilot understood** (parsed inputs) so input errors are caught.
- **Latency budget [open]:** a response that arrives after the consult is unused.
- **Feedback capture:** physician marks candidates as considered/excluded/confirmed
  later; this is the main source of real-world eval data.

## 11. Evaluation

| Dimension | Metric | Notes |
|---|---|---|
| Differential quality | Final diagnosis in top-k; can't-miss recall; proposal recall vs post-verification recall; wrongly-dropped rate | Gold cases needed. |
| Test recommendations | Discriminating value judged by clinicians | Hard to automate. |
| Treatment safety | Contraindication/interaction catch rate on seeded cases | Should be near-perfect; deterministic layer. |
| Provenance | Citation resolves; claim supported (precision); unsupported-claim rate | Automatable with an entailment check + human audit sample. |
| Language | Banned-phrase rate in *generated* fields only; vagueness rate; tier calibration | Scanning echoed input gives false positives. |
| Abstention | Says "insufficient evidence" when it should | Needs cases with no good answer. |

- **Memorisation risk:** published cases (e.g. NEJM case records, MedQA) may be
  in model training data. Report results on post-training-cutoff cases separately.
- **[open]** Who are the clinician reviewers, and how many cases make v1 credible?

## 12. Open questions (summary)

1. Jurisdiction(s) and regulatory path.
2. Setting, specialty and patient population for v1.
3. Input form and EHR integration (free text / form / FHIR).
4. ~~Retrieve-first vs propose-then-verify~~: decided, propose then verify (§8).
   Can't-miss candidates that fail verification are shown, flagged unverified.
   Still open: the curated can't-miss list and its owner.
5. Interaction database and its licence.
6. Treatment phase gated on physician selection, or run for all candidates?
7. Language of input and output vs English-language literature.
8. Latency and cost budget per case.
9. Clinician reviewers for evals and the size of the gold set.

## 13. Tech stack (draft, 2026-10-29)

### Given by the owner

| Layer | Choice | Status |
|---|---|---|
| Agent framework | LangChain **deepagents**: main agent spawns researcher subagents | **[given]** |
| Base model | Claude Sonnet 5.5 (`claude-sonnet-5-5`), temperature 0 | **[given]**; temperature 0 **not possible as stated**, see below |
| Input guardrails | TypeSafe **Jev** (non-generative decision model) analyses the initial prompt | **[given]** |
| Serving | FastAPI service | **[given]** (already scaffolded) |
| Subagent tools | database querying, PubMed retrieval, drug information retrieval | **[given]** |

### Temperature 0 is rejected **[verified in Anthropic API docs bundled with Claude Code]**

- Sonnet 5.5 rejects non-default `temperature` / `top_p` / `top_k` with a 400.
- On API version `2026-10-21`, sending any of the three returns a 400 on
  every model, even at the default value.
- Temperature 0 never guaranteed identical output anyway. The real goal
  (reproducible, auditable answers) needs other levers **[proposed]**:
  - pinned model ID and fixed `effort` (Sonnet 5.5 defaults to `high`; levels
    were recalibrated, so pick one by eval);
  - versioned prompts and pack files, logged with each response;
  - structured outputs for every agent result;
  - deterministic code (not the model) for safety checks, citation resolution
    and the can't-miss list;
  - the source snapshots from §6.6, so a response can be replayed and audited.
- **Checked in `langchain-openrouter` 0.2.9:** `ChatOpenRouter.temperature`
  and `top_p` default to `None` and are only sent when set. So: never set them.
  Not verified: whether OpenRouter drops or forwards a set value to Anthropic.

### Model-API constraints that shape the design **[verified in the same docs]**

- **Forced tool choice returns a 400 on Sonnet 5.5** (`tool_choice` `any`/`tool`).
  deepagents subagent `response_format` accepts `ToolStrategy` or
  `ProviderStrategy`. **Checked:** `ChatOpenRouter.with_structured_output`
  defaults to `method="function_calling"`, which binds `tool_choice=<schema
  name>` (a forced call). Use `method="json_schema"` / `ProviderStrategy`.
  **[open, unverified]** whether OpenRouter passes forced `tool_choice` to
  Anthropic as-is (400) or rewrites it; test with one live call.
- **Native citations can't be combined with structured outputs** (400), and
  API version `2026-10-21` restricts cited text passed back as user or tool
  input. Proposal: carry provenance as schema fields (PMID/DOI/NCT/label set ID,
  quoted excerpt, URL, access depth, retrieval date), not as API citation
  blocks. This matches §6.
- **Refusals.** Sonnet 5.5's safety classifiers include a `bio` category; a
  medical copilot will sometimes get `stop_reason: "refusal"`. Needs explicit
  handling (show "the model declined this part", never fail silently) and
  possibly a fallback. **[open]** how OpenRouter maps Anthropic's `refusal`
  stop reason (finish reason) and whether `ChatOpenRouter` surfaces it.

### Graph: guardrail → deep agent **[decided 2026-10-29]**

Two nodes for now:

```
START → guardrail (Jev) ──fail──→ refusal (predefined message from the pack) → END
                        └─pass──→ agent (deepagents) → END
```

- **guardrail**: the Jev questions below on the initial prompt. Pass/fail is
  decided in code from Jev's probabilities and thresholds in config.
- **refusal**: returns a fixed, pre-written message (pack file, e.g.
  `packs/default/refusal.md`); no model call.
- **agent**: one deep agent built with `create_deep_agent`, added as a graph
  node. Its main agent plans and spawns the subagents through its built-in
  `task` tool. Subagents are passed as `subagents=[{...}]`, each with `name`,
  `description`, `system_prompt`, `tools`, and `response_format`:
  - `diagnostic_researcher`: database query + PubMed tools; returns
    candidates, findings for/against, discriminating tests, sources.
  - `treatment_researcher`: PubMed + drug information tools; returns options,
    evidence level, patient-specific warnings, sources.

Per the current LangChain docs (via Context7, 2026-10-29):

- `create_deep_agent(model="openrouter:<model id>", ...)` accepts an
  OpenRouter model string; a subagent without `model` inherits the main one.
- A subagent's `response_format` result reaches the main agent as
  JSON-serialized `ToolMessage` content (deepagents >= 0.5.3). Without it, the
  main agent gets only the subagent's last message text.
- A top-level `response_format` puts the final validated output in
  `result["structured_response"]`.
- `interrupt_on` (human review of specific tools) needs a checkpointer.

**Consequence of this shape.** With no code steps after the agent, the spec's
mandatory steps (§8 verify every candidate, §4 safety check, curated can't-miss
list, physician pick before treatment) are now up to the agent's prompt and
tools. One way to keep them hard without adding graph nodes **[proposed]**:
make them tools or middleware the agent cannot skip, e.g. the subagent
`response_format` requires a source per claim, and a deterministic check
runs on the final `structured_response` before it is returned.

### Jev guardrails **[proposed]**

Installed: `typesafe-sdk` 0.7.5 (already a dev dependency). Its default model
is `jev-latest`, which moves; pin `jev-1.13.0` (or whatever build the
thresholds were tuned on). No official TypeSafe docs were found; details below
come from the installed SDK and earlier project experience.

- One narrow question per call. Broad questions score near a coin flip.
- Jev never abstains: give every Choice an `unclear` option.
- Noul returns one probability, no confidence and no rationale: log the
  question, build and probabilities with each request for the audit trail.
- Measure one call's cost before running batches.
- Candidate questions on the initial prompt:
  - Is the requester acting as a clinician (vs patient-facing use)?
  - Does it ask for a final diagnosis or a prescription?
  - Does it contain direct identifiers (name, MRN, address) that must be
    removed before external queries?
  - Is the patient outside the v1 population (e.g. paediatric, pregnant)?
  - Does it contain instruction text aimed at the system (prompt injection)?
- The same question style can score generated output for overconfidence and
  vagueness in the eval gate (§7, §11).
- TypeSafe is another vendor that sees patient text: same BAA/DPA question as §9.

### Model provider path **[decided 2026-10-29: OpenRouter via `langchain-openrouter`]**

Model ID on OpenRouter: `anthropic/claude-sonnet-5.5` (verified 2026-10-29 in the
OpenRouter model list; it lists no temperature/top_p support). Consequences for §9 **[proposed]**:

- Turn on zero data retention for the Anthropic scope in OpenRouter's privacy
  settings, and also send `provider.zdr: true` per request (it can only add
  ZDR, never remove it). Per OpenRouter's ZDR docs.
- OpenRouter's ZDR page does not mention HIPAA or a BAA. **[open]** whether
  OpenRouter offers one; until then, only de-identified or synthetic cases go
  through it.
- Pin the upstream provider (OpenRouter provider routing) so requests don't
  fall through to a different host with different retention terms.
  **[open, unverified]** exact routing fields.
- `ChatOpenRouter` `timeout` is in milliseconds, not seconds (earlier project
  pitfall); cost is in `response_metadata["cost"]`.

### Tools mapped to the spec

| Tool | Given / proposed | Notes |
|---|---|---|
| Database query | **[given]** | Fixed parameterized queries only, no text-to-SQL (scaffold rule). Candidate data: `data/primekg/` (PrimeKG; licence unverified). **[open]** which database. |
| PubMed retrieval | **[given]** | De-identify before querying. E-utilities rate limits (from recall, unverified): about 3 req/s without an API key, 10 with one. Abstract vs full text recorded (§6.4). |
| Drug information | **[given]** | Labels: DailyMed/openFDA; names: RxNorm. Interactions: **[open]** licensed source (NLM interaction API is gone). |
| Retraction lookup | **[proposed]** | `data/retractions/retraction_watch.csv` is already local. |
| ICD lookup | **[proposed]** | WHO ICD-11 API or ICD-10-CM. |
| Can't-miss list | **[proposed]** | Curated pack file per presenting complaint (§8). |
| Guideline retrieval | **[proposed]** | Evidence ranking puts guidelines first (§6.7). |
| Citation-support check | **[proposed]** | Deterministic resolution + claim-support check on the final output (§6.3). |

### Serving

- Runs are long and pause for the physician. Use either streaming (SSE) or
  202 + job ID + polling, backed by a durable checkpointer (Postgres) so a
  paused run survives a restart. **[open]** which.
