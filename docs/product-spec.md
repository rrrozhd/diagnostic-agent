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
