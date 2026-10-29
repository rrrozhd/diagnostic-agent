# Reference datasets

Retrieved 2026-10-29 with `bash data/fetch.sh`. Payloads are gitignored; checksums in
`SHA256SUMS` (`cd data && shasum -c SHA256SUMS`). Spec sections refer to `docs/product-spec.md`.

| Dir | File(s) | Release | Source | License | Spec use |
|---|---|---|---|---|---|
| `icd11/` | `SimpleTabulation-ICD-11-MMS-en.zip`, `icd11-icd10-mapping.zip` | ICD-11 MMS 2026-01 | icdcdn.who.int/static/releasefiles/2026-01 | CC BY-ND 3.0 IGO: redistribute unmodified only | §5 codes, ICD-10↔11 crosswalk |
| `icd10cm/` | code descriptions, table and index | FY2027 (effective 2026-10-01) | ftp.cdc.gov … /ICD10CM/2027 | Public domain (US Gov) | §5 codes |
| `hpo/` | `phenotype.hpoa`, `hp.json` | 2026-09-02 | github.com/obophenotype/human-phenotype-ontology | HPO license (free, attribution) | §8 symptom/phenotype → disease (rare-disease weighted) |
| `orphanet/` | `en_product1.xml` (nomenclature + ICD/OMIM xrefs), `en_product4.xml` (phenotypes with frequency) | 2026-06-23 | orphadata.com | CC BY 4.0 | §8 rare disease |
| `medrt/` | `Core_MEDRT_XML.zip` | 2026.10.05 | evs.nci.nih.gov/ftp1/MED-RT | Public domain (VA) | treatment: `may_treat`, `may_prevent`; safety: `CI_with` (drug–condition) |
| `rxnorm/` | `RxNorm_full_prescribe_10052026.zip` | 2026-10-05 | download.nlm.nih.gov/rxnorm | Prescribable subset, no UMLS licence needed | §3 med-list normalisation, links MED-RT/PrimeKG drugs |
| `primekg/` | `drug_disease.csv` (derived), `nodes.tab` | PrimeKG v2 (2023) | Harvard Dataverse doi:10.7910/DVN/IXA7BM | CC0 on the KG; edges come from DrugCentral (CC BY-SA 4.0), drug IDs are DrugBank IDs | treatment options: 9,388 indication, 2,568 off-label, 30,675 contraindication edges |
| `retractions/` | `retraction_watch.csv` | live snapshot | gitlab.com/crossref/retraction-watch-data | Free via Crossref (see repo terms) | §6.5 retraction check |

`primekg/drug_disease.csv` is filtered from PrimeKG `edges.csv` + `nodes.tab` (drug → disease
rows only); disease IDs are PrimeKG's grouped MONDO IDs, not ICD codes. It is 2023 data and
is not itself a citable source per §6.2: use it to propose options, then cite the label,
guideline or paper.

## SQLite: `data/reference.db`

`make seed` (= `uv run python data/seed.py`, ~90 s) loads everything above into one
gitignored SQLite file and fails if any table comes out empty or a known entry is missing.
Table and column notes are SQL comments in the schema:
`SELECT sql FROM sqlite_master WHERE type = 'table'`. The agent reads it through the
`query_reference_db` tool in `app/tools.py` (read-only, SELECT only, capped rows/time/size;
limits in `app/config.py`).

| Table | Rows | Join keys |
|---|---|---|
| `source` | 8 | release + licence per dataset; cite with any claim |
| `icd11`, `icd11_to_icd10`, `icd10_to_icd11` | 31,678 / 17,943 / 12,597 | `code`; WHO ICD-10 is dotted |
| `icd10cm` | 98,403 | `code` dotted (A00.0), `billable` |
| `hpo_term`, `hpo_synonym`, `hpo_is_a` | 20,482 / 26,268 / 24,436 | `HP:` ids |
| `hpo_annotation` | 286,651 | `hpo_id` → `disease_id` (OMIM/ORPHA), `reference` is the citation |
| `orphanet_disorder`, `_synonym`, `_xref`, `_phenotype` | 11,645 / 15,307 / 52,456 / 116,664 | `orpha_code`; xref to ICD-10/11, OMIM, MONDO |
| `medrt_association`, `medrt_concept` | 97,009 / 3,711 | `from_code` = RxNorm rxcui; `rel` = may_treat, CI_with, … |
| `rxnorm_concept`, `rxnorm_rel` | 141,074 / 553,500 | `rxcui` |
| `primekg_drug_disease` | 42,631 | `disease_id` = MONDO number(s) |
| `retraction` | 73,444 | `original_doi` (lowercase), `original_pmid` |

Example: drugs MED-RT lists as contraindicated with kidney failure:

```sql
SELECT DISTINCT r.name FROM medrt_association m
JOIN rxnorm_concept r ON r.rxcui = m.from_code AND r.tty = 'IN'
WHERE m.rel = 'CI_with' AND m.to_name = 'Kidney Failure';
```

## Not pulled

- **Runtime APIs, not datasets:** PubMed/Europe PMC, DailyMed/openFDA labels, ClinicalTrials.gov, ICD-11 API (needs WHO registration).
- **Licensed:** UMLS, SNOMED CT, DrugBank.
- **Too large for the value now:** DrugCentral Postgres dump (1.4 GB), openFDA bulk labels, full PrimeKG (~1 GB).
- **Drug–drug interactions:** still open (§8, §12.5). No free vetted source pulled; check a candidate's licence first.
- **Can't-miss list:** no dataset; needs a curated list and owner (§8).
